"""Verify EOD logic fix."""
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.settings import Settings
from src.database.db_manager import DBManager
from src.database.repositories.reminder_repository import ReminderRepository

def verify():
    settings = Settings()
    db_manager = DBManager(settings)
    repo = ReminderRepository(db_manager)
    
    print("Checking pending follow-ups...")
    followups = repo.get_pending_followups()
    
    print(f"Found {len(followups)} pending follow-ups.")
    for reminder in followups:
        print(f" - ID: {reminder.id}, User: {reminder.user_id}, Created: {reminder.created_at}")
        print(f"   Sent At: {reminder.sent_at}")
        print(f"   Reminder Sent At: {reminder.reminder_sent_at}")
        
    if len(followups) > 0:
        print("\nSUCCESS: The query correctly identifies legacy reminders!")
    else:
        print("\nFAILURE: No reminders found (check if ID 69 meets criteria: status='sent', etc.)")

if __name__ == "__main__":
    verify()
