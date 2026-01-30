# Project Overview

- **Purpose**: Slack bot that monitors thread messages for ETC (Estimated Time of Completion) mentions and schedules reminder notifications
- **Responsibilities**:
  - Detect deadline expressions in Slack thread messages
  - Parse natural language time/date expressions using AI (Gemini) with regex fallback
  - Schedule reminders using background job scheduler
  - Persist reminders to SQLite database (or PostgreSQL/MySQL)
  - Provide authenticated admin web panel for reminder management
- **Intended Usage**: Internal tool for team productivity - deployed as a Slack app

---

# Tech Stack

## Languages
- Python 3.11+

## Frameworks
- Slack Bolt 1.18.0 (Slack bot framework)
- Flask 3.0.0 (admin web panel)

## Key Libraries
- `slack-sdk` 3.26.0 - Slack API client
- `apscheduler` 3.10.4 - Background job scheduling
- `google-generativeai` >=0.3.2 - Gemini AI for NLP deadline parsing
- `dateparser` 1.2.0 - Flexible date/time parsing
- `sqlalchemy` 2.0.23 - Database toolkit (with raw SQL execution)
- `pytz` 2023.3 - Timezone handling
- `python-dotenv` 1.0.0 - Environment variable management
- `requests` 2.31.0 - HTTP client
- `flask-cors` - CORS support for admin API

## Databases
- **SQLite** (default) - Single database file for reminder persistence (`reminders.db`)
- **PostgreSQL** (optional) - For production deployments
- **MySQL** (optional) - Alternative production database

## Infrastructure
- Socket Mode for Slack WebSocket connection
- Flask development server on port 5000 (configurable via `ADMIN_PORT`)
- Slack bot running independently
- Systemd service for production deployment (`deploy/etc-monitor-bot.service`)

---

# Project Architecture

## Architectural Style
- Modular monolithic application with clear separation of concerns
- Event-driven (Slack events trigger processing)
- Service-oriented architecture within the monolith
- Repository pattern for data access

## Folder Structure

```
etc-moniter/
├── config/                          # Application configuration
│   ├── __init__.py
│   └── settings.py                  # Settings dataclass, environment variable loading
│
├── src/                             # Main source code
│   ├── __init__.py
│   │
│   ├── admin/                       # Flask admin panel
│   │   ├── __init__.py
│   │   ├── app.py                   # Flask app creation, routes, authentication
│   │   ├── middleware/              # Flask middleware
│   │   │   ├── __init__.py
│   │   │   └── auth_middleware.py   # Authentication middleware
│   │   ├── routes/                  # API route blueprints
│   │   │   ├── __init__.py
│   │   │   ├── health_routes.py     # Health check endpoints
│   │   │   └── reminder_routes.py   # Reminder CRUD API endpoints
│   │   └── templates/               # HTML templates (currently empty)
│   │                                # NOTE: HTML is inline in app.py, can be migrated here
│   │
│   ├── bot/                         # Slack bot application
│   │   ├── __init__.py
│   │   ├── app.py                   # Bot initialization, event setup
│   │   ├── handlers/                # Event handlers
│   │   │   ├── __init__.py
│   │   │   ├── command_handler.py   # Slash commands
│   │   │   └── message_handler.py   # Message events
│   │   └── scheduler/               # Job scheduling
│   │       ├── __init__.py
│   │       └── reminder_scheduler.py # APScheduler management
│   │
│   ├── core/                        # Domain models
│   │   ├── __init__.py
│   │   └── models.py                # Reminder, AuditLog dataclasses, enums
│   │
│   ├── database/                    # Data layer
│   │   ├── __init__.py
│   │   ├── db_manager.py            # Database connection, raw SQL execution
│   │   ├── repositories/            # Repository pattern
│   │   │   ├── __init__.py
│   │   │   ├── reminder_repository.py  # Reminder CRUD operations
│   │   │   └── audit_repository.py     # Audit log operations
│   │   └── migrations/              # Database schema management
│   │       ├── __init__.py
│   │       ├── migration_manager.py # Migration execution
│   │       └── versions/            # Migration SQL files
│   │
│   ├── parsers/                     # Deadline parsing logic
│   │   ├── __init__.py
│   │   ├── ai_parser.py             # Gemini AI integration
│   │   ├── datetime_parser.py       # Dateparser integration, datetime utilities
│   │   └── pattern_matcher.py       # Regex pattern matching
│   │
│   ├── services/                    # Business logic
│   │   ├── __init__.py
│   │   ├── ai_service.py            # Gemini AI service
│   │   ├── deadline_service.py      # Deadline detection orchestration
│   │   ├── notification_service.py  # Slack notification formatting/sending
│   │   └── reminder_service.py      # Reminder business logic
│   │
│   └── utils/                       # Shared utilities
│       ├── __init__.py
│       ├── logger.py                # Structured logging setup
│       └── timezone.py              # Timezone conversion utilities
│
├── scripts/                         # Utility scripts
│   └── setup_db.py                  # Database initialization
│
├── deploy/                          # Deployment configuration
│   └── etc-monitor-bot.service      # Systemd service file
│
├── tests/                           # Test suite (structure only)
│   ├── __init__.py
│   ├── fixtures/                    # Test fixtures
│   ├── integration/                 # Integration tests
│   └── unit/                        # Unit tests
│
├── run_bot.py                       # Bot entry point
├── run_admin.py                     # Admin panel entry point
├── requirements.txt                 # Python dependencies
├── database_schema.sql              # Database schema documentation
├── reminders.db                     # SQLite database file
├── pyrightconfig.json               # Type checker configuration
├── .env                             # Environment variables (not in git)
└── README.md                        # Project documentation
```

## Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| **config/** | Application configuration, environment variable loading |
| `config/settings.py` | Settings dataclass, validation, environment variable parsing |
| **src/admin/** | Flask admin panel, web UI, API routes |
| `src/admin/app.py` | Flask app creation, authentication, **inline HTML templates** |
| `src/admin/routes/` | API endpoint blueprints (reminders, health) |
| `src/admin/templates/` | HTML templates folder (currently empty - HTML is inline) |
| **src/bot/** | Slack bot, event handling, scheduling |
| `src/bot/app.py` | Bot initialization, Slack event registration |
| `src/bot/handlers/` | Message and command event handlers |
| `src/bot/scheduler/` | APScheduler job management |
| **src/core/** | Domain models, enums, dataclasses |
| `src/core/models.py` | Reminder, AuditLog, ReminderStatus, AuditAction |
| **src/database/** | Database access, repositories, migrations |
| `src/database/db_manager.py` | Connection pooling, raw SQL execution |
| `src/database/repositories/` | Data access layer (Repository pattern) |
| `src/database/migrations/` | Schema migrations |
| **src/parsers/** | Deadline detection, AI parsing, regex matching |
| `src/parsers/ai_parser.py` | Gemini AI integration |
| `src/parsers/datetime_parser.py` | Datetime parsing and utilities |
| `src/parsers/pattern_matcher.py` | Regex pattern matching |
| **src/services/** | Business logic layer |
| `src/services/deadline_service.py` | Orchestrates deadline detection (AI + regex fallback) |
| `src/services/reminder_service.py` | Reminder creation, cancellation, status management |
| `src/services/notification_service.py` | Slack message formatting and sending |
| **src/utils/** | Shared utilities |
| `src/utils/logger.py` | Structured logging with emoji prefixes |
| `src/utils/timezone.py` | Timezone conversion utilities |

## HTML/CSS/JavaScript Location

### Current Implementation (Inline HTML)

HTML code is currently **embedded as Python f-strings** in `src/admin/app.py`:

1. **Login Page**: `get_login_page()` function (lines 157-306)
   - Contains full HTML, CSS (inline styles), and basic form
   - Styled with gradient background, modern card design
   - Error message support

2. **Dashboard Page**: `get_dashboard_html()` function (lines 309-1243)
   - Full admin dashboard with:
     - HTML structure
     - Inline CSS (900+ lines of custom styles)
     - JavaScript (DataTables integration, AJAX, theme toggle)
     - Responsive design with light/dark mode
     - Stats cards, reminder table, action buttons
     - Toast notifications

### Migrating to Templates (Future)

The `src/admin/templates/` folder exists but is currently **empty**. To migrate HTML to proper Flask templates:

1. Create template files in `src/admin/templates/`:
   - `login.html` - Extract from `get_login_page()`
   - `dashboard.html` - Extract from `get_dashboard_html()`
   - `base.html` - Base template with shared layout
   - `partials/` - Reusable components

2. Create static assets folder:
   - `src/admin/static/css/` - Extract inline CSS
   - `src/admin/static/js/` - Extract inline JavaScript
   - `src/admin/static/img/` - Images, icons

3. Update `src/admin/app.py` to use `render_template()`:
   ```python
   from flask import render_template

   @app.route('/login')
   def login():
       return render_template('login.html', error=error)

   @app.route('/dashboard')
   def dashboard():
       return render_template('dashboard.html')
   ```

**Why HTML is currently inline:**
- Simplifies deployment (single Python file)
- No need to manage static asset paths
- Easier for quick prototyping

**Benefits of migrating to templates:**
- Better separation of concerns
- Easier to maintain and update UI
- Better syntax highlighting and validation
- Reusable components
- Easier to add more pages

## Data Flow

### Reminder Creation Flow
```
1. Slack Message Event
   ↓
2. src/bot/handlers/message_handler.py
   ↓
3. src/services/deadline_service.py (detect deadline)
   ├─→ src/parsers/ai_parser.py (Gemini AI - primary)
   └─→ src/parsers/pattern_matcher.py (regex - fallback)
   ↓
4. src/parsers/datetime_parser.py (parse datetime)
   ↓
5. src/services/reminder_service.py (create reminder)
   ↓
6. src/database/repositories/reminder_repository.py (save to DB)
   ↓
7. src/bot/scheduler/reminder_scheduler.py (schedule job)
```

### Reminder Execution Flow
```
1. APScheduler triggers job at reminder_datetime
   ↓
2. src/bot/scheduler/reminder_scheduler.py
   ↓
3. src/services/notification_service.py (format message)
   ↓
4. Slack API (send message to thread)
   ↓
5. src/services/reminder_service.py (update status to 'sent')
   ↓
6. src/database/repositories/reminder_repository.py (update DB)
```

### Admin Panel Flow
```
1. User accesses /dashboard
   ↓
2. src/admin/app.py (authentication check)
   ↓
3. Return inline HTML from get_dashboard_html()
   ↓
4. JavaScript makes AJAX call to /api/reminders
   ↓
5. src/admin/routes/reminder_routes.py
   ↓
6. src/services/reminder_service.py
   ↓
7. src/database/repositories/reminder_repository.py
   ↓
8. Return JSON data
   ↓
9. JavaScript renders data in DataTable
```

---

# Coding Standards

## Formatting Rules
- 4-space indentation
- Single quotes for strings (preferred)
- f-strings for string interpolation
- Max line length: ~100 chars (not strictly enforced)
- Type hints for function signatures
- Docstrings for all public functions/classes (Google style)

## Naming Conventions
- `snake_case` for functions, variables, module names
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- Private methods/attributes prefixed with underscore (`_init_database`)
- Descriptive names over abbreviations

## Patterns to Follow
- Dataclasses for domain models (see `src/core/models.py`)
- Repository pattern for data access (see `src/database/repositories/`)
- Service layer for business logic (see `src/services/`)
- Environment variables via `config/settings.py` dataclass
- Structured logging via `src/utils/logger.py` (emoji prefixes)
- Retry with exponential backoff for external API calls
- Fallback pattern: AI first, regex second (deadline detection)
- Cache-aside pattern for Slack user/channel names

## Patterns to Avoid
- Do not use SQLAlchemy ORM - use raw SQL via `DBManager`
- Do not add external logging frameworks - use built-in structured logger
- Do not refactor to async/await - current sync model is intentional
- Do not split into microservices
- Do not hardcode secrets - use environment variables

## Error Handling
- Wrap external API calls in try/except
- Use custom exception classes where appropriate
- Log errors with context using structured logger
- Graceful degradation (e.g., Gemini fails → regex fallback)
- Return meaningful error messages to users

---

# AI Coding Instructions (CRITICAL)

## How to Write Code in This Repo

1. **Follow the modular structure** - Don't create files outside existing modules
2. **Use the logger** - Import from `src.utils.logger`, use emoji prefixes:
   - `logger.info()` - 📝 info
   - `logger.success()` - ✅ success
   - `logger.warning()` - ⚠️ warning
   - `logger.error()` - ❌ error
3. **Use DBManager for database access** - Never use SQLAlchemy ORM directly
4. **All configuration via Settings** - Import from `config.settings`
5. **New deadline patterns** - Add to `src/parsers/pattern_matcher.py`
6. **Maintain AI → regex fallback** - Always try Gemini first, fall back to regex

## Abstractions to Respect

- `Reminder` dataclass in `src/core/models.py` - Core domain model, extend carefully
- `Settings` dataclass in `config/settings.py` - Single source of configuration
- `DBManager` in `src/database/db_manager.py` - All database access goes through this
- Repository pattern - Data access only through repository classes
- Service pattern - Business logic only in service classes

## What NOT to Change Without Instruction

- Database schema - requires migration planning
- Environment variable names - affects deployment
- Timezone from `Asia/Kolkata` - team is India-based
- Logging format/structure - tools may depend on it
- Repository/Service interfaces - may break existing code
- AI → regex fallback order - critical for reliability

## Adding New Features Safely

### New Deadline Detection Pattern
```python
# src/parsers/pattern_matcher.py
def __init__(self):
    self.patterns = [
        # Add your new pattern here
        (r'new pattern regex', 'pattern description'),
        # Keep existing patterns
    ]
```

### New API Endpoint
```python
# src/admin/routes/reminder_routes.py
@reminder_bp.route('/api/reminders/new-endpoint', methods=['GET'])
def new_endpoint():
    """Endpoint description."""
    # Use _reminder_service for business logic
    # Return JSON response
```

### New Slack Command
```python
# src/bot/handlers/command_handler.py
def register_command_handlers(app, services):
    @app.command('/new-command')
    def handle_new_command(ack, command, logger):
        ack()
        # Handle command
```

### New Service Method
```python
# src/services/reminder_service.py
def new_method(self, param: str) -> bool:
    """Method description.

    Args:
        param: Parameter description

    Returns:
        Success status
    """
    # Business logic
    # Use self.reminder_repo for data access
    # Use self.audit_repo for audit logging
```

## HTML/Template Development

### Currently (Inline HTML)
```python
# src/admin/app.py
def get_new_page() -> str:
    """Generate new page HTML."""
    return f'''
<!DOCTYPE html>
<html>
<head>
    <title>New Page</title>
    <style>
        /* Your CSS here */
    </style>
