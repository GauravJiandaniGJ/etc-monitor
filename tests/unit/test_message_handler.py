"""Unit tests for src/bot/handlers/message_handler.py

Tests the Slack message handler with mocked services.
"""
import pytest
from unittest.mock import Mock, AsyncMock
from src.bot.handlers.message_handler import MessageHandler


@pytest.fixture
def mock_services():
    """Create mocked services."""
    return {
        'deadline_service': Mock(),
        'reminder_service': Mock(),
        'notification_service': Mock(),
        'scheduler': Mock()
    }


@pytest.fixture
def handler(mock_services):
    """Create MessageHandler with mocked services."""
    return MessageHandler(
        deadline_service=mock_services['deadline_service'],
        reminder_service=mock_services['reminder_service'],
        notification_service=mock_services['notification_service'],
        scheduler=mock_services['scheduler']
    )


class TestHandleMessage:
    """Tests for handle_message method."""
    
    def test_ignores_non_thread_messages(self, handler, mock_services):
        """Test that non-thread messages are ignored."""
        message = {
            'text': 'Hello',
            'user': 'U123456',
            'ts': '1234567890.123456'
            # No thread_ts
        }
        
        handler.handle_message(message=message, say=Mock())
        
        # Should not call deadline service
        mock_services['deadline_service'].detect.assert_not_called()
    
    def test_ignores_bot_messages(self, handler, mock_services):
        """Test that bot messages are ignored."""
        message = {
            'text': 'Hello',
            'user': 'U123456',
            'ts': '1234567890.123456',
            'thread_ts': '1234567890.000000',
            'subtype': 'bot_message'
        }
        
        handler.handle_message(message=message, say=Mock())
        
        mock_services['deadline_service'].detect.assert_not_called()
    
    def test_detects_etc_in_thread_reply(self, handler, mock_services, sample_deadline):
        """Test detecting ETC in thread reply."""
        message = {
            'text': 'Will finish ETC 2 hours',
            'user': 'U123456',
            'ts': '1234567890.123456',
            'thread_ts': '1234567890.000000',
            'channel': 'C123456'
        }
        
        # Mock deadline detection
        mock_services['deadline_service'].detect.return_value = sample_deadline()
        mock_services['reminder_service'].create_or_update.return_value = 1
        
        handler.handle_message(message=message, say=Mock())
        
        mock_services['deadline_service'].detect.assert_called_once()
        mock_services['reminder_service'].create_or_update.assert_called_once()


class TestSendReminderCallback:
    """Tests for _send_reminder_callback method."""
    
    def test_sends_reminder_and_marks_sent(self, handler, mock_services, sample_reminder):
        """Test successful reminder sending."""
        reminder = sample_reminder()
        
        mock_services['notification_service'].send_reminder.return_value = True
        
        handler._send_reminder_callback(reminder)
        
        mock_services['notification_service'].send_reminder.assert_called_once_with(reminder)
        mock_services['reminder_service'].mark_sent.assert_called_once_with(reminder.id)
    
    def test_marks_failed_on_send_error(self, handler, mock_services, sample_reminder):
        """Test marking reminder as failed on send error."""
        reminder = sample_reminder()
        
        mock_services['notification_service'].send_reminder.return_value = False
        
        handler._send_reminder_callback(reminder)
        
        mock_services['reminder_service'].mark_failed.assert_called_once()
