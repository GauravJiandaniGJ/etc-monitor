"""Integration tests for database layer.

Tests DBManager, ReminderRepository, and AuditRepository with real in-memory SQLite database.
"""
import pytest
from datetime import datetime, timedelta
from src.core.models import Reminder, ReminderStatus, AuditLog, AuditAction
from src.utils.timezone import now_ist


@pytest.mark.integration
class TestDBManager:
    """Integration tests for DBManager."""
    
    def test_execute_query(self, db_manager):
        """Test executing a query."""
        db_manager.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, name TEXT)")
        db_manager.execute("INSERT INTO test (name) VALUES (?)", ("test_value",))
        
        result = db_manager.fetch_one("SELECT name FROM test WHERE id = 1")
        assert result is not None
        assert result[0] == "test_value"
    
    def test_fetch_all(self, db_manager):
        """Test fetching all rows."""
        db_manager.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, name TEXT)")
        db_manager.execute("INSERT INTO test (name) VALUES (?)", ("value1",))
        db_manager.execute("INSERT INTO test (name) VALUES (?)", ("value2",))
        
        results = db_manager.fetch_all("SELECT name FROM test")
        assert len(results) == 2
    
    def test_table_exists(self, db_manager):
        """Test checking if table exists."""
        # reminders table should exist from migrations
        assert db_manager.table_exists("reminders") is True
        assert db_manager.table_exists("nonexistent_table") is False


@pytest.mark.integration
class TestReminderRepository:
    """Integration tests for ReminderRepository."""
    
    def test_create_reminder(self, reminder_repo, sample_reminder):
        """Test creating a reminder."""
        reminder = sample_reminder()
        
        reminder_id = reminder_repo.create(reminder)
        
        assert reminder_id is not None
        assert reminder_id > 0
    
    def test_get_by_id(self, reminder_repo, sample_reminder):
        """Test getting reminder by ID."""
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        retrieved = reminder_repo.get_by_id(reminder_id)
        
        assert retrieved is not None
        assert retrieved.id == reminder_id
        assert retrieved.channel_id == reminder.channel_id
        assert retrieved.user_id == reminder.user_id
    
    def test_get_by_composite_key(self, reminder_repo, sample_reminder):
        """Test getting reminder by composite key."""
        reminder = sample_reminder()
        reminder_repo.create(reminder)
        
        retrieved = reminder_repo.get_by_composite_key(
            reminder.channel_id,
            reminder.thread_ts,
            reminder.user_id
        )
        
        assert retrieved is not None
        assert retrieved.channel_id == reminder.channel_id
    
    def test_update_reminder(self, reminder_repo, sample_reminder):
        """Test updating a reminder."""
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        # Update fields
        reminder.id = reminder_id
        reminder.deadline_text = "3 hours"
        
        success = reminder_repo.update(reminder)
        
        assert success is True
        
        # Verify update
        retrieved = reminder_repo.get_by_id(reminder_id)
        assert retrieved.deadline_text == "3 hours"
    
    def test_update_status(self, reminder_repo, sample_reminder):
        """Test updating reminder status."""
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        success = reminder_repo.update_status(reminder_id, ReminderStatus.SENT)
        
        assert success is True
        
        # Verify status change
        retrieved = reminder_repo.get_by_id(reminder_id)
        assert retrieved.status == ReminderStatus.SENT
    
    def test_reschedule_reminder(self, reminder_repo, sample_reminder):
        """Test rescheduling a reminder."""
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        new_deadline = now_ist() + timedelta(hours=3)
        new_reminder_time = new_deadline
        
        success = reminder_repo.reschedule(
            reminder_id,
            new_deadline,
            new_reminder_time,
            "3 hours"
        )
        
        assert success is True
        
        # Verify reschedule
        retrieved = reminder_repo.get_by_id(reminder_id)
        assert retrieved.deadline_text == "3 hours"
        assert retrieved.status == ReminderStatus.RESCHEDULED
    
    def test_delete_reminder(self, reminder_repo, sample_reminder):
        """Test deleting a reminder."""
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        success = reminder_repo.delete(reminder_id)
        
        assert success is True
        
        # Verify deletion
        retrieved = reminder_repo.get_by_id(reminder_id)
        assert retrieved is None
    
    def test_get_pending_reminders(self, reminder_repo, sample_reminder):
        """Test getting pending reminders."""
        # Create pending reminder
        reminder1 = sample_reminder(status=ReminderStatus.PENDING)
        reminder_repo.create(reminder1)
        
        # Create sent reminder
        reminder2 = sample_reminder(
            message_ts="9999999999.999999",
            status=ReminderStatus.SENT
        )
        reminder_repo.create(reminder2)
        
        pending = reminder_repo.get_pending()
        
        # Should only return pending
        assert len(pending) >= 1
        assert all(r.status == ReminderStatus.PENDING for r in pending)
    
    def test_get_due_reminders(self, reminder_repo, sample_reminder):
        """Test getting due reminders."""
        # Create reminder due in past
        past_time = now_ist() - timedelta(hours=1)
        reminder1 = sample_reminder(
            deadline_datetime=past_time,
            reminder_datetime=past_time
        )
        reminder_repo.create(reminder1)
        
        # Create reminder due in future
        future_time = now_ist() + timedelta(hours=2)
        reminder2 = sample_reminder(
            message_ts="9999999999.999999",
            deadline_datetime=future_time,
            reminder_datetime=future_time
        )
        reminder_repo.create(reminder2)
        
        due = reminder_repo.get_due(threshold=now_ist())
        
        # Should only return past reminder
        assert len(due) >= 1
    
    def test_find_existing_active(self, reminder_repo, sample_reminder):
        """Test finding existing active reminder."""
        reminder = sample_reminder()
        reminder_repo.create(reminder)
        
        found = reminder_repo.find_existing_active(
            reminder.channel_id,
            reminder.thread_ts,
            reminder.user_id
        )
        
        assert found is not None
        assert found.channel_id == reminder.channel_id


