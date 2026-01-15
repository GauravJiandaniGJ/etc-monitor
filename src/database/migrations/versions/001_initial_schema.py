"""Initial database schema migration.

Creates reminders, audit_logs, and schema_migrations tables.
Supports SQLite, PostgreSQL, and MySQL.
"""
from src.utils.logger import get_logger

logger = get_logger('Migration001')


def upgrade(db_manager):
    """Create initial schema."""
    db_type = db_manager.database_type

    if db_type == 'sqlite':
        _upgrade_sqlite(db_manager)
    elif db_type == 'postgresql':
        _upgrade_postgresql(db_manager)
    elif db_type == 'mysql':
        _upgrade_mysql(db_manager)
    else:
        raise ValueError(f'Unsupported database type: {db_type}')


def _upgrade_sqlite(db_manager):
    """SQLite-specific schema."""
    schema = '''
        -- Main reminders table
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            thread_ts TEXT NOT NULL,
            user_id TEXT NOT NULL,
            message_ts TEXT NOT NULL,
            original_message TEXT,
            deadline_text TEXT NOT NULL,
            deadline_datetime DATETIME NOT NULL,
            reminder_datetime DATETIME NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'cancelled', 'failed', 'rescheduled')),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            sent_at DATETIME,
            retry_count INTEGER DEFAULT 0,
            reschedule_count INTEGER DEFAULT 0,
            previous_deadline DATETIME
        );

        CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);
        CREATE INDEX IF NOT EXISTS idx_reminders_reminder_datetime ON reminders(reminder_datetime);
        CREATE INDEX IF NOT EXISTS idx_reminders_composite ON reminders(channel_id, thread_ts, user_id);
        CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reminder_id INTEGER,
            action TEXT NOT NULL CHECK(action IN ('created', 'updated', 'rescheduled', 'cancelled', 'sent', 'failed', 'deleted')),
            field_changed TEXT,
            old_value TEXT,
            new_value TEXT,
            performed_by TEXT,
            performed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT,
            FOREIGN KEY (reminder_id) REFERENCES reminders(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_reminder ON audit_logs(reminder_id);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
    '''
    db_manager.execute_script(schema)
    logger.success('Created SQLite schema: reminders, audit_logs tables with indexes')


def _upgrade_postgresql(db_manager):
    """PostgreSQL-specific schema."""
    schema = '''
        -- Main reminders table
        CREATE TABLE IF NOT EXISTS reminders (
            id SERIAL PRIMARY KEY,
            channel_id TEXT NOT NULL,
            thread_ts TEXT NOT NULL,
            user_id TEXT NOT NULL,
            message_ts TEXT NOT NULL,
            original_message TEXT,
            deadline_text TEXT NOT NULL,
            deadline_datetime TIMESTAMP NOT NULL,
            reminder_datetime TIMESTAMP NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'cancelled', 'failed', 'rescheduled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sent_at TIMESTAMP,
            retry_count INTEGER DEFAULT 0,
            reschedule_count INTEGER DEFAULT 0,
            previous_deadline TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);
        CREATE INDEX IF NOT EXISTS idx_reminders_reminder_datetime ON reminders(reminder_datetime);
        CREATE INDEX IF NOT EXISTS idx_reminders_composite ON reminders(channel_id, thread_ts, user_id);
        CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);

        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            reminder_id INTEGER,
            action TEXT NOT NULL CHECK(action IN ('created', 'updated', 'rescheduled', 'cancelled', 'sent', 'failed', 'deleted')),
            field_changed TEXT,
            old_value TEXT,
            new_value TEXT,
            performed_by TEXT,
            performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT,
            FOREIGN KEY (reminder_id) REFERENCES reminders(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_reminder ON audit_logs(reminder_id);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
    '''
    db_manager.execute_script(schema)
    logger.success('Created PostgreSQL schema: reminders, audit_logs tables with indexes')


def _upgrade_mysql(db_manager):
    """MySQL-specific schema."""
    schema = '''
        -- Main reminders table
        CREATE TABLE IF NOT EXISTS reminders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            thread_ts TEXT NOT NULL,
            user_id TEXT NOT NULL,
            message_ts TEXT NOT NULL,
            original_message TEXT,
            deadline_text TEXT NOT NULL,
            deadline_datetime DATETIME NOT NULL,
            reminder_datetime DATETIME NOT NULL,
            status VARCHAR(20) DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'cancelled', 'failed', 'rescheduled')),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            sent_at DATETIME,
            retry_count INT DEFAULT 0,
            reschedule_count INT DEFAULT 0,
            previous_deadline DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);
        CREATE INDEX IF NOT EXISTS idx_reminders_reminder_datetime ON reminders(reminder_datetime);
        CREATE INDEX IF NOT EXISTS idx_reminders_composite ON reminders(channel_id, thread_ts, user_id);
        CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            reminder_id INT,
            action VARCHAR(20) NOT NULL CHECK(action IN ('created', 'updated', 'rescheduled', 'cancelled', 'sent', 'failed', 'deleted')),
            field_changed TEXT,
            old_value TEXT,
            new_value TEXT,
            performed_by TEXT,
            performed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT,
            FOREIGN KEY (reminder_id) REFERENCES reminders(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        CREATE INDEX IF NOT EXISTS idx_audit_reminder ON audit_logs(reminder_id);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
    '''
    db_manager.execute_script(schema)
    logger.success('Created MySQL schema: reminders, audit_logs tables with indexes')


def downgrade(db_manager):
    """Drop initial schema."""
    db_type = db_manager.database_type

    schema = '''
        DROP INDEX IF EXISTS idx_audit_action;
        DROP INDEX IF EXISTS idx_audit_reminder;
        DROP TABLE IF EXISTS audit_logs;

        DROP INDEX IF EXISTS idx_reminders_user;
        DROP INDEX IF EXISTS idx_reminders_composite;
        DROP INDEX IF EXISTS idx_reminders_reminder_datetime;
        DROP INDEX IF EXISTS idx_reminders_status;
        DROP TABLE IF EXISTS reminders;
    '''

    db_manager.execute_script(schema)
    logger.success('Dropped initial schema: reminders, audit_logs tables and indexes')
