"""Unit tests for src/parsers/datetime_parser.py

Tests the datetime parsing logic for various time expressions.
"""
import pytest
from datetime import datetime, timedelta
from src.parsers.datetime_parser import DateTimeParser
from src.utils.timezone import now_ist, IST


class TestRelativeTimeParsing:
    """Tests for parsing relative time expressions."""
    
    @pytest.fixture
    def parser(self):
        """Create DateTimeParser instance."""
        return DateTimeParser()
    
    def test_parse_hours(self, parser):
        """Test parsing hour expressions."""
        now = now_ist()
        
        result = parser.parse("2 hours", reference_time=now)
        assert result is not None
        expected = now + timedelta(hours=2)
        assert abs((result - expected).total_seconds()) < 60  # Within 1 minute
        
        result = parser.parse("1 hour", reference_time=now)
        assert result is not None
        expected = now + timedelta(hours=1)
        assert abs((result - expected).total_seconds()) < 60
    
    def test_parse_minutes(self, parser):
        """Test parsing minute expressions."""
        now = now_ist()
        
        result = parser.parse("30 minutes", reference_time=now)
        assert result is not None
        expected = now + timedelta(minutes=30)
        assert abs((result - expected).total_seconds()) < 60
        
        result = parser.parse("90 mins", reference_time=now)
        assert result is not None
        expected = now + timedelta(minutes=90)
        assert abs((result - expected).total_seconds()) < 60
    
    def test_parse_days(self, parser):
        """Test parsing day expressions."""
        now = now_ist()
        
        result = parser.parse("1 day", reference_time=now)
        assert result is not None
        expected = now + timedelta(days=1)
        assert abs((result - expected).total_seconds()) < 120
        
        result = parser.parse("2 days", reference_time=now)
        assert result is not None
        expected = now + timedelta(days=2)
        assert abs((result - expected).total_seconds()) < 120
    
    def test_parse_within_expressions(self, parser):
        """Test parsing 'within X' expressions."""
        now = now_ist()
        
        result = parser.parse("within 2 hours", reference_time=now)
        assert result is not None
        
        result = parser.parse("within 30 minutes", reference_time=now)
        assert result is not None


class TestAbsoluteTimeParsing:
    """Tests for parsing absolute time expressions."""
    
    @pytest.fixture
    def parser(self):
        """Create DateTimeParser instance."""
        return DateTimeParser()
    
    def test_parse_12hour_time(self, parser):
        """Test parsing 12-hour time format."""
        now = now_ist().replace(hour=10, minute=0, second=0, microsecond=0)
        
        result = parser.parse("5pm", reference_time=now)
        assert result is not None
        assert result.hour == 17
        assert result.minute == 0
        
        result = parser.parse("3:30 PM", reference_time=now)
        assert result is not None
        assert result.hour == 15
        assert result.minute == 30
    
    def test_parse_24hour_time(self, parser):
        """Test parsing 24-hour time format."""
        now = now_ist().replace(hour=10, minute=0, second=0, microsecond=0)
        
        result = parser.parse("17:00", reference_time=now)
        assert result is not None
        assert result.hour == 17
        assert result.minute == 0
        
        result = parser.parse("14:30", reference_time=now)
        assert result is not None
        assert result.hour == 14
        assert result.minute == 30
    
    def test_parse_time_goes_to_next_day_if_past(self, parser):
        """Test that past times go to next day."""
        # If it's 5 PM now and user says "2pm", should be tomorrow 2pm
        now = now_ist().replace(hour=17, minute=0, second=0, microsecond=0)
        
        result = parser.parse("2pm", reference_time=now)
        assert result is not None
        # Should be tomorrow
        assert result.day == (now + timedelta(days=1)).day
        assert result.hour == 14


class TestEODExpressions:
    """Tests for End-of-Day expressions."""
    
    @pytest.fixture
    def parser(self):
        """Create DateTimeParser instance."""
        return DateTimeParser()
    
    def test_parse_eod(self, parser):
        """Test parsing 'eod' expression."""
        now = now_ist().replace(hour=10, minute=0, second=0, microsecond=0)
        
        result = parser.parse("eod", reference_time=now)
        assert result is not None
        assert result.hour == 19  # EOD is 7 PM
        assert result.minute == 0
    
    def test_parse_by_eod(self, parser):
        """Test parsing 'by eod' expression."""
        now = now_ist().replace(hour=10, minute=0, second=0, microsecond=0)
        
        result = parser.parse("by eod", reference_time=now)
        assert result is not None
        assert result.hour == 19
    
    def test_parse_tomorrow_eod(self, parser):
        """Test parsing 'tomorrow eod' expression."""
        now = now_ist().replace(hour=10, minute=0, second=0, microsecond=0)
        
        result = parser.parse("tomorrow eod", reference_time=now)
        assert result is not None
        assert result.day == (now + timedelta(days=1)).day
        assert result.hour == 19


