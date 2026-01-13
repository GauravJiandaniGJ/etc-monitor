"""Reminder repository for database operations."""
from typing import Optional, List
from datetime import datetime
from src.core.models import Reminder, ReminderStatus
from src.database.db_manager import DBManager
from src.utils.logger import get_logger
from src.utils.timezone import to_ist, make_naive


logger = get_logger('ReminderRepository')


class ReminderRepository:
    """Repository for reminder database operations.
    
    Handles all CRUD operations for reminders table.
    """
    
    def __init__(self, db_manager: DBManager):
        """Initialize reminder repository.
        
        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager
        logger.info('Reminder repository initialized')
    
    def create(self, reminder: Reminder) -> int:
        """Create a new reminder.
        
        Args:
            reminder: Reminder object to create
            
        Returns:
            ID of created reminder
            
        Raises:
            sqlite3.Error: If creation fails
        """
        query = '''
            INSERT INTO reminders (
                channel_id, thread_ts, user_id, message_ts,
                original_message, deadline_text, deadline_datetime,
                reminder_datetime, status, retry_count, reschedule_count,
                previous_deadline
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        
        params = (
            reminder.channel_id,
            reminder.thread_ts,
            reminder.user_id,
            reminder.message_ts,
            reminder.original_message,
            reminder.deadline_text,
            self._datetime_to_str(reminder.deadline_datetime),
            self._datetime_to_str(reminder.reminder_datetime),
            reminder.status.value,
            reminder.retry_count,
            reminder.reschedule_count,
            self._datetime_to_str(reminder.previous_deadline)
        )
        
        reminder_id = self.db.execute(query, params)
        logger.success(f'Created reminder ID {reminder_id} for user {reminder.user_id}')
        return reminder_id
    
    def get_by_id(self, reminder_id: int) -> Optional[Reminder]:
        """Get reminder by ID.
        
        Args:
            reminder_id: Reminder ID
            
        Returns:
            Reminder object or None if not found
        """
        query = 'SELECT * FROM reminders WHERE id = ?'
        row = self.db.fetch_one(query, (reminder_id,))
        
        if row:
            return self._row_to_reminder(row)
        return None
    
    def get_by_composite_key(
        self,
        channel_id: str,
        thread_ts: str,
        user_id: str
    ) -> Optional[Reminder]:
        """Get reminder by composite key (channel, thread, user).
        
        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp
            user_id: User ID
            
        Returns:
            Reminder object or None if not found
        """
        query = '''
            SELECT * FROM reminders 
            WHERE channel_id = ? AND thread_ts = ? AND user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        '''
        row = self.db.fetch_one(query, (channel_id, thread_ts, user_id))
        
        if row:
            return self._row_to_reminder(row)
        return None
    
    def get_pending(self) -> List[Reminder]:
        """Get all pending reminders.
        
        Returns:
            List of pending reminders
        """
        query = '''
            SELECT * FROM reminders 
            WHERE status = 'pending'
            ORDER BY reminder_datetime ASC
        '''
        rows = self.db.fetch_all(query)
        return [self._row_to_reminder(row) for row in rows]
    
    def get_due(self, before: datetime) -> List[Reminder]:
        """Get reminders due before specified time.
        
        Args:
            before: Datetime threshold
            
        Returns:
            List of due reminders
        """
        query = '''
            SELECT * FROM reminders 
            WHERE status = 'pending' 
            AND reminder_datetime <= ?
            ORDER BY reminder_datetime ASC
        '''
        before_str = self._datetime_to_str(before)
        rows = self.db.fetch_all(query, (before_str,))
        return [self._row_to_reminder(row) for row in rows]
    
    def get_by_channel(
        self,
        channel_id: str,
        thread_ts: Optional[str] = None
    ) -> List[Reminder]:
        """Get reminders by channel, optionally filtered by thread.
        
        Args:
            channel_id: Slack channel ID
            thread_ts: Optional thread timestamp
            
        Returns:
            List of reminders
        """
        if thread_ts:
            query = '''
                SELECT * FROM reminders 
                WHERE channel_id = ? AND thread_ts = ?
                ORDER BY created_at DESC
            '''
            rows = self.db.fetch_all(query, (channel_id, thread_ts))
        else:
            query = '''
                SELECT * FROM reminders 
                WHERE channel_id = ?
                ORDER BY created_at DESC
            '''
            rows = self.db.fetch_all(query, (channel_id,))
        
        return [self._row_to_reminder(row) for row in rows]
    
    def get_by_user(self, user_id: str) -> List[Reminder]:
        """Get reminders by user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of reminders
        """
        query = '''
            SELECT * FROM reminders 
            WHERE user_id = ?
            ORDER BY created_at DESC
        '''
        rows = self.db.fetch_all(query, (user_id,))
        return [self._row_to_reminder(row) for row in rows]
    
    def update(self, reminder_id: int, updates: dict) -> bool:
        """Update reminder fields.
        
        Args:
            reminder_id: Reminder ID
            updates: Dictionary of field names to values
            
        Returns:
            True if update successful
            
        Raises:
            sqlite3.Error: If update fails
        """
        if not updates:
            return False
        
        # Build SET clause
        set_clauses = []
        params = []
        
        for field, value in updates.items():
            set_clauses.append(f'{field} = ?')
            # Convert datetime objects to strings
            if isinstance(value, datetime):
                value = self._datetime_to_str(value)
            elif isinstance(value, ReminderStatus):
                value = value.value
            params.append(value)
        
        # Add updated_at timestamp
        set_clauses.append('updated_at = ?')
        params.append(self._datetime_to_str(datetime.now()))
        
        # Add reminder_id for WHERE clause
        params.append(reminder_id)
        
        query = f'''
            UPDATE reminders 
            SET {', '.join(set_clauses)}
            WHERE id = ?
        '''
        
        self.db.execute(query, tuple(params))
        logger.success(f'Updated reminder ID {reminder_id}')
        return True
    
    def update_status(self, reminder_id: int, status: ReminderStatus) -> bool:
        """Update reminder status.
        
        Args:
            reminder_id: Reminder ID
            status: New status
            
        Returns:
            True if update successful
        """
        updates = {'status': status.value}
        
        # If marking as sent, record sent_at timestamp
        if status == ReminderStatus.SENT:
            updates['sent_at'] = self._datetime_to_str(datetime.now())
        
        return self.update(reminder_id, updates)
    
    def reschedule(
        self,
        reminder_id: int,
        new_deadline: datetime,
        new_reminder: datetime
    ) -> bool:
        """Reschedule a reminder.
        
        Args:
            reminder_id: Reminder ID
            new_deadline: New deadline datetime
            new_reminder: New reminder datetime
            
        Returns:
            True if reschedule successful
        """
        # Get current reminder to store previous deadline
        reminder = self.get_by_id(reminder_id)
        if not reminder:
            logger.error(f'Cannot reschedule: reminder ID {reminder_id} not found')
            return False
        
        updates = {
            'previous_deadline': self._datetime_to_str(reminder.deadline_datetime),
            'deadline_datetime': self._datetime_to_str(new_deadline),
            'reminder_datetime': self._datetime_to_str(new_reminder),
            'reschedule_count': reminder.reschedule_count + 1,
            'status': ReminderStatus.PENDING.value
        }
        
        result = self.update(reminder_id, updates)
        if result:
            logger.success(f'Rescheduled reminder ID {reminder_id}')
        return result
    
    def delete(self, reminder_id: int) -> bool:
        """Delete a reminder.
        
        Args:
            reminder_id: Reminder ID
            
        Returns:
            True if deletion successful
            
        Raises:
            sqlite3.Error: If deletion fails
        """
        query = 'DELETE FROM reminders WHERE id = ?'
        self.db.execute(query, (reminder_id,))
        logger.success(f'Deleted reminder ID {reminder_id}')
        return True
    
    def find_existing_active(
        self,
        channel_id: str,
        thread_ts: str,
        user_id: str
    ) -> Optional[Reminder]:
        """Find existing active reminder for same user in same thread.

        Active means status is 'pending' or 'rescheduled'.

        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp
            user_id: User ID

        Returns:
            Active reminder or None
        """
        query = '''
            SELECT * FROM reminders
            WHERE channel_id = ?
            AND thread_ts = ?
            AND user_id = ?
            AND status IN ('pending', 'rescheduled')
            ORDER BY created_at DESC
            LIMIT 1
        '''
        row = self.db.fetch_one(query, (channel_id, thread_ts, user_id))

        if row:
            return self._row_to_reminder(row)
        return None

    def find_by_message(
        self,
        channel_id: str,
        thread_ts: str,
        user_id: str,
        message_ts: str
    ) -> Optional[Reminder]:
        """Find reminder by message timestamp.

        Uses message_ts as the unique identifier to determine if an ETC
        is for a new task or an update to an existing task.

        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp
            user_id: User ID
            message_ts: Message timestamp (unique identifier)

        Returns:
            Reminder for this specific message or None
        """
        query = '''
            SELECT * FROM reminders
            WHERE channel_id = ?
            AND thread_ts = ?
            AND user_id = ?
            AND message_ts = ?
            AND status IN ('pending', 'rescheduled')
            ORDER BY created_at DESC
            LIMIT 1
        '''
        row = self.db.fetch_one(query, (channel_id, thread_ts, user_id, message_ts))

        if row:
            return self._row_to_reminder(row)
        return None
    
    def _row_to_reminder(self, row: dict) -> Reminder:
        """Convert database row to Reminder object.
        
        Args:
            row: Database row as dictionary
            
        Returns:
            Reminder object
        """
        return Reminder(
            id=row['id'],
            channel_id=row['channel_id'],
            thread_ts=row['thread_ts'],
            user_id=row['user_id'],
            message_ts=row['message_ts'],
            original_message=row['original_message'],
            deadline_text=row['deadline_text'],
            deadline_datetime=self._str_to_datetime(row['deadline_datetime']),
            reminder_datetime=self._str_to_datetime(row['reminder_datetime']),
            status=ReminderStatus(row['status']),
            created_at=self._str_to_datetime(row['created_at']),
            updated_at=self._str_to_datetime(row['updated_at']),
            sent_at=self._str_to_datetime(row['sent_at']),
            retry_count=row['retry_count'],
            reschedule_count=row['reschedule_count'],
            previous_deadline=self._str_to_datetime(row['previous_deadline'])
        )
    
    @staticmethod
    def _datetime_to_str(dt: Optional[datetime]) -> Optional[str]:
        """Convert datetime to string for database storage.
        
        Args:
            dt: Datetime to convert
            
        Returns:
            ISO format string or None
        """
        if dt is None:
            return None
        # Convert to IST and make naive for consistent storage
        dt_naive = make_naive(to_ist(dt))
        return dt_naive.isoformat()
    
    @staticmethod
    def _str_to_datetime(dt_str: Optional[str]) -> Optional[datetime]:
        """Convert string to datetime from database.
        
        Args:
            dt_str: ISO format datetime string
            
        Returns:
            Datetime object or None
        """
        if not dt_str:
            return None
        # Parse and assume IST
        dt = datetime.fromisoformat(dt_str)
        return to_ist(dt)
