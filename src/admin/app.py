"""Flask admin panel application."""
from typing import Optional
from flask import Flask, jsonify
from flask_cors import CORS
from config.settings import Settings
from src.admin.routes.health_routes import health_bp
from src.admin.routes.reminder_routes import reminder_bp, init_reminder_routes
from src.utils.logger import get_logger, init_logger


logger = get_logger('AdminApp')


def create_app(settings: Optional[Settings] = None) -> Flask:
    """Create and configure Flask application.

    Args:
        settings: Optional settings instance (creates new if not provided)

    Returns:
        Configured Flask application
    """
    if settings is None:
        settings = Settings()

    # Initialize logger
    init_logger(settings.log_level)
    logger.info('Creating Flask admin application')

    # Create Flask app
    app = Flask(__name__)
    app.secret_key = settings.flask_secret_key

    # Configure CORS
    CORS(app, resources={
        r"/api/*": {"origins": "*"},
        r"/health/*": {"origins": "*"}
    })

    # Initialize reminder routes
    init_reminder_routes(settings)

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(reminder_bp)

    # Root route - Dashboard UI
    @app.route('/')
    def root():
        """Dashboard UI for managing reminders."""
        dashboard_html = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETC Monitor • Admin</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --secondary: #64748b;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
            --shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
            --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
        }
        [data-theme="light"] {
            --background: #f8fafc;
            --surface: #ffffff;
            --surface-secondary: #f1f5f9;
            --border: #e2e8f0;
            --text-primary: #2e2e2f;
            --text-secondary: #64748b;
            --text-muted: #94a3b8;
            --icon-bg-primary: #dbeafe;
            --icon-bg-success: #d1fae5;
            --icon-bg-warning: #fef3c7;
            --icon-bg-danger: #fee2e2;
            --error-bg: #fee2e2;
            --error-text: #991b1b;
        }
        [data-theme="dark"] {
            --background: #2e2e2f;
            --surface: #414141;
            --surface-secondary: #334155;
            --border: #475569;
            --text-primary: #f8fafc;
            --text-secondary: #cbd5e1;
            --text-muted: #94a3b8;
            --icon-bg-primary: rgba(37, 99, 235, 0.2);
            --icon-bg-success: rgba(16, 185, 129, 0.2);
            --icon-bg-warning: rgba(245, 158, 11, 0.2);
            --icon-bg-danger: rgba(239, 68, 68, 0.2);
            --error-bg: rgba(239, 68, 68, 0.2);
            --error-text: #fca5a5;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--background);
            color: var(--text-primary);
            line-height: 1.6;
            font-size: 14px;
        }
        .app { min-height: 100vh; display: flex; flex-direction: column; }
        .header {
            background: var(--surface);
            border-bottom: 1px solid var(--border);
            padding: 0 2rem;
            height: 64px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 50;
        }
        .logo {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-weight: 600;
            font-size: 1.125rem;
            color: var(--text-primary);
        }
        .header-right {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        .theme-toggle {
            padding: 0.5rem;
            background: transparent;
            border: 1px solid transparent;
            border-radius: 8px;
            cursor: pointer;
        }
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            background: var(--success);
            color: white;
            border-radius: 6px;
            font-size: 0.875rem;
            font-weight: 500;
        }
        .status-dot {
            width: 8px;
            height: 8px;
            background: white;
            border-radius: 50%;
        }
        .main {
            flex: 1;
            padding: 1rem;
            margin: 0 auto;
            width: 100%;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.5rem;
            margin-bottom: 1rem;
        }
        .stat-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 7px;
            padding: 1rem;
        }
        .stat-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1rem;
        }
        .stat-title {
            font-size: 0.875rem;
            font-weight: 500;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .stat-icon {
            width: 40px;
            height: 40px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.25rem;
        }
        .stat-icon.primary { background: var(--icon-bg-primary); color: var(--primary); }
        .stat-icon.success { background: var(--icon-bg-success); color: var(--success); }
        .stat-icon.warning { background: var(--icon-bg-warning); color: var(--warning); }
        .stat-icon.danger { background: var(--icon-bg-danger); color: var(--danger); }
        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            color: var(--text-primary);
            line-height: 1;
        }
        .content-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 7px;
            overflow: hidden;
        }
        .content-header {
            padding: 1.5rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .content-title {
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--text-primary);
        }
        .tabs {
            display: flex;
            background: var(--background);
            border-radius: 8px;
            padding: 4px;
            gap: 4px;
        }
        .tab {
            padding: 0.75rem 1.5rem;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 500;
            font-size: 0.875rem;
            color: var(--text-secondary);
            border: none;
            background: transparent;
        }
        .tab.active {
            background: var(--surface);
            color: var(--text-primary);
            box-shadow: var(--shadow-sm);
        }
        .table-container { overflow-x: auto; }
        .data-table {
            width: 100%;
            border-collapse: collapse;
        }
        .data-table th {
            padding: 1rem 1.5rem;
            text-align: left;
            font-weight: 600;
            font-size: 0.875rem;
            color: var(--text-secondary);
            background: var(--background);
            border-bottom: 1px solid var(--border);
            white-space: nowrap;
        }
        .data-table td {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
        }
        .data-table tbody tr { }
        .data-table tbody tr:last-child td { border-bottom: none; }
        .user-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.25rem 0.75rem;
            background: var(--surface-secondary);
            color: var(--text-primary);
            border-radius: 6px;
            font-size: 0.875rem;
            font-weight: 500;
        }
        .user-avatar {
            width: 20px;
            height: 20px;
            background: var(--primary);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.25rem 0.75rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .status-badge.pending { background: rgba(245, 158, 11, 0.1); color: var(--warning); }
        .status-badge.sent { background: rgba(16, 185, 129, 0.1); color: var(--success); }
        .status-badge.cancelled { background: rgba(239, 68, 68, 0.1); color: var(--danger); }
        .status-badge.failed { background: rgba(239, 68, 68, 0.1); color: var(--danger); }
        .status-badge.rescheduled { background: rgba(59, 130, 246, 0.1); color: var(--primary); }
        .status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
        }
        .status-dot.pending { background: var(--warning); }
        .status-dot.sent { background: var(--success); }
        .status-dot.cancelled { background: var(--danger); }
        .status-dot.failed { background: var(--danger); }
        .status-dot.rescheduled { background: var(--primary); }
        .time-stamp {
            color: var(--text-muted);
            font-size: 0.875rem;
            font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
        }
        .message-preview {
            max-width: 300px;
            color: var(--text-secondary);
            font-size: 0.875rem;
            line-height: 1.4;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .action-buttons { display: flex; gap: 0.5rem; }
        .btn {
            padding: 0.375rem 0.75rem;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.8125rem;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }
        .btn-danger {
            background: var(--danger);
            color: white;
        }
        .btn-warning {
            background: var(--warning);
            color: white;
        }
        .empty-state {
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text-muted);
        }
        .empty-state-icon {
            width: 64px;
            height: 64px;
            background: var(--background);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 1rem;
            font-size: 1.5rem;
        }
        .empty-state h3 {
            font-size: 1.125rem;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
        }
        .loading {
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
        }
        .error {
            background: var(--error-bg);
            color: var(--error-text);
            padding: 1rem;
            border-radius: 8px;
            margin: 1rem;
        }
    </style>
