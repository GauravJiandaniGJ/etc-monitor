"""Add EOD follow-up fields migration.

Adds columns for tracking reminder sent time, user activity, and follow-ups.
"""
from src.utils.logger import get_logger

logger = get_logger('Migration002')


def upgrade(db_manager):
    """Add reminder_sent_at, last_user_update_at, followup_sent_at columns."""
    db_type = db_manager.database_type
    
    # Define common schema for SQLite/MySQL (DATETIME)
    # Note: SQLite supports ADD COLUMN but one per statement
    schema = '''
        ALTER TABLE reminders ADD COLUMN reminder_sent_at DATETIME;
        ALTER TABLE reminders ADD COLUMN last_user_update_at DATETIME;
        ALTER TABLE reminders ADD COLUMN followup_sent_at DATETIME;
    '''
    
    # PostgreSQL uses TIMESTAMP
    if db_type == 'postgresql':
        schema = '''
            ALTER TABLE reminders ADD COLUMN reminder_sent_at TIMESTAMP;
            ALTER TABLE reminders ADD COLUMN last_user_update_at TIMESTAMP;
            ALTER TABLE reminders ADD COLUMN followup_sent_at TIMESTAMP;
        '''
        
    db_manager.execute_script(schema)
    logger.success('Applied migration 002: Added follow-up fields')


def downgrade(db_manager):
    """Remove columns."""
    db_type = db_manager.database_type
    
    if db_type == 'sqlite':
        # SQLite doesn't support DROP COLUMN in older versions, and it's complex
        # For this simple project, we might just warn or skip
        logger.warning('SQLite does not support DROP COLUMN cleanly. Downgrade skipped.')
        return
        
    schema = '''
        ALTER TABLE reminders DROP COLUMN reminder_sent_at;
        ALTER TABLE reminders DROP COLUMN last_user_update_at;
        ALTER TABLE reminders DROP COLUMN followup_sent_at;
    '''
    
    db_manager.execute_script(schema)
    logger.success('Downgraded migration 002: Removed follow-up fields')
