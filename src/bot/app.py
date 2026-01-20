"""Slack bot application entry point."""
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient

from config.settings import Settings
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
            notification_service=self.notification_service
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
            """Handle message events - ONLY thread replies (includes edited messages)."""
            # Handle both new messages and edited messages
            subtype = event.get("subtype")
            is_edit = subtype == "message_changed"

            logger.info(f'[APP] Received message event - subtype: {subtype}, is_edit: {is_edit}')

            # For edited messages, check thread_ts in event["message"]
            # For new messages, check thread_ts directly in event
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

            # Connect to Slack
            logger.info('Connecting to Slack via Socket Mode')
            self.handler.connect()
            logger.success('Slack bot started successfully')

        except Exception as e:
            logger.error(f'Error starting bot: {e}', exc=e)
            raise

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
