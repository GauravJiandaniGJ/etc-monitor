"""Unit tests for src/utils/timezone.py

Tests all 18 timezone utility functions with various edge cases.
"""
import pytest
from datetime import datetime, timedelta
import pytz

from src.utils.timezone import (
    now_ist, now_utc, to_ist, to_utc,
    make_aware, make_naive,
    format_datetime, format_datetime_friendly,
    format_time_only, format_date_only,
    parse_datetime_str,
    is_past, is_future,
    time_until, time_since,
    format_timedelta,
    get_timezone,
    IST, UTC
)


class TestTimezoneAwareness:
    """Tests for timezone-aware datetime creation and conversion."""
    
    def test_now_ist_returns_ist_timezone(self):
        """Test that now_ist() returns datetime in IST timezone."""
        dt = now_ist()
        assert dt.tzinfo is not None
        assert dt.tzinfo == IST
    
    def test_now_utc_returns_utc_timezone(self):
        """Test that now_utc() returns datetime in UTC timezone."""
        dt = now_utc()
        assert dt.tzinfo is not None
        assert dt.tzinfo == UTC
    
    def test_to_ist_with_naive_datetime(self):
        """Test converting naive datetime to IST (assumes IST)."""
        naive_dt = datetime(2026, 2, 16, 14, 30, 0)
        ist_dt = to_ist(naive_dt)
        
        assert ist_dt.tzinfo == IST
        assert ist_dt.hour == 14  # Same hour, just made aware
    
    def test_to_ist_with_utc_datetime(self):
        """Test converting UTC datetime to IST."""
        utc_dt = datetime(2026, 2, 16, 9, 0, 0, tzinfo=UTC)  # 9 AM UTC
        ist_dt = to_ist(utc_dt)
        
        assert ist_dt.tzinfo == IST
        assert ist_dt.hour == 14  # 9 AM UTC = 2:30 PM IST (UTC+5:30)
        assert ist_dt.minute == 30
    
    def test_to_ist_with_none(self):
        """Test that to_ist(None) returns None."""
        assert to_ist(None) is None
    
    def test_to_utc_with_naive_datetime(self):
        """Test converting naive datetime to UTC (assumes IST first)."""
        naive_dt = datetime(2026, 2, 16, 14, 30, 0)
        utc_dt = to_utc(naive_dt)
        
        assert utc_dt.tzinfo == UTC
        assert utc_dt.hour == 9  # 2:30 PM IST = 9 AM UTC
        assert utc_dt.minute == 0
    
    def test_to_utc_with_ist_datetime(self):
        """Test converting IST datetime to UTC."""
        ist_dt = IST.localize(datetime(2026, 2, 16, 14, 30, 0))
        utc_dt = to_utc(ist_dt)
        
        assert utc_dt.tzinfo == UTC
        assert utc_dt.hour == 9
        assert utc_dt.minute == 0
    
    def test_to_utc_with_none(self):
        """Test that to_utc(None) returns None."""
        assert to_utc(None) is None


class TestMakeAwareNaive:
    """Tests for making datetimes aware/naive."""
    
    def test_make_aware_with_naive_datetime(self):
        """Test making naive datetime aware (default IST)."""
        naive_dt = datetime(2026, 2, 16, 14, 30, 0)
        aware_dt = make_aware(naive_dt)
        
        assert aware_dt.tzinfo == IST
        assert aware_dt.hour == 14
    
    def test_make_aware_with_custom_timezone(self):
        """Test making naive datetime aware with custom timezone."""
        naive_dt = datetime(2026, 2, 16, 14, 30, 0)
        aware_dt = make_aware(naive_dt, tz=UTC)
        
        assert aware_dt.tzinfo == UTC
    
    def test_make_aware_with_already_aware_datetime(self):
        """Test that make_aware returns datetime unchanged if already aware."""
        aware_dt = IST.localize(datetime(2026, 2, 16, 14, 30, 0))
        result = make_aware(aware_dt)
        
        assert result == aware_dt
        assert result.tzinfo == IST
    
    def test_make_aware_with_none(self):
        """Test that make_aware(None) returns None."""
        assert make_aware(None) is None
    
    def test_make_naive_with_aware_datetime(self):
        """Test removing timezone from aware datetime."""
        aware_dt = IST.localize(datetime(2026, 2, 16, 14, 30, 0))
        naive_dt = make_naive(aware_dt)
        
        assert naive_dt.tzinfo is None
        assert naive_dt.hour == 14
    
    def test_make_naive_with_utc_datetime(self):
        """Test that make_naive converts to IST first, then removes timezone."""
        utc_dt = datetime(2026, 2, 16, 9, 0, 0, tzinfo=UTC)
        naive_dt = make_naive(utc_dt)
        
        assert naive_dt.tzinfo is None
        assert naive_dt.hour == 14  # Converted to IST first
        assert naive_dt.minute == 30
    
    def test_make_naive_with_already_naive_datetime(self):
        """Test that make_naive returns datetime unchanged if already naive."""
        naive_dt = datetime(2026, 2, 16, 14, 30, 0)
        result = make_naive(naive_dt)
        
        assert result == naive_dt
        assert result.tzinfo is None
    
    def test_make_naive_with_none(self):
        """Test that make_naive(None) returns None."""
        assert make_naive(None) is None


