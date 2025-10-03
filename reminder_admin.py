from flask import Flask, render_template_string, request, redirect, url_for, flash, send_from_directory
import sqlite3
from datetime import datetime
import pytz
import os
from slack_sdk import WebClient

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# Initialize Slack client
slack_token = os.environ.get('SLACK_BOT_TOKEN')
slack_client = WebClient(token=slack_token) if slack_token else None

# Cache for user and channel names
user_cache = {}
channel_cache = {}

def get_user_name(user_id):
    """Get user display name from Slack API"""
    if not slack_client:
        return user_id

    if user_id in user_cache:
        return user_cache[user_id]

    try:
        response = slack_client.users_info(user=user_id)
        if response['ok']:
            user_info = response['user']
            # Try to get display name, real name, or fallback to username
            display_name = user_info.get('profile', {}).get('display_name')
            real_name = user_info.get('profile', {}).get('real_name')
            username = user_info.get('name')

            name = display_name or real_name or username or user_id
            user_cache[user_id] = name
            return name
    except Exception as e:
        print(f"Error fetching user info for {user_id}: {e}")

    user_cache[user_id] = user_id
    return user_id

def get_channel_name(channel_id):
    """Get channel name from Slack API"""
    if not slack_client:
        return channel_id

    if channel_id in channel_cache:
        return channel_cache[channel_id]

    try:
        response = slack_client.conversations_info(channel=channel_id)
        if response['ok']:
            channel_info = response['channel']
            name = channel_info.get('name', channel_id)
            # Add # prefix for channels
            if not name.startswith('#'):
                name = f"#{name}"
            channel_cache[channel_id] = name
            return name
    except Exception as e:
        print(f"Error fetching channel info for {channel_id}: {e}")

    channel_cache[channel_id] = channel_id
    return channel_id

def format_datetime(datetime_str):
    """Format datetime string to readable format with AM/PM"""
    try:
        # Parse the datetime string
        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        # Format as "YYYY-MM-DD HH:MM:SS AM/PM"
        return dt.strftime('%Y-%m-%d %I:%M:%S %p')
    except Exception as e:
        print(f"Error formatting datetime {datetime_str}: {e}")
        return datetime_str

