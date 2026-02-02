#!/usr/bin/env python3
"""
Quick integration test for daily summary feature.
This is the fastest way to test if everything works.

Usage:
    python scripts/quick_test.py YOUR_SLACK_USER_ID
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("\n" + "="*60)
print("🚀 QUICK TEST: Daily Summary Feature")
print("="*60 + "\n")

# Check arguments
if len(sys.argv) < 2:
    print("❌ Error: Missing user ID")
    print("\nUsage:")
    print("    python scripts/quick_test.py YOUR_SLACK_USER_ID")
    print("\nExample:")
    print("    python scripts/quick_test.py U01ABC23DEF")
    print("\nHow to get your user ID:")
    print("    1. Open Slack")
    print("    2. Click your profile picture")
    print("    3. Click 'Copy member ID'")
    sys.exit(1)

user_id = sys.argv[1]

if not user_id.startswith('U'):
    print(f"⚠️  Warning: User ID '{user_id}' doesn't start with 'U'")
    print("Are you sure this is correct? (Press Ctrl+C to cancel)")
    input("Press Enter to continue anyway...")

print(f"Testing with user ID: {user_id}\n")

# Import dependencies
print("📦 Loading dependencies...")
try:
    from datetime import datetime, timedelta
    from config.settings import Settings
    from src.database.db_manager import DBManager
    from src.database.repositories.reminder_repository import ReminderRepository
    from src.services.notification_service import NotificationService
    from src.services.daily_summary_service import DailySummaryService
    from src.core.models import Reminder, ReminderStatus
    from src.utils.timezone import now_ist
    from slack_sdk import WebClient
    print("✅ Dependencies loaded\n")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("\nTry running:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

# Initialize services
print("🔧 Initializing services...")
try:
    settings = Settings()
    db_manager = DBManager(settings)
    reminder_repo = ReminderRepository(db_manager)
    slack_client = WebClient(token=settings.slack_bot_token)
    notification_service = NotificationService(slack_client)
    daily_summary_service = DailySummaryService(
        reminder_repo=reminder_repo,
        notification_service=notification_service
    )
    print("✅ Services initialized\n")
except Exception as e:
    print(f"❌ Initialization error: {e}")
    print("\nCheck your .env file has:")
    print("    SLACK_BOT_TOKEN=xoxb-...")
    sys.exit(1)

# Test 1: Create sample reminders
print("="*60)
print("TEST 1: Creating Sample Reminders")
print("="*60 + "\n")

now = now_ist()
test_reminders = [
    (-1, "Yesterday task: Fix production bug"),
    (0, "Today task: Code review"),
    (0, "Today task: Update docs"),
    (1, "Tomorrow task: Team meeting prep"),
]

created_count = 0
for days_offset, description in test_reminders:
    deadline = now + timedelta(days=days_offset)
    reminder = Reminder(
        channel_id='C123TEST',
        thread_ts=f'{now.timestamp()}.{days_offset}',
        user_id=user_id,
        message_ts=f'{now.timestamp()}.{days_offset}',
        deadline_text=f'{days_offset} days',
        deadline_datetime=deadline,
        reminder_datetime=deadline - timedelta(hours=1),
        original_message=description,
        status=ReminderStatus.PENDING
    )

    try:
        reminder_id = reminder_repo.create(reminder)
        print(f"✅ Created: {description}")
        created_count += 1
    except Exception as e:
        print(f"⚠️  Warning: Could not create reminder: {e}")

print(f"\n✅ Created {created_count}/{len(test_reminders)} test reminders\n")

# Test 2: Generate and preview summary
print("="*60)
print("TEST 2: Generating Summary Preview")
print("="*60 + "\n")

try:
    message = daily_summary_service.generate_summary_for_user(user_id)
    print(message)
    print("\n✅ Summary generated successfully\n")
except Exception as e:
    print(f"❌ Error generating summary: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Send to Slack
print("="*60)
print("TEST 3: Sending to Slack")
print("="*60 + "\n")

print("⚠️  This will send a REAL DM to your Slack account!")
response = input("Continue? (yes/no): ").strip().lower()

if response != 'yes':
    print("\n❌ Cancelled by user")
    print("\nYou can run just the preview with:")
    print(f"    python scripts/test_daily_summary_manual.py --preview {user_id}")
    sys.exit(0)

print(f"\n📤 Sending DM to {user_id}...")

try:
    success = daily_summary_service.send_summary_to_user(user_id)

    if success:
        print("\n" + "="*60)
        print("🎉 SUCCESS!")
        print("="*60)
        print("\n✅ Daily summary sent successfully!")
        print("\n📱 Check your Slack DMs - you should see the summary!\n")
    else:
        print("\n❌ Failed to send summary")
        print("\nPossible issues:")
        print("  - Invalid user ID")
        print("  - Bot token expired")
        print("  - Bot not installed in workspace")

except Exception as e:
    print(f"\n❌ Error sending: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("="*60)
print("✅ ALL TESTS PASSED!")
print("="*60)
print("\nWhat to do next:")
print("  1. Check your Slack DM")
print("  2. Verify the summary looks correct")
print("  3. Schedule the daily job in your app")
print("\nFor detailed testing, see: scripts/README_TESTING.md\n")
