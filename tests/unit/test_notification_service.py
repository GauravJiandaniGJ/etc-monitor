"""Unit tests for src/services/notification_service.py

Tests the Slack notification service with mocked WebClient.
"""
import pytest
from unittest.mock import Mock
from src.services.notification_service import NotificationService


@pytest.fixture
def service(mock_slack_client):
    """Create NotificationService with mocked Slack client."""
    return NotificationService(client=mock_slack_client)


class TestSendReminder:
    """Tests for send_reminder method."""
    
    def test_send_reminder_success(self, service, mock_slack_client, sample_reminder):
        """Test successful reminder sending."""
        reminder = sample_reminder()
        
        result = service.send_reminder(reminder)
        
        assert result is True
        mock_slack_client.chat_postMessage.assert_called_once()
    
    def test_send_reminder_failure(self, service, mock_slack_client, sample_reminder):
        """Test reminder sending failure."""
        reminder = sample_reminder()
        mock_slack_client.chat_postMessage.side_effect = Exception("API Error")
        
        result = service.send_reminder(reminder)
        
        assert result is False


class TestSendConfirmation:
    """Tests for send_confirmation method."""
    
    def test_send_confirmation_new_reminder(self, service, mock_slack_client, sample_reminder):
        """Test sending confirmation for new reminder."""
        reminder = sample_reminder()
        
        result = service.send_confirmation(reminder, is_update=False)
        
        assert result is True
        mock_slack_client.chat_postMessage.assert_called_once()
    
    def test_send_confirmation_updated_reminder(self, service, mock_slack_client, sample_reminder):
        """Test sending confirmation for updated reminder."""
        reminder = sample_reminder()
        
        result = service.send_confirmation(reminder, is_update=True)
        
        assert result is True
        mock_slack_client.chat_postMessage.assert_called_once()


class TestResolveNames:
    """Tests for user/channel name resolution."""
    
    def test_resolve_user_name_success(self, service, mock_slack_client):
        """Test successful user name resolution."""
        result = service.resolve_user_name("U123456")
        
        assert result == "testuser"
        mock_slack_client.users_info.assert_called_once_with(user="U123456")
    
    def test_resolve_user_name_cached(self, service, mock_slack_client):
        """Test that user name is cached."""
        # First call
        result1 = service.resolve_user_name("U123456")
        # Second call should use cache
        result2 = service.resolve_user_name("U123456")
        
        assert result1 == result2
        # Should only call API once
        assert mock_slack_client.users_info.call_count == 1
    
    def test_resolve_user_name_failure(self, service, mock_slack_client):
        """Test user name resolution failure."""
        mock_slack_client.users_info.side_effect = Exception("API Error")
        
        result = service.resolve_user_name("U123456")
        
        # Should return user ID as fallback
        assert result == "U123456"
    
    def test_resolve_channel_name_success(self, service, mock_slack_client):
        """Test successful channel name resolution."""
        result = service.resolve_channel_name("C123456")
        
        assert result == "test-channel"
        mock_slack_client.conversations_info.assert_called_once_with(channel="C123456")


class TestClearCache:
    """Tests for clear_cache method."""
    
    def test_clear_cache(self, service, mock_slack_client):
        """Test clearing name cache."""
        # Populate cache
        service.resolve_user_name("U123456")
        
        # Clear cache
        service.clear_cache()
        
        # Next call should hit API again
        service.resolve_user_name("U123456")
        
        assert mock_slack_client.users_info.call_count == 2
