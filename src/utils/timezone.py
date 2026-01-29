"""Timezone utility for ETC Monitor application.

All datetime operations should use IST (Asia/Kolkata) timezone.
This module provides helper functions for timezone-aware datetime operations.
"""
from datetime import datetime, timedelta
from typing import Optional
import pytz


# IST timezone constant
IST = pytz.timezone('Asia/Kolkata')
UTC = pytz.utc


def now_ist() -> datetime:
    """Get current datetime in IST timezone.
    
    Returns:
        Current datetime with IST timezone
    """
    return datetime.now(IST)


def now_utc() -> datetime:
    """Get current datetime in UTC timezone.
    
    Returns:
        Current datetime with UTC timezone
    """
    return datetime.now(UTC)


def to_ist(dt: datetime) -> datetime:
    """Convert datetime to IST timezone.
    
    If datetime is naive (no timezone), assumes it's in IST.
    If datetime has timezone, converts to IST.
    
    Args:
        dt: Datetime to convert
        
    Returns:
        Datetime in IST timezone
    """
    if dt is None:
        return None
    
    # If naive, assume IST
    if dt.tzinfo is None:
        return IST.localize(dt)
    
    # If already has timezone, convert to IST
    return dt.astimezone(IST)


def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC timezone.
    
    If datetime is naive (no timezone), assumes it's in IST.
    If datetime has timezone, converts to UTC.
    
    Args:
        dt: Datetime to convert
        
    Returns:
        Datetime in UTC timezone
    """
    if dt is None:
        return None
    
    # If naive, assume IST first
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    
    # Convert to UTC
    return dt.astimezone(UTC)


def make_aware(dt: datetime, tz: Optional[pytz.timezone] = None) -> datetime:
    """Make a naive datetime timezone-aware.
    
    Args:
        dt: Naive datetime
        tz: Timezone to use (defaults to IST)
        
    Returns:
        Timezone-aware datetime
    """
    if dt is None:
        return None
    
    if dt.tzinfo is not None:
        return dt
    
    timezone = tz or IST
    return timezone.localize(dt)


def make_naive(dt: datetime) -> datetime:
    """Remove timezone information from datetime.
    
    Converts to IST first if timezone-aware, then removes timezone.
    
    Args:
        dt: Datetime to make naive
        
    Returns:
        Naive datetime in IST
    """
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        return dt
    
    # Convert to IST first, then make naive
    dt_ist = dt.astimezone(IST)
    return dt_ist.replace(tzinfo=None)


def format_datetime(dt: datetime, format_str: str = '%Y-%m-%d %H:%M:%S %Z') -> str:
    """Format datetime as string in IST timezone.
    
    Args:
        dt: Datetime to format
        format_str: Format string (default: 'YYYY-MM-DD HH:MM:SS TZ')
        
    Returns:
        Formatted datetime string
    """
    if dt is None:
        return 'None'
    
    # Convert to IST first
    dt_ist = to_ist(dt)
    return dt_ist.strftime(format_str)


def format_datetime_friendly(dt: datetime) -> str:
    """Format datetime in a user-friendly format.
    
    Args:
        dt: Datetime to format
        
    Returns:
        Friendly formatted string (e.g., "Jan 12, 2026 11:30 PM IST")
    """
    if dt is None:
        return 'None'
    
    dt_ist = to_ist(dt)
    return dt_ist.strftime('%b %d, %Y %I:%M %p IST')


def format_time_only(dt: datetime) -> str:
    """Format only time part of datetime.
    
    Args:
        dt: Datetime to format
        
    Returns:
        Time string (e.g., "11:30 PM")
    """
    if dt is None:
        return 'None'
    
    dt_ist = to_ist(dt)
    return dt_ist.strftime('%I:%M %p')


def format_date_only(dt: datetime) -> str:
    """Format only date part of datetime.
    
    Args:
        dt: Datetime to format
        
    Returns:
        Date string (e.g., "Jan 12, 2026")
    """
    if dt is None:
        return 'None'
    
    dt_ist = to_ist(dt)
    return dt_ist.strftime('%b %d, %Y')


def parse_datetime_str(dt_str: str, format_str: str = '%Y-%m-%d %H:%M:%S') -> datetime:
    """Parse datetime string and make it IST-aware.
    
    Args:
        dt_str: Datetime string to parse
        format_str: Format string for parsing
        
    Returns:
        Timezone-aware datetime in IST
    """
    dt = datetime.strptime(dt_str, format_str)
    return make_aware(dt, IST)


def is_past(dt: datetime) -> bool:
    """Check if datetime is in the past.
    
    Args:
        dt: Datetime to check
        
    Returns:
        True if datetime is in the past
    """
    if dt is None:
        return False
    
    current = now_ist()
    dt_ist = to_ist(dt)
    return dt_ist < current


def is_future(dt: datetime) -> bool:
    """Check if datetime is in the future.
    
    Args:
        dt: Datetime to check
        
    Returns:
        True if datetime is in the future
    """
    if dt is None:
        return False
    
    current = now_ist()
    dt_ist = to_ist(dt)
    return dt_ist > current


def time_until(dt: datetime) -> timedelta:
    """Calculate time remaining until datetime.
    
    Args:
        dt: Target datetime
        
    Returns:
        Timedelta representing time until target
    """
    if dt is None:
        return timedelta(0)
    
    current = now_ist()
    dt_ist = to_ist(dt)
    return dt_ist - current


def time_since(dt: datetime) -> timedelta:
    """Calculate time elapsed since datetime.
    
    Args:
        dt: Past datetime
        
    Returns:
        Timedelta representing time since datetime
    """
    if dt is None:
        return timedelta(0)
    
    current = now_ist()
    dt_ist = to_ist(dt)
    return current - dt_ist


def format_timedelta(td: timedelta) -> str:
    """Format timedelta in human-readable format.
    
    Args:
        td: Timedelta to format
        
    Returns:
        Human-readable string (e.g., "2 hours 30 minutes")
    """
    if td is None:
        return 'None'
    
    total_seconds = int(td.total_seconds())
    
    if total_seconds < 0:
        return 'in the past'
    
    if total_seconds < 60:
        return f'{total_seconds} seconds'
    
    minutes = total_seconds // 60
    if minutes < 60:
        return f'{minutes} minutes'
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if hours < 24:
        if remaining_minutes > 0:
            return f'{hours} hours {remaining_minutes} minutes'
        return f'{hours} hours'
    
    days = hours // 24
    remaining_hours = hours % 24
    if remaining_hours > 0:
        return f'{days} days {remaining_hours} hours'
    return f'{days} days'


def get_timezone(tz_name: str = 'Asia/Kolkata') -> pytz.timezone:
    """Get timezone object by name.
    
    Args:
        tz_name: Timezone name (default: Asia/Kolkata)
        
    Returns:
        Timezone object
        
    Raises:
        pytz.exceptions.UnknownTimeZoneError: If timezone name is invalid
    """
    return pytz.timezone(tz_name)
