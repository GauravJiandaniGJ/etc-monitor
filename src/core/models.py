"""Core data models for ETC Monitor application."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class ReminderStatus(Enum):
    """Status of a reminder."""
    PENDING = 'pending'
    SENT = 'sent'
    CANCELLED = 'cancelled'
    FAILED = 'failed'
    RESCHEDULED = 'rescheduled'


class AuditAction(Enum):
    """Action types for audit logging."""
    CREATED = 'created'
    UPDATED = 'updated'
    RESCHEDULED = 'rescheduled'
    CANCELLED = 'cancelled'
    SENT = 'sent'
    FAILED = 'failed'
    DELETED = 'deleted'


@dataclass
class Reminder:
    """Reminder data model.
    
    Represents a scheduled reminder for an ETC deadline in a Slack thread.
    """
    channel_id: str
    thread_ts: str
    user_id: str
    message_ts: str
    deadline_text: str
    deadline_datetime: datetime
    reminder_datetime: datetime
    id: Optional[int] = None
    original_message: Optional[str] = None
    status: ReminderStatus = ReminderStatus.PENDING
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    retry_count: int = 0
    reschedule_count: int = 0
    previous_deadline: Optional[datetime] = None
    
    @property
    def composite_key(self) -> str:
        """Returns unique identifier for this reminder context.
        
        Returns:
            Composite key string (channel:thread:user)
        """
        return f"{self.channel_id}:{self.thread_ts}:{self.user_id}"
    
    @property
    def job_id(self) -> str:
        """Returns unique job ID for scheduler.
        
        Returns:
            Job ID for APScheduler
        """
        return f"reminder_{self.channel_id}_{self.thread_ts}_{self.user_id}"


@dataclass
class AuditLog:
    """Audit log entry for tracking reminder changes.
    
    Records all actions performed on reminders for tracking and debugging.
    """
    reminder_id: int
    action: AuditAction
    id: Optional[int] = None
    field_changed: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    performed_by: Optional[str] = None
    performed_at: Optional[datetime] = None
    metadata: Optional[dict] = None


@dataclass
class ReminderContext:
    """Context extracted from Slack message.
    
    Contains all information needed to create a reminder from a Slack message.
    """
    channel_id: str
    thread_ts: str
    user_id: str
    message_ts: str
    message_text: str


@dataclass 
class ParsedDeadline:
    """Result of deadline parsing.
    
    Contains the extracted deadline information and metadata about parsing.
    """
    original_text: str
    deadline_datetime: datetime
    reminder_datetime: datetime
    confidence: float = 1.0
    parsed_by: str = 'regex'  # 'regex' or 'ai'
