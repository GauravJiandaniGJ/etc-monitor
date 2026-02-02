"""Tests for DailySummaryService."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from src.services.daily_summary_service import DailySummaryService
from src.core.models import Reminder, ReminderStatus
from src.utils.timezone import now_ist


class TestDailySummaryService:
    """Test cases for DailySummaryService."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_reminder_repo = Mock()
        self.mock_notification_service = Mock()
        self.service = DailySummaryService(
            self.mock_reminder_repo,
            self.mock_notification_service
        )

    def _create_reminder(
        self,
        user_id: str = 'U123',
        deadline_days_offset: int = 0,
        status: ReminderStatus = ReminderStatus.PENDING,
        task_desc: str = 'Test task'
    ) -> Reminder:
        """Helper to create test reminder."""
        now = now_ist()
        deadline = now + timedelta(days=deadline_days_offset)

        reminder = Reminder(
            channel_id='C123',
            thread_ts='1234567890.123456',
            user_id=user_id,
            message_ts='1234567890.123457',
            deadline_text='test',
            deadline_datetime=deadline,
            reminder_datetime=deadline - timedelta(hours=1),
            original_message=task_desc,
            status=status
        )
        return reminder

    def test_generate_summary_with_all_sections(self):
        """Test summary generation with tasks in all three sections."""
        # Arrange
        yesterday_reminder = self._create_reminder(
            deadline_days_offset=-1,
            task_desc='Yesterday task'
        )
        today_reminder = self._create_reminder(
            deadline_days_offset=0,
            task_desc='Today task'
        )
        tomorrow_reminder = self._create_reminder(
            deadline_days_offset=1,
            task_desc='Tomorrow task'
        )

        self.mock_reminder_repo.get_by_user_and_date_range.return_value = [
            yesterday_reminder,
            today_reminder,
            tomorrow_reminder
        ]

        # Act
        message = self.service.generate_summary_for_user('U123')

        # Assert
        assert "📝 *Your ETC Summary*" in message
        assert "⚠️ *Yesterday's ETCs (Missed)*:" in message
        assert "Yesterday task" in message
        assert "📅 *Today's ETCs*:" in message
        assert "Today task" in message
        assert "🔜 *Tomorrow's ETCs*:" in message
        assert "Tomorrow task" in message

    def test_generate_summary_with_no_tasks(self):
        """Test summary when user has no pending tasks."""
        # Arrange
        self.mock_reminder_repo.get_by_user_and_date_range.return_value = []

        # Act
        message = self.service.generate_summary_for_user('U123')

        # Assert
        assert "✨ No pending ETCs" in message

    def test_generate_summary_excludes_cancelled_and_confirmed(self):
        """Test that cancelled and confirmed reminders are excluded."""
        # Arrange
        pending = self._create_reminder(status=ReminderStatus.PENDING)
        cancelled = self._create_reminder(status=ReminderStatus.CANCELLED)
        confirmed = self._create_reminder(status=ReminderStatus.CONFIRMED)

        self.mock_reminder_repo.get_by_user_and_date_range.return_value = [pending]

        # Act
        message = self.service.generate_summary_for_user('U123')

        # Assert
        # Verify that get_by_user_and_date_range was called with exclude_statuses
        call_args = self.mock_reminder_repo.get_by_user_and_date_range.call_args
        exclude_statuses = call_args.kwargs.get('exclude_statuses', [])
        assert ReminderStatus.CANCELLED in exclude_statuses
        assert ReminderStatus.CONFIRMED in exclude_statuses

    def test_send_summary_success(self):
        """Test successful summary sending."""
        # Arrange
        self.mock_reminder_repo.get_by_user_and_date_range.return_value = [
            self._create_reminder()
        ]
        self.mock_notification_service.send_dm.return_value = True

        # Act
        result = self.service.send_summary_to_user('U123')

        # Assert
        assert result is True
        self.mock_notification_service.send_dm.assert_called_once()
        call_args = self.mock_notification_service.send_dm.call_args
        assert call_args[0][0] == 'U123'  # user_id
        assert isinstance(call_args[0][1], str)  # message

    def test_send_summary_failure(self):
        """Test summary sending failure."""
        # Arrange
        self.mock_reminder_repo.get_by_user_and_date_range.return_value = []
        self.mock_notification_service.send_dm.return_value = False

        # Act
        result = self.service.send_summary_to_user('U123')

        # Assert
        assert result is False

    def test_send_summaries_to_multiple_users(self):
        """Test sending summaries to all users."""
        # Arrange
        reminder1 = self._create_reminder(user_id='U111')
        reminder2 = self._create_reminder(user_id='U222')
        reminder3 = self._create_reminder(user_id='U111')  # Same user

        self.mock_reminder_repo.get_pending.return_value = [
            reminder1, reminder2, reminder3
        ]
        self.mock_reminder_repo.get_by_user_and_date_range.return_value = []
        self.mock_notification_service.send_dm.return_value = True

        # Act
        results = self.service.send_summaries_to_all_users()

        # Assert
        assert len(results) == 2  # Only 2 unique users
        assert 'U111' in results
        assert 'U222' in results


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
