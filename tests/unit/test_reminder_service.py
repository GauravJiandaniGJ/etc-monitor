"""Unit tests for src/services/reminder_service.py

Tests the reminder business logic service with mocked repositories.
"""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta
from src.services.reminder_service import ReminderService
from src.core.models import Reminder, ReminderStatus, AuditAction, ReminderContext, ParsedDeadline
from src.utils.timezone import now_ist


@pytest.fixture
def mock_reminder_repo():
    """Create a mocked ReminderRepository."""
    return Mock()


@pytest.fixture
def mock_audit_repo():
    """Create a mocked AuditRepository."""
    return Mock()


@pytest.fixture
def mock_scheduler():
    """Create a mocked ReminderScheduler."""
    return Mock()


@pytest.fixture
def service(mock_reminder_repo, mock_audit_repo, mock_scheduler):
    """Create ReminderService with mocked dependencies."""
    return ReminderService(
        reminder_repo=mock_reminder_repo,
        audit_repo=mock_audit_repo,
        scheduler=mock_scheduler
    )


class TestCreateOrUpdate:
    """Tests for create_or_update method."""
    
    def test_create_new_reminder(self, service, mock_reminder_repo, mock_audit_repo, sample_context, sample_deadline):
        """Test creating a new reminder."""
        context = sample_context()
        deadline = sample_deadline()
        
        # No existing reminder
        mock_reminder_repo.find_existing_active.return_value = None
        mock_reminder_repo.create.return_value = 1
        
        reminder_id = service.create_or_update(context, deadline)
        
        assert reminder_id == 1
        mock_reminder_repo.create.assert_called_once()
        mock_audit_repo.log.assert_called_once()
    
    def test_update_existing_reminder(self, service, mock_reminder_repo, mock_audit_repo, sample_context, sample_deadline, sample_reminder):
        """Test updating an existing reminder."""
        context = sample_context()
        deadline = sample_deadline()
        existing = sample_reminder(id=1)
        
        # Existing reminder found
        mock_reminder_repo.find_existing_active.return_value = existing
        mock_reminder_repo.reschedule.return_value = True
        
        reminder_id = service.create_or_update(context, deadline)
        
        assert reminder_id == 1
        mock_reminder_repo.reschedule.assert_called_once()
        mock_audit_repo.log.assert_called_once()


class TestCancel:
    """Tests for cancel method."""
    
    def test_cancel_success(self, service, mock_reminder_repo, mock_audit_repo, mock_scheduler):
        """Test successful reminder cancellation."""
        mock_reminder_repo.update_status.return_value = True
        
        result = service.cancel(reminder_id=1, cancelled_by="U123456")
        
        assert result is True
        mock_reminder_repo.update_status.assert_called_once_with(1, ReminderStatus.CANCELLED)
        mock_audit_repo.log.assert_called_once()
        mock_scheduler.cancel.assert_called_once()
    
    def test_cancel_failure(self, service, mock_reminder_repo):
        """Test cancellation failure."""
        mock_reminder_repo.update_status.return_value = False
        
        result = service.cancel(reminder_id=1, cancelled_by="U123456")
        
        assert result is False


class TestMarkSent:
    """Tests for mark_sent method."""
    
    def test_mark_sent_success(self, service, mock_reminder_repo, mock_audit_repo):
        """Test marking reminder as sent."""
        mock_reminder_repo.update_status.return_value = True
        
        result = service.mark_sent(reminder_id=1)
        
        assert result is True
        mock_reminder_repo.update_status.assert_called_once_with(1, ReminderStatus.SENT)
        mock_audit_repo.log.assert_called_once()


class TestMarkFailed:
    """Tests for mark_failed method."""
    
    def test_mark_failed_success(self, service, mock_reminder_repo, mock_audit_repo):
        """Test marking reminder as failed."""
        mock_reminder_repo.update_status.return_value = True
        
        result = service.mark_failed(reminder_id=1, error_message="Test error")
        
        assert result is True
        mock_reminder_repo.update_status.assert_called_once_with(1, ReminderStatus.FAILED)
        mock_audit_repo.log.assert_called_once()


class TestQueryMethods:
    """Tests for query methods."""
    
    def test_get_user_reminders(self, service, mock_reminder_repo, sample_reminder):
        """Test getting user reminders."""
        mock_reminder_repo.get_by_user.return_value = [sample_reminder()]
        
        result = service.get_user_reminders("U123456")
        
        assert len(result) == 1
        mock_reminder_repo.get_by_user.assert_called_once_with("U123456")
    
    def test_get_pending_reminders(self, service, mock_reminder_repo, sample_reminder):
        """Test getting pending reminders."""
        mock_reminder_repo.get_pending.return_value = [sample_reminder()]
        
        result = service.get_pending_reminders()
        
        assert len(result) == 1
        mock_reminder_repo.get_pending.assert_called_once()
