# ETC Monitor - Slack Bot

A Slack bot that automatically detects and tracks "ETC" (Estimated Time of Completion) deadlines from thread replies, sending reminders to users before their deadlines.

## 🎯 Features

- **Automatic Deadline Detection**: Detects ETC deadlines from Slack thread replies using AI (Gemini) or regex fallback
- **Smart Reminder Scheduling**: Automatically schedules reminders 1 hour before deadlines (or 5 minutes for deadlines within 1 hour)
- **Reschedule Support**: Automatically updates reminders when users post new ETCs in the same thread
- **Slash Commands**:
  - `/my-reminders` - List your active reminders
  - `/cancel-reminder <id>` - Cancel a specific reminder
  - `/list-thread-reminders` - List all reminders in current thread
- **Admin Panel**: Web-based admin interface for managing reminders and viewing audit logs
- **Audit Logging**: Complete audit trail of all reminder operations
- **IST Timezone**: All operations use Asia/Kolkata timezone

## 📋 Prerequisites

- Python 3.8+
- Slack Workspace with Bot Token, Signing Secret, and App Token
- (Optional) Google Gemini API key for AI-powered deadline parsing

## 🚀 Quick Start

### 1. Clone and Install

```bash
cd etc-moniter
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your Slack tokens and optional Gemini API key:

```env
SLACK_BOT_TOKEN=xoxb-your-actual-token
SLACK_SIGNING_SECRET=your-actual-secret
SLACK_APP_TOKEN=xapp-your-actual-token
GEMINI_API_KEY=your-api-key  # Optional
```

### 3. Setup Database

Initialize the database and run migrations:

```bash
python scripts/setup_db.py
```

### 4. Run the Bot

Start the Slack bot:

```bash
python run_bot.py
```

### 5. Run Admin Panel (Optional)

In a separate terminal, start the admin panel:

```bash
python run_admin.py
```

The admin panel will be available at `http://localhost:5000` (or the port specified in `ADMIN_PORT`).

## 📁 Project Structure

```
etc-moniter/
├── src/
│   ├── bot/              # Slack bot application
│   │   ├── app.py        # Bot entry point
│   │   ├── handlers/     # Message and command handlers
│   │   └── scheduler/    # Reminder scheduling
│   ├── admin/            # Admin panel (Flask)
│   │   ├── app.py        # Admin entry point
│   │   ├── routes/       # API routes
│   │   └── middleware/   # Auth middleware
│   ├── services/         # Business logic services
│   ├── parsers/          # Deadline parsing (AI + regex)
│   ├── database/         # Database layer
│   │   ├── repositories/ # Data access
│   │   └── migrations/   # Schema migrations
│   ├── core/             # Core models
│   └── utils/            # Utilities (logger, timezone)
├── config/               # Configuration
├── scripts/              # Setup scripts
├── tests/                # Test suite
├── run_bot.py            # Bot entry point
├── run_admin.py          # Admin entry point
└── requirements.txt      # Dependencies
```

## ⚙️ Configuration

All configuration is done via environment variables in `.env`:

### Required Settings

- `SLACK_BOT_TOKEN` - Slack bot token (starts with `xoxb-`)
- `SLACK_SIGNING_SECRET` - Slack signing secret
- `SLACK_APP_TOKEN` - Slack app token (starts with `xapp-`)
- `FLASK_SECRET_KEY` - Secret key for Flask sessions

### Optional Settings

- `GEMINI_API_KEY` - Google Gemini API key (enables AI parsing)
- `GEMINI_MODEL` - Gemini model to use (default: `gemini-1.5-flash`)
- `GEMINI_TEMPERATURE` - Gemini temperature (default: `0.2`)
- `DATABASE_PATH` - Path to SQLite database (default: `reminders.db`)
- `ADMIN_USERNAME` - Admin panel username (default: `admin`)
- `ADMIN_PASSWORD` - Admin panel password (default: `changeme`)
- `ADMIN_PORT` - Admin panel port (default: `5000`)
- `TIMEZONE` - Application timezone (default: `Asia/Kolkata`)
- `DEBUG` - Enable debug mode (default: `false`)
- `LOG_LEVEL` - Logging level: DEBUG, INFO, WARNING, ERROR (default: `INFO`)