# Database helper functions
def get_db_connection():
    conn = sqlite3.connect('reminders.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_all_reminders():
    conn = get_db_connection()
    reminders = conn.execute('''
        SELECT * FROM reminders
        ORDER BY created_at DESC
    ''').fetchall()
    conn.close()
    return reminders

def get_active_reminders():
    conn = get_db_connection()
    reminders = conn.execute('''
        SELECT * FROM reminders
        WHERE is_active = 1 AND due_at > datetime('now')
        ORDER BY due_at ASC
    ''').fetchall()
    conn.close()
    return reminders

def delete_reminder(reminder_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM reminders WHERE id = ?', (reminder_id,))
    conn.commit()
    conn.close()

def deactivate_reminder(reminder_id):
    conn = get_db_connection()
    conn.execute('UPDATE reminders SET is_active = 0 WHERE id = ?', (reminder_id,))
    conn.commit()
    conn.close()

# HTML Template
HTML_TEMPLATE = '''
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

        /* Light Theme (Default) */
        [data-theme="light"] {
            --background: #f8fafc;
            --surface: #ffffff;
            --surface-secondary: #f1f5f9;
            --border: #e2e8f0;
            --border-light: #f1f5f9;
            --text-primary: #0f172a;
            --text-secondary: #64748b;
            --text-muted: #94a3b8;
            --text-inverse: #ffffff;
            --hover-bg: #f1f5f9;
            --active-bg: #e2e8f0;
        }

        /* Dark Theme */
        [data-theme="dark"] {
            --background: #0f172a;
            --surface: #1e293b;
            --surface-secondary: #334155;
            --border: #475569;
            --border-light: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #cbd5e1;
            --text-muted: #94a3b8;
            --text-inverse: #0f172a;
            --hover-bg: #334155;
            --active-bg: #475569;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--background);
            color: var(--text-primary);
            line-height: 1.6;
            font-size: 14px;
        }

        .app {
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

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

        .header-left {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 0.25rem;
            font-weight: 600;
            font-size: 1.125rem;
            color: var(--text-primary);
        }

        .logo-icon {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            background-image: url('etc.jpg');
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .theme-toggle {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem;
            background: var(--surface-secondary);
            border: 1px solid transparent;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .theme-toggle:hover {
            background: var(--hover-bg);
            transform: translateY(-1px);
        }

        .theme-icon {
            width: 20px;
            height: 20px;
            fill: var(--text-secondary);
            transition: all 0.2s;
        }

        .theme-toggle:hover .theme-icon {
            fill: var(--text-primary);
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
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .main {
            flex: 1;
            padding: 1rem;
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }

        .stat-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1rem;
            transition: all 0.2s;
        }

        .stat-card:hover {
            box-shadow: var(--shadow);
            transform: translateY(-1px);
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

        .stat-icon.primary { background: #dbeafe; color: var(--primary); }
        .stat-icon.success { background: #d1fae5; color: var(--success); }
        .stat-icon.warning { background: #fef3c7; color: var(--warning); }

        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            color: var(--text-primary);
            line-height: 1;
        }

        .content-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
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
            transition: all 0.2s;
            color: var(--text-secondary);
            border: none;
            background: transparent;
        }

        .tab.active {
            background: var(--surface);
            color: var(--text-primary);
            box-shadow: var(--shadow-sm);
        }

        .tab:hover:not(.active) {
            color: var(--text-primary);
        }

        .table-container {
            overflow-x: auto;
        }

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

        .data-table tbody tr {
            transition: background-color 0.2s;
        }

        .data-table tbody tr:hover {
            background: var(--background);
        }

        .data-table tbody tr:last-child td {
            border-bottom: none;
        }

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

        .status-badge.active {
            background: rgba(16, 185, 129, 0.1);
            color: var(--success);
        }

        .status-badge.inactive {
            background: rgba(239, 68, 68, 0.1);
            color: var(--danger);
        }

        .status-badge.expired {
            background: rgba(245, 158, 11, 0.1);
            color: var(--warning);
        }

        .status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
        }

        .status-dot.active { background: var(--success); }
        .status-dot.inactive { background: var(--danger); }
        .status-dot.expired { background: var(--warning); }

        .message-preview {
            max-width: 300px;
            color: var(--text-secondary);
            font-size: 0.875rem;
            line-height: 1.4;
        }

        .time-stamp {
            color: var(--text-muted);
            font-size: 0.875rem;
            font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
        }

        .action-buttons {
            display: flex;
            gap: 0.5rem;
        }

        .btn {
            padding: 0.5rem;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.7rem;
            font-weight: 500;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }

        .btn-sm {
            padding: 0.375rem 0.75rem;
            font-size: 0.8125rem;
        }

        .btn-outline {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-secondary);
        }

        .btn-outline:hover {
            background: var(--background);
            color: var(--text-primary);
        }

        .btn-danger {
            background: var(--danger);
            color: white;
        }

        .btn-danger:hover {
            background: #dc2626;
        }

        .btn-warning {
            background: var(--warning);
            color: white;
        }

        .btn-warning:hover {
            background: #d97706;
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

        .empty-state p {
            font-size: 0.875rem;
            color: var(--text-muted);
        }

        .notification {
            position: fixed;
            top: 1rem;
            right: 1rem;
            background: var(--success);
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            box-shadow: var(--shadow-lg);
            z-index: 1000;
            transform: translateX(100%);
            transition: transform 0.3s ease;
        }

        .notification.show {
            transform: translateX(0);
        }

        .loading {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid var(--border);
            border-radius: 50%;
            border-top-color: var(--primary);
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="app">
        <header class="header">
            <div class="header-left">
                <div class="logo">
                    <div class="logo-icon"></div>
                    <span>ETC Monitor</span>
                </div>
            </div>
            <div class="header-right">
                <button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme">
                    <svg class="theme-icon" id="theme-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
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
            {% with messages = get_flashed_messages() %}
                {% if messages %}
                    <div class="notification show" id="notification">
                        {{ messages[0] }}
                    </div>
                {% endif %}
            {% endwith %}

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-header">
                        <span class="stat-title">Total Reminders</span>
                        <div class="stat-icon primary">📊</div>
                    </div>
                    <div class="stat-value">{{ total_reminders }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-header">
                        <span class="stat-title">Active Reminders</span>
                        <div class="stat-icon success">⚡</div>
                    </div>
                    <div class="stat-value">{{ active_reminders }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-header">
                        <span class="stat-title">Expired Reminders</span>
                        <div class="stat-icon warning">⏰</div>
                    </div>
                    <div class="stat-value">{{ expired_reminders }}</div>
                </div>
            </div>

            <div class="content-card">
                <div class="content-header">
                    <h2 class="content-title">Reminder Management</h2>
                    <div class="tabs">
                        <button class="tab active" onclick="showTab('all')">All Reminders</button>
                        <button class="tab" onclick="showTab('active')">Active Only</button>
                    </div>
                </div>

                <div class="table-container">
                    <div id="all-tab">
                        {% if all_reminders %}
                            <table class="data-table">
                                <thead>
                                    <tr>
                                        <th>User</th>
                                        <th>Channel</th>
                                        <th>Message</th>
                                        <th>Due At</th>
                                        <th>Status</th>
                                        <th>Created</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for reminder in all_reminders %}
                                    <tr>
                                        <td>
                                            <div class="user-badge">
                                                <div class="user-avatar">{{ get_user_name(reminder.user_id)[0].upper() }}</div>
                                                <span>{{ get_user_name(reminder.user_id) }}</span>
                                            </div>
                                        </td>
                                        <td>
                                            <code class="time-stamp">{{ get_channel_name(reminder.channel_id) }}</code>
                                        </td>
                                        <td>
                                            <div class="message-preview">{{ reminder.original_text[:60] }}{% if reminder.original_text|length > 60 %}...{% endif %}</div>
                                        </td>
                                        <td>
                                            <span class="time-stamp">{{ format_datetime(reminder.due_at) }}</span>
                                        </td>
                                        <td>
                                            {% if reminder.is_active == 1 %}
                                                {% set due_time = reminder.due_at|replace('T', ' ')|replace('+05:30', '') %}
                                                {% if due_time > now %}
                                                    <span class="status-badge active">
                                                        <span class="status-dot active"></span>
                                                        Active
                                                    </span>
                                                {% else %}
                                                    <span class="status-badge expired">
                                                        <span class="status-dot expired"></span>
                                                        Expired
                                                    </span>
                                                {% endif %}
                                            {% else %}
                                                <span class="status-badge inactive">
                                                    <span class="status-dot inactive"></span>
                                                    Inactive
                                                </span>
                                            {% endif %}
                                        </td>
                                        <td>
                                            <span class="time-stamp">{{ format_datetime(reminder.created_at) }}</span>
                                        </td>
                                        <td>
                                            <div class="action-buttons">
                                                {% if reminder.is_active == 1 %}
                                                    <button class="btn btn-sm btn-warning" onclick="deactivateReminder('{{ reminder.id }}')">
                                                        Pause
                                                    </button>
                                                {% endif %}
                                                <button class="btn btn-sm btn-danger" onclick="deleteReminder('{{ reminder.id }}')">
                                                    Delete
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        {% else %}
                            <div class="empty-state">
                                <div class="empty-state-icon">📝</div>
                                <h3>No reminders found</h3>
                                <p>Create some ETC reminders in Slack to see them here!</p>
                            </div>
                        {% endif %}
                    </div>

                    <div id="active-tab" style="display: none;">
                        {% if active_reminders_list %}
                            <table class="data-table">
                                <thead>
                                    <tr>
                                        <th>User</th>
                                        <th>Channel</th>
                                        <th>Message</th>
                                        <th>Due At</th>
                                        <th>Created</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for reminder in active_reminders_list %}
                                    <tr>
                                        <td>
                                            <div class="user-badge">
                                                <div class="user-avatar">{{ get_user_name(reminder.user_id)[0].upper() }}</div>
                                                <span>{{ get_user_name(reminder.user_id) }}</span>
                                            </div>
                                        </td>
                                        <td>
                                            <code class="time-stamp">{{ get_channel_name(reminder.channel_id) }}</code>
                                        </td>
                                        <td>
                                            <div class="message-preview">{{ reminder.original_text[:60] }}{% if reminder.original_text|length > 60 %}...{% endif %}</div>
                                        </td>
                                        <td>
                                            <span class="time-stamp">{{ format_datetime(reminder.due_at) }}</span>
                                        </td>
                                        <td>
                                            <span class="time-stamp">{{ format_datetime(reminder.created_at) }}</span>
                                        </td>
                                        <td>
                                            <div class="action-buttons">
                                                <button class="btn btn-sm btn-warning" onclick="deactivateReminder('{{ reminder.id }}')">
                                                    Pause
                                                </button>
                                                <button class="btn btn-sm btn-danger" onclick="deleteReminder('{{ reminder.id }}')">
                                                    Delete
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        {% else %}
                            <div class="empty-state">
                                <div class="empty-state-icon">✅</div>
                                <h3>No active reminders</h3>
                                <p>All reminders have been completed or deactivated.</p>
                            </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </main>
    </div>

    <script>
        // Global variables
        var allReminders = [];
        var filteredReminders = [];

        // Theme Management
        function getSystemTheme() {
            if (window.matchMedia) {
                return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            }
            return 'light';
        }

        function getStoredTheme() {
            var stored = localStorage.getItem('theme');
            return stored || 'auto';
        }

        function setTheme(theme) {
            var root = document.documentElement;
            var themeIcon = document.getElementById('theme-icon');

            root.setAttribute('data-theme', theme);
            updateThemeIcon(theme);
            localStorage.setItem('theme', theme);
        }

        function updateThemeIcon(theme) {
            var themeIcon = document.getElementById('theme-icon');

            if (theme === 'dark') {
                themeIcon.innerHTML = '<path d="M12 2a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0V3a1 1 0 0 1 1-1zm7.071 2.929a1 1 0 0 1 0 1.414l-.707.707a1 1 0 1 1-1.414-1.414l.707-.707a1 1 0 0 1 1.414 0zm-14.142 0a1 1 0 0 1 1.414 0l.707.707A1 1 0 0 1 5.636 7.05l-.707-.707a1 1 0 0 1 0-1.414zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm-6 4a6 6 0 1 1 12 0 6 6 0 0 1-12 0zm-4 0a1 1 0 0 1 1-1h1a1 1 0 1 1 0 2H3a1 1 0 0 1-1-1zm17 0a1 1 0 0 1 1-1h1a1 1 0 1 1 0 2h-1a1 1 0 0 1-1-1zM5.636 16.95a1 1 0 0 1 1.414 1.414l-.707.707a1 1 0 0 1-1.414-1.414l.707-.707zm11.314 1.414a1 1 0 0 1 1.414-1.414l.707.707a1 1 0 0 1-1.414 1.414l-.707-.707zM12 19a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1z" fill="white"/>';
            } else {
                themeIcon.innerHTML = '<path d="M10.41 13.28C7.332 10.205 6.716 5.693 8.357 2c-1.23.41-2.256 1.23-3.281 2.256a10.399 10.399 0 0 0 0 14.768c4.102 4.102 10.46 3.897 14.562-.205 1.026-1.026 1.846-2.051 2.256-3.282-3.896 1.436-8.409.82-11.486-2.256Z" fill="currentColor" fill-opacity=".16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>';
            }
        }

        function toggleTheme() {
            var currentTheme = getStoredTheme();
            var newTheme;

            if (currentTheme === 'light') {
                newTheme = 'dark';
            } else {
                newTheme = 'light';
            }

            setTheme(newTheme);
        }

        // Tab Management
        function showTab(tabName) {
            document.getElementById('all-tab').style.display = 'none';
            document.getElementById('active-tab').style.display = 'none';

            document.querySelectorAll('.tab').forEach(function(tab) {
                tab.classList.remove('active');
            });

            document.getElementById(tabName + '-tab').style.display = 'block';
            event.target.classList.add('active');
        }

        // Reminder Management
        function deleteReminder(id) {
            if (confirm('Are you sure you want to delete this reminder? This action cannot be undone.')) {
                showLoading();
                fetch('/delete/' + id, {method: 'POST'})
                .then(function() { location.reload(); });
            }
        }

        function deactivateReminder(id) {
            if (confirm('Are you sure you want to pause this reminder?')) {
                showLoading();
                fetch('/deactivate/' + id, {method: 'POST'})
                .then(function() { location.reload(); });
            }
        }

        function showLoading() {
            var buttons = document.querySelectorAll('.btn');
            buttons.forEach(function(btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="loading"></span> Processing...';
            });
        }

        // Auto-hide notifications
        setTimeout(function() {
            var notification = document.getElementById('notification');
            if (notification) {
                notification.classList.remove('show');
                setTimeout(function() {
                    notification.remove();
                }, 300);
            }
        }, 4000);

        // Initialize theme on page load
        document.addEventListener('DOMContentLoaded', function() {
            var storedTheme = getStoredTheme();
            if (storedTheme === 'auto') {
                var systemTheme = getSystemTheme();
                setTheme(systemTheme);
            } else {
                setTheme(storedTheme);
            }

            // Enhanced system theme change listener
            var mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            mediaQuery.addEventListener('change', function() {
                if (getStoredTheme() === 'auto') {
                    var systemTheme = getSystemTheme();
                    setTheme(systemTheme);
                }
            });
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    all_reminders = get_all_reminders()
    active_reminders_list = get_active_reminders()

    # Calculate stats
    total_reminders = len(all_reminders)
    active_reminders = len(active_reminders_list)
    expired_reminders = total_reminders - active_reminders

    # Get current time for comparison
    now = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')

    return render_template_string(HTML_TEMPLATE,
                                all_reminders=all_reminders,
                                active_reminders_list=active_reminders_list,
                                total_reminders=total_reminders,
                                active_reminders=active_reminders,
                                expired_reminders=expired_reminders,
                                now=now,
                                get_user_name=get_user_name,
                                get_channel_name=get_channel_name,
                                format_datetime=format_datetime)

@app.route('/delete/<reminder_id>', methods=['POST'])
def delete_reminder_route(reminder_id):
    delete_reminder(reminder_id)
    flash('Reminder deleted successfully!')
    return redirect(url_for('index'))

@app.route('/deactivate/<reminder_id>', methods=['POST'])
def deactivate_reminder_route(reminder_id):
    deactivate_reminder(reminder_id)
    flash('Reminder deactivated successfully!')
    return redirect(url_for('index'))

@app.route('/etc.jpg')
def serve_logo():
    return send_from_directory('.', 'etc.jpg')

@app.route('/favicon.ico')
def serve_favicon():
    return send_from_directory('.', 'favicon.ico')

if __name__ == '__main__':
    print("🌐 Starting ETC-Monitor Admin Panel...")
    print("📊 Access at: http://localhost:8080")
    app.run(debug=True, host='0.0.0.0', port=8080)
