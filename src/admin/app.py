"""Flask admin panel application with authentication."""
from typing import Optional
from functools import wraps
from flask import Flask, jsonify, request, session, redirect, url_for
from flask_cors import CORS
from config.settings import Settings
from src.admin.routes.health_routes import health_bp
from src.admin.routes.reminder_routes import reminder_bp, init_reminder_routes
from src.utils.logger import get_logger, init_logger


logger = get_logger('AdminApp')

# Global settings reference for auth
_settings: Optional[Settings] = None


def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            # For API routes, return 401
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            # For page routes, redirect to login
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def create_app(settings: Optional[Settings] = None) -> Flask:
    """Create and configure Flask application.

    Args:
        settings: Optional settings instance (creates new if not provided)

    Returns:
        Configured Flask application
    """
    global _settings

    if settings is None:
        settings = Settings()

    _settings = settings

    # Initialize logger
    init_logger(settings.log_level)
    logger.info('Creating Flask admin application')

    # Create Flask app
    app = Flask(__name__)
    app.secret_key = settings.flask_secret_key

    # Configure session
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

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

    # Login page
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Login page and authentication handler."""
        if request.method == 'POST':
            username = request.form.get('username', '')
            password = request.form.get('password', '')

            if username == _settings.admin_username and password == _settings.admin_password:
                session['logged_in'] = True
                session['username'] = username
                session.permanent = True
                logger.info(f'User {username} logged in successfully')
                return redirect(url_for('dashboard'))
            else:
                logger.warning(f'Failed login attempt for user: {username}')
                return get_login_page(error='Invalid username or password')

        return get_login_page()

    # Logout
    @app.route('/logout')
    def logout():
        """Logout and clear session."""
        username = session.get('username', 'unknown')
        session.clear()
        logger.info(f'User {username} logged out')
        return redirect(url_for('login'))

    # Root route - redirect to dashboard or login
    @app.route('/')
    def root():
        """Redirect to dashboard or login."""
        if session.get('logged_in'):
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))

    # Dashboard route (protected)
    @app.route('/dashboard')
    @login_required
    def dashboard():
        """Dashboard UI for managing reminders."""
        return get_dashboard_html(), 200, {'Content-Type': 'text/html; charset=utf-8'}

    # Protect API routes
    @app.before_request
    def check_auth():
        """Check authentication for API routes."""
        # Skip auth for login, logout, health, and static
        public_paths = ['/login', '/logout', '/health', '/static']
        if any(request.path.startswith(p) for p in public_paths):
            return None

        # Check auth for all other routes
        if not session.get('logged_in'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            if request.path != '/':
                return redirect(url_for('login'))

        return None

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


def get_login_page(error: str = None) -> str:
    """Generate login page HTML."""
    error_html = f'<div class="error-message">{error}</div>' if error else ''

    return f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - ETC Monitor</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .login-container {{
            background: white;
            border-radius: 16px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            padding: 40px;
            width: 100%;
            max-width: 400px;
        }}
        .login-header {{
            text-align: center;
            margin-bottom: 32px;
        }}
        .login-logo {{
            width: 64px;
            height: 64px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 16px;
            color: white;
            font-size: 28px;
            font-weight: 700;
        }}
        .login-title {{
            font-size: 24px;
            font-weight: 700;
            color: #1f2937;
            margin-bottom: 8px;
        }}
        .login-subtitle {{
            color: #6b7280;
            font-size: 14px;
        }}
        .form-group {{
            margin-bottom: 20px;
        }}
        .form-label {{
            display: block;
            font-size: 14px;
            font-weight: 500;
            color: #374151;
            margin-bottom: 8px;
        }}
        .form-input {{
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e5e7eb;
            border-radius: 10px;
            font-size: 15px;
            font-family: inherit;
            transition: all 0.2s;
            outline: none;
        }}
        .form-input:focus {{
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }}
        .form-input::placeholder {{
            color: #9ca3af;
        }}
        .login-btn {{
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            font-family: inherit;
        }}
        .login-btn:hover {{
            transform: translateY(-1px);
            box-shadow: 0 10px 20px -10px rgba(102, 126, 234, 0.5);
        }}
        .login-btn:active {{
            transform: translateY(0);
        }}
        .error-message {{
            background: #fef2f2;
            border: 1px solid #fecaca;
            color: #dc2626;
            padding: 12px 16px;
            border-radius: 10px;
            margin-bottom: 20px;
            font-size: 14px;
            text-align: center;
        }}
        .footer-text {{
            text-align: center;
            margin-top: 24px;
            color: #9ca3af;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <div class="login-logo">E</div>
            <h1 class="login-title">ETC Monitor</h1>
            <p class="login-subtitle">Sign in to access the admin dashboard</p>
        </div>

        {error_html}

        <form method="POST" action="/login">
            <div class="form-group">
                <label class="form-label" for="username">Username</label>
                <input type="text" id="username" name="username" class="form-input" placeholder="Enter your username" required autofocus>
            </div>
            <div class="form-group">
                <label class="form-label" for="password">Password</label>
                <input type="password" id="password" name="password" class="form-input" placeholder="Enter your password" required>
            </div>
            <button type="submit" class="login-btn">Sign In</button>
        </form>

        <p class="footer-text">ETC Monitor Admin Panel</p>
    </div>
</body>
</html>
'''


def get_dashboard_html() -> str:
    """Generate dashboard HTML with DataTables."""
    return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETC Monitor - Admin Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.datatables.net/1.13.7/css/jquery.dataTables.min.css">
    <link rel="stylesheet" href="https://cdn.datatables.net/responsive/2.5.0/css/responsive.dataTables.min.css">
    <style>
        :root {
            --primary: #667eea;
            --primary-dark: #5a67d8;
            --secondary: #64748b;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --info: #3b82f6;
            --gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
            --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
            --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);
        }
        [data-theme="light"] {
            --background: #f3f4f6;
            --surface: #ffffff;
            --surface-secondary: #f9fafb;
            --border: #e5e7eb;
            --text-primary: #111827;
            --text-secondary: #6b7280;
            --text-muted: #9ca3af;
            --table-stripe: #f9fafb;
            --table-hover: #f3f4f6;
        }
        [data-theme="dark"] {
            --background: #111827;
            --surface: #1f2937;
            --surface-secondary: #374151;
            --border: #374151;
            --text-primary: #f9fafb;
            --text-secondary: #d1d5db;
            --text-muted: #9ca3af;
            --table-stripe: #1f2937;
            --table-hover: #374151;
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

        /* Header */
        .header {
            background: var(--gradient);
            padding: 0 2rem;
            height: 70px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: var(--shadow-lg);
        }
        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
            color: white;
            font-weight: 700;
            font-size: 1.25rem;
        }
        .logo-icon {
            width: 40px;
            height: 40px;
            background: rgba(255,255,255,0.2);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 1.1rem;
        }
        .header-right {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        .header-btn {
            padding: 8px 16px;
            background: rgba(255,255,255,0.15);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            color: white;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s;
        }
        .header-btn:hover {
            background: rgba(255,255,255,0.25);
        }
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: rgba(16, 185, 129, 0.2);
            border: 1px solid rgba(16, 185, 129, 0.3);
            border-radius: 8px;
            color: white;
            font-size: 13px;
            font-weight: 500;
        }
        .status-dot {
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        /* Main Content */
        .main {
            flex: 1;
            padding: 24px;
            max-width: 1600px;
            margin: 0 auto;
            width: 100%;
        }

        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            align-items: center;
            gap: 16px;
            transition: all 0.2s;
        }
        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow);
        }
        .stat-icon {
            width: 52px;
            height: 52px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
        }
        .stat-icon.total { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .stat-icon.pending { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; }
        .stat-icon.sent { background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; }
        .stat-icon.cancelled { background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); color: white; }
        .stat-content { flex: 1; }
        .stat-value {
            font-size: 28px;
            font-weight: 700;
            color: var(--text-primary);
            line-height: 1;
        }
        .stat-label {
            font-size: 13px;
            font-weight: 500;
            color: var(--text-secondary);
            margin-top: 4px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        /* Content Card */
        .content-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
        }
        .content-header {
            padding: 20px 24px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 16px;
        }
        .content-title {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-primary);
        }
        .header-actions {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .tabs {
            display: flex;
            background: var(--background);
            border-radius: 10px;
            padding: 4px;
            gap: 4px;
        }
        .tab {
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 500;
            font-size: 14px;
            color: var(--text-secondary);
            border: none;
            background: transparent;
            transition: all 0.2s;
        }
        .tab:hover {
            color: var(--text-primary);
        }
        .tab.active {
            background: var(--surface);
            color: var(--primary);
            box-shadow: var(--shadow-sm);
        }
        .refresh-btn {
            padding: 10px 16px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s;
        }
        .refresh-btn:hover {
            background: var(--primary-dark);
        }
        .refresh-btn.loading svg {
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        /* DataTables Customization */
        .table-container {
            padding: 0;
        }
        .dataTables_wrapper {
            padding: 20px;
        }
        .dataTables_wrapper .dataTables_length,
        .dataTables_wrapper .dataTables_filter {
            margin-bottom: 16px;
        }
        .dataTables_wrapper .dataTables_length select,
        .dataTables_wrapper .dataTables_filter input {
            padding: 8px 12px;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--surface);
            color: var(--text-primary);
            font-size: 14px;
        }
        .dataTables_wrapper .dataTables_filter input {
            width: 250px;
        }
        .dataTables_wrapper .dataTables_info {
            color: var(--text-secondary);
            font-size: 13px;
        }
        .dataTables_wrapper .dataTables_paginate {
            margin-top: 16px;
        }
        .dataTables_wrapper .dataTables_paginate .paginate_button {
            padding: 6px 12px;
            border-radius: 6px;
            border: 1px solid var(--border) !important;
            background: var(--surface) !important;
            color: var(--text-primary) !important;
            margin: 0 2px;
        }
        .dataTables_wrapper .dataTables_paginate .paginate_button:hover {
            background: var(--background) !important;
            color: var(--primary) !important;
        }
        .dataTables_wrapper .dataTables_paginate .paginate_button.current {
            background: var(--primary) !important;
            color: white !important;
            border-color: var(--primary) !important;
        }
        .dataTables_wrapper .dataTables_paginate .paginate_button.disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        table.dataTable {
            border-collapse: collapse !important;
            width: 100% !important;
        }
        table.dataTable thead th {
            padding: 14px 16px;
            text-align: left;
            font-weight: 600;
            font-size: 12px;
            color: var(--text-secondary);
            background: var(--background);
            border-bottom: 2px solid var(--border);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        table.dataTable tbody td {
            padding: 14px 16px;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
            color: var(--text-primary);
        }
        table.dataTable tbody tr:hover {
            background: var(--table-hover) !important;
        }
        table.dataTable.stripe tbody tr.odd {
            background: var(--table-stripe);
        }

        /* Badges */
        .user-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 4px 12px 4px 4px;
            background: var(--background);
            border-radius: 20px;
            font-size: 13px;
            font-weight: 500;
        }
        .user-avatar {
            width: 26px;
            height: 26px;
            background: var(--gradient);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 600;
        }
        .channel-badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            color: var(--text-secondary);
            font-size: 13px;
        }
        .channel-badge::before {
            content: '#';
            color: var(--text-muted);
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        .status-badge.pending { background: rgba(245, 158, 11, 0.15); color: #d97706; }
        .status-badge.sent { background: rgba(16, 185, 129, 0.15); color: #059669; }
        .status-badge.cancelled { background: rgba(239, 68, 68, 0.15); color: #dc2626; }
        .status-badge.failed { background: rgba(239, 68, 68, 0.15); color: #dc2626; }
        .status-badge.rescheduled { background: rgba(59, 130, 246, 0.15); color: #2563eb; }
        .status-dot-sm {
            width: 6px;
            height: 6px;
            border-radius: 50%;
        }
        .status-dot-sm.pending { background: #f59e0b; }
        .status-dot-sm.sent { background: #10b981; }
        .status-dot-sm.cancelled { background: #ef4444; }
        .status-dot-sm.failed { background: #ef4444; }
        .status-dot-sm.rescheduled { background: #3b82f6; }

        /* Message Preview */
        .message-preview {
            max-width: 250px;
            color: var(--text-secondary);
            font-size: 13px;
            line-height: 1.4;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        /* Time Stamps */
        .time-stamp {
            color: var(--text-muted);
            font-size: 13px;
            font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
        }
        .time-primary {
            color: var(--text-primary);
            font-weight: 500;
        }

        /* Action Buttons */
        .btn {
            padding: 6px 14px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
        }
        .btn-cancel {
            background: rgba(239, 68, 68, 0.1);
            color: #dc2626;
        }
        .btn-cancel:hover {
            background: #ef4444;
            color: white;
        }

        /* Loading & Error States */
        .loading-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 60px 20px;
            color: var(--text-muted);
        }
        .spinner {
            width: 40px;
            height: 40px;
            border: 3px solid var(--border);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 16px;
        }
        .error-container {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            color: #dc2626;
            padding: 16px 20px;
            border-radius: 10px;
            margin: 20px;
            text-align: center;
        }

        /* Empty State */
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
        }
        .empty-state-icon {
            width: 80px;
            height: 80px;
            background: var(--background);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
            font-size: 32px;
        }
        .empty-state h3 {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }

        /* Toast Notifications */
        .toast-container {
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 1000;
        }
        .toast {
            padding: 14px 20px;
            border-radius: 10px;
            margin-top: 10px;
            box-shadow: var(--shadow-lg);
            display: flex;
            align-items: center;
            gap: 12px;
            animation: slideIn 0.3s ease;
        }
        .toast.success {
            background: #059669;
            color: white;
        }
        .toast.error {
            background: #dc2626;
            color: white;
        }
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
    </style>
</head>
<body>
    <div class="app" data-theme="light">
        <header class="header">
            <div class="logo">
                <div class="logo-icon">E</div>
                <span>ETC Monitor</span>
            </div>
            <div class="header-right">
                <button class="header-btn" onclick="toggleTheme()" title="Toggle theme">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" id="theme-icon">
                        <path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
                <div class="status-indicator">
                    <div class="status-dot"></div>
                    <span>System Online</span>
                </div>
                <a href="/logout" class="header-btn">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/>
                    </svg>
                    Logout
                </a>
            </div>
        </header>

        <main class="main">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-icon total">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                            <line x1="16" y1="2" x2="16" y2="6"></line>
                            <line x1="8" y1="2" x2="8" y2="6"></line>
                            <line x1="3" y1="10" x2="21" y2="10"></line>
                        </svg>
                    </div>
                    <div class="stat-content">
                        <div class="stat-value" id="stat-total">-</div>
                        <div class="stat-label">Total Reminders</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon pending">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <polyline points="12 6 12 12 16 14"></polyline>
                        </svg>
                    </div>
                    <div class="stat-content">
                        <div class="stat-value" id="stat-pending">-</div>
                        <div class="stat-label">Pending</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon sent">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    </div>
                    <div class="stat-content">
                        <div class="stat-value" id="stat-sent">-</div>
                        <div class="stat-label">Sent</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon cancelled">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="15" y1="9" x2="9" y2="15"></line>
                            <line x1="9" y1="9" x2="15" y2="15"></line>
                        </svg>
                    </div>
                    <div class="stat-content">
                        <div class="stat-value" id="stat-cancelled">-</div>
                        <div class="stat-label">Cancelled/Failed</div>
                    </div>
                </div>
            </div>

            <div class="content-card">
                <div class="content-header">
                    <h2 class="content-title">Reminder Management</h2>
                    <div class="header-actions">
                        <div class="tabs">
                            <button class="tab active" data-tab="all">All Reminders</button>
                            <button class="tab" data-tab="pending">Pending Only</button>
                        </div>
                        <button class="refresh-btn" onclick="refreshData()">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="23 4 23 10 17 10"></polyline>
                                <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"></path>
                            </svg>
                            Refresh
                        </button>
                    </div>
                </div>

                <div class="table-container">
                    <div id="loading-container" class="loading-container">
                        <div class="spinner"></div>
                        <span>Loading reminders...</span>
                    </div>
                    <div id="error-container" class="error-container" style="display:none;"></div>
                    <table id="reminders-table" class="display stripe" style="display:none;width:100%">
                        <thead>
                            <tr>
                                <th>User</th>
                                <th>Channel</th>
                                <th>Message</th>
                                <th>Deadline</th>
                                <th>Reminder</th>
                                <th>Status</th>
                                <th>Created</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        </main>
    </div>

    <div class="toast-container" id="toast-container"></div>

    <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
    <script src="https://cdn.datatables.net/responsive/2.5.0/js/dataTables.responsive.min.js"></script>
    <script>
        let dataTable = null;
        let currentTab = 'all';
        let allReminders = [];

        // Theme Management
        function getSystemTheme() {
            return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }

        function setTheme(theme) {
            document.querySelector('.app').setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
            const icon = document.getElementById('theme-icon');
            if (theme === 'dark') {
                icon.innerHTML = '<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" stroke="currentColor" stroke-width="2" fill="none"/>';
            } else {
                icon.innerHTML = '<path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>';
            }
        }

        function toggleTheme() {
            const current = localStorage.getItem('theme') || getSystemTheme();
            setTheme(current === 'dark' ? 'light' : 'dark');
        }

        // Toast Notifications
        function showToast(message, type = 'success') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    ${type === 'success' ? '<polyline points="20 6 9 17 4 12"></polyline>' : '<circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line>'}
                </svg>
                <span>${message}</span>
            `;
            container.appendChild(toast);
            setTimeout(() => toast.remove(), 4000);
        }

        // Data Formatting
        function formatDate(dateStr) {
            if (!dateStr) return '-';
            try {
                const date = new Date(dateStr);
                if (isNaN(date.getTime())) return '-';
                return date.toLocaleString('en-IN', {
                    day: '2-digit',
                    month: 'short',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: true
                });
            } catch (e) {
                return '-';
            }
        }

        function getUserInitial(userId, userName) {
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
            return reminder.user_id || '-';
        }

        function formatChannelName(reminder) {
            let name = reminder.channel_name || reminder.channel_id || '-';
            return name.replace(/^#/, '');
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
        }

        // Tab Management
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', function() {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                this.classList.add('active');
                currentTab = this.dataset.tab;
                loadReminders();
            });
        });

        // Initialize DataTable
        function initDataTable() {
            if (dataTable) {
                dataTable.destroy();
            }

            dataTable = $('#reminders-table').DataTable({
                responsive: true,
                pageLength: 25,
                lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]],
                order: [[6, 'desc']],
                language: {
                    search: "Search:",
                    lengthMenu: "Show _MENU_ entries",
                    info: "Showing _START_ to _END_ of _TOTAL_ reminders",
                    infoEmpty: "No reminders found",
                    infoFiltered: "(filtered from _MAX_ total)",
                    paginate: {
                        first: "First",
                        last: "Last",
                        next: "Next",
                        previous: "Prev"
                    }
                },
                columnDefs: [
                    { orderable: false, targets: [7] },
                    { className: 'dt-head-left', targets: '_all' }
                ]
            });
        }

        // Load Reminders
        function loadReminders() {
            const loadingEl = document.getElementById('loading-container');
            const errorEl = document.getElementById('error-container');
            const tableEl = document.getElementById('reminders-table');

            loadingEl.style.display = 'flex';
            errorEl.style.display = 'none';
            tableEl.style.display = 'none';

            const statusParam = currentTab === 'pending' ? '&status=pending' : '';

            fetch(`/api/reminders?limit=1000${statusParam}`)
                .then(response => {
                    if (!response.ok) {
                        if (response.status === 401) {
                            window.location.href = '/login';
                            return;
                        }
                        throw new Error(`HTTP ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    loadingEl.style.display = 'none';
                    tableEl.style.display = 'table';

                    allReminders = data.reminders || [];
                    updateStats(data);
                    populateTable(allReminders);
                })
                .catch(error => {
                    loadingEl.style.display = 'none';
                    errorEl.style.display = 'block';
                    errorEl.textContent = 'Error loading reminders: ' + error.message;
                });
        }

        // Update Stats
        function updateStats(data) {
            if (data.stats) {
                document.getElementById('stat-total').textContent = data.total || 0;
                document.getElementById('stat-pending').textContent = data.stats.pending || 0;
                document.getElementById('stat-sent').textContent = data.stats.sent || 0;
                document.getElementById('stat-cancelled').textContent = (data.stats.cancelled || 0) + (data.stats.failed || 0);
            }
        }

        // Populate Table
        function populateTable(reminders) {
            if (dataTable) {
                dataTable.destroy();
            }

            const tbody = document.querySelector('#reminders-table tbody');
            tbody.innerHTML = '';

            if (reminders.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" class="empty-state"><div class="empty-state-icon">📭</div><h3>No reminders found</h3></td></tr>';
            } else {
                reminders.forEach(reminder => {
                    const row = document.createElement('tr');
                    const status = (reminder.status || 'pending').toLowerCase();
                    const userName = formatUserName(reminder);
                    const channelName = formatChannelName(reminder);
                    const message = escapeHtml(reminder.deadline_text || '-');

                    row.innerHTML = `
                        <td>
                            <div class="user-badge">
                                <div class="user-avatar">${getUserInitial(reminder.user_id, reminder.user_name)}</div>
                                <span>${escapeHtml(userName)}</span>
                            </div>
                        </td>
                        <td><span class="channel-badge">${escapeHtml(channelName)}</span></td>
                        <td><div class="message-preview" title="${message}">${message.substring(0, 40)}${message.length > 40 ? '...' : ''}</div></td>
                        <td><span class="time-stamp time-primary">${formatDate(reminder.deadline_datetime)}</span></td>
                        <td><span class="time-stamp">${formatDate(reminder.reminder_datetime)}</span></td>
                        <td>
                            <span class="status-badge ${status}">
                                <span class="status-dot-sm ${status}"></span>
                                ${status}
                            </span>
                        </td>
                        <td><span class="time-stamp">${formatDate(reminder.created_at)}</span></td>
                        <td>
                            ${status === 'pending' ? `<button class="btn btn-cancel" onclick="cancelReminder(${reminder.id})">Cancel</button>` : '-'}
                        </td>
                    `;
                    tbody.appendChild(row);
                });
            }

            initDataTable();
        }

        // Cancel Reminder
        function cancelReminder(id) {
            if (!confirm('Are you sure you want to cancel this reminder?')) return;

            fetch(`/api/reminders/${id}/cancel`, { method: 'POST' })
                .then(response => {
                    if (!response.ok) {
                        if (response.status === 401) {
                            window.location.href = '/login';
                            return;
                        }
                        throw new Error('Failed to cancel');
                    }
                    return response.json();
                })
                .then(() => {
                    showToast('Reminder cancelled successfully');
                    loadReminders();
                })
                .catch(error => {
                    showToast('Error: ' + error.message, 'error');
                });
        }

        // Refresh Data
        function refreshData() {
            const btn = document.querySelector('.refresh-btn');
            btn.classList.add('loading');
            loadReminders();
            setTimeout(() => btn.classList.remove('loading'), 1000);
        }

        // Initialize
        const storedTheme = localStorage.getItem('theme') || getSystemTheme();
        setTheme(storedTheme);
        loadReminders();

        // Auto-refresh every 30 seconds
        setInterval(loadReminders, 30000);
    </script>
</body>
</html>
'''


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
