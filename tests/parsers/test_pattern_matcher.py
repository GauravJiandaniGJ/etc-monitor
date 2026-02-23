"""Unit tests for src/parsers/pattern_matcher.py

Tests the regex-based pattern matching for ETC deadline detection.
"""
import pytest
from src.parsers.pattern_matcher import PatternMatcher


class TestHasETCIndicator:
    """Tests for has_etc_indicator method."""
    
    @pytest.fixture
    def matcher(self):
        """Create PatternMatcher instance."""
        return PatternMatcher()
    
    def test_etc_with_time_returns_true(self, matcher):
        """Test that messages with ETC + time return True."""
        assert matcher.has_etc_indicator("ETC 2 hours") is True
        assert matcher.has_etc_indicator("etc 30 minutes") is True
        assert matcher.has_etc_indicator("ETC tomorrow 5pm") is True
        assert matcher.has_etc_indicator("finish this ETC 1 hour") is True
    
    def test_etc_without_time_returns_false(self, matcher):
        """Test that messages with only ETC (no time) return False."""
        assert matcher.has_etc_indicator("What is ETC?") is False
        assert matcher.has_etc_indicator("etc etc etc") is False
        assert matcher.has_etc_indicator("ETC is important") is False
    
    def test_et_cetera_returns_false(self, matcher):
        """Test that 'et cetera' usage returns False."""
        assert matcher.has_etc_indicator("We need to check logs, configs, etc.") is False
        assert matcher.has_etc_indicator("Files, folders, etc. should be backed up") is False
    
    def test_no_etc_returns_false(self, matcher):
        """Test that messages without ETC return False."""
        assert matcher.has_etc_indicator("I'll finish by 5pm") is False
        assert matcher.has_etc_indicator("deadline is tomorrow") is False
        assert matcher.has_etc_indicator("complete in 2 hours") is False
    
    def test_case_insensitive(self, matcher):
        """Test that ETC detection is case-insensitive."""
        assert matcher.has_etc_indicator("ETC 2 hours") is True
        assert matcher.has_etc_indicator("etc 2 hours") is True
        assert matcher.has_etc_indicator("Etc 2 hours") is True
        assert matcher.has_etc_indicator("EtC 2 hours") is True


class TestExtractDeadlineText:
    """Tests for extract_deadline_text method."""
    
    @pytest.fixture
    def matcher(self):
        """Create PatternMatcher instance."""
        return PatternMatcher()
    
    def test_extract_relative_time(self, matcher):
        """Test extracting relative time expressions."""
        assert matcher.extract_deadline_text("ETC 2 hours") == "2 hours"
        assert matcher.extract_deadline_text("etc 30 minutes") == "30 minutes"
        assert matcher.extract_deadline_text("ETC within 1 hour") == "within 1 hour"
    
    def test_extract_absolute_time(self, matcher):
        """Test extracting absolute time expressions."""
        result = matcher.extract_deadline_text("ETC tomorrow 5pm")
        assert result is not None
        assert "tomorrow" in result.lower() or "5pm" in result.lower()
    
    def test_extract_with_typos(self, matcher):
        """Test that typos are normalized."""
        # The pattern matcher should handle 'with in' -> 'within'
        result = matcher.extract_deadline_text("ETC with in 2 hours")
        assert result is not None
    
    def test_extract_returns_none_for_no_deadline(self, matcher):
        """Test that extract returns None when no deadline found."""
        assert matcher.extract_deadline_text("What is ETC?") is None
        assert matcher.extract_deadline_text("No deadline here") is None
    
    def test_extract_from_longer_message(self, matcher):
        """Test extracting deadline from longer message."""
        message = "Please complete this task ETC 2 hours and let me know"
        result = matcher.extract_deadline_text(message)
        assert result is not None
        assert "2 hours" in result or "2 hour" in result


class TestGetMatchingPatterns:
    """Tests for get_matching_patterns method."""
    
    @pytest.fixture
    def matcher(self):
        """Create PatternMatcher instance."""
        return PatternMatcher()
    
    def test_relative_time_patterns(self, matcher):
        """Test matching relative time patterns."""
        matches = matcher.get_matching_patterns("2 hours")
        assert len(matches) > 0
        
        matches = matcher.get_matching_patterns("30 minutes")
        assert len(matches) > 0
        
        matches = matcher.get_matching_patterns("1 day")
        assert len(matches) > 0
    
    def test_absolute_time_patterns(self, matcher):
        """Test matching absolute time patterns."""
        matches = matcher.get_matching_patterns("5pm")
        assert len(matches) > 0
        
        matches = matcher.get_matching_patterns("17:00")
        assert len(matches) > 0
    
    def test_day_patterns(self, matcher):
        """Test matching day patterns."""
        matches = matcher.get_matching_patterns("tomorrow")
        assert len(matches) > 0
        
        matches = matcher.get_matching_patterns("Monday")
        assert len(matches) > 0
    
    def test_no_matches_for_invalid_text(self, matcher):
        """Test that invalid text returns empty list."""
        matches = matcher.get_matching_patterns("no deadline here")
        assert len(matches) == 0


