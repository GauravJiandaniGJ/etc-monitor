"""Flask admin panel application."""
import hmac
import ipaddress
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

# Brute-force protection, over a sliding window:
# - one client may fail MAX_FAILURES_PER_CLIENT times, then must wait;
# - once MAX_FAILURES_TOTAL failures pile up across all clients (an attack from
#   many addresses), any client that has failed even once must wait. Clients
#   with no recent failures - such as the real admin - can still log in.
MAX_FAILURES_PER_CLIENT = 5
MAX_FAILURES_TOTAL = 50
FAILURE_WINDOW_SECONDS = 15 * 60

# Cloudflare's published ranges (https://www.cloudflare.com/ips/, checked 2026-11-23).
# CF-Connecting-IP is only trusted when nginx says the request came from one of these;
# otherwise anyone reaching the server directly could forge it.
CLOUDFLARE_NETWORKS = tuple(ipaddress.ip_network(net) for net in (
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22',
    '141.101.64.0/18', '108.162.192.0/18', '190.93.240.0/20', '188.114.96.0/20',
    '197.234.240.0/22', '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/13',
    '104.24.0.0/14', '172.64.0.0/13', '131.0.72.0/22',
    '2400:cb00::/32', '2606:4700::/32', '2803:f800::/32', '2405:b500::/32',
    '2405:8100::/32', '2a06:98c0::/29', '2c0f:f248::/32',
))


class LoginThrottle:
    """Counts failed logins in memory over a sliding window.

    Each attempt is counted as a failure *before* the password is checked, in
    the same locked step as the limit check, so parallel requests can't slip
    past the limit. A successful login removes that count again.

    The admin panel runs as a single process, so in-memory state is enough.
    It resets when the admin service restarts.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._by_client = {}
        self._all = deque()
        self._under_attack = False

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

    def begin_attempt(self, client: str, now: Optional[float] = None) -> Optional[float]:
        """Check the limits and reserve this attempt as a failure, atomically.

        Returns a token for succeeded(), or None if the client has to wait.
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            self._expire_all(now)
            under_attack = len(self._all) >= MAX_FAILURES_TOTAL
            if under_attack != self._under_attack:
                self._under_attack = under_attack
                if under_attack:
                    logger.warning('Many failed admin logins: clients with any recent failure must wait')
            limit = 1 if under_attack else MAX_FAILURES_PER_CLIENT
            if len(self._by_client.get(client, ())) >= limit:
                return None
            self._by_client.setdefault(client, deque()).append(now)
            self._all.append(now)
            return now

    def succeeded(self, client: str, token: float):
        """Forget the client's failures, including this attempt's reservation."""
        with self._lock:
            self._by_client.pop(client, None)
            try:
                self._all.remove(token)
            except ValueError:
                pass


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


def _parse_ip(address: str):
    """Parse an IP address, or return None. IPv4-mapped IPv6 (::ffff:a.b.c.d) becomes plain IPv4."""
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError:
        return None
    if ip.version == 6 and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


def _is_cloudflare(ip) -> bool:
    return ip is not None and any(ip in network for network in CLOUDFLARE_NETWORKS)


def _client_ip() -> str:
    """Client IP used for login throttling and logs, resistant to forged headers.

    - Direct connection (e.g. to port 8090): the socket address.
    - Through the local nginx: nginx overwrites X-Real-IP with the address that
      connected to it (`proxy_set_header X-Real-IP $remote_addr` in the server's
      site config). If that is Cloudflare, the client is in CF-Connecting-IP
      (set by Cloudflare); if not, the request bypassed Cloudflare and
      X-Real-IP is the client itself.
    Header values that aren't valid IP addresses are ignored.
    """
    remote = _parse_ip(request.remote_addr or '')
    if remote is None:
        return request.remote_addr or 'unknown'
    if not remote.is_loopback:
        return str(remote)
    peer = _parse_ip(request.headers.get('X-Real-IP', '')) or remote
    if _is_cloudflare(peer):
        client = _parse_ip(request.headers.get('CF-Connecting-IP', ''))
        if client is not None:
            return str(client)
    return str(peer)


def _throttle_key(client_ip: str) -> str:
    """Group IPv6 clients by /64, since one user can easily switch addresses inside it."""
    ip = _parse_ip(client_ip)
    if ip is None:
        return client_ip
    if ip.version == 6:
        return str(ipaddress.ip_network(f'{ip}/64', strict=False))
    return str(ip)


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
        throttle_key = _throttle_key(client)

        # Reserved before the password is checked, so a locked-out client can't keep guessing.
        attempt = login_throttle.begin_attempt(throttle_key)
        if attempt is None:
            logger.warning(f'Admin login blocked after too many failures: {shown_name} from {client}')
            error = 'Too many failed attempts. Please try again in 15 minutes.'
            return render_template('login.html', error=error, username=username), 429

        if _credentials_match(settings, username, password):
            login_throttle.succeeded(throttle_key, attempt)
            session.clear()
            session['logged_in'] = True
            session['username'] = username
            session.permanent = True
            logger.info(f'Admin login succeeded for {shown_name} from {client}')
            return redirect(url_for('root'))

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
