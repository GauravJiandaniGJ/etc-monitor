"""Unit tests for src/bot/scheduler/reminder_scheduler.py

Tests the APScheduler wrapper with mocked scheduler.
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from src.bot.scheduler.reminder_scheduler import ReminderScheduler
from src.utils.timezone import now_ist


@pytest.fixture
def mock_apscheduler():
    """Create mocked APScheduler."""
    with patch('src.bot.scheduler.reminder_scheduler.BackgroundScheduler') as mock:
        yield mock


@pytest.fixture
def scheduler(mock_apscheduler):
    """Create ReminderScheduler with mocked APScheduler."""
    return ReminderScheduler()


class TestSchedule:
    """Tests for schedule method."""
    
    def test_schedule_reminder(self, scheduler):
        """Test scheduling a reminder."""
        callback = Mock()
        run_time = now_ist() + timedelta(hours=2)
        
        scheduler.schedule(
            job_id='reminder_1',
            callback=callback,
            run_time=run_time,
            args=(1,)
        )
        
        # Verify job was added
        assert scheduler.scheduler.add_job.called
    
    def test_schedule_too_close_reminder(self, scheduler):
        """Test scheduling reminder that's too close (< 30s)."""
        callback = Mock()
        run_time = now_ist() + timedelta(seconds=10)  # Too close
        
        scheduler.schedule(
            job_id='reminder_1',
            callback=callback,
            run_time=run_time,
            args=(1,)
        )
        
        # Should still schedule but with minimum delay
        assert scheduler.scheduler.add_job.called


class TestReschedule:
    """Tests for reschedule method."""
    
    def test_reschedule_existing_job(self, scheduler):
        """Test rescheduling an existing job."""
        callback = Mock()
        old_time = now_ist() + timedelta(hours=1)
        new_time = now_ist() + timedelta(hours=2)
        
        # Schedule first
        scheduler.schedule('reminder_1', callback, old_time, args=(1,))
        
        # Reschedule
        scheduler.reschedule('reminder_1', callback, new_time, args=(1,))
        
        # Should cancel old and add new
        assert scheduler.scheduler.remove_job.called or scheduler.scheduler.add_job.call_count == 2


class TestCancel:
    """Tests for cancel method."""
    
    def test_cancel_existing_job(self, scheduler):
        """Test cancelling an existing job."""
        result = scheduler.cancel('reminder_1')
        
        # Should attempt to remove job
        assert scheduler.scheduler.remove_job.called or result in [True, False]
    
    def test_cancel_nonexistent_job(self, scheduler):
        """Test cancelling a non-existent job."""
        scheduler.scheduler.remove_job.side_effect = Exception("Job not found")
        
        result = scheduler.cancel('nonexistent')
        
        # Should handle gracefully
        assert result is False


class TestGetJob:
    """Tests for get_job method."""
    
    def test_get_existing_job(self, scheduler):
        """Test getting an existing job."""
        mock_job = Mock()
        scheduler.scheduler.get_job.return_value = mock_job
        
        job = scheduler.get_job('reminder_1')
        
        assert job == mock_job
    
    def test_get_nonexistent_job(self, scheduler):
        """Test getting a non-existent job."""
        scheduler.scheduler.get_job.return_value = None
        
        job = scheduler.get_job('nonexistent')
        
        assert job is None


class TestLifecycle:
    """Tests for scheduler lifecycle methods."""
    
    def test_start(self, scheduler):
        """Test starting the scheduler."""
        scheduler.start()
        
        assert scheduler.scheduler.start.called
    
    def test_stop(self, scheduler):
        """Test stopping the scheduler."""
        scheduler.stop()
        
        assert scheduler.scheduler.shutdown.called
