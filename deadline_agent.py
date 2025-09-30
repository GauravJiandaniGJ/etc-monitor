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

        # Comprehensive patterns that work with long messages
        self.deadline_patterns = [
            # Relative time patterns (most reliable)
            r"in\s+(\d+\s+(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?))",

            # "at" time patterns
            r"at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"at\s+(evening|morning|noon|midnight)",

            # "by" patterns
            r"by\s+(EOD|eod|end of day)",
            r"by\s+(evening|night|morning|noon|midnight)",
            r"by\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"by\s+(.+?)(?:\s|$|\.|\,|\!|\?)",

            # "till" patterns
            r"till\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"till\s+(evening|night|morning|noon|midnight)",

            # Date patterns
            r"in\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"on\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"by\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",

            # Single word time references
            r"^(evening|morning|noon|midnight|tonight|today|tomorrow)$",

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

        now = datetime.now(self.timezone)

        # Handle common time expressions first
        date_text_lower = date_text.lower().strip()

        # EOD (End of Day) - 6 PM
        if date_text_lower in ['eod', 'end of day']:
            today = now.replace(hour=18, minute=0, second=0, microsecond=0)
            if today <= now:
                today += timedelta(days=1)
            print(f"EOD parsed: {today}")
            return today

        # Time of day expressions
        time_mappings = {
            'morning': 9,
            'noon': 12,
            'evening': 18,
            'night': 21,
            'midnight': 0
        }

        if date_text_lower in time_mappings:
            hour = time_mappings[date_text_lower]
            target_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)
            print(f"Time expression parsed: {target_time}")
            return target_time

        # Handle relative time expressions
        relative_match = re.search(r'(\d+)\s+(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?)', date_text, re.IGNORECASE)
        if relative_match:
            amount = int(relative_match.group(1))
            unit = relative_match.group(2).lower()

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

        # Handle specific date patterns (e.g., "2nd Oct", "15th Dec")
        date_pattern = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', date_text, re.IGNORECASE)
        if date_pattern:
            day = int(date_pattern.group(1))
            month_name = date_pattern.group(2).lower()

            # Map month names to numbers
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }

            if month_name in month_map:
                month = month_map[month_name]
                year = now.year

                # If the date is in the past this year, assume next year
                try:
                    target_date = now.replace(year=year, month=month, day=day, hour=18, minute=0, second=0, microsecond=0)
                    if target_date <= now:
                        target_date = target_date.replace(year=year + 1)
                    print(f"Specific date parsed: {target_date}")
                    return target_date
                except ValueError:
                    # Invalid date (e.g., Feb 30th)
                    pass

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
