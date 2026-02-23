"""Unit tests for src/core/models.py

Tests all dataclasses and enums in the core models module.
"""
import pytest
from datetime import datetime
from src.core.models import (
    ReminderStatus,
    AuditAction,
    Reminder,
    AuditLog,
    ReminderContext,
    ParsedDeadline
)
from src.utils.timezone import now_ist


class TestEnums:
    """Tests for enum classes."""
    
    def test_reminder_status_values(self):
        """Test that ReminderStatus enum has correct values."""
        assert ReminderStatus.PENDING.value == 'pending'
        assert ReminderStatus.SENT.value == 'sent'
        assert ReminderStatus.CANCELLED.value == 'cancelled'
        assert ReminderStatus.FAILED.value == 'failed'
        assert ReminderStatus.RESCHEDULED.value == 'rescheduled'
    
    def test_audit_action_values(self):
        """Test that AuditAction enum has correct values."""
        assert AuditAction.CREATED.value == 'created'
        assert AuditAction.UPDATED.value == 'updated'
        assert AuditAction.RESCHEDULED.value == 'rescheduled'
        assert AuditAction.CANCELLED.value == 'cancelled'
        assert AuditAction.SENT.value == 'sent'
        assert AuditAction.FAILED.value == 'failed'
        assert AuditAction.DELETED.value == 'deleted'


class TestReminder:
    """Tests for Reminder dataclass."""
    
    def test_reminder_creation_with_required_fields(self):
        """Test creating Reminder with only required fields."""
        now = now_ist()
        
        reminder = Reminder(
            channel_id='C123456',
            thread_ts='1234567890.123456',
            user_id='U123456',
            message_ts='1234567890.654321',
            deadline_text='2 hours',
            deadline_datetime=now,
            reminder_datetime=now
        )
        
        assert reminder.channel_id == 'C123456'
        assert reminder.thread_ts == '1234567890.123456'
        assert reminder.user_id == 'U123456'
        assert reminder.message_ts == '1234567890.654321'
        assert reminder.deadline_text == '2 hours'
        assert reminder.deadline_datetime == now
        assert reminder.reminder_datetime == now
    
    def test_reminder_default_values(self):
        """Test that Reminder has correct default values."""
        now = now_ist()
        
        reminder = Reminder(
            channel_id='C123456',
            thread_ts='1234567890.123456',
            user_id='U123456',
            message_ts='1234567890.654321',
            deadline_text='2 hours',
            deadline_datetime=now,
            reminder_datetime=now
        )
        
        assert reminder.id is None
        assert reminder.original_message is None
        assert reminder.status == ReminderStatus.PENDING
        assert reminder.created_at is None
        assert reminder.updated_at is None
        assert reminder.sent_at is None
        assert reminder.retry_count == 0
        assert reminder.reschedule_count == 0
        assert reminder.previous_deadline is None
        assert reminder.reminder_sent_at is None
        assert reminder.last_user_update_at is None
        assert reminder.followup_sent_at is None
    
    def test_reminder_composite_key(self):
        """Test Reminder composite_key property."""
        now = now_ist()
        
        reminder = Reminder(
            channel_id='C123456',
            thread_ts='1234567890.123456',
            user_id='U123456',
            message_ts='1234567890.654321',
            deadline_text='2 hours',
            deadline_datetime=now,
            reminder_datetime=now
        )
        
        assert reminder.composite_key == 'C123456:1234567890.123456:U123456'
    
    def test_reminder_job_id(self):
        """Test Reminder job_id property."""
        now = now_ist()
        
        reminder = Reminder(
            channel_id='C123456',
            thread_ts='1234567890.123456',
            user_id='U123456',
            message_ts='1234567890.654321',
            deadline_text='2 hours',
            deadline_datetime=now,
            reminder_datetime=now
        )
        
        assert reminder.job_id == 'reminder_C123456_1234567890.123456_U123456'
    
    def test_reminder_with_all_fields(self):
        """Test creating Reminder with all fields populated."""
        now = now_ist()
        
        reminder = Reminder(
            id=1,
            channel_id='C123456',
            thread_ts='1234567890.123456',
            user_id='U123456',
            message_ts='1234567890.654321',
            deadline_text='2 hours',
            deadline_datetime=now,
            reminder_datetime=now,
            original_message='Test task ETC 2 hours',
            status=ReminderStatus.SENT,
            created_at=now,
            updated_at=now,
            sent_at=now,
            retry_count=1,
            reschedule_count=2,
            previous_deadline=now,
            reminder_sent_at=now,
            last_user_update_at=now,
            followup_sent_at=now
        )
        
        assert reminder.id == 1
        assert reminder.original_message == 'Test task ETC 2 hours'
        assert reminder.status == ReminderStatus.SENT
        assert reminder.retry_count == 1
        assert reminder.reschedule_count == 2


