-- ============================================
-- ETC Monitor Database Schema (SQLite)
-- ============================================
-- Run this script in DBeaver SQL Editor to create all tables
-- ============================================

-- ============================================
-- 1. REMINDERS TABLE
-- ============================================
-- Main table for storing ETC reminders
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

-- Indexes for reminders table
CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);
CREATE INDEX IF NOT EXISTS idx_reminders_reminder_datetime ON reminders(reminder_datetime);
CREATE INDEX IF NOT EXISTS idx_reminders_composite ON reminders(channel_id, thread_ts, user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);

-- ============================================
-- 2. AUDIT_LOGS TABLE
-- ============================================
-- Table for tracking all changes to reminders
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

-- Indexes for audit_logs table
CREATE INDEX IF NOT EXISTS idx_audit_reminder ON audit_logs(reminder_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);

-- ============================================
-- 3. SCHEMA_MIGRATIONS TABLE
-- ============================================
-- Table for tracking database migrations
CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- ============================================
-- VERIFICATION QUERIES
-- ============================================
-- Run these to verify tables were created:

-- SELECT name FROM sqlite_master WHERE type='table';
-- SELECT * FROM reminders;
-- SELECT * FROM audit_logs;
-- SELECT * FROM schema_migrations;