@pytest.mark.integration
class TestAuditRepository:
    """Integration tests for AuditRepository."""
    
    def test_log_audit(self, audit_repo, reminder_repo, sample_reminder, sample_audit_log):
        """Test logging an audit entry."""
        # Create reminder first
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        # Log audit
        audit = sample_audit_log(reminder_id=reminder_id)
        audit_id = audit_repo.log(audit)
        
        assert audit_id is not None
        assert audit_id > 0
    
    def test_get_by_reminder(self, audit_repo, reminder_repo, sample_reminder, sample_audit_log):
        """Test getting audit logs by reminder ID."""
        # Create reminder
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        # Log multiple audits
        audit1 = sample_audit_log(reminder_id=reminder_id, action=AuditAction.CREATED)
        audit2 = sample_audit_log(reminder_id=reminder_id, action=AuditAction.UPDATED)
        audit_repo.log(audit1)
        audit_repo.log(audit2)
        
        # Get audits
        audits = audit_repo.get_by_reminder(reminder_id)
        
        assert len(audits) >= 2
        assert all(a.reminder_id == reminder_id for a in audits)
    
    def test_get_recent(self, audit_repo, reminder_repo, sample_reminder, sample_audit_log):
        """Test getting recent audit logs."""
        # Create reminder
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        # Log audit
        audit = sample_audit_log(reminder_id=reminder_id)
        audit_repo.log(audit)
        
        # Get recent
        recent = audit_repo.get_recent(limit=10)
        
        assert len(recent) >= 1
    
    def test_get_by_action(self, audit_repo, reminder_repo, sample_reminder, sample_audit_log):
        """Test getting audit logs by action."""
        # Create reminder
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        # Log with specific action
        audit = sample_audit_log(reminder_id=reminder_id, action=AuditAction.CANCELLED)
        audit_repo.log(audit)
        
        # Get by action
        audits = audit_repo.get_by_action(AuditAction.CANCELLED)
        
        assert len(audits) >= 1
        assert all(a.action == AuditAction.CANCELLED for a in audits)