</head>
<body>
    <h1>New Page</h1>
    <script>
        // Your JavaScript here
    </script>
</body>
</html>
'''
```

### Future (Flask Templates)
```python
# src/admin/app.py
from flask import render_template

@app.route('/new-page')
def new_page():
    return render_template('new_page.html', data=data)
```

```html
<!-- src/admin/templates/new_page.html -->
{% extends 'base.html' %}

{% block title %}New Page{% endblock %}

{% block content %}
    <h1>New Page</h1>
    {{ data }}
{% endblock %}
```

---

# Environment & Setup

## Required Environment Variables

Create a `.env` file in project root:

```bash
# Slack Configuration (Required)
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
SLACK_APP_TOKEN=xapp-your-app-token

# Gemini AI (Optional - falls back to regex if not set)
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-1.5-flash
GEMINI_TEMPERATURE=0.2

# Database Configuration
DATABASE_TYPE=sqlite                 # Options: sqlite, postgresql, mysql
DATABASE_PATH=reminders.db           # SQLite only
# DATABASE_HOST=localhost            # PostgreSQL/MySQL
# DATABASE_PORT=5432                 # PostgreSQL/MySQL
# DATABASE_NAME=etc_monitor          # PostgreSQL/MySQL
# DATABASE_USER=dbuser               # PostgreSQL/MySQL
# DATABASE_PASSWORD=dbpass           # PostgreSQL/MySQL
# DATABASE_URL=postgresql://...      # Full URL (optional)

# Admin Panel (Required)
FLASK_SECRET_KEY=generate-secure-random-key-here
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password

# Application Configuration
TIMEZONE=Asia/Kolkata
DEBUG=false
LOG_LEVEL=INFO
ADMIN_PORT=5000
```

## Development Setup

```bash
# 1. Clone repository
cd etc-moniter

# 2. Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
cp .env.example .env  # Then edit with your values

# 5. Initialize database
python scripts/setup_db.py

# 6. Run bot (in one terminal)
python run_bot.py

# 7. Run admin panel (in another terminal)
python run_admin.py

# 8. Access admin panel
# Open browser: http://localhost:5000
# Login with credentials from .env
```

## Production Deployment

```bash
# 1. Set production environment variables
export DEBUG=false
export LOG_LEVEL=INFO

# 2. Use PostgreSQL/MySQL instead of SQLite
export DATABASE_TYPE=postgresql
export DATABASE_HOST=your-db-host
export DATABASE_NAME=etc_monitor

# 3. Set secure secrets
export FLASK_SECRET_KEY=$(openssl rand -hex 32)
export ADMIN_PASSWORD=$(openssl rand -base64 24)

# 4. Install systemd service
sudo cp deploy/etc-monitor-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable etc-monitor-bot
sudo systemctl start etc-monitor-bot

# 5. Check logs
sudo journalctl -u etc-monitor-bot -f
```

## Database Migration

```bash
# Run migrations
python -m src.database.migrations.migration_manager

# Create new migration
# 1. Add SQL file to src/database/migrations/versions/
# 2. Name format: YYYYMMDD_HHMMSS_description.sql
# 3. Run migration command
```

---

# Testing Strategy

## Current State
- No automated tests yet
- Manual testing only
- Test structure exists in `tests/` folder

## Test Structure (Planned)
```
tests/
├── unit/              # Unit tests for individual functions
│   ├── test_parsers/
│   ├── test_services/
│   └── test_repositories/
├── integration/       # Integration tests
│   ├── test_slack_bot/
│   ├── test_admin_api/
│   └── test_database/
└── fixtures/          # Test data and fixtures
```

## Testing Guidelines

### Unit Tests
- Test individual functions in isolation
- Mock external dependencies (Slack API, Gemini API, database)
- Use pytest fixtures for common setup
- Aim for >80% code coverage

### Integration Tests
- Test end-to-end workflows
- Use test database (SQLite in-memory)
- Test actual Slack API calls (with test workspace)
- Verify database state changes

### Manual Testing
- Test Slack bot in development workspace
- Test admin panel UI flows
- Test different deadline formats
- Verify notifications are sent correctly

---

# Performance & Security

## Performance Considerations

### Database
- SQLite adequate for small teams (<100 users)
- PostgreSQL recommended for production (>100 users)
- Connection pooling via DBManager
- Indexes on frequently queried columns

### Caching
- User/channel name cache in `reminder_routes.py` (reduces Slack API calls)
- Reminder cache in scheduler (in-memory)
- Cache invalidation on updates

### API Rate Limits
- Slack API: Respect rate limits (tier-based)
- Gemini API: Handle quota errors, fall back to regex
- Retry with exponential backoff for both

### Optimization Tips
- Use batch operations for bulk reminders
- Limit API endpoint pagination (max 1000 results)
- Pre-fetch user/channel names for dashboard
- Use DataTables client-side pagination

## Security Considerations

### Current Security Measures
✅ Environment variables for all secrets
✅ Flask session-based authentication
✅ CORS configuration for API routes
✅ Input validation on API endpoints
✅ SQL injection protection (parameterized queries)
✅ Password-protected admin panel

### Security Warnings
⚠️ **CRITICAL**: Change `FLASK_SECRET_KEY` before production deployment
⚠️ **CRITICAL**: Change `ADMIN_PASSWORD` from default
⚠️ No rate limiting on admin API endpoints
⚠️ No HTTPS enforcement (add reverse proxy for production)
⚠️ Session cookies not marked secure/httponly
⚠️ No CSRF protection on POST endpoints
⚠️ Admin panel authentication is basic (consider OAuth)

### Production Security Checklist
- [ ] Generate secure `FLASK_SECRET_KEY`
- [ ] Set strong `ADMIN_PASSWORD`
- [ ] Use HTTPS (reverse proxy with Let's Encrypt)
- [ ] Add rate limiting (Flask-Limiter)
- [ ] Add CSRF protection (Flask-WTF)
- [ ] Set secure session cookie flags
- [ ] Implement OAuth login (optional)
- [ ] Regular security audits
- [ ] Database backups
- [ ] Monitor error logs for suspicious activity

---

# Known Constraints & Gotchas

## Legacy Decisions
- **Folder name typo**: `etc-moniter` instead of `etc-monitor` - Keep for consistency
- **Raw SQL instead of ORM**: Intentional for simplicity and performance
- **Sync code instead of async**: Compatible with Slack Bolt, easier to debug

## Intentional Design Choices
- **Inline HTML in Python**: Simplifies deployment, single file for UI
- **Print-based logging** (now structured logger): Simple, readable, emoji prefixes
- **IST timezone (`Asia/Kolkata`)**: Team is India-based
- **Gemini + regex fallback**: Ensures bot works without API key
- **Thread-only detection**: Only processes thread replies, not channel messages
- **Session-based auth**: Simple, stateless not required for admin panel

## Areas to Be Careful With

### Database
- SQLite doesn't support concurrent writes well - use PostgreSQL for production
- Schema changes require migrations - don't alter tables directly
- Backup `reminders.db` before migrations

### Datetime Parsing
- Complex parsing logic in `src/parsers/datetime_parser.py`
- Always use timezone-aware datetimes
- Test with multiple time formats

### Scheduler
- Job IDs must be unique: `{channel}_{thread_ts}_{user}_{message_ts}`
- APScheduler persistence not enabled - jobs lost on restart
- Consider persistent job store for production

### Message Deduplication
- In-memory set for processed messages - clears on restart
- May cause duplicate processing after bot restart
- Consider persistent deduplication store

### Admin Panel
- HTML is inline in `app.py` - large file, hard to maintain
- No WebSocket support - requires page refresh for updates
- Auto-refresh every 30 seconds - configurable in JavaScript

### Slack API
- Rate limits vary by endpoint - implement backoff
- Message threading requires `thread_ts` - validate before use
- User/channel names may change - cache invalidation needed

---

# TODO / Missing Features

## High Priority
- [ ] Migrate inline HTML to `src/admin/templates/`
- [ ] Add CSRF protection to admin panel
- [ ] Implement rate limiting on API endpoints
- [ ] Add persistent job store for APScheduler
- [ ] Create `.env.example` file with all variables
- [ ] Implement comprehensive test suite (unit + integration)
- [ ] Add database migration documentation

## Medium Priority
- [ ] Add CI/CD pipeline (GitHub Actions)
- [ ] Create Docker containerization setup
- [ ] Add health check endpoint for monitoring
- [ ] Implement WebSocket for real-time admin panel updates
- [ ] Add audit log viewer in admin panel
- [ ] Create API documentation (OpenAPI/Swagger)
- [ ] Add Prometheus metrics export

## Low Priority
- [ ] OAuth login for admin panel
- [ ] Multi-timezone support (currently IST only)
- [ ] Reminder templates/presets
- [ ] Bulk reminder operations
- [ ] Export reminders to CSV/JSON
- [ ] Email notifications (in addition to Slack)
- [ ] Mobile-responsive admin panel improvements

## Documentation
- [ ] API endpoint documentation
- [ ] Deployment guide (various platforms)
- [ ] Contributing guidelines
- [ ] Troubleshooting guide
- [ ] Architecture decision records (ADR)

## Infrastructure
- [ ] Database backup automation
- [ ] Log rotation configuration
- [ ] Monitoring dashboard (Grafana)
- [ ] Error tracking (Sentry integration)
- [ ] Performance profiling setup

---

# Quick Reference

## Common Commands

```bash
# Start bot
python run_bot.py

# Start admin panel
python run_admin.py

# Run database migrations
python -m src.database.migrations.migration_manager

# Initialize database
python scripts/setup_db.py

# Check logs (if using systemd)
journalctl -u etc-monitor-bot -f

# Python REPL with imports
python -i -c "from src.services.deadline_service import DeadlineService"
```

## Important File Locations

| What | Where |
|------|-------|
| **HTML Code** | `src/admin/app.py` (inline, lines 157-1243) |
| **CSS Styles** | `src/admin/app.py` (inline in HTML) |
| **JavaScript** | `src/admin/app.py` (inline in HTML) |
| **Templates Folder** | `src/admin/templates/` (empty, ready for migration) |
| **Configuration** | `config/settings.py` |
| **Environment Variables** | `.env` (create from `.env.example`) |
| **Database Schema** | `database_schema.sql` (documentation) |
| **Migrations** | `src/database/migrations/versions/` |
| **Logs** | Console output (structured with emoji) |
| **Deadline Patterns** | `src/parsers/pattern_matcher.py` |
| **API Routes** | `src/admin/routes/` |
| **Slack Handlers** | `src/bot/handlers/` |

## Key URLs

- Admin Panel: `http://localhost:5000`
- Login Page: `http://localhost:5000/login`
- Dashboard: `http://localhost:5000/dashboard`
- Health Check: `http://localhost:5000/health`
- API Base: `http://localhost:5000/api/`

## Useful Queries

```sql
-- Get all pending reminders
SELECT * FROM reminders WHERE status = 'pending';

-- Get reminders for specific user
SELECT * FROM reminders WHERE user_id = 'U12345678';

-- Get today's reminders
SELECT * FROM reminders
WHERE date(reminder_datetime) = date('now');

-- Audit log for reminder
SELECT * FROM audit_logs WHERE reminder_id = 123;
```

---

# Getting Help

- **Documentation**: Read this file and README.md
- **Code Examples**: Check existing services/handlers for patterns
- **Logs**: Use structured logger for debugging
- **Slack API**: https://api.slack.com/docs
- **Gemini API**: https://ai.google.dev/docs
- **Flask Docs**: https://flask.palletsprojects.com/
- **APScheduler**: https://apscheduler.readthedocs.io/

---

**Last Updated**: 2026-01-29
**Project Version**: 2.0 (Refactored modular architecture)
