"""Initial database schema migration.

Creates reminders, audit_logs, and schema_migrations tables.
"""


def upgrade(db_manager):
    """Create initial schema."""
    schema = '''
        -- Main reminders table
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- Composite identifier (channel + thread + user)
            channel_id TEXT NOT NULL,
            thread_ts TEXT NOT NULL,
            user_id TEXT NOT NULL,
            
            -- Message reference
            message_ts TEXT NOT NULL,
            original_message TEXT,
            
            -- Deadline information
            deadline_text TEXT NOT NULL,
            deadline_datetime DATETIME NOT NULL,
            reminder_datetime DATETIME NOT NULL,
            
            -- Status tracking
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'cancelled', 'failed', 'rescheduled')),
            
            -- Timestamps
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            sent_at DATETIME,
            
            -- Retry & reschedule tracking
            retry_count INTEGER DEFAULT 0,
            reschedule_count INTEGER DEFAULT 0,
            previous_deadline DATETIME
        );
        
        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);
        CREATE INDEX IF NOT EXISTS idx_reminders_reminder_datetime ON reminders(reminder_datetime);
        CREATE INDEX IF NOT EXISTS idx_reminders_composite ON reminders(channel_id, thread_ts, user_id);
        CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);
        
        -- Audit log for tracking all changes
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
    print('✅ Created initial schema: reminders, audit_logs tables with indexes')


def downgrade(db_manager):
    """Drop initial schema."""
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
    print('✅ Dropped initial schema: reminders, audit_logs tables and indexes')