class TestFormatting:
    """Tests for datetime formatting functions."""
    
    def test_format_datetime_default_format(self):
        """Test default datetime formatting."""
        dt = IST.localize(datetime(2026, 2, 16, 14, 30, 0))
        formatted = format_datetime(dt)
        
        assert '2026-02-16' in formatted
        assert '14:30:00' in formatted
        assert 'IST' in formatted
    
    def test_format_datetime_custom_format(self):
        """Test custom datetime formatting."""
        dt = IST.localize(datetime(2026, 2, 16, 14, 30, 0))
        formatted = format_datetime(dt, format_str='%Y/%m/%d %H:%M')
        
        assert formatted == '2026/02/16 14:30'
    
    def test_format_datetime_with_none(self):
        """Test that format_datetime(None) returns 'None'."""
        assert format_datetime(None) == 'None'
    
    def test_format_datetime_friendly(self):
        """Test friendly datetime formatting."""
        dt = IST.localize(datetime(2026, 2, 16, 14, 30, 0))
        formatted = format_datetime_friendly(dt)
        
        assert 'Feb 16, 2026' in formatted
        assert '02:30 PM' in formatted
        assert 'IST' in formatted
    
    def test_format_datetime_friendly_with_none(self):
        """Test that format_datetime_friendly(None) returns 'None'."""
        assert format_datetime_friendly(None) == 'None'
    
    def test_format_time_only(self):
        """Test time-only formatting."""
        dt = IST.localize(datetime(2026, 2, 16, 14, 30, 0))
        formatted = format_time_only(dt)
        
        assert formatted == '02:30 PM'
    
    def test_format_time_only_with_none(self):
        """Test that format_time_only(None) returns 'None'."""
        assert format_time_only(None) == 'None'
    
    def test_format_date_only(self):
        """Test date-only formatting."""
        dt = IST.localize(datetime(2026, 2, 16, 14, 30, 0))
        formatted = format_date_only(dt)
        
        assert formatted == 'Feb 16, 2026'
    
    def test_format_date_only_with_none(self):
        """Test that format_date_only(None) returns 'None'."""
        assert format_date_only(None) == 'None'


class TestParsing:
    """Tests for datetime parsing."""
    
    def test_parse_datetime_str_default_format(self):
        """Test parsing datetime string with default format."""
        dt_str = '2026-02-16 14:30:00'
        dt = parse_datetime_str(dt_str)
        
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 16
        assert dt.hour == 14
        assert dt.minute == 30
        assert dt.tzinfo == IST
    
    def test_parse_datetime_str_custom_format(self):
        """Test parsing datetime string with custom format."""
        dt_str = '16/02/2026 14:30'
        dt = parse_datetime_str(dt_str, format_str='%d/%m/%Y %H:%M')
        
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 16
        assert dt.hour == 14
        assert dt.minute == 30
        assert dt.tzinfo == IST


class TestComparison:
    """Tests for datetime comparison functions."""
    
    def test_is_past_with_past_datetime(self):
        """Test that is_past returns True for past datetime."""
        past_dt = now_ist() - timedelta(hours=1)
        assert is_past(past_dt) is True
    
    def test_is_past_with_future_datetime(self):
        """Test that is_past returns False for future datetime."""
        future_dt = now_ist() + timedelta(hours=1)
        assert is_past(future_dt) is False
    
    def test_is_past_with_none(self):
        """Test that is_past(None) returns False."""
        assert is_past(None) is False
    
    def test_is_future_with_future_datetime(self):
        """Test that is_future returns True for future datetime."""
        future_dt = now_ist() + timedelta(hours=1)
        assert is_future(future_dt) is True
    
    def test_is_future_with_past_datetime(self):
        """Test that is_future returns False for past datetime."""
        past_dt = now_ist() - timedelta(hours=1)
        assert is_future(past_dt) is False
    
    def test_is_future_with_none(self):
        """Test that is_future(None) returns False."""
        assert is_future(None) is False


