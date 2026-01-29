# ETC Monitor

Slack bot that automatically detects "Estimated Time of Completion" (ETC) deadlines from thread replies and sends reminder notifications before deadlines expire.


## Claude Operating Rules

When working in this repository, follow these rules strictly:

- Do NOT change externally visible behavior unless explicitly asked
- Do NOT break Slack timing constraints (3s response window)
- Do NOT remove or bypass audit logging
- Prefer minimal, surgical changes over large refactors
- Backward compatibility is more important than elegance
- Assume this bot is already in production usage


## Domain Invariants

The following rules must always hold true:

- Only thread replies are processed (never channel root messages)
- `message_ts` is the primary identifier for reminders
- One active reminder per (thread, user) at a time
- Reminder rescheduling must preserve audit history
- AI parsing is best-effort; regex fallback must always work


## How to Suggest Changes

When proposing improvements:

- First explain the current behavior
- Then explain the risk or limitation
- Then propose the smallest possible change
- Always mention which files are affected
- If behavior changes, call it out explicitly


## Preferred Improvement Areas

Safe areas for refactoring or improvement:

- Deadline parsing accuracy
- False-positive reduction
- Scheduler resilience
- Logging clarity
- Test coverage

Avoid major architectural changes unless explicitly requested.



## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
# Edit .env with your Slack tokens and other settings

# Run the Slack bot
python run_bot.py

# Run the admin panel (separate terminal)
python run_admin.py
```

## Project Structure

```
src/
├── bot/              # Slack bot (Bolt framework, Socket Mode)
│   ├── app.py        # Bot initialization and event registration
│   ├── handlers/     # Message and slash command handlers
│   └── scheduler/    # APScheduler for reminder scheduling
├── services/         # Business logic layer
│   ├── deadline_service.py    # Deadline detection orchestration
│   ├── reminder_service.py    # Reminder CRUD and rescheduling
│   ├── notification_service.py # Slack message sending
│   └── ai_service.py          # Google Gemini integration
├── parsers/          # Deadline parsing
│   ├── ai_parser.py           # AI-powered parsing (Gemini)
│   ├── datetime_parser.py     # Date/time text parsing
│   └── pattern_matcher.py     # Regex fallback patterns
├── database/         # Data persistence
│   ├── db_manager.py          # Connection management
│   ├── repositories/          # CRUD operations
│   └── migrations/            # Schema versioning
├── admin/            # Flask admin panel
│   ├── app.py                 # Flask app setup
│   ├── routes/                # REST API endpoints
│   └── middleware/            # Authentication
├── core/             # Data models (Reminder, AuditLog, etc.)
└── utils/            # Logger, timezone utilities
config/
└── settings.py       # Environment configuration loader
```

## Configuration

Required environment variables (in `.env`):
- `SLACK_BOT_TOKEN` - Slack bot OAuth token
- `SLACK_SIGNING_SECRET` - Slack app signing secret
- `SLACK_APP_TOKEN` - Socket Mode app token
- `FLASK_SECRET_KEY` - Flask session encryption key

Optional:
- `GEMINI_API_KEY` - Google Gemini API key for AI parsing
- `DATABASE_TYPE` - `sqlite` (default), `postgresql`, or `mysql`
- `TIMEZONE` - Default `Asia/Kolkata`
- `ADMIN_USERNAME`/`ADMIN_PASSWORD` - Admin panel credentials

## Key Patterns

- **Thread replies only**: Bot only processes messages in threads, not main channel messages
- **message_ts as identifier**: Uses Slack message timestamp to uniquely identify tasks
- **AI-first parsing**: Tries Gemini AI (5s timeout), falls back to regex patterns
- **Async processing**: Background task processing to prevent Slack timeouts

## Slash Commands

- `/my-reminders` - List user's active reminders
- `/cancel-reminder <id>` - Cancel a specific reminder
- `/list-thread-reminders` - List all reminders in current thread

## Database

Default SQLite (`reminders.db`). Tables:
- `reminders` - ETC reminders with deadlines and status
- `audit_logs` - Operation history for all reminder changes
- `schema_migrations` - Database version tracking

## Testing

```bash
pytest tests/
```

## Code Style

- Python 3.8+
- Type hints encouraged
- Dataclasses for models (`src/core/models.py`)
- Repository pattern for database access
- Service layer for business logic
