"""Unit tests for src/services/deadline_service.py

Tests the deadline detection and parsing service with mocked parsers.
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from src.services.deadline_service import DeadlineService
from src.core.models import ParsedDeadline
from src.utils.timezone import now_ist


class TestDetect:
    """Tests for detect method."""
    
    @patch('src.services.deadline_service.AIParser')
    @patch('src.services.deadline_service.DateTimeParser')
    @patch('src.services.deadline_service.PatternMatcher')
    def test_detect_ai_parser_success(self, mock_pattern_class, mock_datetime_class, mock_ai_class):
        """Test detect with successful AI parsing."""
        # Setup mocks
        mock_pattern = Mock()
        mock_pattern.has_etc_indicator.return_value = True
        mock_pattern.extract_deadline_text.return_value = "2 hours"
        mock_pattern_class.return_value = mock_pattern
        
        mock_ai = Mock()
        mock_ai.is_available.return_value = True
        now = now_ist()
        expected_deadline = ParsedDeadline(
            original_text="2 hours",
            deadline_datetime=now + timedelta(hours=2),
            reminder_datetime=now + timedelta(hours=2),
            confidence=0.9,
            parsed_by="ai"
        )
        mock_ai.parse_deadline.return_value = expected_deadline
        mock_ai_class.return_value = mock_ai
        
        service = DeadlineService(api_key="test-key")
        result = service.detect("finish this ETC 2 hours")
        
        assert result is not None
        assert result.parsed_by == "ai"
        assert result.confidence == 0.9
    
    @patch('src.services.deadline_service.AIParser')
    @patch('src.services.deadline_service.DateTimeParser')
    @patch('src.services.deadline_service.PatternMatcher')
    def test_detect_fallback_to_regex(self, mock_pattern_class, mock_datetime_class, mock_ai_class):
        """Test detect falls back to regex when AI fails."""
        # Setup mocks
        mock_pattern = Mock()
        mock_pattern.has_etc_indicator.return_value = True
        mock_pattern.extract_deadline_text.return_value = "2 hours"
        mock_pattern_class.return_value = mock_pattern
        
        mock_ai = Mock()
        mock_ai.is_available.return_value = True
        mock_ai.parse_deadline.return_value = None  # AI fails
        mock_ai_class.return_value = mock_ai
        
        mock_datetime = Mock()
        now = now_ist()
        mock_datetime.parse.return_value = now + timedelta(hours=2)
        mock_datetime_class.return_value = mock_datetime
        
        service = DeadlineService(api_key="test-key")
        result = service.detect("finish this ETC 2 hours")
        
        assert result is not None
        assert result.parsed_by == "regex"
    
    @patch('src.services.deadline_service.AIParser')
    @patch('src.services.deadline_service.DateTimeParser')
    @patch('src.services.deadline_service.PatternMatcher')
    def test_detect_no_etc_indicator(self, mock_pattern_class, mock_datetime_class, mock_ai_class):
        """Test detect returns None when no ETC indicator."""
        mock_pattern = Mock()
        mock_pattern.has_etc_indicator.return_value = False
        mock_pattern_class.return_value = mock_pattern
        
        service = DeadlineService(api_key="test-key")
        result = service.detect("No deadline here")
        
        assert result is None
    
    @patch('src.services.deadline_service.AIParser')
    @patch('src.services.deadline_service.DateTimeParser')
    @patch('src.services.deadline_service.PatternMatcher')
    def test_detect_both_parsers_fail(self, mock_pattern_class, mock_datetime_class, mock_ai_class):
        """Test detect returns None when both AI and regex fail."""
        mock_pattern = Mock()
        mock_pattern.has_etc_indicator.return_value = True
        mock_pattern.extract_deadline_text.return_value = "invalid"
        mock_pattern_class.return_value = mock_pattern
        
        mock_ai = Mock()
        mock_ai.is_available.return_value = True
        mock_ai.parse_deadline.return_value = None
        mock_ai_class.return_value = mock_ai
        
        mock_datetime = Mock()
        mock_datetime.parse.return_value = None
        mock_datetime_class.return_value = mock_datetime
        
        service = DeadlineService(api_key="test-key")
        result = service.detect("ETC invalid")
        
        assert result is None


class TestHasETCIndicator:
    """Tests for has_etc_indicator method."""
    
    @patch('src.services.deadline_service.PatternMatcher')
    def test_has_etc_indicator_delegates_to_pattern_matcher(self, mock_pattern_class):
        """Test that has_etc_indicator delegates to PatternMatcher."""
        mock_pattern = Mock()
        mock_pattern.has_etc_indicator.return_value = True
        mock_pattern_class.return_value = mock_pattern
        
        service = DeadlineService(api_key="test-key")
        result = service.has_etc_indicator("ETC 2 hours")
        
        assert result is True
        mock_pattern.has_etc_indicator.assert_called_once_with("ETC 2 hours")


class TestExtractDeadlineText:
    """Tests for extract_deadline_text method."""
    
    @patch('src.services.deadline_service.PatternMatcher')
    def test_extract_deadline_text_delegates_to_pattern_matcher(self, mock_pattern_class):
        """Test that extract_deadline_text delegates to PatternMatcher."""
        mock_pattern = Mock()
        mock_pattern.extract_deadline_text.return_value = "2 hours"
        mock_pattern_class.return_value = mock_pattern
        
        service = DeadlineService(api_key="test-key")
        result = service.extract_deadline_text("finish this ETC 2 hours")
        
        assert result == "2 hours"
        mock_pattern.extract_deadline_text.assert_called_once()


class TestGetParsingStats:
    """Tests for get_parsing_stats method."""
    
    @patch('src.services.deadline_service.AIParser')
    def test_get_parsing_stats(self, mock_ai_class):
        """Test getting parsing statistics."""
        mock_ai = Mock()
        mock_ai.is_available.return_value = True
        mock_ai_class.return_value = mock_ai
        
        service = DeadlineService(api_key="test-key", ai_priority=True)
        stats = service.get_parsing_stats()
        
        assert stats['ai_available'] is True
        assert stats['ai_priority'] is True
        assert 'pattern_matcher' in stats
        assert 'datetime_parser' in stats