class TestTimeDelta:
    """Tests for timedelta calculation and formatting."""
    
    def test_time_until_future_datetime(self):
        """Test calculating time until future datetime."""
        future_dt = now_ist() + timedelta(hours=2, minutes=30)
        delta = time_until(future_dt)
        
        # Should be approximately 2.5 hours
        assert delta.total_seconds() > 9000  # > 2.5 hours
        assert delta.total_seconds() < 9100  # < 2.52 hours
    
    def test_time_until_past_datetime(self):
        """Test that time_until returns negative timedelta for past datetime."""
        past_dt = now_ist() - timedelta(hours=1)
        delta = time_until(past_dt)
        
        assert delta.total_seconds() < 0
    
    def test_time_until_with_none(self):
        """Test that time_until(None) returns zero timedelta."""
        delta = time_until(None)
        assert delta == timedelta(0)
    
    def test_time_since_past_datetime(self):
        """Test calculating time since past datetime."""
        past_dt = now_ist() - timedelta(hours=1, minutes=30)
        delta = time_since(past_dt)
        
        # Should be approximately 1.5 hours
        assert delta.total_seconds() > 5400  # > 1.5 hours
        assert delta.total_seconds() < 5500  # < 1.53 hours
    
    def test_time_since_future_datetime(self):
        """Test that time_since returns negative timedelta for future datetime."""
        future_dt = now_ist() + timedelta(hours=1)
        delta = time_since(future_dt)
        
        assert delta.total_seconds() < 0
    
    def test_time_since_with_none(self):
        """Test that time_since(None) returns zero timedelta."""
        delta = time_since(None)
        assert delta == timedelta(0)
    
    def test_format_timedelta_seconds(self):
        """Test formatting timedelta in seconds."""
        td = timedelta(seconds=45)
        formatted = format_timedelta(td)
        
        assert formatted == '45 seconds'
    
    def test_format_timedelta_minutes(self):
        """Test formatting timedelta in minutes."""
        td = timedelta(minutes=30)
        formatted = format_timedelta(td)
        
        assert formatted == '30 minutes'
    
    def test_format_timedelta_hours(self):
        """Test formatting timedelta in hours."""
        td = timedelta(hours=2)
        formatted = format_timedelta(td)
        
        assert formatted == '2 hours'
    
    def test_format_timedelta_hours_and_minutes(self):
        """Test formatting timedelta with hours and minutes."""
        td = timedelta(hours=2, minutes=30)
        formatted = format_timedelta(td)
        
        assert formatted == '2 hours 30 minutes'
    
    def test_format_timedelta_days(self):
        """Test formatting timedelta in days."""
        td = timedelta(days=3)
        formatted = format_timedelta(td)
        
        assert formatted == '3 days'
    
    def test_format_timedelta_days_and_hours(self):
        """Test formatting timedelta with days and hours."""
        td = timedelta(days=2, hours=5)
        formatted = format_timedelta(td)
        
        assert formatted == '2 days 5 hours'
    
    def test_format_timedelta_negative(self):
        """Test formatting negative timedelta."""
        td = timedelta(hours=-2)
        formatted = format_timedelta(td)
        
        assert formatted == 'in the past'
    
    def test_format_timedelta_with_none(self):
        """Test that format_timedelta(None) returns 'None'."""
        assert format_timedelta(None) == 'None'


class TestGetTimezone:
    """Tests for get_timezone function."""
    
    def test_get_timezone_default(self):
        """Test getting default timezone (IST)."""
        tz = get_timezone()
        assert tz == IST
    
    def test_get_timezone_custom(self):
        """Test getting custom timezone."""
        tz = get_timezone('America/New_York')
        assert tz == pytz.timezone('America/New_York')
    
    def test_get_timezone_invalid(self):
        """Test that invalid timezone raises exception."""
        with pytest.raises(pytz.exceptions.UnknownTimeZoneError):
            get_timezone('Invalid/Timezone')
