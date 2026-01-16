"""Reminder management routes for admin panel - Production Optimized & Tested."""
from flask import Blueprint, jsonify, request
from typing import Optional
from functools import wraps
import time
from src.database.db_manager import DBManager
from src.database.repositories.reminder_repository import ReminderRepository
from src.database.repositories.audit_repository import AuditRepository
from src.services.reminder_service import ReminderService
from src.services.notification_service import NotificationService
from src.core.models import ReminderStatus
from config.settings import Settings
from src.utils.logger import get_logger
from slack_sdk import WebClient


logger = get_logger('ReminderRoutes')

# Create blueprint
reminder_bp = Blueprint('reminders', __name__)

# Initialize services (will be set up in app.py)
_reminder_service: Optional[ReminderService] = None
_notification_service: Optional[NotificationService] = None


def init_reminder_routes(settings: Settings):
    """Initialize reminder routes with services.

    Args:
        settings: Application settings
    """
    global _reminder_service, _notification_service

    db_manager = DBManager(settings)
    reminder_repo = ReminderRepository(db_manager)
    audit_repo = AuditRepository(db_manager)

    _reminder_service = ReminderService(
        reminder_repo=reminder_repo,
        audit_repo=audit_repo
    )

    slack_client = WebClient(token=settings.slack_bot_token)
    _notification_service = NotificationService(slack_client)

    logger.info('Reminder routes initialized')


