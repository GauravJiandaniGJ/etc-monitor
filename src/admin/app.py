"""Flask admin panel application."""
import hmac
import os
import threading
import time
from collections import deque
from datetime import timedelta
from typing import Optional
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_cors import CORS
from src.config.settings import Settings
from src.admin.routes.health_routes import health_bp
from src.admin.routes.reminder_routes import reminder_bp, init_reminder_routes
from src.utils.logger import get_logger, init_logger


logger = get_logger('AdminApp')

# Paths that work without logging in. Everything else needs a login session.
PUBLIC_PATHS = ('/login', '/logout', '/health')
PUBLIC_PREFIXES = ('/health/', '/static/')

# Settings falls back to this when ADMIN_PASSWORD is missing from .env.
# While it is in use, every login is refused.
DEFAULT_ADMIN_PASSWORD = 'changeme'
FAILED_LOGIN_DELAY_SECONDS = 1
SESSION_LIFETIME = timedelta(days=7)

# Brute-force protection. Within the window, one client may fail this many times
# before it is locked out; the total cap pauses all logins if many clients fail
# (e.g. an attacker rotating IP addresses or forged headers).
MAX_FAILURES_PER_CLIENT = 5
MAX_FAILURES_TOTAL = 50
FAILURE_WINDOW_SECONDS = 15 * 60

# Requests from these addresses come through the local nginx proxy, so the real
# client address is in the forwarded headers. Anything else connected directly.
LOCAL_PROXY_ADDRS = ('127.0.0.1', '::1')


class LoginThrottle:
    """Counts failed logins in memory over a sliding window.

    The admin panel runs as a single process, so in-memory state is enough.
    It resets when the admin service restarts.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._by_client = {}
        self._all = deque()

    @staticmethod
    def _expire(failures: deque, now: float):
        while failures and now - failures[0] >= FAILURE_WINDOW_SECONDS:
            failures.popleft()

    def _expire_all(self, now: float):
        self._expire(self._all, now)
        for key in list(self._by_client):
            self._expire(self._by_client[key], now)
            if not self._by_client[key]:
                del self._by_client[key]

    def is_blocked(self, client: str, now: Optional[float] = None) -> bool:
        """True if this client, or everyone, has failed too often recently."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self._expire_all(now)
            if len(self._all) >= MAX_FAILURES_TOTAL:
                return True
            return len(self._by_client.get(client, ())) >= MAX_FAILURES_PER_CLIENT

    def record_failure(self, client: str, now: Optional[float] = None):
        now = time.monotonic() if now is None else now
        with self._lock:
            self._expire_all(now)
            self._by_client.setdefault(client, deque()).append(now)
            self._all.append(now)

    def reset(self, client: str):
        """Forget a client's failures after it logs in successfully."""
        with self._lock:
            self._by_client.pop(client, None)


def _login_configured(settings: Settings) -> bool:
    """Return True only when a real ADMIN_PASSWORD is set in .env."""
    password = settings.admin_password or ''
    return bool(password) and password != DEFAULT_ADMIN_PASSWORD


def _credentials_match(settings: Settings, username: str, password: str) -> bool:
    """Check the submitted credentials against .env in constant time."""
    if not _login_configured(settings):
        return False
    username_ok = hmac.compare_digest(
        username.encode('utf-8'), (settings.admin_username or '').encode('utf-8')
    )
    password_ok = hmac.compare_digest(
        password.encode('utf-8'), settings.admin_password.encode('utf-8')
    )
    return username_ok and password_ok


def _client_ip() -> str:
    """Client IP used for login throttling and logs.

    Through nginx (Cloudflare in front), the client is in CF-Connecting-IP or
    X-Real-IP. A direct connection (e.g. to port 8090) could forge those
    headers, so its socket address is used instead.
    """
    remote = request.remote_addr or 'unknown'
    if remote in LOCAL_PROXY_ADDRS:
        return (
            request.headers.get('CF-Connecting-IP')
            or request.headers.get('X-Real-IP')
            or remote
        )
    return remote


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

    # Login session: a signed cookie that stays valid for 7 days.
    app.config.update(
        PERMANENT_SESSION_LIFETIME=SESSION_LIFETIME,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        # Only sent over HTTPS. Set ADMIN_COOKIE_SECURE=false for local http testing.
        SESSION_COOKIE_SECURE=os.environ.get('ADMIN_COOKIE_SECURE', 'true').strip().lower() != 'false',
    )
    if not _login_configured(settings):
        logger.warning('ADMIN_PASSWORD is not set in .env - all admin logins will be refused')
    login_throttle = LoginThrottle()

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

    @app.before_request
    def require_login():
        """Let public paths through; everything else needs a login session."""
        path = request.path
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return None
        if session.get('logged_in'):
            return None
        if path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized'}), 401
        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Show the login form and check the submitted credentials."""
        if request.method == 'GET':
            if session.get('logged_in'):
                return redirect(url_for('root'))
            return render_template('login.html')

        username = request.form.get('username', '')
        password = request.form.get('password', '')
        shown_name = repr(username[:64])
        client = _client_ip()

        # Checked before the password, so a locked-out client can't keep guessing.
        if login_throttle.is_blocked(client):
            logger.warning(f'Admin login blocked after too many failures: {shown_name} from {client}')
            error = 'Too many failed attempts. Please try again in 15 minutes.'
            return render_template('login.html', error=error, username=username), 429

        if _credentials_match(settings, username, password):
            login_throttle.reset(client)
            session.clear()
            session['logged_in'] = True
            session['username'] = username
            session.permanent = True
            logger.info(f'Admin login succeeded for {shown_name} from {client}')
            return redirect(url_for('root'))

        login_throttle.record_failure(client)
        time.sleep(FAILED_LOGIN_DELAY_SECONDS)
        if _login_configured(settings):
            error = 'Invalid username or password'
        else:
            error = 'Login is not set up on the server yet (ADMIN_PASSWORD missing in .env)'
        logger.warning(f'Admin login failed for {shown_name} from {client}')
        return render_template('login.html', error=error, username=username), 401

    @app.route('/logout')
    def logout():
        """End the session and go back to the login page."""
        username = session.get('username')
        session.clear()
        if username:
            logger.info(f'Admin logout for {repr(username[:64])} from {_client_ip()}')
        return redirect(url_for('login'))

    # Root route - Dashboard UI
    @app.route('/')
    def root():
        """Dashboard UI for managing reminders."""
        return render_template('dashboard.html')

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
