"""Unit tests for src/bot/handlers/command_handler.py

Tests the Slack command handler with mocked services.
"""
import pytest
from unittest.mock import Mock
from src.bot.handlers.command_handler import CommandHandler


@pytest.fixture
def mock_services():
    """Create mocked services."""
    return {
        'reminder_service': Mock(),
        'notification_service': Mock()
    }


@pytest.fixture
def handler(mock_services):
    """Create CommandHandler with mocked services."""
    return CommandHandler(
        reminder_service=mock_services['reminder_service'],
        notification_service=mock_services['notification_service']
    )


class TestHandleMyReminders:
    """Tests for handle_my_reminders command."""
    
    def test_lists_user_reminders(self, handler, mock_services, sample_reminder):
        """Test listing user's reminders."""
        ack = Mock()
        respond = Mock()
        command = {
            'user_id': 'U123456',
            'text': ''
        }
        
        mock_services['reminder_service'].get_user_reminders.return_value = [
            sample_reminder(id=1),
            sample_reminder(id=2)
        ]
        
        handler.handle_my_reminders(ack=ack, respond=respond, command=command)
        
        ack.assert_called_once()
        respond.assert_called_once()
        mock_services['reminder_service'].get_user_reminders.assert_called_once_with('U123456')
    
    def test_no_reminders_message(self, handler, mock_services):
        """Test message when user has no reminders."""
        ack = Mock()
        respond = Mock()
        command = {
            'user_id': 'U123456',
            'text': ''
        }
        
        mock_services['reminder_service'].get_user_reminders.return_value = []
        
        handler.handle_my_reminders(ack=ack, respond=respond, command=command)
        
        ack.assert_called_once()
        respond.assert_called_once()


class TestHandleCancelReminder:
    """Tests for handle_cancel_reminder command."""
    
    def test_cancel_with_valid_id(self, handler, mock_services):
        """Test cancelling reminder with valid ID."""
        ack = Mock()
        respond = Mock()
        command = {
            'user_id': 'U123456',
            'text': '123'
        }
        
        mock_services['reminder_service'].cancel.return_value = True
        
        handler.handle_cancel_reminder(ack=ack, respond=respond, command=command)
        
        ack.assert_called_once()
        respond.assert_called_once()
        mock_services['reminder_service'].cancel.assert_called_once_with(123, 'U123456')
    
    def test_cancel_with_invalid_id(self, handler, mock_services):
        """Test cancelling with invalid ID."""
        ack = Mock()
        respond = Mock()
        command = {
            'user_id': 'U123456',
            'text': 'invalid'
        }
        
        handler.handle_cancel_reminder(ack=ack, respond=respond, command=command)
        
        ack.assert_called_once()
        respond.assert_called_once()
        # Should not call cancel with invalid ID
        mock_services['reminder_service'].cancel.assert_not_called()
    
    def test_cancel_with_missing_id(self, handler, mock_services):
        """Test cancelling without providing ID."""
        ack = Mock()
        respond = Mock()
        command = {
            'user_id': 'U123456',
            'text': ''
        }
        
        handler.handle_cancel_reminder(ack=ack, respond=respond, command=command)
        
        ack.assert_called_once()
        respond.assert_called_once()
        mock_services['reminder_service'].cancel.assert_not_called()


class TestHandleTriggerEod:
    """/trigger-eod posts Slack follow-ups, so only listed admins may run it."""

    def _run(self, handler, user_id):
        ack, respond = Mock(), Mock()
        handler.handle_trigger_eod(ack, respond, {'user_id': user_id, 'text': ''})
        ack.assert_called_once()
        return respond

    def test_refuses_a_user_who_is_not_listed(self, handler, mock_services, monkeypatch):
        monkeypatch.setenv('ADMIN_SLACK_USER_IDS', 'UADMIN1,UADMIN2')
        respond = self._run(handler, 'USOMEONE')
        mock_services['reminder_service'].process_eod_followups.assert_not_called()
        assert 'only' in respond.call_args[0][0].lower()

    def test_refuses_everyone_when_no_admins_are_configured(self, handler, mock_services, monkeypatch):
        monkeypatch.delenv('ADMIN_SLACK_USER_IDS', raising=False)
        self._run(handler, 'UADMIN1')
        mock_services['reminder_service'].process_eod_followups.assert_not_called()

    def test_runs_for_a_listed_admin(self, handler, mock_services, monkeypatch):
        monkeypatch.setenv('ADMIN_SLACK_USER_IDS', ' UADMIN1 , UADMIN2 ')
        mock_services['reminder_service'].process_eod_followups.return_value = 2
        respond = self._run(handler, 'UADMIN2')
        mock_services['reminder_service'].process_eod_followups.assert_called_once_with(
            mock_services['notification_service'])
        assert 'Sent 2 follow-up(s)' in respond.call_args[0][0]

    def test_error_reply_does_not_leak_internal_details(self, handler, mock_services, monkeypatch):
        monkeypatch.setenv('ADMIN_SLACK_USER_IDS', 'UADMIN1')
        mock_services['reminder_service'].process_eod_followups.side_effect = RuntimeError('db password=secret')
        respond = self._run(handler, 'UADMIN1')
        assert 'secret' not in respond.call_args[0][0]
