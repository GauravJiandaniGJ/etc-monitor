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

        # Comprehensive patterns that work with long messages and natural language
        # Order matters - more specific patterns first
        self.deadline_patterns = [
            # Till expressions with specific dates - highest priority
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))\s+(\d{1,2}(?::\d{2})?)",
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",

            # Standalone times - high priority
            r"^(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))$",
            r"^(\d{1,2}(?::\d{2})?)$",

            # Days with times (most specific first)
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?)",
            r"on\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"on\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?)",
            r"on\s+a\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"on\s+a\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?)",
            r"on\s+the\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"on\s+the\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?)",

            # Professional expressions - highest priority (most flexible patterns first)
            r".*?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r".*?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r".*?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",

            # Specific date with time patterns (most specific first)
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(?:morning|evening|night))",

            # Short month format with time patterns
            r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\s+(?:morning|evening|night))",
            r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\s+at\s+\d{1,2}(?::\d{2})?)",

            # Days of the week patterns with natural language
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(next-to-next|next\s+to\s+next|after\s+next)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"(next-to-next|next\s+to\s+next|after\s+next)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+morning",
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+evening",
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+night",
            r"on\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"on\s+a\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"on\s+the\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"on\s+a\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"on\s+the\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"on\s+a\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"on\s+the\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"by\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"until\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"until\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"until\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"till\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"till\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?)",
            r"till\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"till\s+(tomorrow|today|tonight)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"till\s+(tomorrow|today|tonight)\s+(\d{1,2}(?::\d{2})?)",
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))\s+(\d{1,2}(?::\d{2})?)",
            r"this\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",

            # Enhanced natural language patterns
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",

            # Week patterns
            r"(this\s+week|next\s+week|coming\s+week)",
            r"(this\s+week|next\s+week|coming\s+week)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"(this\s+week|next\s+week|coming\s+week)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",

            # Time expressions with natural language
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(morning|evening|night|noon|midnight)",

            # Date patterns with natural language
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2})",
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+at\s+\d{1,2}(?::\d{2})?)",

            # Flexible time expressions
            r"(in\s+)?(\d+)\s+(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?)\s+(before|after|from\s+now|later)",
            r"(in\s+)?(\d+)\s+(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?)\s+(before|after|from\s+now|later)\s+(morning|evening|night)",


            # Time + day expressions (highest priority)
            r"(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))\s+(tomorrow|today|tonight)",
            r"(\d{1,2}(?::\d{2})?)\s+(tomorrow|today|tonight)",

            # Common informal expressions with time (higher priority)
            r"(tonight|today|tomorrow|day\s+after\s+tomorrow|yesterday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"(tonight|today|tomorrow|day\s+after\s+tomorrow|yesterday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(tonight|today|tomorrow|day\s+after\s+tomorrow|yesterday)\s+(morning|evening|night|noon|midnight)",
            # Common informal expressions without time (lower priority)
            r"(tonight|today|tomorrow|day\s+after\s+tomorrow|yesterday)",

            # EOD and time of day variations
            r"(eod|end\s+of\s+day|end\s+of\s+work|close\s+of\s+business|cob)",
            r"(morning|evening|night|noon|midnight|dawn|dusk)",
            r"(early\s+morning|late\s+evening|late\s+night|early\s+evening)",

            # Relative time patterns (most specific first)
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

            # Date patterns (without time)
            r"in\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"on\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"by\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",

            # Short month format without time
            r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2})(?:\s|$)",

            # Single word time references
            r"^(evening|morning|noon|midnight|tonight|today|tomorrow|eod|monday|tuesday|wednesday|thursday|friday|saturday|sunday)$",

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
                # Always try to return the full match first
                full_match = match.group(0).strip()
                print(f"Pattern {i+1} matched: '{pattern}' -> '{full_match}'")

                # For patterns that match the full message, return the full message
                if full_match == message.strip():
                    print(f"Full message match: '{message}'")
                    return message.strip()

                # For patterns with multiple groups, try to get meaningful text
                # Always return the full match to preserve context
                return full_match

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

        # EOD and work-related expressions - 6 PM
        eod_expressions = ['eod', 'end of day', 'end of work', 'close of business', 'cob']
        if any(expr in date_text_lower for expr in eod_expressions):
            today = now.replace(hour=18, minute=0, second=0, microsecond=0)
            if today <= now:
                today += timedelta(days=1)
            print(f"EOD parsed: {today}")
            return today

        # Handle days of the week
        day_mappings = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }

        # Handle time + day expressions first (highest priority)
        time_day_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s+(tomorrow|today|tonight)', date_text_lower)
        if time_day_match:
            hour = int(time_day_match.group(1))
            minute = int(time_day_match.group(2)) if time_day_match.group(2) else 0
            period = time_day_match.group(3)
            day_expr = time_day_match.group(4)

            # Convert to 24-hour format
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0

            if day_expr == 'tomorrow':
                target_date = now + timedelta(days=1)
            elif day_expr == 'today':
                target_date = now
            elif day_expr == 'tonight':
                target_date = now

            target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_date <= now and day_expr in ['today', 'tonight']:
                target_date += timedelta(days=1)
            print(f"Time + day parsed: {target_date}")
            return target_date

        # Handle time + day expressions without AM/PM
        time_day_24_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s+(tomorrow|today|tonight)', date_text_lower)
        if time_day_24_match:
            hour = int(time_day_24_match.group(1))
            minute = int(time_day_24_match.group(2)) if time_day_24_match.group(2) else 0
            day_expr = time_day_24_match.group(3)

            # Apply smart AM/PM inference
            if hour == 12:
                hour = 12  # 12 PM
            elif hour == 0:
                hour = 0
            elif 1 <= hour <= 11:
                if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                    hour = hour  # Keep as AM
                else:  # 2, 6-11 are more likely to be PM
                    hour = hour + 12  # Convert to PM
            elif 13 <= hour <= 23:
                pass  # Keep as is
            else:
                hour = 9

            if day_expr == 'tomorrow':
                target_date = now + timedelta(days=1)
            elif day_expr == 'today':
                target_date = now
            elif day_expr == 'tonight':
                target_date = now

            target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_date <= now and day_expr in ['today', 'tonight']:
                target_date += timedelta(days=1)
            print(f"Time + day 24h parsed: {target_date}")
            return target_date

        # Handle standalone times first (highest priority)
        standalone_time_match = re.search(r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$', date_text_lower)
        if standalone_time_match:
            hour = int(standalone_time_match.group(1))
            minute = int(standalone_time_match.group(2)) if standalone_time_match.group(2) else 0
            period = standalone_time_match.group(3)

            # Convert to 24-hour format
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0

            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)
            print(f"Standalone time parsed: {target_time}")
            return target_time

        # Handle standalone times without AM/PM
        standalone_time_24_match = re.search(r'^(\d{1,2})(?::(\d{2}))?$', date_text_lower)
        if standalone_time_24_match:
            hour = int(standalone_time_24_match.group(1))
            minute = int(standalone_time_24_match.group(2)) if standalone_time_24_match.group(2) else 0

            # Apply smart AM/PM inference
            if hour == 12:
                hour = 12  # 12 PM
            elif hour == 0:
                hour = 0
            elif 1 <= hour <= 11:
                if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                    hour = hour  # Keep as AM
                else:  # 2, 6-11 are more likely to be PM
                    hour = hour + 12  # Convert to PM
            elif 13 <= hour <= 23:
                pass  # Keep as is
            else:
                hour = 9

            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)
            print(f"Standalone time 24h parsed: {target_time}")
            return target_time

        # Handle days with times (e.g., "friday 2pm", "monday 9am")
        day_time_match = re.search(r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
        if day_time_match:
            day_name = day_time_match.group(1)
            hour = int(day_time_match.group(2))
            minute = int(day_time_match.group(3)) if day_time_match.group(3) else 0
            period = day_time_match.group(4)

            # Convert to 24-hour format
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0

            # Calculate target date
            day_mappings = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                'friday': 4, 'saturday': 5, 'sunday': 6
            }
            target_day = day_mappings[day_name]
            current_day = now.weekday()
            days_ahead = target_day - current_day
            if days_ahead <= 0:  # Target day already passed this week
                days_ahead += 7
            target_date = now + timedelta(days=days_ahead)
            target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            print(f"Day with time parsed: {target_date}")
            return target_date

        # Handle days with times without AM/PM (e.g., "friday 2", "monday 9")
        day_time_24_match = re.search(r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2})(?::(\d{2}))?', date_text_lower)
        if day_time_24_match:
            day_name = day_time_24_match.group(1)
            hour = int(day_time_24_match.group(2))
            minute = int(day_time_24_match.group(3)) if day_time_24_match.group(3) else 0

            # Apply smart AM/PM inference
            if hour == 12:
                hour = 12  # 12 PM
            elif hour == 0:
                hour = 0
            elif 1 <= hour <= 11:
                if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                    hour = hour  # Keep as AM
                else:  # 2, 6-11 are more likely to be PM
                    hour = hour + 12  # Convert to PM
            elif 13 <= hour <= 23:
                pass  # Keep as is
            else:
                hour = 9

            # Calculate target date
            day_mappings = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                'friday': 4, 'saturday': 5, 'sunday': 6
            }
            target_day = day_mappings[day_name]
            current_day = now.weekday()
            days_ahead = target_day - current_day
            if days_ahead <= 0:  # Target day already passed this week
                days_ahead += 7
            target_date = now + timedelta(days=days_ahead)
            target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            print(f"Day with time 24h parsed: {target_date}")
            return target_date

        # Handle "till" expressions with specific dates first (most specific)
        till_date_match = re.search(r'till\s+(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
        if till_date_match:
            day = int(till_date_match.group(1))
            month_name = till_date_match.group(2)
            hour = int(till_date_match.group(3))
            minute = int(till_date_match.group(4)) if till_date_match.group(4) else 0
            period = till_date_match.group(5)

            month_mapping = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }
            month = month_mapping[month_name]

            # Convert to 24-hour format
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0

            # Use current year, or next year if date has passed
            year = now.year
            target_date = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
            # Only go to next year if the date has completely passed (not just the time)
            if target_date.date() < now.date():
                target_date = target_date.replace(year=year + 1)

            print(f"Till specific date parsed: {target_date}")
            return target_date

        # Handle "till" expressions with specific dates without AM/PM
        till_date_match_24 = re.search(r'till\s+(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?::(\d{2}))?', date_text_lower)
        if till_date_match_24:
            day = int(till_date_match_24.group(1))
            month_name = till_date_match_24.group(2)
            hour = int(till_date_match_24.group(3))
            minute = int(till_date_match_24.group(4)) if till_date_match_24.group(4) else 0

            month_mapping = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }
            month = month_mapping[month_name]

            # Apply smart AM/PM inference
            if hour == 12:
                hour = 12  # 12 PM
            elif hour == 0:
                hour = 0
            elif 1 <= hour <= 11:
                if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                    hour = hour  # Keep as AM
                else:  # 2, 6-11 are more likely to be PM
                    hour = hour + 12  # Convert to PM
            elif 13 <= hour <= 23:
                pass  # Keep as is
            else:
                hour = 9

            # Use current year, or next year if date has passed
            year = now.year
            target_date = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
            # Only go to next year if the date has completely passed (not just the time)
            if target_date.date() < now.date():
                target_date = target_date.replace(year=year + 1)

            print(f"Till specific date parsed: {target_date}")
            return target_date

        # Handle "till" expressions first (most specific)
        if 'till' in date_text_lower:
            # Handle "till tomorrow 5 am" or "till tomorrow 5"
            if 'tomorrow' in date_text_lower:
                target_date = now + timedelta(days=1)
                # Extract time from the text
                time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    period = time_match.group(3)

                    if period == 'pm' and hour != 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0

                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    # Check for time without AM/PM
                    time_match_24 = re.search(r'(\d{1,2})(?::(\d{2}))?', date_text_lower)
                    if time_match_24:
                        hour = int(time_match_24.group(1))
                        minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0
                        target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    else:
                        # Default to 9 AM for tomorrow
                        target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

                print(f"Till tomorrow parsed: {target_date}")
                return target_date

            # Handle "till friday" or "till saturday 2 pm"
            for day_name, day_num in day_mappings.items():
                if day_name in date_text_lower:
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7
                    if days_ahead == 0:  # If it's the same day, use today
                        days_ahead = 0
                    target_date = now + timedelta(days=days_ahead)

                    # Extract time from the text
                    time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
                    if time_match:
                        hour = int(time_match.group(1))
                        minute = int(time_match.group(2)) if time_match.group(2) else 0
                        period = time_match.group(3)

                        if period == 'pm' and hour != 12:
                            hour += 12
                        elif period == 'am' and hour == 12:
                            hour = 0

                        target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    else:
                        # Check for time without AM/PM
                        time_match_24 = re.search(r'(\d{1,2})(?::(\d{2}))?', date_text_lower)
                        if time_match_24:
                            hour = int(time_match_24.group(1))
                            minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0
                            target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        else:
                            # Default to 9 AM for day
                            target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

                    print(f"Till {day_name} parsed: {target_date}")
                    return target_date

            # Handle "till 4th Oct 5 pm" or "till 4th Oct 5"
            date_match = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', date_text_lower)
            if date_match:
                day = int(date_match.group(1))
                month_name = date_match.group(2)
                month_mapping = {
                    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                }
                month = month_mapping[month_name]

                # Use current year, or next year if date has passed
                year = now.year
                target_date = now.replace(month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
                # Only go to next year if the date has completely passed (not just the time)
                if target_date.date() < now.date():
                    target_date = target_date.replace(year=year + 1)

                # Extract time from the text
                time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    period = time_match.group(3)

                    if period == 'pm' and hour != 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0

                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    # Check for time without AM/PM
                    time_match_24 = re.search(r'(\d{1,2})(?::(\d{2}))?', date_text_lower)
                    if time_match_24:
                        hour = int(time_match_24.group(1))
                        minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0
                        target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    else:
                        # Default to 6 PM for specific dates
                        target_date = target_date.replace(hour=18, minute=0, second=0, microsecond=0)

                print(f"Till {day} {month_name} parsed: {target_date}")
                return target_date

        # Handle week expressions first
        if 'this week' in date_text_lower or 'coming week' in date_text_lower:
            # Find day of week in the text
            for day_name, day_num in day_mappings.items():
                if day_name in date_text_lower:
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7
                    if days_ahead == 0:  # If it's the same day, use today
                        days_ahead = 0
                    target_date = now + timedelta(days=days_ahead)
                    break
        elif 'next week' in date_text_lower:
            # Find day of week in the text
            for day_name, day_num in day_mappings.items():
                if day_name in date_text_lower:
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7 + 7  # Add 7 for next week
                    target_date = now + timedelta(days=days_ahead)
                    break
        elif 'next-to-next' in date_text_lower or 'next to next' in date_text_lower or 'after next' in date_text_lower:
            # Find day of week in the text for next-to-next week
            for day_name, day_num in day_mappings.items():
                if day_name in date_text_lower:
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7 + 14  # Add 14 for next-to-next week
                    target_date = now + timedelta(days=days_ahead)
                    break
        else:
            # Check for day of week patterns
            for day_name, day_num in day_mappings.items():
                if day_name in date_text_lower:
                    # Check for various modifiers
                    is_next = 'next' in date_text_lower
                    is_this = 'this' in date_text_lower
                    is_before = 'before' in date_text_lower
                    is_after = 'after' in date_text_lower
                    is_particular = 'particular' in date_text_lower
                    is_on_that_day = 'on that day' in date_text_lower
                    is_after_that = 'after that' in date_text_lower

                    # Calculate target day
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7

                    if is_next:
                        days_ahead = (day_num - current_weekday) % 7
                        if days_ahead == 0:  # If it's the same day, go to next week
                            days_ahead = 7
                    elif is_this:
                        days_ahead = (day_num - current_weekday) % 7
                        if days_ahead == 0:  # If it's the same day, use today
                            days_ahead = 0
                    elif is_before:
                        # If it's before a day, go to previous week
                        days_ahead = (day_num - current_weekday) % 7 - 7
                        if days_ahead >= 0:
                            days_ahead -= 7
                    elif is_after or is_particular or is_on_that_day or is_after_that:
                        # Default behavior for these
                        if days_ahead == 0 and now.hour >= 18:  # If it's evening, assume next week
                            days_ahead = 7
                        elif days_ahead == 0:  # If it's the same day but not evening, use today
                            days_ahead = 0
                    else:
                        # Default behavior: if it's the same day or past, go to next week
                        if days_ahead == 0 and now.hour >= 18:  # If it's evening, assume next week
                            days_ahead = 7
                        elif days_ahead == 0:  # If it's the same day but not evening, use today
                            days_ahead = 0

                    target_date = now + timedelta(days=days_ahead)
                    break

        # If we found a target_date, now handle time parsing
        if 'target_date' in locals():
            # Check for specific time with day (AM/PM format)
            time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                period = time_match.group(3)

                if period == 'pm' and hour != 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0

                target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            else:
                # Check for time without AM/PM (e.g., "Friday at 12:00" or "Saturday at 2:00")
                time_match_24 = re.search(r'at\s+(\d{1,2})(?::(\d{2}))?', date_text_lower)
                if time_match_24:
                    hour = int(time_match_24.group(1))
                    minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0

                    # Smart AM/PM inference
                    if hour == 12:
                        # 12:00 is ambiguous, default to PM for most cases
                        hour = 12  # 12 PM
                    elif hour == 0:
                        # 0:00 should be 12 AM
                        hour = 0
                    elif 1 <= hour <= 11:
                        # 1-11 could be AM or PM, use smart inference
                        current_hour = now.hour
                        if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                            hour = hour  # Keep as AM
                        else:  # 2, 6-11 are more likely to be PM
                            # For common afternoon times like 2:00, 3:00, etc., default to PM
                            hour = hour + 12  # Convert to PM
                    elif 13 <= hour <= 23:
                        # 13-23 are clearly 24-hour format
                        pass  # Keep as is
                    else:
                        # Invalid hour, default to 9 AM
                        hour = 9

                    # Convert to 24-hour format if needed
                    if hour > 23:
                        hour = hour % 24
                    if minute > 59:
                        minute = 59

                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    # Check for time of day expressions with day
                    if 'morning' in date_text_lower:
                        target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)
                    elif 'night' in date_text_lower:
                        target_date = target_date.replace(hour=21, minute=0, second=0, microsecond=0)
                    else:
                        # Default to 9 AM for day of week
                        target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

            print(f"Day of week parsed: {target_date}")
            return target_date

        # Handle professional expressions with flexible patterns
        # Check for any day of week in the text (for professional expressions)
        day_mappings = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }

        for day_name, day_num in day_mappings.items():
            if day_name in date_text_lower:
                # Check for time with day (AM/PM format)
                time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    period = time_match.group(3)

                    if period == 'pm' and hour != 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0

                    # Calculate target day
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7
                    if days_ahead == 0:  # If it's the same day, use today
                        days_ahead = 0
                    target_date = now + timedelta(days=days_ahead)
                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

                    print(f"Professional expression parsed: {target_date}")
                    return target_date

                # Check for time without AM/PM
                time_match_24 = re.search(r'at\s+(\d{1,2})(?::(\d{2}))?', date_text_lower)
                if time_match_24:
                    hour = int(time_match_24.group(1))
                    minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0

                    # Apply smart AM/PM inference
                    if hour == 12:
                        hour = 12  # 12 PM
                    elif hour == 0:
                        hour = 0
                    elif 1 <= hour <= 11:
                        if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                            hour = hour  # Keep as AM
                        else:  # 2, 6-11 are more likely to be PM
                            hour = hour + 12  # Convert to PM
                    elif 13 <= hour <= 23:
                        pass  # Keep as is
                    else:
                        hour = 9

                    # Calculate target day
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7
                    if days_ahead == 0:  # If it's the same day, use today
                        days_ahead = 0
                    target_date = now + timedelta(days=days_ahead)
                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

                    print(f"Professional expression parsed: {target_date}")
                    return target_date

                # No specific time, use default
                current_weekday = now.weekday()
                days_ahead = (day_num - current_weekday) % 7
                if days_ahead == 0:  # If it's the same day, use today
                    days_ahead = 0
                target_date = now + timedelta(days=days_ahead)
                target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

                print(f"Professional expression parsed: {target_date}")
                return target_date

        # Handle common informal expressions
        if 'tonight' in date_text_lower:
            target_date = now.replace(hour=21, minute=0, second=0, microsecond=0)
            if target_date <= now:
                target_date += timedelta(days=1)
            print(f"Tonight parsed: {target_date}")
            return target_date

        if 'today' in date_text_lower:
            target_date = now

            # Extract time from the text if present
            time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                period = time_match.group(3)

                # Convert to 24-hour format
                if period == 'pm' and hour != 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0

                target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target_date <= now:
                    target_date += timedelta(days=1)
            else:
                # Check for time without AM/PM
                time_match_24 = re.search(r'(\d{1,2})(?::(\d{2}))?', date_text_lower)
                if time_match_24:
                    hour = int(time_match_24.group(1))
                    minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0
                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if target_date <= now:
                        target_date += timedelta(days=1)
                else:
                    # Default to 6 PM today
                    target_date = target_date.replace(hour=18, minute=0, second=0, microsecond=0)
                    if target_date <= now:
                        target_date += timedelta(days=1)

            print(f"Today parsed: {target_date}")
            return target_date

        if 'tomorrow' in date_text_lower:
            target_date = now + timedelta(days=1)

            # Check for time of day expressions first
            time_mappings = {
                'morning': 9,
                'noon': 12,
                'evening': 18,
                'night': 21,
                'midnight': 0
            }

            time_found = False
            for time_expr, hour in time_mappings.items():
                if time_expr in date_text_lower:
                    target_date = target_date.replace(hour=hour, minute=0, second=0, microsecond=0)
                    time_found = True
                    break

            if not time_found:
                # Extract time from the text if present
                time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    period = time_match.group(3)

                    # Convert to 24-hour format
                    if period == 'pm' and hour != 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0

                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    # Check for time without AM/PM
                    time_match_24 = re.search(r'(\d{1,2})(?::(\d{2}))?', date_text_lower)
                    if time_match_24:
                        hour = int(time_match_24.group(1))
                        minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0
                        target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    else:
                        # Default to 9 AM tomorrow
                        target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

            print(f"Tomorrow parsed: {target_date}")
            return target_date

        if 'day after tomorrow' in date_text_lower:
            target_date = now + timedelta(days=2)
            # Default to 9 AM day after tomorrow
            target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)
            print(f"Day after tomorrow parsed: {target_date}")
            return target_date

        # Handle specific time patterns (AM/PM)
        time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            period = time_match.group(3)

            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0

            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)
            print(f"Specific time parsed: {target_time}")
            return target_time

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

        # Handle specific date patterns (e.g., "2nd Oct", "15th Dec", "Oct 2")
        # Pattern 1: "2nd Oct" format
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

                # Check for specific time with date
                time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text, re.IGNORECASE)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    period = time_match.group(3).lower()

                    if period == 'pm' and hour != 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0
                else:
                    # Default to 6 PM for dates without specific time
                    hour = 18
                    minute = 0

                # If the date is in the past this year, assume next year
                try:
                    target_date = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    if target_date <= now:
                        target_date = target_date.replace(year=year + 1)
                    print(f"Specific date parsed: {target_date}")
                    return target_date
                except ValueError:
                    # Invalid date (e.g., Feb 30th)
                    pass

        # Pattern 2: "Oct 2" format (only if no time is specified)
        short_date_pattern = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?:\s|$)', date_text, re.IGNORECASE)
        if short_date_pattern and not re.search(r'at\s+\d{1,2}(?::\d{2})?', date_text):
            month_name = short_date_pattern.group(1).lower()
            day = int(short_date_pattern.group(2))

            # Map month names to numbers
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }

            if month_name in month_map:
                month = month_map[month_name]
                year = now.year

                # Default to 6 PM for dates without specific time
                hour = 18
                minute = 0

                # If the date is in the past this year, assume next year
                try:
                    target_date = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    if target_date <= now:
                        target_date = target_date.replace(year=year + 1)
                    print(f"Short date format parsed: {target_date}")
                    return target_date
                except ValueError:
                    # Invalid date (e.g., Feb 30th)
                    pass

        # Pattern 3: "Oct 2 at 10:48" format (without AM/PM)
        short_date_time_pattern = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})\s+at\s+(\d{1,2})(?::(\d{2}))?', date_text, re.IGNORECASE)
        if short_date_time_pattern:
            month_name = short_date_time_pattern.group(1).lower()
            day = int(short_date_time_pattern.group(2))
            hour = int(short_date_time_pattern.group(3))
            minute = int(short_date_time_pattern.group(4)) if short_date_time_pattern.group(4) else 0

            # Apply smart AM/PM inference
            if hour == 12:
                # 12:00 is ambiguous, default to PM for most cases
                hour = 12  # 12 PM
            elif hour == 0:
                # 0:00 should be 12 AM
                hour = 0
            elif 1 <= hour <= 11:
                # 1-11 could be AM or PM, use smart inference
                if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                    hour = hour  # Keep as AM
                else:  # 2, 6-11 are more likely to be PM
                    hour = hour + 12  # Convert to PM
            elif 13 <= hour <= 23:
                # 13-23 are clearly 24-hour format
                pass  # Keep as is
            else:
                # Invalid hour, default to 9 AM
                hour = 9

            # Map month names to numbers
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }

            if month_name in month_map:
                month = month_map[month_name]
                year = now.year

                # If the date is in the past this year, assume next year
                # But if it's the same day and time has passed, assume tomorrow
                try:
                    target_date = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    if target_date <= now:
                        # If it's the same day but time has passed, schedule for tomorrow
                        if target_date.date() == now.date():
                            target_date = target_date + timedelta(days=1)
                        else:
                            # If it's a different day, schedule for next year
                            target_date = target_date.replace(year=year + 1)
                    print(f"Short date with time parsed: {target_date}")
                    return target_date
                except ValueError:
                    # Invalid date (e.g., Feb 30th)
                    pass

        # Pattern 4: Full date+time combinations (e.g., "2nd October 2025 10:47 AM")
        full_date_time_pattern = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{4})?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text, re.IGNORECASE)
        if full_date_time_pattern:
            day = int(full_date_time_pattern.group(1))
            month_name = full_date_time_pattern.group(2).lower()
            year = int(full_date_time_pattern.group(3)) if full_date_time_pattern.group(3) else now.year
            hour = int(full_date_time_pattern.group(4))
            minute = int(full_date_time_pattern.group(5)) if full_date_time_pattern.group(5) else 0
            period = full_date_time_pattern.group(6).lower()

            # Map month names to numbers
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }

            if month_name in month_map:
                month = month_map[month_name]

                # Convert to 24-hour format
                if period == 'pm' and hour != 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0

                try:
                    target_date = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    if target_date <= now:
                        target_date = target_date.replace(year=year + 1)
                    print(f"Full date+time parsed: {target_date}")
                    return target_date
                except ValueError:
                    # Invalid date (e.g., Feb 30th)
                    pass

        # Pattern 5: Handle the case where the pattern matches but parsing fails
        # This is a fallback to use dateparser for complex patterns
        if any(keyword in date_text_lower for keyword in ['october', 'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'november', 'december']):
            # Use dateparser for full month names with time
            parsed_date = dateparser.parse(date_text, settings={
                'TIMEZONE': str(self.timezone),
                'RETURN_AS_TIMEZONE_AWARE': True,
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': now
            })

            if parsed_date:
                if parsed_date.tzinfo is None:
                    parsed_date = self.timezone.localize(parsed_date)

                now = datetime.now(self.timezone)
                if parsed_date > now:
                    print(f"Dateparser fallback parsed: {parsed_date}")
                    return parsed_date

        # Use dateparser for absolute dates and complex patterns
        parsed_date = dateparser.parse(date_text, settings={
            'TIMEZONE': str(self.timezone),
            'RETURN_AS_TIMEZONE_AWARE': True,
            'PREFER_DATES_FROM': 'future',
            'RELATIVE_BASE': now
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

        print(f"Reminder created: {deadline_text} -> {due_at}")
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
