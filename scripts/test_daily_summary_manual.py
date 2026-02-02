#!/usr/bin/env python3
"""
Manual testing script for daily summary feature.

This script allows you to test the daily summary generation and sending
without waiting for the scheduled job.

Usage:
    python scripts/test_daily_summary_manual.py --user U123456
    python scripts/test_daily_summary_manual.py --all-users
    python scripts/test_daily_summary_manual.py --preview U123456
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import Settings
from src.database.db_manager import DBManager
from src.database.repositories.reminder_repository import ReminderRepository
from src.services.notification_service import NotificationService
from src.services.daily_summary_service import DailySummaryService
from slack_sdk import WebClient
from src.utils.logger import get_logger, init_logger

logger = get_logger('TestDailySummary')


def init_services(settings: Settings):
    """Initialize all required services."""
    # Database
    db_manager = DBManager(settings)
    reminder_repo = ReminderRepository(db_manager)

    # Slack
    slack_client = WebClient(token=settings.slack_bot_token)
    notification_service = NotificationService(slack_client)

    # Daily summary
    daily_summary_service = DailySummaryService(
        reminder_repo=reminder_repo,
        notification_service=notification_service
    )

    return daily_summary_service, reminder_repo


def preview_summary(user_id: str, daily_summary_service: DailySummaryService):
    """Preview summary without sending."""
    print(f"\n{'='*60}")
    print(f"PREVIEW: Daily Summary for User {user_id}")
    print(f"{'='*60}\n")

    try:
        message = daily_summary_service.generate_summary_for_user(user_id)
        print(message)
        print(f"\n{'='*60}\n")
        print("✅ Summary generated successfully (NOT sent)")

    except Exception as e:
        print(f"\n❌ Error generating summary: {e}")
        import traceback
        traceback.print_exc()


def send_to_user(user_id: str, daily_summary_service: DailySummaryService):
    """Send summary to specific user."""
    print(f"\n{'='*60}")
    print(f"SENDING: Daily Summary to User {user_id}")
    print(f"{'='*60}\n")

    try:
        success = daily_summary_service.send_summary_to_user(user_id)

        if success:
            print(f"\n✅ Summary sent successfully to {user_id}")
        else:
            print(f"\n❌ Failed to send summary to {user_id}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


def send_to_all(daily_summary_service: DailySummaryService):
    """Send summaries to all users."""
    print(f"\n{'='*60}")
    print(f"SENDING: Daily Summaries to All Users")
    print(f"{'='*60}\n")

    try:
        results = daily_summary_service.send_summaries_to_all_users()

        print(f"\nResults:")
        print(f"{'='*60}")

        success_count = 0
        for user_id, success in results.items():
            status = "✅ Success" if success else "❌ Failed"
            print(f"{user_id}: {status}")
            if success:
                success_count += 1

        print(f"\n{'='*60}")
        print(f"Total: {success_count}/{len(results)} successful")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


def list_users_with_reminders(reminder_repo: ReminderRepository):
    """List all users with pending reminders."""
    print(f"\n{'='*60}")
    print(f"Users with Pending Reminders")
    print(f"{'='*60}\n")

    try:
        reminders = reminder_repo.get_pending()
        user_ids = sorted(set(r.user_id for r in reminders))

        if not user_ids:
            print("No users with pending reminders found.")
            return

        print(f"Found {len(user_ids)} users:\n")
        for user_id in user_ids:
            user_reminders = [r for r in reminders if r.user_id == user_id]
            print(f"  • {user_id} ({len(user_reminders)} reminders)")

        print(f"\n{'='*60}\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


def create_test_reminders(reminder_repo: ReminderRepository, user_id: str):
    """Create test reminders for a user (for testing purposes)."""
    from src.core.models import Reminder, ReminderStatus
    from src.utils.timezone import now_ist

    print(f"\n{'='*60}")
    print(f"Creating Test Reminders for {user_id}")
    print(f"{'='*60}\n")

    now = now_ist()

    test_data = [
        (-1, "Fix critical bug in production", "yesterday"),
        (0, "Complete code review for PR #123", "today"),
        (0, "Update documentation", "today"),
        (1, "Prepare for team meeting", "tomorrow"),
    ]

    created = []

    for days_offset, description, label in test_data:
        deadline = now + timedelta(days=days_offset)
        reminder_time = deadline - timedelta(hours=1)

        reminder = Reminder(
            channel_id='C123TEST',
            thread_ts=f'{now.timestamp()}.{days_offset}',
            user_id=user_id,
            message_ts=f'{now.timestamp()}.{days_offset}',
            deadline_text=f'{days_offset} days',
            deadline_datetime=deadline,
            reminder_datetime=reminder_time,
            original_message=description,
            status=ReminderStatus.PENDING
        )

        try:
            reminder_id = reminder_repo.create(reminder)
            created.append((reminder_id, label, description))
            print(f"✅ Created {label} reminder: {description}")
        except Exception as e:
            print(f"❌ Failed to create {label} reminder: {e}")

    print(f"\n{'='*60}")
    print(f"Created {len(created)} test reminders")
    print(f"{'='*60}\n")

    return created


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Test daily summary feature manually',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview summary for a specific user (doesn't send)
  python scripts/test_daily_summary_manual.py --preview U123456

  # Send summary to a specific user
  python scripts/test_daily_summary_manual.py --user U123456

  # Send summaries to all users
  python scripts/test_daily_summary_manual.py --all-users

  # List all users with pending reminders
  python scripts/test_daily_summary_manual.py --list-users

  # Create test reminders for a user
  python scripts/test_daily_summary_manual.py --create-test U123456
        """
    )

    parser.add_argument(
        '--preview',
        metavar='USER_ID',
        help='Preview summary for user (no sending)'
    )
    parser.add_argument(
        '--user',
        metavar='USER_ID',
        help='Send summary to specific user'
    )
    parser.add_argument(
        '--all-users',
        action='store_true',
        help='Send summaries to all users with pending reminders'
    )
    parser.add_argument(
        '--list-users',
        action='store_true',
        help='List all users with pending reminders'
    )
    parser.add_argument(
        '--create-test',
        metavar='USER_ID',
        help='Create test reminders for user (for testing)'
    )

    args = parser.parse_args()

    # Validate arguments
    if not any([args.preview, args.user, args.all_users, args.list_users, args.create_test]):
        parser.print_help()
        sys.exit(1)

    # Initialize
    print("\n🚀 Initializing services...")
    settings = Settings()
    init_logger(settings.log_level)

    daily_summary_service, reminder_repo = init_services(settings)
    print("✅ Services initialized\n")

    # Execute command
    if args.list_users:
        list_users_with_reminders(reminder_repo)

    elif args.create_test:
        create_test_reminders(reminder_repo, args.create_test)

    elif args.preview:
        preview_summary(args.preview, daily_summary_service)

    elif args.user:
        send_to_user(args.user, daily_summary_service)

    elif args.all_users:
        send_to_all(daily_summary_service)


if __name__ == '__main__':
    main()
