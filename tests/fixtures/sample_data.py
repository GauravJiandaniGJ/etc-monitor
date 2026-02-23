"""Sample data factory functions for tests.

Provides reusable factory functions for creating test data objects
with sensible defaults.
"""
from datetime import datetime, timedelta
from typing import Optional
from src.core.models import (
    Reminder,
    ReminderContext,
    ParsedDeadline,
    AuditLog,
    ReminderStatus,
    AuditAction
)
from src.utils.timezone import now_ist


def create_sample_reminder(
    channel_id: str = "C123456",
    thread_ts: str = "1234567890.123456",
    user_id: str = "U123456",
    message_ts: str = "1234567890.654321",
    deadline_text: str = "2 hours",
    deadline_datetime: Optional[datetime] = None,
    reminder_datetime: Optional[datetime] = None,
    **kwargs
) -> Reminder:
    """Create a sample Reminder object with sensible defaults.
    
    Args:
        channel_id: Slack channel ID
        thread_ts: Thread timestamp
        user_id: User ID
        message_ts: Message timestamp
        deadline_text: Deadline text
        deadline_datetime: Deadline datetime (defaults to 2 hours from now)
        reminder_datetime: Reminder datetime (defaults to same as deadline)
        **kwargs: Additional fields to override
        
    Returns:
        Reminder object
    """
    if deadline_datetime is None:
        deadline_datetime = now_ist() + timedelta(hours=2)
    
    if reminder_datetime is None:
        reminder_datetime = deadline_datetime
    
    defaults = {
        'channel_id': channel_id,
        'thread_ts': thread_ts,
        'user_id': user_id,
        'message_ts': message_ts,
        'deadline_text': deadline_text,
        'deadline_datetime': deadline_datetime,
        'reminder_datetime': reminder_datetime,
        'original_message': 'Test task ETC 2 hours',
        'status': ReminderStatus.PENDING,
        'created_at': now_ist(),
        'updated_at': now_ist(),
    }
    
    # Override with any provided kwargs
    defaults.update(kwargs)
    
    return Reminder(**defaults)


def create_sample_context(
    channel_id: str = "C123456",
    thread_ts: str = "1234567890.123456",
    user_id: str = "U123456",
    message_ts: str = "1234567890.654321",
    message_text: str = "Test task ETC 2 hours",
    **kwargs
) -> ReminderContext:
    """Create a sample ReminderContext object.
    
    Args:
        channel_id: Slack channel ID
        thread_ts: Thread timestamp
        user_id: User ID
        message_ts: Message timestamp
        message_text: Message text
        **kwargs: Additional fields to override
        
    Returns:
        ReminderContext object
    """
    defaults = {
        'channel_id': channel_id,
        'thread_ts': thread_ts,
        'user_id': user_id,
        'message_ts': message_ts,
        'message_text': message_text,
    }
    
    defaults.update(kwargs)
    
    return ReminderContext(**defaults)


def create_sample_deadline(
    original_text: str = "2 hours",
    deadline_datetime: Optional[datetime] = None,
    reminder_datetime: Optional[datetime] = None,
    confidence: float = 1.0,
    parsed_by: str = 'regex',
    **kwargs
) -> ParsedDeadline:
    """Create a sample ParsedDeadline object.
    
    Args:
        original_text: Original deadline text
        deadline_datetime: Deadline datetime (defaults to 2 hours from now)
        reminder_datetime: Reminder datetime (defaults to same as deadline)
        confidence: Parsing confidence (0.0-1.0)
        parsed_by: Parser used ('regex' or 'ai')
        **kwargs: Additional fields to override
        
    Returns:
        ParsedDeadline object
    """
    if deadline_datetime is None:
        deadline_datetime = now_ist() + timedelta(hours=2)
    
    if reminder_datetime is None:
        reminder_datetime = deadline_datetime
    
    defaults = {
        'original_text': original_text,
        'deadline_datetime': deadline_datetime,
        'reminder_datetime': reminder_datetime,
        'confidence': confidence,
        'parsed_by': parsed_by,
    }
    
    defaults.update(kwargs)
    
    return ParsedDeadline(**defaults)


def create_sample_audit_log(
    reminder_id: int = 1,
    action: AuditAction = AuditAction.CREATED,
    field_changed: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    performed_by: str = "U123456",
    performed_at: Optional[datetime] = None,
    **kwargs
) -> AuditLog:
    """Create a sample AuditLog object.
    
    Args:
        reminder_id: Reminder ID
        action: Action performed
        field_changed: Field that was changed
        old_value: Old value
        new_value: New value
        performed_by: User who performed the action
        performed_at: When the action was performed
        **kwargs: Additional fields to override
        
    Returns:
        AuditLog object
    """
    if performed_at is None:
        performed_at = now_ist()
    
    defaults = {
        'reminder_id': reminder_id,
        'action': action,
        'field_changed': field_changed,
        'old_value': old_value,
        'new_value': new_value,
        'performed_by': performed_by,
        'performed_at': performed_at,
    }
    
    defaults.update(kwargs)
    
    return AuditLog(**defaults)
