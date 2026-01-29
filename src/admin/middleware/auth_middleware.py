"""Authentication middleware for admin panel."""
from functools import wraps
from flask import request, Response, make_response
import base64
from config.settings import Settings
from src.utils.logger import get_logger


logger = get_logger('AuthMiddleware')


def require_auth(settings: Settings):
    """Create authentication decorator.

    Args:
        settings: Application settings with admin credentials

    Returns:
        Decorator function for protecting routes
    """
    def decorator(f):
        """Decorator to require HTTP Basic Authentication.

        Uses credentials from settings (admin_username, admin_password).
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            """Check authentication before allowing access."""
            auth = request.authorization

            if not auth:
                # Request authentication
                return _make_auth_response()

            # Check credentials
            if auth.username == settings.admin_username and auth.password == settings.admin_password:
                logger.debug(f'Authenticated user: {auth.username}')
                return f(*args, **kwargs)
            else:
                logger.warning(f'Authentication failed for user: {auth.username}')
                return _make_auth_response()

        return decorated_function
    return decorator


def _make_auth_response() -> Response:
    """Create HTTP 401 Unauthorized response with Basic Auth challenge.

    Returns:
        Flask Response with 401 status and WWW-Authenticate header
    """
    response = make_response('Authentication required', 401)
    response.headers['WWW-Authenticate'] = 'Basic realm="ETC Monitor Admin"'
    return response
