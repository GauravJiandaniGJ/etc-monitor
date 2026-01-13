"""Health check routes for admin panel."""
from flask import Blueprint, jsonify
from src.database.db_manager import DBManager
from slack_sdk import WebClient
from config.settings import Settings
from src.utils.logger import get_logger


logger = get_logger('HealthRoutes')

# Create blueprint
health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health_check():
    """Basic health check endpoint.

    Returns:
        JSON response with status
    """
    return jsonify({
        'status': 'ok',
        'service': 'ETC Monitor Admin'
    }), 200


@health_bp.route('/health/db', methods=['GET'])
def health_db():
    """Database connectivity check.

    Returns:
        JSON response with database status
    """
    try:
        settings = Settings()
        db_manager = DBManager(settings.database_path)

        # Try to execute a simple query
        result = db_manager.fetch_one('SELECT 1')

        if result:
            return jsonify({
                'status': 'ok',
                'database': 'connected',
                'path': settings.database_path
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'database': 'query failed'
            }), 500

    except Exception as e:
        logger.error(f'Database health check failed: {e}')
        return jsonify({
            'status': 'error',
            'database': 'connection failed',
            'error': str(e)
        }), 500


@health_bp.route('/health/slack', methods=['GET'])
def health_slack():
    """Slack API connectivity check.

    Returns:
        JSON response with Slack API status
    """
    try:
        settings = Settings()
        client = WebClient(token=settings.slack_bot_token)

        # Try to call auth.test endpoint
        response = client.auth_test()

        if response['ok']:
            return jsonify({
                'status': 'ok',
                'slack': 'connected',
                'team': response.get('team'),
                'user': response.get('user')
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'slack': 'api_error',
                'error': response.get('error')
            }), 500

    except Exception as e:
        logger.error(f'Slack health check failed: {e}')
        return jsonify({
            'status': 'error',
            'slack': 'connection failed',
            'error': str(e)
        }), 500
