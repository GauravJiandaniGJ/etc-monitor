"""Flask admin panel application with authentication."""
from typing import Optional
from functools import wraps
from flask import Flask, jsonify, request, session, redirect, url_for, render_template
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
        error = None
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
                error = 'Invalid username or password'

        return render_template('login.html', error=error)

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
        return render_template('dashboard.html')

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