</head>
<body>
    <div class="app">
        <header class="header">
            <div class="logo">
                <span>ETC Monitor</span>
            </div>
            <div class="header-right">
                <button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" id="theme-icon">
                        <path d="M10.41 13.28C7.332 10.205 6.716 5.693 8.357 2c-1.23.41-2.256 1.23-3.281 2.256a10.399 10.399 0 0 0 0 14.768c4.102 4.102 10.46 3.897 14.562-.205 1.026-1.026 1.846-2.051 2.256-3.282-3.896 1.436-8.409.82-11.486-2.256Z" fill="currentColor" fill-opacity=".16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
                <div class="status-indicator">
                    <div class="status-dot"></div>
                    <span>System Online</span>
                </div>
            </div>
        </header>

        <main class="main">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-header">
                        <span class="stat-title">Total Reminders</span>
                        <div class="stat-icon primary">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <line x1="18" y1="20" x2="18" y2="10"></line>
                                <line x1="12" y1="20" x2="12" y2="4"></line>
                                <line x1="6" y1="20" x2="6" y2="14"></line>
                            </svg>
                        </div>
                    </div>
                    <div class="stat-value" id="total">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-header">
                        <span class="stat-title">Pending</span>
                        <div class="stat-icon warning">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <circle cx="12" cy="12" r="10"></circle>
                                <polyline points="12 6 12 12 16 14"></polyline>
                            </svg>
                        </div>
                    </div>
                    <div class="stat-value" id="pending">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-header">
                        <span class="stat-title">Sent</span>
                        <div class="stat-icon success">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"></polyline>
                            </svg>
                        </div>
                    </div>
                    <div class="stat-value" id="sent">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-header">
                        <span class="stat-title">Cancelled</span>
                        <div class="stat-icon danger">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <line x1="18" y1="6" x2="6" y2="18"></line>
                                <line x1="6" y1="6" x2="18" y2="18"></line>
                            </svg>
                        </div>
                    </div>
                    <div class="stat-value" id="cancelled">-</div>
                </div>
            </div>

            <div class="content-card">
                <div class="content-header">
                    <h2 class="content-title">Reminder Management</h2>
                    <div style="display: flex; gap: 1rem; align-items: center;">
                        <div class="tabs">
                            <button class="tab active" onclick="showTab('all')">All Reminders</button>
                            <button class="tab" onclick="showTab('pending')">Pending Only</button>
                        </div>
                    </div>
                </div>

                <div class="table-container">
                    <div id="all-tab">
                        <div id="loading" class="loading">Loading reminders...</div>
                        <div id="error" class="error" style="display:none;"></div>
                        <table class="data-table" id="remindersTable" style="display:none;">
                            <thead>
                                <tr>
                                    <th>User</th>
                                    <th>Channel</th>
                                    <th>Message</th>
                                    <th>Deadline</th>
                                    <th>Reminder Time</th>
                                    <th>Status</th>
                                    <th>Created</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody id="remindersBody">
                            </tbody>
                        </table>
                    </div>
                    <div id="pending-tab" style="display:none;">
                        <div id="loading-pending" class="loading">Loading pending reminders...</div>
                        <table class="data-table" id="pendingTable" style="display:none;">
                            <thead>
                                <tr>
                                    <th>User</th>
                                    <th>Channel</th>
                                    <th>Message</th>
                                    <th>Deadline</th>
                                    <th>Reminder Time</th>
                                    <th>Created</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody id="pendingBody">
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <script>
        let allReminders = [];
        let currentTab = 'all';

        function getSystemTheme() {
            return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }

        function setTheme(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
            const icon = document.getElementById('theme-icon');
            if (theme === 'dark') {
                icon.innerHTML = '<path d="M12 2a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0V3a1 1 0 0 1 1-1zm7.071 2.929a1 1 0 0 1 0 1.414l-.707.707a1 1 0 1 1-1.414-1.414l.707-.707a1 1 0 0 1 1.414 0zm-14.142 0a1 1 0 0 1 1.414 0l.707.707A1 1 0 0 1 5.636 7.05l-.707-.707a1 1 0 0 1 0-1.414zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm-6 4a6 6 0 1 1 12 0 6 6 0 0 1-12 0zm-4 0a1 1 0 0 1 1-1h1a1 1 0 1 1 0 2H3a1 1 0 0 1-1-1zm17 0a1 1 0 0 1 1-1h1a1 1 0 1 1 0 2h-1a1 1 0 0 1-1-1zM5.636 16.95a1 1 0 0 1 1.414 1.414l-.707.707a1 1 0 0 1-1.414-1.414l.707-.707zm11.314 1.414a1 1 0 0 1 1.414-1.414l.707.707a1 1 0 0 1-1.414 1.414l-.707-.707zM12 19a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1z" fill="currentColor"/>';
            } else {
                icon.innerHTML = '<path d="M10.41 13.28C7.332 10.205 6.716 5.693 8.357 2c-1.23.41-2.256 1.23-3.281 2.256a10.399 10.399 0 0 0 0 14.768c4.102 4.102 10.46 3.897 14.562-.205 1.026-1.026 1.846-2.051 2.256-3.282-3.896 1.436-8.409.82-11.486-2.256Z" fill="currentColor" fill-opacity=".16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>';
            }
        }

        function toggleTheme() {
            const current = localStorage.getItem('theme') || getSystemTheme();
            setTheme(current === 'dark' ? 'light' : 'dark');
        }

        function showTab(tabName) {
            currentTab = tabName;
            document.getElementById('all-tab').style.display = tabName === 'all' ? 'block' : 'none';
            document.getElementById('pending-tab').style.display = tabName === 'pending' ? 'block' : 'none';
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            if (tabName === 'pending') {
                loadPendingReminders();
            } else {
                loadReminders();
            }
        }

        function formatDate(dateStr) {
            if (!dateStr) return '-';
            try {
                const date = new Date(dateStr);
                if (isNaN(date.getTime())) return '-';
                return date.toLocaleString();
            } catch (e) {
                return '-';
            }
        }

        function getUserInitial(userId, userName) {
            // Use first letter of name if available, otherwise use first letter of ID
            if (userName && userName !== '-' && userName !== userId) {
                return userName.charAt(0).toUpperCase();
            }
            if (userId && userId !== '-') {
                return userId.charAt(0).toUpperCase();
            }
            return '?';
        }

        function formatUserName(reminder) {
            if (reminder.user_name && reminder.user_name !== reminder.user_id && reminder.user_name !== '-') {
                return reminder.user_name;
            }
            if (reminder.user_id && reminder.user_id !== '-') {
                return reminder.user_id;
            }
            return '-';
        }

        function formatChannelName(reminder) {
            let channelName = reminder.channel_name || reminder.channel_id || '-';
            // Remove # if already present, we'll add it in display
            if (channelName.startsWith('#')) {
                channelName = channelName.substring(1);
            }
            return channelName;
        }

        function createReminderRow(reminder) {
            const row = document.createElement('tr');
            const status = reminder.status || 'pending';
            const statusClass = status.toLowerCase();

            const messageText = reminder.deadline_text || '-';
            const escapedMessage = messageText.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
            const userName = formatUserName(reminder);
            const channelName = formatChannelName(reminder);
            row.innerHTML = `
                <td>
                    <div class="user-badge">
                        <div class="user-avatar">${getUserInitial(reminder.user_id, reminder.user_name)}</div>
                        <span>${userName}</span>
                    </div>
                </td>
                <td><span>#${channelName}</span></td>
                <td><div class="message-preview" title="${escapedMessage}">${escapedMessage.substring(0, 40)}${messageText.length > 40 ? '...' : ''}</div></td>
                <td><span class="time-stamp">${formatDate(reminder.deadline_datetime)}</span></td>
                <td><span class="time-stamp">${formatDate(reminder.reminder_datetime)}</span></td>
                <td>
                    <span class="status-badge ${statusClass}">
                        <span class="status-dot ${statusClass}"></span>
                        ${status}
                    </span>
                </td>
                <td><span class="time-stamp">${formatDate(reminder.created_at)}</span></td>
                <td>
                    <div class="action-buttons">
                        ${status === 'pending' ? `<button class="btn btn-warning" onclick="cancelReminder(${reminder.id})">Cancel</button>` : ''}
                    </div>
                </td>
            `;
            return row;
        }

        function loadReminders() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('error').style.display = 'none';
            document.getElementById('remindersTable').style.display = 'none';

            fetch('/api/reminders?limit=500')
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => {
                        throw new Error(err.error || 'Failed to load reminders');
                    }).catch(() => {
                        throw new Error('Failed to load reminders (HTTP ' + response.status + ')');
                    });
                }
                return response.json();
            })
            .then(data => {
                document.getElementById('loading').style.display = 'none';
                document.getElementById('remindersTable').style.display = 'table';

                const tbody = document.getElementById('remindersBody');
                tbody.innerHTML = '';

                if (!data.reminders || data.reminders.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-muted);">No reminders found</td></tr>';
                    updateStats({total: 0, pending: 0, sent: 0, cancelled: 0});
                    return;
                }

                allReminders = data.reminders;
                data.reminders.forEach(reminder => {
                    tbody.appendChild(createReminderRow(reminder));
                });

                updateStats(data);
            })
            .catch(error => {
                document.getElementById('loading').style.display = 'none';
                document.getElementById('error').style.display = 'block';
                document.getElementById('error').textContent = 'Error: ' + error.message;
            });
        }

        function loadPendingReminders() {
            document.getElementById('loading-pending').style.display = 'block';
            document.getElementById('pendingTable').style.display = 'none';

            fetch('/api/reminders?status=pending&limit=500')
            .then(response => response.json())
            .then(data => {
                document.getElementById('loading-pending').style.display = 'none';
                document.getElementById('pendingTable').style.display = 'table';

                const tbody = document.getElementById('pendingBody');
                tbody.innerHTML = '';

                if (!data.reminders || data.reminders.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;color:var(--text-muted);">No pending reminders</td></tr>';
                    return;
                }

                data.reminders.forEach(reminder => {
                    const row = document.createElement('tr');
                    const messageText = reminder.deadline_text || '-';
                    const escapedMessage = messageText.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
                    const userName = formatUserName(reminder);
                    const channelName = formatChannelName(reminder);
                    row.innerHTML = `
                        <td>
                            <div class="user-badge">
                                <div class="user-avatar">${getUserInitial(reminder.user_id, reminder.user_name)}</div>
                                <span>${userName}</span>
                            </div>
                        </td>
                        <td><span>#${channelName}</span></td>
                        <td><div class="message-preview" title="${escapedMessage}">${escapedMessage.substring(0, 40)}${messageText.length > 40 ? '...' : ''}</div></td>
                        <td><span class="time-stamp">${formatDate(reminder.deadline_datetime)}</span></td>
                        <td><span class="time-stamp">${formatDate(reminder.reminder_datetime)}</span></td>
                        <td><span class="time-stamp">${formatDate(reminder.created_at)}</span></td>
                        <td>
                            <div class="action-buttons">
                                <button class="btn btn-warning" onclick="cancelReminder(${reminder.id})">Cancel</button>
                            </div>
                        </td>
                    `;
                    tbody.appendChild(row);
                });
            })
            .catch(error => {
                document.getElementById('loading-pending').style.display = 'none';
                console.error('Error loading pending reminders:', error);
            });
        }

        function updateStats(data) {
            // Use API stats if available (accurate counts from database)
            // Otherwise fall back to counting returned reminders
            if (data.stats) {
                // Use accurate stats from API
                document.getElementById('total').textContent = data.total || 0;
                document.getElementById('pending').textContent = data.stats.pending || 0;
                document.getElementById('sent').textContent = data.stats.sent || 0;
                document.getElementById('cancelled').textContent = (data.stats.cancelled || 0) + (data.stats.failed || 0);
            } else {
                // Fallback: count from returned reminders (less accurate with pagination)
                const reminders = data.reminders || [];
                const stats = {
                    total: data.total !== undefined ? data.total : reminders.length,
                    pending: reminders.filter(r => (r.status || '').toLowerCase() === 'pending').length,
                    sent: reminders.filter(r => (r.status || '').toLowerCase() === 'sent').length,
                    cancelled: reminders.filter(r => (r.status || '').toLowerCase() === 'cancelled').length,
                    failed: reminders.filter(r => (r.status || '').toLowerCase() === 'failed').length
                };
                document.getElementById('total').textContent = stats.total;
                document.getElementById('pending').textContent = stats.pending;
                document.getElementById('sent').textContent = stats.sent;
                document.getElementById('cancelled').textContent = stats.cancelled + stats.failed;
            }
        }

        function cancelReminder(id) {
            if (!confirm('Are you sure you want to cancel this reminder?')) return;

            fetch('/api/reminders/' + encodeURIComponent(id) + '/cancel', {
                method: 'POST'
            })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => {
                        throw new Error(err.error || 'Failed to cancel reminder');
                    });
                }
                return response.json();
            })
            .then(data => {
                alert('Reminder cancelled successfully');
                if (currentTab === 'pending') {
                    loadPendingReminders();
                } else {
                    loadReminders();
                }
            })
            .catch(error => {
                alert('Error cancelling reminder: ' + (error.message || 'Unknown error'));
            });
        }

        // Initialize theme
        const storedTheme = localStorage.getItem('theme') || getSystemTheme();
        setTheme(storedTheme);

        // Load on page load
        loadReminders();
        // Auto-refresh every 10 seconds for better responsiveness
        setInterval(() => {
            if (currentTab === 'all') loadReminders();
            else loadPendingReminders();
        }, 10000);
    </script>
</body>
</html>
        '''
        return dashboard_html, 200, {'Content-Type': 'text/html; charset=utf-8'}

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 errors."""
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        logger.error(f'Internal server error: {error}', exc=error)
        return jsonify({'error': 'Internal server error'}), 500

    @app.errorhandler(401)
    def unauthorized(error):
        """Handle 401 errors."""
        return jsonify({'error': 'Unauthorized'}), 401

    logger.success('Flask admin application created')

    return app


def main():
    """Main entry point for admin panel."""
    try:
        # Load settings
        settings = Settings()

        # Create app
        app = create_app(settings)

        # Get port from environment or default
        import os
        port = int(os.environ.get('ADMIN_PORT', 5000))
        debug = settings.debug

        logger.info(f'Starting admin panel on port {port} (debug={debug})')

        # Run app
        app.run(host='0.0.0.0', port=port, debug=debug)

    except Exception as e:
        logger.error(f'Fatal error starting admin panel: {e}', exc=e)
        raise


if __name__ == "__main__":
    main()
