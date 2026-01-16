"""Message handler for processing Slack messages - Production Optimized."""
from typing import Callable
from concurrent.futures import ThreadPoolExecutor
from src.core.models import ReminderContext
from src.services.deadline_service import DeadlineService
from src.services.reminder_service import ReminderService
from src.services.notification_service import NotificationService
from src.bot.scheduler.reminder_scheduler import ReminderScheduler
from src.utils.logger import get_logger


logger = get_logger('MessageHandler')


class MessageHandler:
    """Handler for processing Slack message events - Production Optimized.

    Features:
    - Immediate acknowledgment to user
    - Background processing for AI parsing
    - Robust error handling
    - Thread-safe operations
    """

    def __init__(
        self,
        deadline_service: DeadlineService,
        reminder_service: ReminderService,
        notification_service: NotificationService,
        reminder_scheduler: ReminderScheduler
    ):
        """Initialize message handler.

        Args:
            deadline_service: Service for detecting and parsing deadlines
            reminder_service: Service for managing reminders
            notification_service: Service for sending Slack messages
            reminder_scheduler: Scheduler for reminder jobs
        """
        self.deadline_service = deadline_service
        self.reminder_service = reminder_service
        self.notification_service = notification_service
        self.scheduler = reminder_scheduler
        self._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="msg-handler")
        logger.info('Message handler initialized')

    def handle_message(
        self,
        event: dict,
        say: Callable
    ) -> None:
        """Handle a Slack message event with immediate acknowledgment.

        Process flow:
        1. Validate message (thread reply only)
        2. Send immediate acknowledgment
        3. Process deadline detection in background
        4. Create reminder and schedule

        Args:
            event: Slack event dictionary
            say: Slack Bolt say function for responding
        """
        try:
            # Step 1: Filter - only process thread replies
            thread_ts = event.get("thread_ts")
            if not thread_ts:
                logger.debug('Not a thread reply - skipping')
                return

            # Extract message data
            text = event.get("text", "").strip()
            channel_id = event.get("channel")
            user_id = event.get("user")
            message_ts = event.get("ts")

            # Validate required fields
            if not all([text, channel_id, user_id, message_ts]):
                logger.warning('Missing required fields in event')
                return

            # Type safety checks
            if not all(isinstance(x, str) for x in [channel_id, user_id, message_ts]):
                logger.warning('Invalid field types in event')
                return

            logger.info(f'Processing message from user {user_id}: "{text}"')

            # Step 2: Quick ETC indicator check
            has_etc = self.deadline_service.has_etc_indicator(text)
            if not has_etc:
                logger.debug(f'No ETC indicator in message: "{text}"')
                return

            logger.info('ETC indicator detected - processing')

            # Step 3: Send immediate acknowledgment
            try:
                say(f"Processing ETC: {text}")
                logger.info('Sent immediate acknowledgment')
            except Exception as e:
                logger.warning(f'Failed to send acknowledgment: {e}')

            # Step 4: Process in background for fast response
            # Type safety: We've already validated these are strings above
            assert isinstance(channel_id, str)
            assert isinstance(user_id, str)
            assert isinstance(message_ts, str)

            self._executor.submit(
                self._process_deadline_async,
                text, channel_id, thread_ts, user_id, message_ts
            )

        except Exception as e:
            logger.error(f'Error handling message: {e}', exc=e)

    def _process_deadline_async(
        self,
        text: str,
        channel_id: str,
        thread_ts: str,
        user_id: str,
        message_ts: str
    ):
        """Process deadline detection and reminder creation asynchronously.

        Args:
            text: Message text
            channel_id: Slack channel ID
            thread_ts: Thread timestamp
            user_id: User ID
            message_ts: Message timestamp
        """
        try:
            # Create context
            context = ReminderContext(
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user_id,
                message_ts=message_ts,
                message_text=text
            )

            # Parse deadline (AI first, always)
            logger.info('=' * 60)
            logger.info('[AI] ALWAYS USING AI FIRST - Processing...')
            logger.info('=' * 60)

            parsed_deadline = self.deadline_service.detect(text, context)

            if not parsed_deadline:
                logger.warning('Failed to parse deadline')
                return

            logger.success(
                f'Deadline parsed: {parsed_deadline.deadline_datetime} '
                f'(method: {parsed_deadline.parsed_by}, confidence: {parsed_deadline.confidence:.2f})'
            )

            # Check for existing reminder
            existing = self.reminder_service.reminder_repo.find_existing_active(
                channel_id, thread_ts, user_id
            )
            is_update = existing is not None

            # Create or update reminder
            reminder = self.reminder_service.create_or_update(context, parsed_deadline)

            if not reminder:
                logger.error('Failed to create or update reminder')
                return

            if not reminder.id:
                logger.error('Reminder created but has no ID')
                return

            logger.success(
                f'Reminder {"updated" if is_update else "created"}: {reminder.id} '
                f'(deadline: {reminder.deadline_datetime})'
            )

            # Schedule reminder job
            if not self.scheduler.schedule(reminder, self._send_reminder_callback):
                logger.error(f'Failed to schedule reminder {reminder.id}')
                self.reminder_service.mark_failed(reminder.id, "Failed to schedule job")
                return

            logger.success(f'Reminder {reminder.id} scheduled successfully')

            # Send confirmation
            if not self.notification_service.send_confirmation(reminder, is_update):
                logger.warning(f'Failed to send confirmation for reminder {reminder.id}')

        except Exception as e:
            logger.error(f'Error in async deadline processing: {e}', exc=e)

    def _send_reminder_callback(self, reminder):
        """Callback function for scheduled reminder jobs.

        Args:
            reminder: Reminder object to send
        """
        try:
            if not reminder or not reminder.id:
                logger.error('Invalid reminder in callback')
                return

            logger.info(f'Sending reminder {reminder.id}')

            success = self.notification_service.send_reminder(reminder)

            if success:
                self.reminder_service.mark_sent(reminder.id)
                logger.success(f'Reminder {reminder.id} sent successfully')
            else:
                self.reminder_service.mark_failed(reminder.id, "Failed to send notification")
                logger.error(f'Reminder {reminder.id} failed to send')

        except Exception as e:
            reminder_id = reminder.id if reminder and reminder.id else 'unknown'
            logger.error(f'Error in reminder callback for {reminder_id}: {e}', exc=e)
            if reminder and reminder.id:
                try:
                    self.reminder_service.mark_failed(
                        reminder.id,
                        f"Callback error: {str(e)}"
                    )
                except:
                    pass

    def __del__(self):
        """Cleanup executor on destruction."""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)