def timing_middleware(func):
    """Middleware to log request timing."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            logger.info(f'{func.__name__} completed in {elapsed:.3f}s')
            return result
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f'{func.__name__} failed after {elapsed:.3f}s: {e}', exc=e)
            raise
    return wrapper


@reminder_bp.route('/api/reminders', methods=['GET'])
@timing_middleware
def list_reminders():
    """List all reminders with optional filters - Production Optimized.

    Query parameters:
        - status: Filter by status (pending, sent, cancelled, failed, rescheduled)
        - user_id: Filter by user ID
        - channel_id: Filter by channel ID
        - limit: Maximum number of results (default: 100, max: 1000)
        - offset: Offset for pagination (default: 0)

    Returns:
        JSON response with list of reminders and stats
    """
    try:
        # Parse and validate parameters
        status_filter = request.args.get('status')
        user_id_filter = request.args.get('user_id')
        channel_id_filter = request.args.get('channel_id')
        limit = min(int(request.args.get('limit', 100)), 1000)  # Cap at 1000
        offset = max(int(request.args.get('offset', 0)), 0)

        logger.info(f'Listing reminders - status: {status_filter}, limit: {limit}, offset: {offset}')

        db_manager = _reminder_service.reminder_repo.db
        placeholder = '%s' if db_manager.database_type != 'sqlite' else '?'

        # Build WHERE clause for count query
        where_conditions = []
        count_params = []

        if status_filter:
            where_conditions.append(f'status = {placeholder}')
            count_params.append(status_filter)
        if user_id_filter:
            where_conditions.append(f'user_id = {placeholder}')
            count_params.append(user_id_filter)
        if channel_id_filter:
            where_conditions.append(f'channel_id = {placeholder}')
            count_params.append(channel_id_filter)

        where_clause = ' AND '.join(where_conditions) if where_conditions else '1=1'

        # Get total count (single optimized query)
        count_query = f'SELECT COUNT(*) as count FROM reminders WHERE {where_clause}'
        count_result = db_manager.fetch_one(count_query, tuple(count_params) if count_params else None)
        total = count_result['count'] if count_result else 0

        # Get status counts (only if no filters for dashboard - single GROUP BY query)
        status_counts = {'pending': 0, 'sent': 0, 'cancelled': 0, 'failed': 0, 'rescheduled': 0}
        if not status_filter and not user_id_filter and not channel_id_filter:
            status_query = '''
                SELECT status, COUNT(*) as count
                FROM reminders
                WHERE status IN (?, ?, ?, ?, ?)
                GROUP BY status
            '''
            if db_manager.database_type != 'sqlite':
                status_query = status_query.replace('?', '%s')

            status_results = db_manager.fetch_all(
                status_query,
                ('pending', 'sent', 'cancelled', 'failed', 'rescheduled')
            )

            for row in status_results:
                status = row.get('status') or row.get('STATUS')
                count = row.get('count') or row.get('COUNT')
                if status in status_counts and count is not None:
                    status_counts[status] = int(count)

        # Get reminders - use repository method for proper object conversion
        # If filtering, we need to get more records, then filter in memory
        # If no filters, use direct pagination from database
        if status_filter or user_id_filter or channel_id_filter:
            # When filtering, fetch more records to ensure we have enough after filtering
            fetch_limit = min(limit * 5, 1000)  # Fetch 5x limit, cap at 1000
            all_reminders = _reminder_service.reminder_repo.get_all(limit=fetch_limit, offset=0)

            # Apply filters in memory
            reminders = all_reminders
            if status_filter:
                reminders = [r for r in reminders if r.status.value == status_filter]
            if user_id_filter:
                reminders = [r for r in reminders if r.user_id == user_id_filter]
            if channel_id_filter:
                reminders = [r for r in reminders if r.channel_id == channel_id_filter]

            # Apply pagination after filtering
            reminders = reminders[offset:offset + limit]
        else:
            # No filters - use direct database pagination (most efficient)
            reminders = _reminder_service.reminder_repo.get_all(limit=limit, offset=offset)

        # Format reminders
        formatted_reminders = [_format_reminder(r) for r in reminders]

        result = {
            'total': total,
            'limit': limit,
            'offset': offset,
            'reminders': formatted_reminders,
            'stats': status_counts
        }

        logger.info(f'Returning {len(formatted_reminders)} reminders (total: {total})')
        return jsonify(result), 200

    except ValueError as e:
        logger.error(f'Invalid parameter: {e}')
        return jsonify({'error': f'Invalid parameter: {str(e)}'}), 400
    except Exception as e:
        logger.error(f'Error listing reminders: {e}', exc=e)
        import traceback
        logger.error(f'Traceback: {traceback.format_exc()}')
        return jsonify({'error': 'Internal server error'}), 500


@reminder_bp.route('/api/reminders/<int:reminder_id>', methods=['GET'])
def get_reminder(reminder_id: int):
    """Get a single reminder by ID.

    Args:
        reminder_id: Reminder ID

    Returns:
        JSON response with reminder data
    """
    try:
        reminder = _reminder_service.get_reminder(reminder_id)

        if not reminder:
            return jsonify({'error': 'Reminder not found'}), 404

        return jsonify(_format_reminder(reminder)), 200

    except Exception as e:
        logger.error(f'Error getting reminder {reminder_id}: {e}', exc=e)
        return jsonify({'error': str(e)}), 500


@reminder_bp.route('/api/reminders/<int:reminder_id>', methods=['PUT'])
def update_reminder(reminder_id: int):
    """Update a reminder.

    Args:
        reminder_id: Reminder ID

    Request body (JSON):
        - status: New status
        - deadline_datetime: New deadline (ISO format)
        - reminder_datetime: New reminder time (ISO format)

    Returns:
        JSON response with updated reminder
    """
    try:
        reminder = _reminder_service.get_reminder(reminder_id)

        if not reminder:
            return jsonify({'error': 'Reminder not found'}), 404

        data = request.get_json() or {}
        updates = {}

        if 'status' in data:
            status_str = data['status']
            try:
                updates['status'] = ReminderStatus(status_str)
            except ValueError:
                return jsonify({'error': f'Invalid status: {status_str}'}), 400

        if 'deadline_datetime' in data:
            from datetime import datetime as dt
            try:
                deadline = dt.fromisoformat(data['deadline_datetime'])
                updates['deadline_datetime'] = deadline
            except ValueError:
                return jsonify({'error': 'Invalid deadline_datetime format'}), 400

        if 'reminder_datetime' in data:
            from datetime import datetime as dt
            try:
                reminder_time = dt.fromisoformat(data['reminder_datetime'])
                updates['reminder_datetime'] = reminder_time
            except ValueError:
                return jsonify({'error': 'Invalid reminder_datetime format'}), 400

        if not updates:
            return jsonify({'error': 'No valid fields to update'}), 400

        # Update reminder
        updated = _reminder_service.reminder_repo.update(reminder_id, updates)

        if updated:
            reminder = _reminder_service.get_reminder(reminder_id)
            return jsonify(_format_reminder(reminder)), 200
        else:
            return jsonify({'error': 'Failed to update reminder'}), 500

    except Exception as e:
        logger.error(f'Error updating reminder {reminder_id}: {e}', exc=e)
        return jsonify({'error': str(e)}), 500


@reminder_bp.route('/api/reminders/<int:reminder_id>', methods=['DELETE'])
def delete_reminder(reminder_id: int):
    """Delete a reminder.

    Args:
        reminder_id: Reminder ID

    Returns:
        JSON response with success status
    """
    try:
        reminder = _reminder_service.get_reminder(reminder_id)

        if not reminder:
            return jsonify({'error': 'Reminder not found'}), 404

        success = _reminder_service.delete_reminder(reminder_id, 'admin')

        if success:
            return jsonify({'success': True, 'message': 'Reminder deleted'}), 200
        else:
            return jsonify({'error': 'Failed to delete reminder'}), 500

    except Exception as e:
        logger.error(f'Error deleting reminder {reminder_id}: {e}', exc=e)
        return jsonify({'error': str(e)}), 500


@reminder_bp.route('/api/reminders/<int:reminder_id>/cancel', methods=['POST'])
def cancel_reminder(reminder_id: int):
    """Cancel a reminder.

    Args:
        reminder_id: Reminder ID

    Returns:
        JSON response with cancelled reminder
    """
    try:
        reminder = _reminder_service.get_reminder(reminder_id)

        if not reminder:
            return jsonify({'error': 'Reminder not found'}), 404

        success = _reminder_service.cancel(reminder_id, 'admin')

        if success:
            # Send cancellation notification
            _notification_service.send_cancellation(reminder)

            reminder = _reminder_service.get_reminder(reminder_id)
            return jsonify(_format_reminder(reminder)), 200
        else:
            return jsonify({'error': 'Failed to cancel reminder'}), 500

    except Exception as e:
        logger.error(f'Error cancelling reminder {reminder_id}: {e}', exc=e)
        return jsonify({'error': str(e)}), 500


@reminder_bp.route('/api/reminders/user/<user_id>', methods=['GET'])
def get_user_reminders(user_id: str):
    """Get all reminders for a specific user.

    Args:
        user_id: Slack user ID

    Returns:
        JSON response with list of reminders
    """
    try:
        reminders = _reminder_service.get_user_reminders(user_id)

        return jsonify({
            'user_id': user_id,
            'count': len(reminders),
            'reminders': [_format_reminder(r) for r in reminders]
        }), 200

    except Exception as e:
        logger.error(f'Error getting reminders for user {user_id}: {e}', exc=e)
        return jsonify({'error': str(e)}), 500


@reminder_bp.route('/api/reminders/channel/<channel_id>', methods=['GET'])
def get_channel_reminders(channel_id: str):
    """Get all reminders for a specific channel.

    Args:
        channel_id: Slack channel ID

    Query parameters:
        - thread_ts: Optional thread timestamp to filter by thread

    Returns:
        JSON response with list of reminders
    """
    try:
        thread_ts = request.args.get('thread_ts')

        if thread_ts:
            reminders = _reminder_service.get_thread_reminders(channel_id, thread_ts)
        else:
            # Get all reminders in channel
            all_reminders = _reminder_service.reminder_repo.get_pending()
            reminders = [r for r in all_reminders if r.channel_id == channel_id]

        return jsonify({
            'channel_id': channel_id,
            'thread_ts': thread_ts,
            'count': len(reminders),
            'reminders': [_format_reminder(r) for r in reminders]
        }), 200

    except Exception as e:
        logger.error(f'Error getting reminders for channel {channel_id}: {e}', exc=e)
        return jsonify({'error': str(e)}), 500


@reminder_bp.route('/api/audit/<int:reminder_id>', methods=['GET'])
def get_audit_log(reminder_id: int):
    """Get audit log for a reminder.

    Args:
        reminder_id: Reminder ID

    Returns:
        JSON response with audit log entries
    """
    try:
        audit_logs = _reminder_service.get_audit_history(reminder_id)

        return jsonify({
            'reminder_id': reminder_id,
            'count': len(audit_logs),
            'audit_logs': [_format_audit_log(a) for a in audit_logs]
        }), 200

    except Exception as e:
        logger.error(f'Error getting audit log for reminder {reminder_id}: {e}', exc=e)
        return jsonify({'error': str(e)}), 500


def _format_reminder(reminder) -> dict:
    """Format reminder for JSON response.

    Args:
        reminder: Reminder object

    Returns:
        Dictionary representation of reminder
    """
    try:
        return {
            'id': reminder.id,
            'channel_id': reminder.channel_id,
            'thread_ts': reminder.thread_ts,
            'user_id': reminder.user_id,
            'message_ts': reminder.message_ts,
            'deadline_text': reminder.deadline_text,
            'deadline_datetime': reminder.deadline_datetime.isoformat() if reminder.deadline_datetime else None,
            'reminder_datetime': reminder.reminder_datetime.isoformat() if reminder.reminder_datetime else None,
            'status': reminder.status.value,
            'created_at': reminder.created_at.isoformat() if reminder.created_at else None,
            'updated_at': reminder.updated_at.isoformat() if reminder.updated_at else None,
            'sent_at': reminder.sent_at.isoformat() if reminder.sent_at else None,
            'retry_count': reminder.retry_count,
            'reschedule_count': reminder.reschedule_count,
            'previous_deadline': reminder.previous_deadline.isoformat() if reminder.previous_deadline else None
        }
    except Exception as e:
        logger.error(f'Error formatting reminder: {e}', exc=e)
        raise


def _format_audit_log(audit_log) -> dict:
    """Format audit log for JSON response.

    Args:
        audit_log: AuditLog object

    Returns:
        Dictionary representation of audit log
    """
    try:
        return {
            'id': audit_log.id,
            'reminder_id': audit_log.reminder_id,
            'action': audit_log.action.value,
            'field_changed': audit_log.field_changed,
            'old_value': audit_log.old_value,
            'new_value': audit_log.new_value,
            'performed_by': audit_log.performed_by,
            'performed_at': audit_log.performed_at.isoformat() if audit_log.performed_at else None,
            'metadata': audit_log.metadata
        }
    except Exception as e:
        logger.error(f'Error formatting audit log: {e}', exc=e)
        raise
