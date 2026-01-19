"""DateTime parser for ETC Monitor application.

Parses natural language time/date expressions into datetime objects.
Supports both relative time (e.g., "2 hours") and absolute time (e.g., "tomorrow 5pm").
"""
import re
from datetime import datetime, timedelta
from typing import Optional
import dateparser
from src.utils.timezone import now_ist, to_ist, IST
from src.utils.logger import get_logger


logger = get_logger('DateTimeParser')


class DateTimeParser:
    """Parses natural language datetime expressions.

    Handles relative times (minutes, hours, days) and absolute times
    (specific dates, days of week, times). Falls back to dateparser library
    for complex expressions.
    """

    def __init__(self):
        """Initialize datetime parser."""
        logger.info('DateTime parser initialized')

    def parse(
        self,
        text: str,
        reference_time: Optional[datetime] = None
    ) -> Optional[datetime]:
        """Parse datetime from text.

        Args:
            text: Text to parse
            reference_time: Reference datetime (defaults to now in IST)

        Returns:
            Parsed datetime in IST or None if parsing fails
        """
        if not text:
            return None

        # Use provided reference time or current IST time
        now = reference_time if reference_time else now_ist()
        text_lower = text.lower().strip()

        # Normalize common typos first
        text_lower = self._normalize_typos(text_lower)

        logger.info(f'Parsing datetime from: "{text}" (normalized: "{text_lower}")')

        # Try parsing methods in order of priority
        # IMPORTANT: Check day+time BEFORE standalone time to avoid false matches
        result = self._parse_relative_time(text_lower, now)
        if result:
            logger.info(f'Matched relative time pattern for: "{text_lower}"')
            logger.success(f'Parsed "{text}" -> {result}')
            return result

        result = self._parse_eod_expressions(text_lower, now)
        if result:
            logger.info(f'Matched EOD expression for: "{text_lower}"')
            logger.success(f'Parsed "{text}" -> {result}')
            return result

        # Check day+time BEFORE standalone time (e.g., "tomorrow 1PM" before "1PM")
        result = self._parse_day_with_time(text_lower, now)
        if result:
            logger.info(f'Matched day with time for: "{text_lower}"')
            logger.success(f'Parsed "{text}" -> {result}')
            return result

        result = self._parse_time_of_day(text_lower, now)
        if result:
            logger.info(f'Matched time of day for: "{text_lower}"')
            logger.success(f'Parsed "{text}" -> {result}')
            return result

        result = self._parse_specific_date(text_lower, now)
        if result:
            logger.info(f'Matched specific date for: "{text_lower}"')
            logger.success(f'Parsed "{text}" -> {result}')
            return result

        result = self._parse_informal_expressions(text_lower, now)
        if result:
            logger.info(f'Matched informal expression for: "{text_lower}"')
            logger.success(f'Parsed "{text}" -> {result}')
            return result

        result = self._parse_with_dateparser(text, now)
        if result:
            logger.info(f'Matched dateparser for: "{text}"')
            logger.success(f'Parsed "{text}" -> {result}')
            return result

        logger.warning(f'Failed to parse: "{text}" - tried all parsing methods')
        return None

    def _normalize_typos(self, text: str) -> str:
        """Normalize common typos in time units.

        Args:
            text: Text to normalize

        Returns:
            Normalized text with typos corrected
        """
        # Common typos for time units
        typo_corrections = {
            'minn': 'min',
            'minnn': 'min',
            'minns': 'mins',
            'minnute': 'minute',
            'minnutes': 'minutes',
            'houur': 'hour',
            'houurs': 'hours',
            'houre': 'hour',
            'houres': 'hours',
            'daay': 'day',
            'daays': 'days',
            'weeeek': 'week',
            'weeeeks': 'weeks',
        }

        normalized = text.lower()
        for typo, correction in typo_corrections.items():
            normalized = normalized.replace(typo, correction)

        return normalized

    def _parse_relative_time(
        self,
        text: str,
        now: datetime
    ) -> Optional[datetime]:
        """Parse relative time expressions (e.g., "2 hours", "30 minutes").

        Args:
            text: Text to parse
            now: Reference datetime

        Returns:
            Future datetime or None
        """
        logger.info(f'Trying to parse relative time from: "{text}"')

        # Comprehensive relative time patterns
        relative_patterns = [
            # Pattern: "X min", "X mins", "X minute", "X minutes", "Xm"
            (r'^(\d+)\s*(?:m|min|mins|minute|minutes)$', 'minutes'),
            (r'^in\s+(\d+)\s*(?:m|min|mins|minute|minutes)$', 'minutes'),
            (r'^(\d+)\s*(?:m|min|mins|minute|minutes)\s+(?:from\s+now|later)?$', 'minutes'),

            # Pattern: "X hr", "X hrs", "X hour", "X hours", "Xh"
            (r'^(\d+)\s*(?:h|hr|hrs|hour|hours)$', 'hours'),
            (r'^in\s+(\d+)\s*(?:h|hr|hrs|hour|hours)$', 'hours'),
            (r'^(\d+)\s*(?:h|hr|hrs|hour|hours)\s+(?:from\s+now|later)?$', 'hours'),

            # Pattern: "X day", "X days", "Xd"
            (r'^(\d+)\s*(?:d|day|days)$', 'days'),
            (r'^in\s+(\d+)\s*(?:d|day|days)$', 'days'),
            (r'^(\d+)\s*(?:d|day|days)\s+(?:from\s+now|later)?$', 'days'),

            # Pattern: "X week", "X weeks", "Xw"
            (r'^(\d+)\s*(?:w|week|weeks)$', 'weeks'),
            (r'^in\s+(\d+)\s*(?:w|week|weeks)$', 'weeks'),

            # Pattern: "X sec", "X secs", "X second", "X seconds", "Xs"
            (r'^(\d+)\s*(?:s|sec|secs|second|seconds)$', 'seconds'),
            (r'^in\s+(\d+)\s*(?:s|sec|secs|second|seconds)$', 'seconds'),

            # Pattern: "half hour", "quarter hour"
            (r'^half\s+(?:an?\s+)?hour$', 'half_hour'),
            (r'^quarter\s+(?:an?\s+)?hour$', 'quarter_hour'),
        ]

        for pattern, unit in relative_patterns:
            match = re.search(pattern, text)
            if match:
                logger.info(f'Matched relative time pattern: "{pattern}" -> "{match.group(0)}" (unit: {unit})')
                if unit == 'half_hour':
                    result = now + timedelta(minutes=30)
                    logger.info(f'Calculated: {result}')
                    return result
                elif unit == 'quarter_hour':
                    result = now + timedelta(minutes=15)
                    logger.info(f'Calculated: {result}')
                    return result
                else:
                    amount = int(match.group(1))
                    if unit == 'seconds':
                        result = now + timedelta(seconds=amount)
                    elif unit == 'minutes':
                        result = now + timedelta(minutes=amount)
                    elif unit == 'hours':
                        result = now + timedelta(hours=amount)
                    elif unit == 'days':
                        result = now + timedelta(days=amount)
                    elif unit == 'weeks':
                        result = now + timedelta(weeks=amount)
                    logger.info(f'Calculated: {result} (amount: {amount} {unit})')
                    return result

        # Flexible patterns (not at start) - these should catch "45mins", "2 min", "2 minn" (typos)
        # Note: text is already normalized for typos, so patterns can be simpler
        flexible_patterns = [
            (r'(\d+)\s*(minutes?|mins?|minn?)', 'minutes'),  # Handles "min", "mins", "minn" (typo)
            (r'(\d+)\s*(hours?|hrs?)', 'hours'),
            (r'(\d+)\s*(days?)', 'days'),
            (r'(\d+)\s*(weeks?)', 'weeks'),
            (r'(\d+)\s*(seconds?|secs?)', 'seconds'),
            (r'(\d+)\s*m\b', 'minutes'),
            (r'(\d+)\s*h\b', 'hours'),
            (r'(\d+)\s*d\b', 'days'),
            (r'(\d+)\s*w\b', 'weeks'),
            (r'(\d+)\s*s\b', 'seconds'),
        ]

        for pattern, unit in flexible_patterns:
            match = re.search(pattern, text)
            if match:
                logger.info(f'Matched flexible pattern: "{pattern}" -> "{match.group(0)}" (unit: {unit})')
                amount = int(match.group(1))
                if unit == 'seconds':
                    result = now + timedelta(seconds=amount)
                elif unit == 'minutes':
                    result = now + timedelta(minutes=amount)
                elif unit == 'hours':
                    result = now + timedelta(hours=amount)
                elif unit == 'days':
                    result = now + timedelta(days=amount)
                elif unit == 'weeks':
                    result = now + timedelta(weeks=amount)
                logger.info(f'Calculated: {result} (amount: {amount} {unit})')
                return result

        logger.warning(f'No relative time pattern matched for: "{text}"')
        return None

    def _parse_eod_expressions(
        self,
        text: str,
        now: datetime
    ) -> Optional[datetime]:
        """Parse end-of-day expressions (e.g., "eod", "by eod", "tomorrow eod").

        EOD is interpreted as 7 PM (19:00).

        Args:
            text: Text to parse
            now: Reference datetime

        Returns:
            EOD datetime or None
        """
        eod_expressions = [
            'eod', 'end of day', 'end of work', 'close of business', 'cob',
            'by eod', 'till eod', 'until eod', 'before eod',
            'end of business', 'eob', 'close of day', 'cod'
        ]

        has_eod = any(expr in text for expr in eod_expressions)
        if not has_eod:
            return None

        # Determine which day EOD refers to
        day_with_eod = None

        if 'tomorrow' in text:
            day_with_eod = now + timedelta(days=1)
        elif 'today' in text:
            day_with_eod = now
        else:
            # Check for day of week with EOD
            day_mappings = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                'friday': 4, 'saturday': 5, 'sunday': 6
            }
            for day_name, day_num in day_mappings.items():
                if day_name in text:
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7
                    if days_ahead == 0 and now.hour >= 19:
                        days_ahead = 7
                    day_with_eod = now + timedelta(days=days_ahead)
                    break

        if day_with_eod:
            target_date = day_with_eod.replace(hour=19, minute=0, second=0, microsecond=0)
        else:
            # Just "EOD" means today at 7PM
            target_date = now.replace(hour=19, minute=0, second=0, microsecond=0)

        if target_date <= now:
            target_date += timedelta(days=1)

        return target_date

    def _parse_time_of_day(
        self,
        text: str,
        now: datetime
    ) -> Optional[datetime]:
        """Parse time of day expressions (e.g., "5pm", "17:00", "3:30 PM").

        Args:
            text: Text to parse
            now: Reference datetime

        Returns:
            Datetime with parsed time or None
        """
        # Try patterns for time with AM/PM
        time_patterns = [
            r'(\d{1,2}):(\d{2})\s*(am|pm)',
            r'(\d{1,2})\s*(am|pm)',
        ]

        for pattern in time_patterns:
            match = re.search(pattern, text)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2)) if len(match.groups()) >= 2 and match.group(2).isdigit() else 0
                period = match.group(len(match.groups()))

                # Convert to 24-hour format
                if period == 'pm' and hour != 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0

                target_date = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target_date <= now:
                    target_date += timedelta(days=1)

                return target_date

        # Try 24-hour format
        match = re.search(r'^(\d{1,2}):(\d{2})$', text)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))

            if 0 <= hour <= 23 and 0 <= minute <= 59:
                target_date = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target_date <= now:
                    target_date += timedelta(days=1)
                return target_date

        # Try standalone hour (assume PM if < 12)
        match = re.search(r'^(\d{1,2})$', text)
        if match:
            hour = int(match.group(1))
            if 1 <= hour <= 12:
                # Assume PM for business hours
                if hour != 12:
                    hour += 12
                target_date = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                if target_date <= now:
                    target_date += timedelta(days=1)
                return target_date

        # Named times
        named_times = {
            'morning': (9, 0),
            'noon': (12, 0),
            'afternoon': (14, 0),
            'evening': (18, 0),
            'night': (20, 0),
            'midnight': (0, 0),
        }

        for name, (hour, minute) in named_times.items():
            if name in text:
                target_date = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target_date <= now:
                    target_date += timedelta(days=1)
                return target_date

        return None

    def _parse_day_with_time(
        self,
        text: str,
        now: datetime
    ) -> Optional[datetime]:
        """Parse day with time (e.g., "Monday 5pm", "tomorrow at 3:30").

        Args:
            text: Text to parse
            now: Reference datetime

        Returns:
            Datetime on specified day with time or None
        """
        day_mappings = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }

        # Pattern: day + time with AM/PM
        for day_name, day_num in day_mappings.items():
            match = re.search(
                rf'{day_name}\s+(?:at\s+)?(\d{{1,2}})(?::(\d{{2}}))?\s*(am|pm)',
                text
            )
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2)) if match.group(2) else 0
                period = match.group(3)

                # Convert to 24-hour
                if period == 'pm' and hour != 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0

                # Calculate target day
                current_weekday = now.weekday()
                days_ahead = (day_num - current_weekday) % 7
                if days_ahead == 0:
                    # Same day - check if time has passed
                    test_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if test_time <= now:
                        days_ahead = 7

                target_date = now + timedelta(days=days_ahead)
                target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                return target_date

        # Tomorrow/today/tonight with time
        day_offsets = {
            'tomorrow': 1,
            'today': 0,
            'tonight': 0,
        }

        for day_word, offset in day_offsets.items():
            # Match patterns like "tomorrow 1PM", "tomorrow at 1PM", "tomorrow 1:30 PM"
            # AM/PM is REQUIRED for this pattern
            match = re.search(
                rf'{day_word}\s+(?:at\s+)?(\d{{1,2}})(?::(\d{{2}}))?\s*(am|pm)',
                text,
                re.IGNORECASE
            )
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2)) if match.group(2) else 0
                period = match.group(3).lower()

                # Convert to 24-hour format
                if period == 'pm' and hour != 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0

                # Calculate target date (tomorrow = +1 day, today = +0 days)
                target_date = now + timedelta(days=offset)
                target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

                # If target is in the past (shouldn't happen for tomorrow, but safety check)
                if target_date <= now:
                    target_date += timedelta(days=1)

                return target_date

        return None

    def _parse_specific_date(
        self,
        text: str,
        now: datetime
    ) -> Optional[datetime]:
        """Parse specific dates (e.g., "15th Jan", "Jan 15 at 3pm").

        Args:
            text: Text to parse
            now: Reference datetime

        Returns:
            Datetime on specified date or None
        """
        # Pattern: "15th Jan" or "Jan 15"
        month_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }

        # Try: "15th Jan" or "15 Jan"
        for month_name, month_num in month_map.items():
            match = re.search(rf'(\d{{1,2}})(?:st|nd|rd|th)?\s+{month_name}', text)
            if match:
                day = int(match.group(1))

                # Determine year (this year or next year)
                year = now.year
                try:
                    target_date = now.replace(year=year, month=month_num, day=day,
                                             hour=17, minute=0, second=0, microsecond=0)
                    if target_date < now:
                        target_date = target_date.replace(year=year + 1)
                except ValueError:
                    continue

                # Check for time in the text
                time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', text)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    period = time_match.group(3)

                    if period == 'pm' and hour != 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0

                    target_date = target_date.replace(hour=hour, minute=minute)

                return target_date

        return None

    def _parse_informal_expressions(
        self,
        text: str,
        now: datetime
    ) -> Optional[datetime]:
        """Parse informal expressions (e.g., "tomorrow", "tonight", "next Monday").

        Args:
            text: Text to parse
            now: Reference datetime

        Returns:
            Datetime or None
        """
        # Simple day expressions
        if text == 'today':
            target = now.replace(hour=17, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target

        if text == 'tomorrow':
            target = now + timedelta(days=1)
            return target.replace(hour=17, minute=0, second=0, microsecond=0)

        if text in ['tonight', 'night']:
            target = now.replace(hour=20, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target

        # Days of week
        day_mappings = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }

        for day_name, day_num in day_mappings.items():
            if text == day_name or text == f'next {day_name}' or text == f'this {day_name}':
                current_weekday = now.weekday()
                days_ahead = (day_num - current_weekday) % 7

                if days_ahead == 0:
                    # Same day
                    if 'next' in text or now.hour >= 17:
                        days_ahead = 7

                target = now + timedelta(days=days_ahead)
                return target.replace(hour=17, minute=0, second=0, microsecond=0)

        return None

    def _parse_with_dateparser(
        self,
        text: str,
        now: datetime
    ) -> Optional[datetime]:
        """Fallback to dateparser library for complex expressions.

        Args:
            text: Text to parse
            now: Reference datetime

        Returns:
            Parsed datetime or None
        """
        try:
            parsed = dateparser.parse(
                text,
                settings={
                    'RELATIVE_BASE': now,
                    'PREFER_DATES_FROM': 'future',
                    'TIMEZONE': 'Asia/Kolkata'
                }
            )
            if parsed:
                # Convert to IST
                return to_ist(parsed)
        except Exception as e:
            logger.debug(f'Dateparser failed: {e}')

        return None

    def calculate_reminder_time(self, deadline: datetime) -> datetime:
        """Calculate reminder time from deadline.

        Always reminds at the exact deadline time - no early reminders.
        User requirement: Remind at the correct time only, no before.

        Args:
            deadline: Deadline datetime

        Returns:
            Reminder datetime (same as deadline)
        """
        now = now_ist()

        # Always remind at the exact deadline time
        reminder_time = deadline

        # Only adjust if deadline is in the past (shouldn't happen, but safety check)
        if reminder_time <= now:
            # If deadline is in the past, schedule for 30 seconds from now as fallback
            reminder_time = now + timedelta(seconds=30)
            logger.warning(f'Deadline was in the past, scheduling reminder for 30 seconds from now')

        return reminder_time
