"""Test script for DM support and daily ETC summary functionality."""
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import Settings
from src.database.db_manager import DBManager
from src.database.repositories.reminder_repository import ReminderRepository
from src.services.etc_summary_service import ETCSummaryService
from src.services.notification_service import NotificationService
from src.core.models import Reminder, ReminderStatus
from src.utils.timezone import now_ist, to_ist
from slack_sdk import WebClient


def create_test_reminders(reminder_repo: ReminderRepository, user_id: str):
    """Create test reminders for yesterday, today, and tomorrow."""
    print('\n📝 Creating test reminders...')
    
    now = now_ist()
    today = now.date()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    
    test_reminders = [
        # Yesterday (missed)
        {
            'task': 'Review PR for booking capacity',
            'deadline': datetime.combine(yesterday, datetime.min.time().replace(hour=17)),
            'status': ReminderStatus.PENDING
        },
        {
            'task': 'Complete authentication module',
            'deadline': datetime.combine(yesterday, datetime.min.time().replace(hour=15)),
            'status': ReminderStatus.PENDING
        },
        # Today
        {
            'task': 'Write API payload for Notiva',
            'deadline': datetime.combine(today, datetime.min.time().replace(hour=14)),
            'status': ReminderStatus.PENDING
        },
        {
            'task': 'Finalize email tracking logic',
            'deadline': datetime.combine(today, datetime.min.time().replace(hour=16)),
            'status': ReminderStatus.CONFIRMED  # Should be excluded from summary
        },
        # Tomorrow
        {
            'task': 'Deploy to staging environment',
            'deadline': datetime.combine(tomorrow, datetime.min.time().replace(hour=10)),
            'status': ReminderStatus.PENDING
        },
        {
            'task': 'Update documentation',
            'deadline': datetime.combine(tomorrow, datetime.min.time().replace(hour=15)),
            'status': ReminderStatus.CANCELLED  # Should be excluded from summary
        }
    ]
    
    created_count = 0
    for reminder_data in test_reminders:
        deadline_dt = to_ist(reminder_data['deadline'])
        reminder_dt = deadline_dt - timedelta(minutes=5)  # Remind 5 mins before
        
        reminder = Reminder(
            channel_id='D12345TEST',  # Test DM channel
            thread_ts='1234567890.123456',
            user_id=user_id,
            message_ts=f'{datetime.now().timestamp()}.{created_count}',
            original_message=f"{reminder_data['task']} ETC {reminder_data['deadline'].strftime('%H:%M')}",
            deadline_text=reminder_data['task'],
            deadline_datetime=deadline_dt,
            reminder_datetime=reminder_dt,
            status=reminder_data['status'],
            created_at=now
        )
        
        reminder_id = reminder_repo.create(reminder)
        status_marker = '✅' if reminder_data['status'] == ReminderStatus.PENDING else '❌'
        print(f"  {status_marker} Created: {reminder_data['task']} ({reminder_data['deadline'].date()}) - {reminder_data['status'].value}")
        created_count += 1
    
    print(f'\n✅ Created {created_count} test reminders')


def test_summary_generation(summary_service: ETCSummaryService, user_id: str):
    """Test summary generation for a user."""
    print('\n🔍 Testing summary generation...')
    
    summary = summary_service.get_user_summary(user_id)
    
    print(f'\n📊 Summary Results:')
    print(f'  - Yesterday (missed): {len(summary["yesterday"])} tasks')
    for r in summary["yesterday"]:
        print(f'    • {r.task_description}')
    
    print(f'  - Today: {len(summary["today"])} tasks')
    for r in summary["today"]:
        print(f'    • {r.task_description}')
    
    print(f'  - Tomorrow: {len(summary["tomorrow"])} tasks')
    for r in summary["tomorrow"]:
        print(f'    • {r.task_description}')
    
    # Format message
    message = summary_service.format_summary_message(summary, user_id)
    
    if message:
        print(f'\n📧 Formatted Message:')
        print('─' * 60)
        print(message)
        print('─' * 60)
    else:
        print('\n❌ No message generated (no active tasks)')
    
    return message


def main():
    """Main test function."""
    print('=' * 60)
    print('ETC Summary & DM Support Test')
    print('=' * 60)
    
    # Load settings
    try:
        settings = Settings()
    except Exception as e:
        print(f'\n❌ Error loading settings: {e}')
        print('\nMake sure you have a .env file with required variables:')
        print('  - SLACK_BOT_TOKEN')
        print('  - SLACK_SIGNING_SECRET')
        print('  - SLACK_APP_TOKEN')
        print('  - FLASK_SECRET_KEY')
        return
    
    # Initialize database
    db_manager = DBManager(settings)
    reminder_repo = ReminderRepository(db_manager)
    
    # Initialize services
    slack_client = WebClient(token=settings.slack_bot_token)
    notification_service = NotificationService(slack_client)
    summary_service = ETCSummaryService(reminder_repo, notification_service)
    
    # Test user ID (you can change this)
    test_user_id = 'U01TESTUSER'
    
    print(f'\n🔧 Test Configuration:')
    print(f'  - Test User ID: {test_user_id}')
    print(f'  - Database: {settings.database_path}')
    print(f'  - Daily Summary: {"Enabled" if settings.daily_summary_enabled else "Disabled"}')
    print(f'  - Summary Time: {settings.daily_summary_hour:02d}:{settings.daily_summary_minute:02d} {settings.timezone}')
    print(f'  - DM Support: {"Enabled" if settings.enable_dm_support else "Disabled"}')
    
    # Ask user what to test
    print('\n📋 Test Options:')
    print('  1. Create test reminders')
    print('  2. Generate summary (without sending)')
    print('  3. Send summary via DM (requires valid Slack user ID)')
    print('  4. All of the above')
    
    choice = input('\nEnter your choice (1-4): ').strip()
    
    if choice in ['1', '4']:
        create_test_reminders(reminder_repo, test_user_id)
    
    if choice in ['2', '4']:
        message = test_summary_generation(summary_service, test_user_id)
    
    if choice == '3' or (choice == '4' and message):
        print('\n📤 Sending summary via DM...')
        
        if choice == '3':
            # We need to generate the summary first
            message = test_summary_generation(summary_service, test_user_id)
        
        if message:
            actual_user_id = input(f'\nEnter actual Slack user ID (or press Enter to use {test_user_id}): ').strip()
            if actual_user_id:
                test_user_id = actual_user_id
            
            confirm = input(f'\nSend DM to {test_user_id}? (yes/no): ').strip().lower()
            if confirm == 'yes':
                success = notification_service.send_dm(test_user_id, message)
                if success:
                    print('\n✅ Summary sent successfully!')
                else:
                    print('\n❌ Failed to send summary. Check logs for details.')
            else:
                print('\n⏭️ Skipped sending DM')
        else:
            print('\n❌ No message to send')
    
    # Cleanup
    db_manager.close_all()
    
    print('\n✅ Test complete!')
    print('=' * 60)


if __name__ == '__main__':
    main()
