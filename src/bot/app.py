"""Slack bot application entry point."""
import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient

from src.config.settings import Settings
from src.database.db_manager import DBManager
from src.database.repositories.reminder_repository import ReminderRepository
from src.database.repositories.audit_repository import AuditRepository
from src.database.migrations.migration_manager import MigrationManager

from src.parsers.pattern_matcher import PatternMatcher
from src.parsers.datetime_parser import DateTimeParser
from src.parsers.ai_parser import AIParser

from src.services.deadline_service import DeadlineService
from src.services.reminder_service import ReminderService
from src.services.notification_service import NotificationService

from src.bot.scheduler.reminder_scheduler import ReminderScheduler
from src.bot.handlers.message_handler import MessageHandler
from src.bot.handlers.command_handler import CommandHandler

from src.utils.logger import get_logger, init_logger


logger = get_logger('SlackBot')

# Flag file written by admin panel to pause message processing
_BOT_PAUSE_FLAG = os.path.join(os.path.dirname(__file__), '..', '..', '.bot_paused')


class SlackBot:
    """Main Slack bot application.

    Initializes and wires up all components including handlers, services,
    and scheduler. Handles startup and shutdown.
    """

    def __init__(self, settings: Settings):
        """Initialize Slack bot.

        Args:
            settings: Application settings
        """
        self.settings = settings

        # Initialize logger
        init_logger(settings.log_level)
        logger.info('Initializing Slack bot')

        # Initialize database
        logger.info('Initializing database')
        self.db_manager = DBManager(settings)

        # Run migrations
        migration_manager = MigrationManager(self.db_manager)
        migration_manager.run_pending()

        # Initialize repositories
        self.reminder_repo = ReminderRepository(self.db_manager)
        self.audit_repo = AuditRepository(self.db_manager)

        # Initialize parsers
        logger.info('Initializing parsers')
        pattern_matcher = PatternMatcher()
        datetime_parser = DateTimeParser()

        # Initialize AI parser (optional)
        ai_parser = None
        if settings.is_gemini_configured:
            ai_parser = AIParser(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                temperature=settings.gemini_temperature
            )
            logger.info('AI parser initialized with Gemini')
        else:
            logger.warning('Gemini API not configured, AI parser disabled')

        # Initialize services
        logger.info('Initializing services')
        self.deadline_service = DeadlineService(
            pattern_matcher=pattern_matcher,
            datetime_parser=datetime_parser,
            ai_parser=ai_parser
        )

        self.reminder_service = ReminderService(
            reminder_repo=self.reminder_repo,
            audit_repo=self.audit_repo
        )

        # Initialize Slack client
        slack_client = WebClient(token=settings.slack_bot_token)
        self.notification_service = NotificationService(slack_client)

        # Store AI parser for morning summary rephrasing
        self.ai_parser = ai_parser

        # Initialize scheduler
        logger.info('Initializing scheduler')
        self.scheduler = ReminderScheduler(reminder_repo=self.reminder_repo)

        # Initialize handlers
        logger.info('Initializing handlers')
        self.message_handler = MessageHandler(
            deadline_service=self.deadline_service,
            reminder_service=self.reminder_service,
            notification_service=self.notification_service,
            reminder_scheduler=self.scheduler
        )

        self.command_handler = CommandHandler(
            reminder_service=self.reminder_service,
            notification_service=self.notification_service,
            ai_service=ai_parser
        )

        # Initialize Slack Bolt app
        logger.info('Initializing Slack Bolt app')
        self.app = App(
            token=settings.slack_bot_token,
            signing_secret=settings.slack_signing_secret
        )

        # Wire up event handlers
        self._register_handlers()

        # Initialize Socket Mode handler
        self.handler = SocketModeHandler(
            self.app,
            settings.slack_app_token
        )

        logger.success('Slack bot initialized successfully')

    def _register_handlers(self):
        """Register all event and command handlers."""
        logger.info('Registering event handlers')

        # Message event handler - ONLY process thread replies (strict filtering)
        @self.app.event("message")
        def handle_message_event(body, event, say):
            """Handle message events - thread replies, edits, and deletions."""
            # Check if bot is paused via admin panel
            if os.path.exists(_BOT_PAUSE_FLAG):
                logger.info('[APP] Bot is paused - skipping message event')
                return

            # Handle different message subtypes
            subtype = event.get("subtype")
            is_edit = subtype == "message_changed"
            is_delete = subtype == "message_deleted"

            logger.info(f'[APP] Received message event - subtype: {subtype}, is_edit: {is_edit}, is_delete: {is_delete}')

            # Step 1: Route deletion events immediately (handler will check DB)
            if is_delete:
                logger.info('[APP] Deletion event - passing to message handler')
                self.message_handler.handle_message(event, say)
                return

            # Step 2: Extract thread_ts for new/edited messages
            if is_edit:
                message_data = event.get("message", {})
                thread_ts = message_data.get("thread_ts")
                logger.info(f'[APP] Edited message - thread_ts: {thread_ts}')
            else:
                thread_ts = event.get("thread_ts")
                logger.info(f'[APP] New message - thread_ts: {thread_ts}')

            # CRITICAL: Only process messages that are thread replies
            if not thread_ts:
                logger.info('[APP] No thread_ts found - skipping (not a thread reply)')
                return

            # Additional validation: ensure thread_ts is valid format
            if not isinstance(thread_ts, str) or len(thread_ts) < 10 or '.' not in thread_ts:
                logger.warning(f'[APP] Invalid thread_ts format: {thread_ts} - skipping')
                return

            logger.info('[APP] Passing to message handler')
            # Only process thread replies
            self.message_handler.handle_message(event, say)

        # Slash command handlers
        @self.app.command("/my-reminders")
        def handle_my_reminders_command(ack, respond, command):
            """Handle /my-reminders command."""
            self.command_handler.handle_my_reminders(ack, respond, command)

        @self.app.command("/cancel-reminder")
        def handle_cancel_reminder_command(ack, respond, command):
            """Handle /cancel-reminder command."""
            self.command_handler.handle_cancel_reminder(ack, respond, command)

        @self.app.command("/list-thread-reminders")
        def handle_list_thread_reminders_command(ack, respond, command):
            """Handle /list-thread-reminders command."""
            self.command_handler.handle_list_thread_reminders(ack, respond, command)

        @self.app.command("/etc-summary")
        def handle_etc_summary_command(ack, respond, command):
            """Handle /etc-summary command."""
            self.command_handler.handle_etc_summary(ack, respond, command)

        @self.app.command("/trigger-eod")
        def handle_trigger_eod_command(ack, respond, command):
            """Handle /trigger-eod command."""
            self.command_handler.handle_trigger_eod(ack, respond, command)

        logger.success('Event handlers registered')

    def start(self):
        """Start the bot.

        Starts the scheduler, loads pending reminders, and connects to Slack.
        """
        try:
            logger.info('Starting Slack bot')

            # Start scheduler
            self.scheduler.start()
            logger.success('Scheduler started')

            # Load pending reminders from database
            def reminder_callback(reminder):
                """Callback for scheduled reminders."""
                self.message_handler._send_reminder_callback(reminder)

            loaded_count = self.scheduler.load_pending_reminders(reminder_callback)
            logger.info(f'Loaded {loaded_count} pending reminders from database')

            # Schedule daily morning summary at 9 AM IST
            def morning_summary_callback():
                """Callback for daily morning summary."""
                self._send_morning_summaries()

            self.scheduler.schedule_morning_summary(morning_summary_callback, hour=9, minute=0)
            self.scheduler.schedule_morning_summary(morning_summary_callback, hour=9, minute=0)
            logger.info('Scheduled daily morning summary at 09:00 IST')

            # Schedule EOD follow-up check at 7 PM IST
            def eod_check_callback():
                """Callback for daily EOD follow-up check."""
                self._send_eod_followups()

            self.scheduler.schedule_eod_check(eod_check_callback, hour=19, minute=0)
            logger.info('Scheduled daily EOD check at 19:00 IST')

            # Connect to Slack
            logger.info('Connecting to Slack via Socket Mode')
            self.handler.connect()
            logger.success('Slack bot started successfully')

        except Exception as e:
            logger.error(f'Error starting bot: {e}', exc=e)
            raise

    def _send_morning_summaries(self):
        """Send morning summaries to all users with pending reminders.

        Fetches all pending reminders, groups by user, and sends summaries.
        Only sends for reminders where deadline is still in the future.
        """
        try:
            from src.utils.timezone import now_ist
            logger.info('Starting morning summary generation')

            # Get all pending reminders
            pending_reminders = self.reminder_repo.get_pending()
            current_time = now_ist()

            # Filter to only reminders with future deadlines
            future_reminders = []
            for reminder in pending_reminders:
                if reminder.deadline_datetime:
                    from src.utils.timezone import make_aware
                    deadline_time = reminder.deadline_datetime
                    if deadline_time.tzinfo is None:
                        deadline_time = make_aware(deadline_time)

                    if deadline_time > current_time:
                        future_reminders.append(reminder)

            if not future_reminders:
                logger.info('No pending reminders with future deadlines for morning summary')
                return

            # Group reminders by user
            user_reminders = {}
            for reminder in future_reminders:
                if reminder.user_id not in user_reminders:
                    user_reminders[reminder.user_id] = []
                user_reminders[reminder.user_id].append(reminder)

            # Send summary to each user
            for user_id, reminders in user_reminders.items():
                logger.info(f'Sending morning summary to {user_id} ({len(reminders)} tasks)')
                self.notification_service.send_morning_summary(
                    user_id,
                    reminders,
                    ai_service=self.ai_parser
                )

            logger.success(f'Morning summaries sent to {len(user_reminders)} users')

        except Exception as e:
            logger.error(f'Error sending morning summaries: {e}', exc=e)

    def _send_eod_followups(self):
        """Send EOD follow-ups for unresponsive users.

        Checks for reminders that were sent but haven't received a response.
        """
        try:
            logger.info('Starting scheduled EOD follow-up check')
            self.reminder_service.process_eod_followups(self.notification_service)

        except Exception as e:
            logger.error(f'Error sending EOD follow-ups: {e}', exc=e)

    def stop(self):
        """Stop the bot.

        Stops the scheduler and disconnects from Slack.
        """
        try:
            logger.info('Stopping Slack bot')

            # Stop scheduler
            self.scheduler.stop()
            logger.success('Scheduler stopped')

            # Close database connections
            self.db_manager.close_all()
            logger.success('Database connections closed')

            logger.success('Slack bot stopped successfully')

        except Exception as e:
            logger.error(f'Error stopping bot: {e}', exc=e)
            raise


def main():
    """Main entry point for the bot."""
    try:
        # Load settings
        settings = Settings()

        # Create and start bot
        bot = SlackBot(settings)
        bot.start()

        # Keep the process alive
        import signal
        import sys

        def signal_handler(sig, frame):
            logger.info('Received shutdown signal')
            bot.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Keep running
        import time
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info('Received keyboard interrupt')
        bot.stop()
    except Exception as e:
        logger.error(f'Fatal error: {e}', exc=e)
        raise


if __name__ == "__main__":
    main()
