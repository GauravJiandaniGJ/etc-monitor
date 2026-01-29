"""Audit repository for tracking reminder changes."""
import json
from typing import Optional, List
from datetime import datetime
from src.core.models import AuditLog, AuditAction
from src.database.db_manager import DBManager
from src.utils.logger import get_logger
from src.utils.timezone import to_ist, make_naive


logger = get_logger('AuditRepository')


class AuditRepository:
    """Repository for audit log database operations.

    Handles all operations for audit_logs table to track reminder changes.
    """

    def __init__(self, db_manager: DBManager):
        """Initialize audit repository.

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager
        logger.info('Audit repository initialized')

    def log(self, audit: AuditLog) -> int:
        """Create a new audit log entry.

        Args:
            audit: AuditLog object to create

        Returns:
            ID of created audit log entry

        Raises:
            sqlite3.Error: If creation fails
        """
        # Build query with RETURNING clause for PostgreSQL/MySQL
        if self.db.database_type == 'postgresql' or self.db.database_type == 'mysql':
            query = '''
                INSERT INTO audit_logs (
                    reminder_id, action, field_changed, old_value, new_value,
                    performed_by, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            '''
        else:
            query = '''
                INSERT INTO audit_logs (
                    reminder_id, action, field_changed, old_value, new_value,
                    performed_by, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            '''

        # Serialize metadata to JSON string
        metadata_str = None
        if audit.metadata:
            try:
                metadata_str = json.dumps(audit.metadata)
            except (TypeError, ValueError) as e:
                logger.warning(f'Failed to serialize metadata: {e}')
                metadata_str = str(audit.metadata)

        params = (
            audit.reminder_id,
            audit.action.value,
            audit.field_changed,
            audit.old_value,
            audit.new_value,
            audit.performed_by,
            metadata_str
        )

        # For PostgreSQL/MySQL, use RETURNING to get the ID
        if self.db.database_type == 'postgresql' or self.db.database_type == 'mysql':
            result = self.db.fetch_one(query, params)
            if result and 'id' in result:
                audit_id = result['id']
                logger.debug(f'Created audit log ID {audit_id} for reminder {audit.reminder_id} - action: {audit.action.value}')
                return audit_id
            else:
                raise ValueError('Failed to get audit log ID from database (RETURNING clause)')
        else:
            # For SQLite, use lastrowid
            audit_id = self.db.execute(query, params)
            if audit_id and audit_id > 0:
                logger.debug(f'Created audit log ID {audit_id} for reminder {audit.reminder_id} - action: {audit.action.value}')
                return audit_id
            else:
                raise ValueError('Failed to get audit log ID from database (lastrowid)')

    def get_by_id(self, audit_id: int) -> Optional[AuditLog]:
        """Get audit log by ID.

        Args:
            audit_id: Audit log ID

        Returns:
            AuditLog object or None if not found
        """
        query = 'SELECT * FROM audit_logs WHERE id = ?'
        row = self.db.fetch_one(query, (audit_id,))

        if row:
            return self._row_to_audit_log(row)
        return None

    def get_by_reminder(self, reminder_id: int) -> List[AuditLog]:
        """Get all audit logs for a specific reminder.

        Args:
            reminder_id: Reminder ID

        Returns:
            List of AuditLog objects ordered by performed_at descending
        """
        query = '''
            SELECT * FROM audit_logs
            WHERE reminder_id = ?
            ORDER BY performed_at DESC
        '''
        rows = self.db.fetch_all(query, (reminder_id,))
        return [self._row_to_audit_log(row) for row in rows]

    def get_recent(self, limit: int = 100) -> List[AuditLog]:
        """Get recent audit logs.

        Args:
            limit: Maximum number of logs to return (default: 100)

        Returns:
            List of recent AuditLog objects ordered by performed_at descending
        """
        query = '''
            SELECT * FROM audit_logs
            ORDER BY performed_at DESC
            LIMIT ?
        '''
        rows = self.db.fetch_all(query, (limit,))
        return [self._row_to_audit_log(row) for row in rows]

    def get_by_action(self, action: AuditAction, limit: int = 100) -> List[AuditLog]:
        """Get audit logs by action type.

        Args:
            action: Action type to filter by
            limit: Maximum number of logs to return (default: 100)

        Returns:
            List of AuditLog objects ordered by performed_at descending
        """
        query = '''
            SELECT * FROM audit_logs
            WHERE action = ?
            ORDER BY performed_at DESC
            LIMIT ?
        '''
        rows = self.db.fetch_all(query, (action.value, limit))
        return [self._row_to_audit_log(row) for row in rows]

    def get_by_performer(self, performer: str, limit: int = 100) -> List[AuditLog]:
        """Get audit logs by performer.

        Args:
            performer: User ID or system identifier
            limit: Maximum number of logs to return (default: 100)

        Returns:
            List of AuditLog objects ordered by performed_at descending
        """
        query = '''
            SELECT * FROM audit_logs
            WHERE performed_by = ?
            ORDER BY performed_at DESC
            LIMIT ?
        '''
        rows = self.db.fetch_all(query, (performer, limit))
        return [self._row_to_audit_log(row) for row in rows]

    def get_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[AuditLog]:
        """Get audit logs within a date range.

        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)

        Returns:
            List of AuditLog objects ordered by performed_at descending
        """
        query = '''
            SELECT * FROM audit_logs
            WHERE performed_at >= ? AND performed_at <= ?
            ORDER BY performed_at DESC
        '''
        start_str = self._datetime_to_str(start_date)
        end_str = self._datetime_to_str(end_date)
        rows = self.db.fetch_all(query, (start_str, end_str))
        return [self._row_to_audit_log(row) for row in rows]

    def delete_old_logs(self, before_date: datetime) -> int:
        """Delete audit logs older than specified date.

        Used for cleanup/maintenance.

        Args:
            before_date: Delete logs before this date

        Returns:
            Number of deleted logs

        Raises:
            sqlite3.Error: If deletion fails
        """
        query = 'DELETE FROM audit_logs WHERE performed_at < ?'
        before_str = self._datetime_to_str(before_date)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (before_str,))
            deleted_count = cursor.rowcount

        logger.info(f'Deleted {deleted_count} old audit logs before {before_date}')
        return deleted_count

    def _row_to_audit_log(self, row: dict) -> AuditLog:
        """Convert database row to AuditLog object.

        Args:
            row: Database row as dictionary

        Returns:
            AuditLog object
        """
        # Parse metadata from JSON string
        metadata = None
        if row['metadata']:
            try:
                metadata = json.loads(row['metadata'])
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f'Failed to parse metadata for audit log {row["id"]}: {e}')
                metadata = {'raw': row['metadata']}

        return AuditLog(
            id=row['id'],
            reminder_id=row['reminder_id'],
            action=AuditAction(row['action']),
            field_changed=row['field_changed'],
            old_value=row['old_value'],
            new_value=row['new_value'],
            performed_by=row['performed_by'],
            performed_at=self._str_to_datetime(row['performed_at']),
            metadata=metadata
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