class TestAuditLog:
    """Tests for AuditLog dataclass."""
    
    def test_audit_log_creation_with_required_fields(self):
        """Test creating AuditLog with only required fields."""
        audit = AuditLog(
            reminder_id=1,
            action=AuditAction.CREATED
        )
        
        assert audit.reminder_id == 1
        assert audit.action == AuditAction.CREATED
    
    def test_audit_log_default_values(self):
        """Test that AuditLog has correct default values."""
        audit = AuditLog(
            reminder_id=1,
            action=AuditAction.CREATED
        )
        
        assert audit.id is None
        assert audit.field_changed is None
        assert audit.old_value is None
        assert audit.new_value is None
        assert audit.performed_by is None
        assert audit.performed_at is None
        assert audit.metadata is None
    
    def test_audit_log_with_all_fields(self):
        """Test creating AuditLog with all fields populated."""
        now = now_ist()
        metadata = {'reason': 'test'}
        
        audit = AuditLog(
            id=1,
            reminder_id=2,
            action=AuditAction.UPDATED,
            field_changed='deadline_datetime',
            old_value='2026-02-16 14:00:00',
            new_value='2026-02-16 16:00:00',
            performed_by='U123456',
            performed_at=now,
            metadata=metadata
        )
        
        assert audit.id == 1
        assert audit.reminder_id == 2
        assert audit.action == AuditAction.UPDATED
        assert audit.field_changed == 'deadline_datetime'
        assert audit.old_value == '2026-02-16 14:00:00'
        assert audit.new_value == '2026-02-16 16:00:00'
        assert audit.performed_by == 'U123456'
        assert audit.performed_at == now
        assert audit.metadata == metadata


class TestReminderContext:
    """Tests for ReminderContext dataclass."""
    
    def test_reminder_context_creation(self):
        """Test creating ReminderContext with all required fields."""
        context = ReminderContext(
            channel_id='C123456',
            thread_ts='1234567890.123456',
            user_id='U123456',
            message_ts='1234567890.654321',
            message_text='Test task ETC 2 hours'
        )
        
        assert context.channel_id == 'C123456'
        assert context.thread_ts == '1234567890.123456'
        assert context.user_id == 'U123456'
        assert context.message_ts == '1234567890.654321'
        assert context.message_text == 'Test task ETC 2 hours'


class TestParsedDeadline:
    """Tests for ParsedDeadline dataclass."""
    
    def test_parsed_deadline_creation_with_required_fields(self):
        """Test creating ParsedDeadline with only required fields."""
        now = now_ist()
        
        deadline = ParsedDeadline(
            original_text='2 hours',
            deadline_datetime=now,
            reminder_datetime=now
        )
        
        assert deadline.original_text == '2 hours'
        assert deadline.deadline_datetime == now
        assert deadline.reminder_datetime == now
    
    def test_parsed_deadline_default_values(self):
        """Test that ParsedDeadline has correct default values."""
        now = now_ist()
        
        deadline = ParsedDeadline(
            original_text='2 hours',
            deadline_datetime=now,
            reminder_datetime=now
        )
        
        assert deadline.confidence == 1.0
        assert deadline.parsed_by == 'regex'
    
    def test_parsed_deadline_with_ai_parser(self):
        """Test creating ParsedDeadline from AI parser."""
        now = now_ist()
        
        deadline = ParsedDeadline(
            original_text='finish this by tomorrow afternoon',
            deadline_datetime=now,
            reminder_datetime=now,
            confidence=0.85,
            parsed_by='ai'
        )
        
        assert deadline.confidence == 0.85
        assert deadline.parsed_by == 'ai'
    
    def test_parsed_deadline_with_low_confidence(self):
        """Test creating ParsedDeadline with low confidence."""
        now = now_ist()
        
        deadline = ParsedDeadline(
            original_text='maybe sometime next week',
            deadline_datetime=now,
            reminder_datetime=now,
            confidence=0.3,
            parsed_by='ai'
        )
        
        assert deadline.confidence == 0.3
