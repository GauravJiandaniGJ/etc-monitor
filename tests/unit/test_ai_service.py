"""Unit tests for src/services/ai_service.py

Tests the Gemini AI service wrapper with mocked genai module.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.services.ai_service import GeminiService


class TestInitialization:
    """Tests for GeminiService initialization."""
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_init_with_api_key(self, mock_genai):
        """Test initialization with API key."""
        mock_model = Mock()
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(api_key="test-key")
        
        assert service.api_key == "test-key"
        assert service.client is not None
        mock_genai.configure.assert_called_once_with(api_key="test-key")
    
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_init_without_api_key(self):
        """Test initialization without API key."""
        service = GeminiService(api_key=None)
        
        assert service.api_key is None
        assert service.client is None
    
    @patch('src.services.ai_service.GEMINI_AVAILABLE', False)
    def test_init_when_gemini_not_available(self):
        """Test initialization when genai package not available."""
        service = GeminiService(api_key="test-key")
        
        assert service.client is None


class TestIsConfigured:
    """Tests for is_configured method."""
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_is_configured_returns_true_when_client_exists(self, mock_genai):
        """Test is_configured returns True when client is set."""
        mock_model = Mock()
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(api_key="test-key")
        
        assert service.is_configured() is True
    
    def test_is_configured_returns_false_when_no_client(self):
        """Test is_configured returns False when client is None."""
        service = GeminiService(api_key=None)
        
        assert service.is_configured() is False


class TestGenerate:
    """Tests for generate method."""
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_generate_success(self, mock_genai):
        """Test successful text generation."""
        mock_response = Mock()
        mock_response.text = "Generated text response"
        
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(api_key="test-key")
        result = service.generate("Test prompt")
        
        assert result == "Generated text response"
        mock_model.generate_content.assert_called_once()
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_generate_with_empty_prompt(self, mock_genai):
        """Test generate with empty prompt returns None."""
        mock_model = Mock()
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(api_key="test-key")
        result = service.generate("")
        
        assert result is None
    
    def test_generate_when_not_configured(self):
        """Test generate returns None when service not configured."""
        service = GeminiService(api_key=None)
        result = service.generate("Test prompt")
        
        assert result is None
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_generate_with_retry_on_failure(self, mock_genai):
        """Test generate retries on failure."""
        mock_model = Mock()
        # First call fails, second succeeds
        mock_response = Mock()
        mock_response.text = "Success"
        mock_model.generate_content.side_effect = [
            Exception("API Error"),
            mock_response
        ]
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(api_key="test-key", max_retries=2, retry_delay=0.1)
        result = service.generate("Test prompt")
        
        assert result == "Success"
        assert mock_model.generate_content.call_count == 2
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_generate_exhausts_retries(self, mock_genai):
        """Test generate returns None after exhausting retries."""
        mock_model = Mock()
        mock_model.generate_content.side_effect = Exception("API Error")
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(api_key="test-key", max_retries=2, retry_delay=0.1)
        result = service.generate("Test prompt")
        
        assert result is None
        assert mock_model.generate_content.call_count == 2
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_generate_with_custom_temperature(self, mock_genai):
        """Test generate with custom temperature."""
        mock_response = Mock()
        mock_response.text = "Generated text"
        
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(api_key="test-key")
        result = service.generate("Test prompt", temperature=0.5)
        
        assert result == "Generated text"


class TestTestConnection:
    """Tests for test_connection method."""
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_connection_success(self, mock_genai):
        """Test successful connection test."""
        mock_response = Mock()
        mock_response.text = "OK"
        
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(api_key="test-key")
        result = service.test_connection()
        
        assert result is True
    
    def test_connection_when_not_configured(self):
        """Test connection test returns False when not configured."""
        service = GeminiService(api_key=None)
        result = service.test_connection()
        
        assert result is False
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_connection_failure(self, mock_genai):
        """Test connection test returns False on failure."""
        mock_model = Mock()
        mock_model.generate_content.side_effect = Exception("Connection error")
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(api_key="test-key", max_retries=1, retry_delay=0.1)
        result = service.test_connection()
        
        assert result is False


class TestRephrase Task:
    """Tests for rephrase_task method."""
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_rephrase_task_success(self, mock_genai):
        """Test successful task rephrasing."""
        mock_response = Mock()
        mock_response.text = "Complete the quarterly report"
        
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(api_key="test-key")
        result = service.rephrase_task("Need to finish the quarterly report by EOD")
        
        assert result == "Complete the quarterly report"
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_rephrase_task_strips_quotes(self, mock_genai):
        """Test that rephrase_task strips quotes from response."""
        mock_response = Mock()
        mock_response.text = '"Complete the report"'
        
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(api_key="test-key")
        result = service.rephrase_task("Finish the report")
        
        assert result == "Complete the report"
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_rephrase_task_failure_returns_original(self, mock_genai):
        """Test that rephrase_task returns original on failure."""
        mock_model = Mock()
        mock_model.generate_content.return_value = None
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(api_key="test-key")
        original = "Finish the report"
        result = service.rephrase_task(original)
        
        assert result == original
    
    def test_rephrase_task_with_empty_text(self):
        """Test rephrase_task with empty text returns None."""
        service = GeminiService(api_key="test-key")
        result = service.rephrase_task("")
        
        assert result is None


class TestGetModelInfo:
    """Tests for get_model_info method."""
    
    @patch('src.services.ai_service.genai')
    @patch('src.services.ai_service.GEMINI_AVAILABLE', True)
    def test_get_model_info(self, mock_genai):
        """Test getting model information."""
        mock_model = Mock()
        mock_genai.GenerativeModel.return_value = mock_model
        
        service = GeminiService(
            api_key="test-key",
            model="gemini-1.5-flash",
            temperature=0.2,
            max_retries=3,
            retry_delay=1.0
        )
        
        info = service.get_model_info()
        
        assert info['model'] == "gemini-1.5-flash"
        assert info['temperature'] == 0.2
        assert info['max_retries'] == 3
        assert info['retry_delay'] == 1.0
        assert info['is_configured'] is True
        assert info['api_key_set'] is True
    
    def test_get_model_info_when_not_configured(self):
        """Test getting model info when not configured."""
        service = GeminiService(api_key=None)
        
        info = service.get_model_info()
        
        assert info['is_configured'] is False
        assert info['api_key_set'] is False
