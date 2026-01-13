"""Reminder service for managing reminder business logic."""
from typing import List, Optional
from datetime import datetime
from src.core.models import Reminder, ReminderContext, ParsedDeadline, ReminderStatus, AuditLog, AuditAction
from src.database.repositories.reminder_repository import ReminderRepository
from src.database.repositories.audit_repository import AuditRepository
from src.utils.logger import get_logger
from src.utils.timezone import now_ist, format_datetime_friendly


logger = get_logger('ReminderService')


class ReminderService:
    """Service for reminder business logic.
    
    Handles create, update, reschedule, cancel operations with
    audit logging.
    """
    
    def __init__(
        self,
        reminder_repo: ReminderRepository,
        audit_repo: AuditRepository
    ):
        """Initialize reminder service.
        
        Args:
            reminder_repo: Reminder repository instance
            audit_repo: Audit repository instance
        """
        self.reminder_repo = reminder_repo
        self.audit_repo = audit_repo
        logger.info('Reminder service initialized')
    
    def create_or_update(
        self,
        context: ReminderContext,
        deadline: ParsedDeadline
    ) -> Reminder:
        """Create new reminder or update existing one.
        
        If an active reminder exists for the same user in the same thread,
        it will be rescheduled. Otherwise, a new reminder is created.
        
        Args:
            context: Reminder context from Slack message
            deadline: Parsed deadline information
            
        Returns:
            Created or updated Reminder object
        """
        logger.info(f'Creating or updating reminder for user {context.user_id} in thread {context.thread_ts}')
        
        # Check for existing active reminder
        existing = self.reminder_repo.find_existing_active(
            context.channel_id,
            context.thread_ts,
            context.user_id
        )
        
        if existing:
            # Reschedule existing reminder
            logger.info(f'Found existing reminder {existing.id}, rescheduling')
            return self._reschedule_reminder(existing, deadline, context)
        else:
            # Create new reminder
            logger.info('No existing reminder found, creating new')
            return self._create_new_reminder(context, deadline)
    
    def _create_new_reminder(
        self,
        context: ReminderContext,
        deadline: ParsedDeadline
    ) -> Reminder:
        """Create a new reminder.
        
        Args:
            context: Reminder context
            deadline: Parsed deadline
            
        Returns:
            Created Reminder object
        """
        # Create reminder object
        reminder = Reminder(
            channel_id=context.channel_id,
            thread_ts=context.thread_ts,
            user_id=context.user_id,
            message_ts=context.message_ts,
            original_message=context.message_text,
            deadline_text=deadline.original_text,
            deadline_datetime=deadline.deadline_datetime,
            reminder_datetime=deadline.reminder_datetime,
            status=ReminderStatus.PENDING,
            created_at=now_ist()
        )
        
        # Save to database
        reminder_id = self.reminder_repo.create(reminder)
        reminder.id = reminder_id
        
        # Log audit entry
        audit = AuditLog(
            reminder_id=reminder_id,
            action=AuditAction.CREATED,
            performed_by=context.user_id,
            performed_at=now_ist(),
            metadata={
                'deadline_text': deadline.original_text,
                'deadline_datetime': deadline.deadline_datetime.isoformat(),
                'parsed_by': deadline.parsed_by,
                'confidence': deadline.confidence
            }
        )
        self.audit_repo.log(audit)
        
        logger.success(f'Created reminder {reminder_id} for deadline: {format_datetime_friendly(deadline.deadline_datetime)}')
        return reminder
    
    def _reschedule_reminder(
        self,
        existing: Reminder,
        deadline: ParsedDeadline,
        context: ReminderContext
    ) -> Reminder:
        """Reschedule an existing reminder.
        
        Args:
            existing: Existing reminder to reschedule
            deadline: New parsed deadline
            context: Message context
            
        Returns:
            Updated Reminder object
        """
        old_deadline = existing.deadline_datetime
        old_deadline_text = existing.deadline_text
        
        # Update reminder
        success = self.reminder_repo.reschedule(
            existing.id,
            deadline.deadline_datetime,
            deadline.reminder_datetime
        )
        
        if not success:
            logger.error(f'Failed to reschedule reminder {existing.id}')
            raise Exception(f'Failed to reschedule reminder {existing.id}')
        
        # Also update deadline text and message
        self.reminder_repo.update(existing.id, {
            'deadline_text': deadline.original_text,
            'original_message': context.message_text
        })
        
        # Log audit entry
        audit = AuditLog(
            reminder_id=existing.id,
            action=AuditAction.RESCHEDULED,
            field_changed='deadline',
            old_value=f'{old_deadline_text} ({format_datetime_friendly(old_deadline)})',
            new_value=f'{deadline.original_text} ({format_datetime_friendly(deadline.deadline_datetime)})',
            performed_by=context.user_id,
            performed_at=now_ist(),
            metadata={
                'parsed_by': deadline.parsed_by,
                'confidence': deadline.confidence
            }
        )
        self.audit_repo.log(audit)
        
        logger.success(f'Rescheduled reminder {existing.id}: {format_datetime_friendly(old_deadline)} -> {format_datetime_friendly(deadline.deadline_datetime)}')
        
        # Return updated reminder
        return self.reminder_repo.get_by_id(existing.id)
    
    def cancel(self, reminder_id: int, cancelled_by: str) -> bool:
        """Cancel a reminder.
        
        Args:
            reminder_id: Reminder ID to cancel
            cancelled_by: User ID who cancelled
            
        Returns:
            True if cancellation successful
        """
        logger.info(f'Cancelling reminder {reminder_id}')
        
        # Get reminder first for audit log
        reminder = self.reminder_repo.get_by_id(reminder_id)
        if not reminder:
            logger.warning(f'Reminder {reminder_id} not found')
            return False
        
        # Update status
        success = self.reminder_repo.update_status(reminder_id, ReminderStatus.CANCELLED)
        
        if success:
            # Log audit entry
            audit = AuditLog(
                reminder_id=reminder_id,
                action=AuditAction.CANCELLED,
                performed_by=cancelled_by,
                performed_at=now_ist(),
                metadata={
                    'deadline': format_datetime_friendly(reminder.deadline_datetime)
                }
            )
            self.audit_repo.log(audit)
            
            logger.success(f'Cancelled reminder {reminder_id}')
        else:
            logger.error(f'Failed to cancel reminder {reminder_id}')
        
        return success
    
    def mark_sent(self, reminder_id: int) -> bool:
        """Mark reminder as sent.
        
        Args:
            reminder_id: Reminder ID
            
        Returns:
            True if update successful
        """
        logger.info(f'Marking reminder {reminder_id} as sent')
        
        success = self.reminder_repo.update_status(reminder_id, ReminderStatus.SENT)
        
        if success:
            # Log audit entry
            audit = AuditLog(
                reminder_id=reminder_id,
                action=AuditAction.SENT,
                performed_by='system',
                performed_at=now_ist()
            )
            self.audit_repo.log(audit)
            
            logger.success(f'Marked reminder {reminder_id} as sent')
        else:
            logger.error(f'Failed to mark reminder {reminder_id} as sent')
        
        return success
    
    def mark_failed(self, reminder_id: int, error: Optional[str] = None) -> bool:
        """Mark reminder as failed.
        
        Args:
            reminder_id: Reminder ID
            error: Optional error message
            
        Returns:
            True if update successful
        """
        logger.warning(f'Marking reminder {reminder_id} as failed')
        
        success = self.reminder_repo.update_status(reminder_id, ReminderStatus.FAILED)
        
        if success:
            # Log audit entry
            audit = AuditLog(
                reminder_id=reminder_id,
                action=AuditAction.FAILED,
                performed_by='system',
                performed_at=now_ist(),
                metadata={'error': error} if error else None
            )
            self.audit_repo.log(audit)
            
            logger.error(f'Marked reminder {reminder_id} as failed')
        
        return success
    
    def get_user_reminders(self, user_id: str) -> List[Reminder]:
        """Get all reminders for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of reminders
        """
        logger.debug(f'Getting reminders for user {user_id}')
        reminders = self.reminder_repo.get_by_user(user_id)
        logger.debug(f'Found {len(reminders)} reminders for user {user_id}')
        return reminders
    
    def get_thread_reminders(
        self,
        channel_id: str,
        thread_ts: str
    ) -> List[Reminder]:
        """Get all reminders for a thread.
        
        Args:
            channel_id: Channel ID
            thread_ts: Thread timestamp
            
        Returns:
            List of reminders
        """
        logger.debug(f'Getting reminders for thread {thread_ts} in channel {channel_id}')
        reminders = self.reminder_repo.get_by_channel(channel_id, thread_ts)
        logger.debug(f'Found {len(reminders)} reminders for thread')
        return reminders
    
    def get_pending_reminders(self) -> List[Reminder]:
        """Get all pending reminders.
        
        Returns:
            List of pending reminders
        """
        logger.debug('Getting all pending reminders')
        reminders = self.reminder_repo.get_pending()
        logger.debug(f'Found {len(reminders)} pending reminders')
        return reminders
    
    def get_due_reminders(self, before: datetime) -> List[Reminder]:
        """Get reminders due before specified time.
        
        Args:
            before: Datetime threshold
            
        Returns:
            List of due reminders
        """
        logger.debug(f'Getting reminders due before {format_datetime_friendly(before)}')
        reminders = self.reminder_repo.get_due(before)
        logger.debug(f'Found {len(reminders)} due reminders')
        return reminders
    
    def get_reminder(self, reminder_id: int) -> Optional[Reminder]:
        """Get reminder by ID.
        
        Args:
            reminder_id: Reminder ID
            
        Returns:
            Reminder or None if not found
        """
        return self.reminder_repo.get_by_id(reminder_id)
    
    def delete_reminder(
        self,
        reminder_id: int,
        deleted_by: str
    ) -> bool:
        """Delete a reminder.
        
        Args:
            reminder_id: Reminder ID
            deleted_by: User ID who deleted
            
        Returns:
            True if deletion successful
        """
        logger.info(f'Deleting reminder {reminder_id}')
        
        # Get reminder first for audit log
        reminder = self.reminder_repo.get_by_id(reminder_id)
        if not reminder:
            logger.warning(f'Reminder {reminder_id} not found')
            return False
        
        # Log audit entry before deletion
        audit = AuditLog(
            reminder_id=reminder_id,
            action=AuditAction.DELETED,
            performed_by=deleted_by,
            performed_at=now_ist(),
            metadata={
                'deadline': format_datetime_friendly(reminder.deadline_datetime),
                'status': reminder.status.value
            }
        )
        self.audit_repo.log(audit)
        
        # Delete reminder
        success = self.reminder_repo.delete(reminder_id)
        
        if success:
            logger.success(f'Deleted reminder {reminder_id}')
        else:
            logger.error(f'Failed to delete reminder {reminder_id}')
        
        return success
    
    def get_audit_history(self, reminder_id: int) -> List[AuditLog]:
        """Get audit history for a reminder.
        
        Args:
            reminder_id: Reminder ID
            
        Returns:
            List of audit log entries
        """
        logger.debug(f'Getting audit history for reminder {reminder_id}')
        return self.audit_repo.get_by_reminder(reminder_id)