## 🎮 Usage

### Creating Reminders

Simply reply to a message in a Slack thread with an ETC deadline:

```
User: "Can you review this PR?"
You: "ETC: tomorrow 5pm"
```

The bot will:
1. Detect the ETC deadline
2. Create a reminder
3. Schedule a notification for 1 hour before the deadline
4. Send a confirmation message

### Supported Deadline Formats

The bot supports many natural language formats:

- **Relative time**: "ETC: 2 hours", "ETC: in 30 minutes"
- **Time of day**: "ETC: 5pm", "ETC: 17:00", "ETC: morning"
- **Days**: "ETC: tomorrow", "ETC: Monday", "ETC: next Friday"
- **EOD**: "ETC: eod", "ETC: end of day", "ETC: tomorrow eod"
- **Specific dates**: "ETC: 15th Jan", "ETC: Jan 15 at 3pm"
- **Combinations**: "ETC: Monday 5pm", "ETC: tomorrow at 3:30"

### Rescheduling

If you post a new ETC in the same thread, the bot automatically reschedules your existing reminder:

```
You: "ETC: 5pm today"
Bot: "✅ Reminder created! Deadline: 5:00 PM IST"

You: "ETC: 6pm today"  # Same thread
Bot: "✅ Reminder updated! Previous: 5:00 PM → New: 6:00 PM IST"
```

### Slash Commands

- `/my-reminders` - List all your active reminders
- `/cancel-reminder <id>` - Cancel a reminder by ID
- `/list-thread-reminders` - List all reminders in the current thread

## 🔧 Development

### Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_models.py
```

### Database Migrations

Migrations are automatically run on startup. To manually run migrations:

```bash
python scripts/setup_db.py
```

### Project Architecture

The project follows a layered architecture:

1. **Bot Layer** (`src/bot/`) - Slack event handling and scheduling
2. **Service Layer** (`src/services/`) - Business logic
3. **Parser Layer** (`src/parsers/`) - Deadline detection and parsing
4. **Database Layer** (`src/database/`) - Data persistence
5. **Admin Layer** (`src/admin/`) - Web interface

### Code Style

- Use `print()` for logging (via `src.utils.logger`)
- Use `sqlite3` directly (not SQLAlchemy ORM)
- All datetimes in IST timezone
- AI-first parsing with regex fallback

## 📊 Admin Panel

The admin panel provides a REST API for managing reminders:

### Health Checks

- `GET /health` - Basic health check
- `GET /health/db` - Database connectivity
- `GET /health/slack` - Slack API connectivity

### Reminder Management

- `GET /api/reminders` - List all reminders (with filters)
- `GET /api/reminders/<id>` - Get single reminder
- `PUT /api/reminders/<id>` - Update reminder
- `DELETE /api/reminders/<id>` - Delete reminder
- `POST /api/reminders/<id>/cancel` - Cancel reminder
- `GET /api/reminders/user/<user_id>` - Get user's reminders
- `GET /api/reminders/channel/<channel_id>` - Get channel reminders
- `GET /api/audit/<reminder_id>` - Get audit log

All API endpoints require HTTP Basic Authentication using `ADMIN_USERNAME` and `ADMIN_PASSWORD`.

## 🐛 Troubleshooting

### Bot not responding

1. Check that `SLACK_APP_TOKEN` is correct and has `connections:write` scope
2. Verify bot is invited to the channel
3. Check logs for errors

### Reminders not being created

1. Ensure message is a thread reply (not a top-level message)
2. Check that message contains "ETC:" or "etc" format
3. Verify deadline parsing is working (check logs)

### Database errors

1. Ensure database file is writable
2. Run migrations: `python scripts/setup_db.py`
3. Check database path in `.env`

## 📝 License

This project is for internal use.

## 🤝 Contributing

1. Follow the existing code style
2. Add tests for new features
3. Update documentation
4. Use the logger utility for all logging

## 📚 Additional Resources

- [Slack Bolt Framework](https://slack.dev/bolt-python/)
- [APScheduler Documentation](https://apscheduler.readthedocs.io/)
- [Flask Documentation](https://flask.palletsprojects.com/)

---

**Note**: This bot requires Socket Mode to be enabled in your Slack app configuration.
