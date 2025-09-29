import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict
import pytz
import dateparser


@dataclass
class Reminder:
    """Data structure for storing deadline reminders"""
    id: str
    user_id: str
    message_text: str
    matched_text: str
    due_at: datetime
    created_at: datetime


class DeadlineAgent:
    """AI agent that detects deadlines in user messages and triggers reminders"""

    def __init__(self, timezone: str = 'UTC'):
        self.timezone = pytz.timezone(timezone)
        self.reminders: Dict[str, Reminder] = {}

        # Simple, flexible patterns that work with long messages
        self.deadline_patterns = [
            # Relative time patterns (most reliable)
            r"in\s+(\d+\s+(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?))",
            
            # "by" patterns
            r"by\s+(.+?)(?:\s|$|\.|\,|\!|\?)",
            
            # "deadline" patterns  
            r"deadline[:\s]+(.+?)(?:\s|$|\.|\,|\!|\?)",
            
            # "due" patterns
            r"due[:\s]+(.+?)(?:\s|$|\.|\,|\!|\?)",
            
            # "will [action] by/in" patterns (flexible)
            r"will\s+\w+.*?(?:by|in)\s+(.+?)(?:\s|$|\.|\,|\!|\?)",
            
            # "i will [action] by/in" patterns
            r"i\s+will\s+\w+.*?(?:by|in)\s+(.+?)(?:\s|$|\.|\,|\!|\?)",
            
            # "before" patterns
            r"before\s+(.+?)(?:\s|$|\.|\,|\!|\?)",
        ]

    def _detect_deadline_text(self, message: str) -> Optional[str]:
        """
        Detect deadline text using regex patterns.
        Returns the first matched deadline text or None.
        """
        print(f"Analyzing message: '{message}'")
        
        for i, pattern in enumerate(self.deadline_patterns):
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                matched_text = match.group(1).strip()
                print(f"Pattern {i+1} matched: '{pattern}' -> '{matched_text}'")
                return matched_text
        
        print("No pattern matched")
        return None

    def _parse_datetime(self, date_text: str) -> Optional[datetime]:
        """
        Parse datetime from text, supporting both absolute and relative formats.
        """
        print(f"Parsing datetime from: '{date_text}'")
        
        # Handle relative time expressions first (more reliable)
        relative_match = re.search(r'(\d+)\s+(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?)', date_text, re.IGNORECASE)
        if relative_match:
            amount = int(relative_match.group(1))
            unit = relative_match.group(2).lower()

            now = datetime.now(self.timezone)
            
            if unit in ['second', 'seconds', 'sec', 'secs']:
                future_time = now + timedelta(seconds=amount)
            elif unit in ['minute', 'minutes', 'min', 'mins']:
                future_time = now + timedelta(minutes=amount)
            elif unit in ['hour', 'hours', 'hr', 'hrs']:
                future_time = now + timedelta(hours=amount)
            elif unit in ['day', 'days']:
                future_time = now + timedelta(days=amount)
            elif unit in ['week', 'weeks']:
                future_time = now + timedelta(weeks=amount)
            elif unit in ['month', 'months']:
                future_time = now + timedelta(days=amount * 30)
            else:
                return None

            print(f"Relative time parsed: {future_time}")
            return future_time

        # Use dateparser for absolute dates
        parsed_date = dateparser.parse(date_text, settings={
            'TIMEZONE': str(self.timezone),
            'RETURN_AS_TIMEZONE_AWARE': True,
            'PREFER_DATES_FROM': 'future'
        })

        if parsed_date:
            if parsed_date.tzinfo is None:
                parsed_date = self.timezone.localize(parsed_date)

            now = datetime.now(self.timezone)
            if parsed_date > now:
                print(f"Absolute date parsed: {parsed_date}")
                return parsed_date

        print("Failed to parse datetime")
        return None

    def handle_message(self, message: str, user_id: str) -> Optional[Reminder]:
        """
        Main function to process a message and detect deadlines.
        Returns a Reminder object if deadline is found, None otherwise.
        """
        # Detect deadline text
        deadline_text = self._detect_deadline_text(message)
        if not deadline_text:
            print("No deadline text detected")
            return None

        # Parse the datetime
        due_at = self._parse_datetime(deadline_text)
        if not due_at:
            print("Failed to parse deadline datetime")
            return None

        # Create reminder
        reminder_id = str(uuid.uuid4())
        created_at = datetime.now(self.timezone)

        reminder = Reminder(
            id=reminder_id,
            user_id=user_id,
            message_text=message,
            matched_text=deadline_text,
            due_at=due_at,
            created_at=created_at
        )

        # Store reminder
        self.reminders[reminder_id] = reminder
        
        print(f"✅ Reminder created: {deadline_text} -> {due_at}")
        return reminder

    def get_reminder(self, reminder_id: str) -> Optional[Reminder]:
        """Retrieve a specific reminder by ID"""
        return self.reminders.get(reminder_id)

    def get_all_reminders(self) -> Dict[str, Reminder]:
        """Get all stored reminders"""
        return self.reminders.copy()

    def remove_reminder(self, reminder_id: str) -> bool:
        """Remove a reminder from storage"""
        if reminder_id in self.reminders:
            del self.reminders[reminder_id]
            return True
        return False