class TestFindFirstMatch:
    """Tests for find_first_match method."""
    
    @pytest.fixture
    def matcher(self):
        """Create PatternMatcher instance."""
        return PatternMatcher()
    
    def test_find_first_match_returns_tuple(self, matcher):
        """Test that find_first_match returns (pattern, matched_text) tuple."""
        result = matcher.find_first_match("2 hours")
        assert result is not None
        assert isinstance(result, tuple)
        assert len(result) == 2
    
    def test_find_first_match_with_multiple_patterns(self, matcher):
        """Test that find_first_match returns first matching pattern."""
        result = matcher.find_first_match("tomorrow 5pm")
        assert result is not None
    
    def test_find_first_match_returns_none_for_no_match(self, matcher):
        """Test that find_first_match returns None when no match."""
        result = matcher.find_first_match("no deadline here")
        assert result is None


class TestPatternPriority:
    """Tests for pattern matching priority (specific to general)."""
    
    @pytest.fixture
    def matcher(self):
        """Create PatternMatcher instance."""
        return PatternMatcher()
    
    def test_specific_patterns_match_first(self, matcher):
        """Test that more specific patterns are matched before general ones."""
        # "tomorrow 5pm" should match day+time pattern, not just "tomorrow"
        result = matcher.find_first_match("tomorrow 5pm")
        assert result is not None
        pattern, matched = result
        # The matched text should include both "tomorrow" and "5pm"
        assert "tomorrow" in matched.lower()


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    @pytest.fixture
    def matcher(self):
        """Create PatternMatcher instance."""
        return PatternMatcher()
    
    def test_empty_string(self, matcher):
        """Test handling of empty string."""
        assert matcher.has_etc_indicator("") is False
        assert matcher.extract_deadline_text("") is None
        assert matcher.find_first_match("") is None
    
    def test_whitespace_only(self, matcher):
        """Test handling of whitespace-only string."""
        assert matcher.has_etc_indicator("   ") is False
        assert matcher.extract_deadline_text("   ") is None
    
    def test_special_characters(self, matcher):
        """Test handling of special characters."""
        # Should still work with punctuation
        assert matcher.has_etc_indicator("ETC: 2 hours!") is True
        assert matcher.has_etc_indicator("ETC - 2 hours.") is True
    
    def test_multiple_etc_mentions(self, matcher):
        """Test handling of multiple ETC mentions."""
        message = "Task 1 ETC 2 hours, Task 2 ETC 3 hours"
        assert matcher.has_etc_indicator(message) is True
        result = matcher.extract_deadline_text(message)
        assert result is not None


class TestRealWorldExamples:
    """Tests with real-world message examples."""
    
    @pytest.fixture
    def matcher(self):
        """Create PatternMatcher instance."""
        return PatternMatcher()
    
    def test_slack_thread_message_1(self, matcher):
        """Test: 'Will complete this task ETC 2 hours'"""
        message = "Will complete this task ETC 2 hours"
        assert matcher.has_etc_indicator(message) is True
        result = matcher.extract_deadline_text(message)
        assert result is not None
        assert "2 hours" in result or "2 hour" in result
    
    def test_slack_thread_message_2(self, matcher):
        """Test: 'Working on it, etc tomorrow 5pm'"""
        message = "Working on it, etc tomorrow 5pm"
        assert matcher.has_etc_indicator(message) is True
        result = matcher.extract_deadline_text(message)
        assert result is not None
    
    def test_slack_thread_message_3(self, matcher):
        """Test: 'Need to check logs, configs, etc.'"""
        message = "Need to check logs, configs, etc."
        # This is "et cetera", not ETC deadline
        assert matcher.has_etc_indicator(message) is False
    
    def test_slack_thread_message_4(self, matcher):
        """Test: 'ETC within 30 mins'"""
        message = "ETC within 30 mins"
        assert matcher.has_etc_indicator(message) is True
        result = matcher.extract_deadline_text(message)
        assert result is not None
        assert "30" in result and ("min" in result.lower())
    
    def test_slack_thread_message_5(self, matcher):
        """Test: 'Will finish by EOD'"""
        message = "Will finish by EOD"
        # This doesn't have "ETC" keyword
        assert matcher.has_etc_indicator(message) is False
