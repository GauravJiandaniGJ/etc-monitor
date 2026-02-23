"""Unit tests for src/parsers/ai_parser.py

Tests the AI-based deadline parsing with mocked Gemini service.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from src.parsers.ai_parser import AIParser
from src.utils.timezone import now_ist


class TestInitialization:
    """Tests for AIParser initialization."""
    
    def test_init_with_api_key(self):
        """Test initialization with API key."""
        parser = AIParser(api_key="test-key")
        assert parser is not None
    
    def test_init_without_api_key(self):
        """Test initialization without API key."""
        parser = AIParser(api_key=None)
        assert parser is not None
        # Should still initialize but not be available
    
    def test_is_available_with_configured_service(self):
        """Test is_available returns True when service is configured."""
        with patch('src.parsers.ai_parser.GeminiService') as mock_service_class:
            mock_service = Mock()
            mock_service.is_configured.return_value = True
            mock_service_class.return_value = mock_service
            
            parser = AIParser(api_key="test-key")
            assert parser.is_available() is True
    
    def test_is_available_without_configured_service(self):
        """Test is_available returns False when service not configured."""
        with patch('src.parsers.ai_parser.GeminiService') as mock_service_class:
            mock_service = Mock()
            mock_service.is_configured.return_value = False
            mock_service_class.return_value = mock_service
            
            parser = AIParser(api_key=None)
            assert parser.is_available() is False


class TestParseDeadline:
    """Tests for parse_deadline method."""
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_parse_deadline_success(self, mock_service_class):
        """Test successful deadline parsing."""
        # Mock the Gemini service
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service.generate.return_value = '''
        {
            "has_deadline": true,
            "extracted_text": "2 hours",
            "deadline_type": "relative",
            "hours": 2
        }
        '''
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        now = now_ist()
        
        result = parser.parse_deadline("finish this ETC 2 hours", reference_time=now)
        
        assert result is not None
        assert result.original_text == "2 hours"
        assert result.parsed_by == "ai"
        # Should be approximately 2 hours from now
        expected = now + timedelta(hours=2)
        assert abs((result.deadline_datetime - expected).total_seconds()) < 120
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_parse_deadline_no_deadline_found(self, mock_service_class):
        """Test parsing when AI finds no deadline."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service.generate.return_value = '''
        {
            "has_deadline": false
        }
        '''
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        result = parser.parse_deadline("What is ETC?")
        
        assert result is None
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_parse_deadline_invalid_json(self, mock_service_class):
        """Test parsing with invalid JSON response."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service.generate.return_value = "This is not JSON"
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        result = parser.parse_deadline("ETC 2 hours")
        
        assert result is None
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_parse_deadline_timeout(self, mock_service_class):
        """Test parsing with timeout."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        # Simulate timeout by returning None
        mock_service.generate.return_value = None
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key", timeout_seconds=1)
        result = parser.parse_deadline("ETC 2 hours")
        
        assert result is None
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_parse_deadline_service_not_available(self, mock_service_class):
        """Test parsing when service is not available."""
        mock_service = Mock()
        mock_service.is_configured.return_value = False
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key=None)
        result = parser.parse_deadline("ETC 2 hours")
        
        assert result is None


class TestGetDeadlineText:
    """Tests for get_deadline_text method."""
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_get_deadline_text_success(self, mock_service_class):
        """Test extracting deadline text."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service.generate.return_value = '''
        {
            "has_deadline": true,
            "extracted_text": "2 hours"
        }
        '''
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        result = parser.get_deadline_text("finish this ETC 2 hours")
        
        assert result == "2 hours"
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_get_deadline_text_no_deadline(self, mock_service_class):
        """Test extracting when no deadline found."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service.generate.return_value = '''
        {
            "has_deadline": false
        }
        '''
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        result = parser.get_deadline_text("What is ETC?")
        
        assert result is None


class TestValidateExtraction:
    """Tests for _validate_extraction method."""
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_validate_extraction_valid(self, mock_service_class):
        """Test validation with valid extraction."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        
        # Valid extraction - extracted text is substring of original
        assert parser._validate_extraction(
            "finish this ETC 2 hours",
            "2 hours"
        ) is True
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_validate_extraction_too_long(self, mock_service_class):
        """Test validation fails when extraction is too long."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        
        # Extracted text longer than original - invalid
        assert parser._validate_extraction(
            "ETC 2 hours",
            "this is much longer than the original text"
        ) is False
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_validate_extraction_empty(self, mock_service_class):
        """Test validation fails with empty extraction."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        
        assert parser._validate_extraction("ETC 2 hours", "") is False
        assert parser._validate_extraction("ETC 2 hours", "   ") is False


class TestBuildPrompt:
    """Tests for _build_prompt method."""
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_build_prompt_returns_string(self, mock_service_class):
        """Test that _build_prompt returns a non-empty string."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        now = now_ist()
        
        prompt = parser._build_prompt("ETC 2 hours", now)
        
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "ETC 2 hours" in prompt


class TestParseResponse:
    """Tests for _parse_response method."""
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_parse_response_valid_json(self, mock_service_class):
        """Test parsing valid JSON response."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        
        response = '''
        {
            "has_deadline": true,
            "extracted_text": "2 hours",
            "deadline_type": "relative",
            "hours": 2
        }
        '''
        
        result = parser._parse_response(response)
        
        assert result is not None
        assert result['has_deadline'] is True
        assert result['extracted_text'] == "2 hours"
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_parse_response_json_in_code_block(self, mock_service_class):
        """Test parsing JSON wrapped in code block."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        
        response = '''
        ```json
        {
            "has_deadline": true,
            "extracted_text": "2 hours"
        }
        ```
        '''
        
        result = parser._parse_response(response)
        
        assert result is not None
        assert result['has_deadline'] is True
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_parse_response_invalid_json(self, mock_service_class):
        """Test parsing invalid JSON returns None."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        
        result = parser._parse_response("This is not JSON")
        
        assert result is None


class TestRephrase Task:
    """Tests for rephrase_task method."""
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_rephrase_task_success(self, mock_service_class):
        """Test successful task rephrasing."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service.rephrase_task.return_value = "Complete the report"
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        result = parser.rephrase_task("Need to finish the quarterly report by EOD")
        
        assert result == "Complete the report"
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_rephrase_task_failure(self, mock_service_class):
        """Test task rephrasing failure returns original."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service.rephrase_task.return_value = None
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        original = "Need to finish the quarterly report by EOD"
        result = parser.rephrase_task(original)
        
        # Should return original text on failure
        assert result == original


class TestEdgeCases:
    """Tests for edge cases."""
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_parse_empty_text(self, mock_service_class):
        """Test parsing empty text."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        result = parser.parse_deadline("")
        
        assert result is None
    
    @patch('src.parsers.ai_parser.GeminiService')
    def test_parse_none_text(self, mock_service_class):
        """Test parsing None text."""
        mock_service = Mock()
        mock_service.is_configured.return_value = True
        mock_service_class.return_value = mock_service
        
        parser = AIParser(api_key="test-key")
        result = parser.parse_deadline(None)
        
        assert result is None
