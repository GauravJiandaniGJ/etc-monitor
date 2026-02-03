"""Command handler for Slack slash commands."""
from typing import Callable, Optional
from src.services.reminder_service import ReminderService
from src.services.notification_service import NotificationService
from src.utils.logger import get_logger
from src.utils.timezone import format_datetime_friendly, now_ist


logger = get_logger('CommandHandler')


class CommandHandler:
    """Handler for Slack slash commands.

    Handles commands like /my-reminders, /cancel-reminder, and /list-thread-reminders.
    """

    def __init__(
        self,
        reminder_service: ReminderService,
        notification_service: NotificationService,
        etc_summary_service: Optional = None
    ):
        """Initialize command handler.

        Args:
            reminder_service: Service for managing reminders
            notification_service: Service for sending Slack messages
            etc_summary_service: Optional ETC summary service for /etc-summary command
        """
        self.reminder_service = reminder_service
        self.notification_service = notification_service
        self.etc_summary_service = etc_summary_service
        logger.info('Command handler initialized')

    def handle_my_reminders(
        self,
        ack: Callable,
        respond: Callable,
        command: dict
    ) -> None:
        """Handle /my-reminders command.

        Lists all active reminders for the user who issued the command.

        Args:
            ack: Slack ack function to acknowledge the command
            respond: Slack respond function to send response
            command: Command dictionary from Slack
        """
        try:
            # Acknowledge the command
            ack()

            user_id = command.get('user_id')
            if not user_id:
                respond("Error: Could not identify user")
                return

            logger.info(f'Handling /my-reminders command from user {user_id}')

            # Get user's reminders
            reminders = self.reminder_service.get_user_reminders(user_id)

            if not reminders:
                respond("You don't have any active reminders.")
                return

            # Filter to only pending/rescheduled reminders
            active_reminders = [
                r for r in reminders
                if r.status.value in ['pending', 'rescheduled']
            ]

            if not active_reminders:
                respond("You don't have any active reminders.")
                return

            # Format response
            lines = [f"You have {len(active_reminders)} active reminder(s):\n"]

            for i, reminder in enumerate(active_reminders, 1):
                deadline_str = format_datetime_friendly(reminder.deadline_datetime)
                channel_name = self.notification_service.resolve_channel_name(
                    reminder.channel_id
                )

                lines.append(
                    f"{i}. Deadline: {deadline_str}\n"
                    f"   Channel: {channel_name}\n"
                    f"   Status: {reminder.status.value}"
                )

                if reminder.reschedule_count > 0:
                    lines.append(f"   (Rescheduled {reminder.reschedule_count} time(s))")

                lines.append("")  # Empty line between reminders

            response_text = "\n".join(lines)
            respond(response_text)

            logger.success(f'Listed {len(active_reminders)} reminders for user {user_id}')

        except Exception as e:
            logger.error(f'Error handling /my-reminders: {e}', exc=e)
            respond("Error: Failed to retrieve your reminders. Please try again later.")

    def handle_cancel_reminder(
        self,
        ack: Callable,
        respond: Callable,
        command: dict
    ) -> None:
        """Handle /cancel-reminder command.

        Cancels a reminder. Expects reminder_id as text parameter.

        Args:
            ack: Slack ack function to acknowledge the command
            respond: Slack respond function to send response
            command: Command dictionary from Slack
        """
        try:
            # Acknowledge the command
            ack()

            user_id = command.get('user_id')
            text = command.get('text', '').strip()

            if not user_id:
                respond("Error: Could not identify user")
                return

            if not text:
                respond(
                    "Usage: /cancel-reminder <reminder_id>\n"
                    "Use /my-reminders to see your reminder IDs."
                )
                return

            logger.info(f'Handling /cancel-reminder command from user {user_id} for reminder {text}')

            # Parse reminder ID
            try:
                reminder_id = int(text)
            except ValueError:
                respond(f"Error: '{text}' is not a valid reminder ID. Use /my-reminders to see your reminder IDs.")
                return

            # Get the reminder to verify ownership
            reminder = self.reminder_service.get_reminder(reminder_id)

            if not reminder:
                respond(f"Error: Reminder {reminder_id} not found.")
                return

            # Verify user owns this reminder
            if reminder.user_id != user_id:
                respond("Error: You can only cancel your own reminders.")
                return

            # Cancel the reminder
            success = self.reminder_service.cancel(reminder_id, user_id)

            if success:
                # Cancel scheduled job
                from src.bot.scheduler.reminder_scheduler import ReminderScheduler
                # Note: This assumes scheduler is accessible - may need refactoring
                # For now, we'll just mark it as cancelled in DB

                # Send cancellation confirmation
                self.notification_service.send_cancellation(reminder)

                deadline_str = format_datetime_friendly(reminder.deadline_datetime)
                respond(
                    f"Reminder {reminder_id} cancelled.\n"
                    f"Original deadline: {deadline_str}"
                )
                logger.success(f'Reminder {reminder_id} cancelled by user {user_id}')
            else:
                respond(f"Error: Failed to cancel reminder {reminder_id}.")
                logger.error(f'Failed to cancel reminder {reminder_id}')

        except Exception as e:
            logger.error(f'Error handling /cancel-reminder: {e}', exc=e)
            respond("Error: Failed to cancel reminder. Please try again later.")

    def handle_list_thread_reminders(
        self,
        ack: Callable,
        respond: Callable,
        command: dict
    ) -> None:
        """Handle /list-thread-reminders command.

        Lists all reminders in the current thread. Must be used in a thread.

        Args:
            ack: Slack ack function to acknowledge the command
            respond: Slack respond function to send response
            command: Command dictionary from Slack
        """
        try:
            # Acknowledge the command
            ack()

            channel_id = command.get('channel_id')
            thread_ts = command.get('thread_ts') or command.get('response_url')  # Try to get thread

            if not channel_id:
                respond("Error: Could not identify channel")
                return

            if not thread_ts:
                respond(
                    "Error: This command must be used in a thread.\n"
                    "Reply to a message in a thread and use this command."
                )
                return

            logger.info(f'Handling /list-thread-reminders in channel {channel_id}, thread {thread_ts}')

            # Get reminders in thread
            reminders = self.reminder_service.get_thread_reminders(channel_id, thread_ts)

            if not reminders:
                respond("No reminders found in this thread.")
                return

            # Filter to only active reminders
            active_reminders = [
                r for r in reminders
                if r.status.value in ['pending', 'rescheduled']
            ]

            if not active_reminders:
                respond("No active reminders found in this thread.")
                return

            # Format response
            lines = [f"This thread has {len(active_reminders)} active reminder(s):\n"]

            for i, reminder in enumerate(active_reminders, 1):
                deadline_str = format_datetime_friendly(reminder.deadline_datetime)
                user_name = self.notification_service.resolve_user_name(reminder.user_id)

                lines.append(
                    f"{i}. User: {user_name} (<@{reminder.user_id}>)\n"
                    f"   Deadline: {deadline_str}\n"
                    f"   Status: {reminder.status.value}"
                )

                if reminder.reschedule_count > 0:
                    lines.append(f"   (Rescheduled {reminder.reschedule_count} time(s))")

                lines.append("")  # Empty line between reminders

            response_text = "\n".join(lines)
            respond(response_text)

            logger.success(f'Listed {len(active_reminders)} reminders in thread')

        except Exception as e:
            logger.error(f'Error handling /list-thread-reminders: {e}', exc=e)
            respond("Error: Failed to retrieve thread reminders. Please try again later.")

    def handle_etc_summary(
        self,
        ack: Callable,
        respond: Callable,
        command: dict
    ) -> None:
        """Handle /etc-summary command.
        
        Manually triggers an ETC summary for the user.
        
        Args:
            ack: Slack ack function to acknowledge the command
            respond: Slack respond function to send response
            command: Command dictionary from Slack
        """
        try:
            # Acknowledge the command
            ack()
            
            user_id = command.get('user_id')
            if not user_id:
                respond("Error: Could not identify user")
                return
                
            logger.info(f'Handling /etc-summary command from user {user_id}')
            
            if not self.etc_summary_service:
                respond("Error: ETC summary service not initialized.")
                return
                
            # Trigger summary generation
            # This sends a DM directly, so we just acknowledge here
            success = self.etc_summary_service.send_summary_to_user(user_id)
            
            if success:
                respond("✅ Generating your ETC summary... Check your DMs!")
            else:
                respond("You don't have any pending ETC tasks to summarize.")
                
        except Exception as e:
            logger.error(f'Error handling /etc-summary: {e}', exc=e)
            respond("Error: Failed to generate summary. Please try again later.")