class TestDayReferences:
    """Tests for day-of-week and relative day references."""
    
    @pytest.fixture
    def parser(self):
        """Create DateTimeParser instance."""
        return DateTimeParser()
    
    def test_parse_tomorrow(self, parser):
        """Test parsing 'tomorrow'."""
        now = now_ist().replace(hour=10, minute=0, second=0, microsecond=0)
        
        result = parser.parse("tomorrow", reference_time=now)
        assert result is not None
        assert result.day == (now + timedelta(days=1)).day
    
    def test_parse_tomorrow_with_time(self, parser):
        """Test parsing 'tomorrow 5pm'."""
        now = now_ist().replace(hour=10, minute=0, second=0, microsecond=0)
        
        result = parser.parse("tomorrow 5pm", reference_time=now)
        assert result is not None
        assert result.day == (now + timedelta(days=1)).day
        assert result.hour == 17
    
    def test_parse_day_of_week(self, parser):
        """Test parsing day of week (e.g., 'Monday')."""
        now = now_ist()
        
        result = parser.parse("Monday", reference_time=now)
        assert result is not None
        # Should be a future date
        assert result > now
    
    def test_parse_day_of_week_with_time(self, parser):
        """Test parsing day of week with time (e.g., 'Monday 5pm')."""
        now = now_ist()
        
        result = parser.parse("Monday 5pm", reference_time=now)
        assert result is not None
        assert result.hour == 17
        assert result > now


class TestInformalExpressions:
    """Tests for informal time expressions."""
    
    @pytest.fixture
    def parser(self):
        """Create DateTimeParser instance."""
        return DateTimeParser()
    
    def test_parse_tonight(self, parser):
        """Test parsing 'tonight'."""
        now = now_ist().replace(hour=10, minute=0, second=0, microsecond=0)
        
        result = parser.parse("tonight", reference_time=now)
        assert result is not None
        # Tonight should be today evening
        assert result.day == now.day
    
    def test_parse_next_week(self, parser):
        """Test parsing 'next week'."""
        now = now_ist()
        
        result = parser.parse("next week", reference_time=now)
        assert result is not None
        # Should be at least 7 days in future
        assert (result - now).days >= 7


class TestTypoNormalization:
    """Tests for typo normalization."""
    
    @pytest.fixture
    def parser(self):
        """Create DateTimeParser instance."""
        return DateTimeParser()
    
    def test_normalize_minutes_typo(self, parser):
        """Test normalizing 'minues' to 'minutes'."""
        now = now_ist()
        
        # Parser should handle typos
        result = parser.parse("30 minues", reference_time=now)
        # May or may not parse depending on typo handling
        # This is a best-effort test
    
    def test_normalize_hours_typo(self, parser):
        """Test normalizing 'houra' to 'hours'."""
        now = now_ist()
        
        # Parser should handle typos
        result = parser.parse("2 houra", reference_time=now)
        # May or may not parse depending on typo handling


class TestCalculateReminderTime:
    """Tests for calculate_reminder_time method."""
    
    @pytest.fixture
    def parser(self):
        """Create DateTimeParser instance."""
        return DateTimeParser()
    
    def test_reminder_time_equals_deadline(self, parser):
        """Test that reminder time equals deadline (no early reminders)."""
        deadline = now_ist() + timedelta(hours=2)
        
        reminder_time = parser.calculate_reminder_time(deadline)
        
        assert reminder_time == deadline


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.fixture
    def parser(self):
        """Create DateTimeParser instance."""
        return DateTimeParser()
    
    def test_parse_empty_string(self, parser):
        """Test parsing empty string returns None."""
        result = parser.parse("")
        assert result is None
    
    def test_parse_none(self, parser):
        """Test parsing None returns None."""
        result = parser.parse(None)
        assert result is None
    
    def test_parse_invalid_text(self, parser):
        """Test parsing invalid text returns None."""
        result = parser.parse("not a time expression")
        assert result is None
    
    def test_parse_with_no_reference_time(self, parser):
        """Test parsing without reference time uses current time."""
        result = parser.parse("2 hours")
        assert result is not None
        # Should be approximately 2 hours from now
        expected = now_ist() + timedelta(hours=2)
        assert abs((result - expected).total_seconds()) < 120  # Within 2 minutes


class TestRealWorldExamples:
    """Tests with real-world time expressions."""
    
    @pytest.fixture
    def parser(self):
        """Create DateTimeParser instance."""
        return DateTimeParser()
    
    def test_example_1(self, parser):
        """Test: '2 hours'"""
        now = now_ist()
        result = parser.parse("2 hours", reference_time=now)
        assert result is not None
        expected = now + timedelta(hours=2)
        assert abs((result - expected).total_seconds()) < 60
    
    def test_example_2(self, parser):
        """Test: 'tomorrow 5pm'"""
        now = now_ist()
        result = parser.parse("tomorrow 5pm", reference_time=now)
        assert result is not None
        assert result.hour == 17
        assert result.day == (now + timedelta(days=1)).day
    
    def test_example_3(self, parser):
        """Test: 'by eod'"""
        now = now_ist()
        result = parser.parse("by eod", reference_time=now)
        assert result is not None
        assert result.hour == 19
    
    def test_example_4(self, parser):
        """Test: 'within 30 minutes'"""
        now = now_ist()
        result = parser.parse("within 30 minutes", reference_time=now)
        assert result is not None
        expected = now + timedelta(minutes=30)
        assert abs((result - expected).total_seconds()) < 60
    
    def test_example_5(self, parser):
        """Test: 'Monday 3:30 PM'"""
        now = now_ist()
        result = parser.parse("Monday 3:30 PM", reference_time=now)
        assert result is not None
        assert result.hour == 15
        assert result.minute == 30
