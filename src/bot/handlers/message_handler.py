"""Message handler for processing Slack thread replies."""
from typing import Callable
from src.core.models import ReminderContext
from src.services.deadline_service import DeadlineService
from src.services.reminder_service import ReminderService
from src.services.notification_service import NotificationService
from src.bot.scheduler.reminder_scheduler import ReminderScheduler
from src.utils.logger import get_logger


logger = get_logger('MessageHandler')


class MessageHandler:
    """Handler for processing Slack message events.

    Handles thread reply events, detects ETC deadlines, creates/updates
    reminders, schedules notifications, and sends confirmations.
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
        logger.info('Message handler initialized')

    def handle_message(
        self,
        event: dict,
        say: Callable
    ) -> None:
        """Handle a Slack message event.

        Processes thread reply events to detect ETC deadlines and create reminders.
        Only processes messages that are replies in threads.

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

            logger.info(f'Processing thread reply in thread: {thread_ts}')

            # Extract message data
            text = event.get("text", "").strip()
            channel_id = event.get("channel")
            user_id = event.get("user")
            message_ts = event.get("ts")

            if not all([text, channel_id, user_id, message_ts]):
                logger.warning('Missing required fields in event')
                return

            # Type safety: ensure all values are strings
            if not isinstance(channel_id, str) or not isinstance(user_id, str) or not isinstance(message_ts, str):
                logger.warning('Invalid field types in event')
                return

            logger.info(f'Processing message from user {user_id}: "{text}"')

            # Step 2: Check for ETC indicator
            has_etc = self.deadline_service.has_etc_indicator(text)
            logger.info(f'ETC indicator check result: {has_etc} for message: "{text}"')

            if not has_etc:
                logger.info(f'No ETC indicator found in message: "{text}"')
                return

            logger.info('ETC indicator detected - proceeding to deadline detection')

            # Step 3: Parse deadline
            context = ReminderContext(
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user_id,
                message_ts=message_ts,
                message_text=text
            )

            parsed_deadline = self.deadline_service.detect(text, context)

            if not parsed_deadline:
                logger.warning('Failed to parse deadline from message')
                return

            logger.success(
                f'Deadline parsed: {parsed_deadline.deadline_datetime} '
                f'(confidence: {parsed_deadline.confidence}, method: {parsed_deadline.parsed_by})'
            )

            # Step 4: Create or update reminder
            # Check if this is an update (existing active reminder)
            existing = self.reminder_service.reminder_repo.find_existing_active(
                channel_id,
                thread_ts,
                user_id
            )
            is_update = existing is not None

            reminder = self.reminder_service.create_or_update(context, parsed_deadline)

            if not reminder:
                logger.error('Failed to create or update reminder')
                return

            if not reminder.id:
                logger.error('Reminder created but has no ID - database issue!')
                return

            logger.success(
                f'Reminder {"updated" if is_update else "created"}: {reminder.id} (deadline: {reminder.deadline_datetime})'
            )

            # Step 5: Schedule job
            if not reminder.id:
                logger.error('Reminder created but has no ID')
                return

            if not self.scheduler.schedule(reminder, self._send_reminder_callback):
                logger.error(f'Failed to schedule reminder {reminder.id}')
                # Mark as failed
                self.reminder_service.mark_failed(reminder.id, "Failed to schedule job")
                return

            logger.success(f'Reminder {reminder.id} scheduled successfully')

            # Step 6: Send confirmation
            if not self.notification_service.send_confirmation(reminder, is_update):
                logger.warning(f'Failed to send confirmation for reminder {reminder.id}')
                # Don't fail the whole operation if confirmation fails

        except Exception as e:
            logger.error(f'Error handling message: {e}', exc=e)

    def _send_reminder_callback(self, reminder):
        """Callback function for scheduled reminder jobs.

        This is called by the scheduler when a reminder is due.
        Sends the notification and updates the reminder status.

        Args:
            reminder: Reminder object to send
        """
        try:
            if not reminder.id:
                logger.error('Reminder has no ID, cannot process callback')
                return

            logger.info(f'Sending reminder {reminder.id} (callback triggered)')

            # Send the reminder notification
            success = self.notification_service.send_reminder(reminder)

            if success:
                # Mark as sent
                self.reminder_service.mark_sent(reminder.id)
                logger.success(f'Reminder {reminder.id} sent and marked as sent')
            else:
                # Mark as failed
                self.reminder_service.mark_failed(
                    reminder.id,
                    "Failed to send notification"
                )
                logger.error(f'Reminder {reminder.id} failed to send')

        except Exception as e:
            reminder_id = reminder.id if reminder.id else 'unknown'
            logger.error(f'Error in reminder callback for {reminder_id}: {e}', exc=e)
            # Mark as failed
            if reminder.id:
                try:
                    self.reminder_service.mark_failed(
                        reminder.id,
                        f"Callback error: {str(e)}"
                    )
                except:
                    pass
