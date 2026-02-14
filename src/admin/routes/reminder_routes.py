"""Reminder management routes for admin panel - FAST VERSION (No Hanging)."""
from flask import Blueprint, jsonify, request
from typing import Optional
from functools import wraps
import time
import os
from datetime import datetime
from src.database.db_manager import DBManager
from src.database.repositories.reminder_repository import ReminderRepository
from src.database.repositories.audit_repository import AuditRepository
from src.services.reminder_service import ReminderService
from src.services.notification_service import NotificationService
from src.core.models import ReminderStatus
from src.config.settings import Settings
from src.utils.logger import get_logger
from slack_sdk import WebClient


logger = get_logger('ReminderRoutes')

# Create blueprint
reminder_bp = Blueprint('reminders', __name__)

# Initialize services (will be set up in app.py)
_reminder_service: Optional[ReminderService] = None
_notification_service: Optional[NotificationService] = None
_slack_client: Optional[WebClient] = None

# Cache for user and channel names to avoid repeated API calls
_user_cache: dict = {}
_channel_cache: dict = {}


def init_reminder_routes(settings: Settings):
    """Initialize reminder routes with services."""
    global _reminder_service, _notification_service, _slack_client

    db_manager = DBManager(settings)
    reminder_repo = ReminderRepository(db_manager)
    audit_repo = AuditRepository(db_manager)

    _reminder_service = ReminderService(
        reminder_repo=reminder_repo,
        audit_repo=audit_repo
    )

    _slack_client = WebClient(token=settings.slack_bot_token)
    _notification_service = NotificationService(_slack_client)

    logger.info('Reminder routes initialized')


def _get_user_name(user_id: str) -> str:
    """Get user name from Slack API with caching."""
    if not user_id:
        return '-'

    if not _slack_client:
        return user_id

    # Check cache first
    if user_id in _user_cache:
        return _user_cache[user_id]

    try:
        response = _slack_client.users_info(user=user_id)
        if response and response.get('ok') and response.get('user'):
            user = response['user']
            # Prefer real_name, fallback to display_name, then name, then user_id
            user_name = (
                user.get('real_name') or
                user.get('profile', {}).get('display_name') or
                user.get('name') or
                user_id
            )
            _user_cache[user_id] = user_name
            return user_name
        else:
            # API returned error, cache the ID to avoid repeated calls
            _user_cache[user_id] = user_id
            return user_id
    except Exception as e:
        logger.warning(f'Error fetching user info for {user_id}: {e}')
        # Cache the ID to avoid repeated failed calls
        _user_cache[user_id] = user_id
        return user_id


def _get_channel_name(channel_id: str) -> str:
    """Get channel name from Slack API with caching."""
    if not channel_id:
        return '-'

    if not _slack_client:
        return channel_id

    # Check cache first
    if channel_id in _channel_cache:
        return _channel_cache[channel_id]

    try:
        response = _slack_client.conversations_info(channel=channel_id)
        if response and response.get('ok') and response.get('channel'):
            channel = response['channel']
            # Get channel name, handle both public and private channels
            channel_name = (
                channel.get('name') or
                channel.get('id', channel_id)
            )
            _channel_cache[channel_id] = channel_name
            return channel_name
        else:
            # API returned error, cache the ID to avoid repeated calls
            _channel_cache[channel_id] = channel_id
            return channel_id
    except Exception as e:
        logger.warning(f'Error fetching channel info for {channel_id}: {e}')
        # Cache the ID to avoid repeated failed calls
        _channel_cache[channel_id] = channel_id
        return channel_id


@reminder_bp.route('/api/reminders', methods=['GET'])
def list_reminders():
    """List all reminders - FAST VERSION (avoids hanging transactions)."""
    start_time = time.time()
    try:
        # Parse parameters
        status_filter = request.args.get('status')
        user_id_filter = request.args.get('user_id')
        channel_id_filter = request.args.get('channel_id')
        limit = min(int(request.args.get('limit', 100)), 1000)
        offset = max(int(request.args.get('offset', 0)), 0)

        logger.info(f'Listing reminders - status: {status_filter}, limit: {limit}, offset: {offset}')

        db_manager = _reminder_service.reminder_repo.db
        placeholder = '%s' if db_manager.database_type != 'sqlite' else '?'

        # Build WHERE clause
        where_conditions = []
        params = []

        if status_filter:
            where_conditions.append(f'status = {placeholder}')
            params.append(status_filter)
        if user_id_filter:
            where_conditions.append(f'user_id = {placeholder}')
            params.append(user_id_filter)
        if channel_id_filter:
            where_conditions.append(f'channel_id = {placeholder}')
            params.append(channel_id_filter)

        where_clause = ' AND '.join(where_conditions) if where_conditions else '1=1'

        # FAST: Get count, stats, and reminders in parallel (but sequentially for safety)
        # 1. Get total count
        count_query = f'SELECT COUNT(*) as count FROM reminders WHERE {where_clause}'
        count_result = db_manager.fetch_one(count_query, tuple(params) if params else None)
        total = count_result['count'] if count_result else 0

        # 2. Get status counts (only if no filters)
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

            try:
                status_results = db_manager.fetch_all(
                    status_query,
                    ('pending', 'sent', 'cancelled', 'failed', 'rescheduled')
                )
                for row in status_results:
                    status = row.get('status') or row.get('STATUS')
                    count = row.get('count') or row.get('COUNT')
                    if status in status_counts and count is not None:
                        status_counts[status] = int(count)
            except Exception as e:
                logger.warning(f'Error getting status counts: {e}')

        # 3. Get reminders - USE DIRECT QUERY (fastest, avoids repository overhead)
        reminders_query = f'''
            SELECT id, channel_id, thread_ts, user_id, message_ts,
                   original_message, deadline_text, deadline_datetime,
                   reminder_datetime, status, created_at, updated_at,
                   sent_at, retry_count, reschedule_count, previous_deadline
            FROM reminders
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT {placeholder} OFFSET {placeholder}
        '''
        reminders_params = tuple(params) + (limit, offset)

        try:
            rows = db_manager.fetch_all(reminders_query, reminders_params)
        except Exception as e:
            logger.error(f'Error fetching reminders: {e}', exc=e)
            rows = []

        # 4. Format reminders directly (avoid slow _row_to_reminder conversion)
        # Helper to safely format datetime
        def format_dt(dt_val):
            if not dt_val:
                return None
            if isinstance(dt_val, str):
                return dt_val  # Already a string
            try:
                return dt_val.isoformat()
            except:
                return str(dt_val)

        # Collect unique user and channel IDs first for batch processing
        unique_user_ids = set()
        unique_channel_ids = set()
        for row in rows:
            user_id = row.get('user_id')
            channel_id = row.get('channel_id')
            if user_id:
                unique_user_ids.add(user_id)
            if channel_id:
                unique_channel_ids.add(channel_id)

        # Pre-fetch names for all unique IDs (this populates cache)
        # This is more efficient than fetching one by one
        for user_id in unique_user_ids:
            if user_id not in _user_cache:
                _get_user_name(user_id)

        for channel_id in unique_channel_ids:
            if channel_id not in _channel_cache:
                _get_channel_name(channel_id)

        # Now format reminders (cache is populated, so this is fast)
        formatted_reminders = []
        for row in rows:
            try:
                user_id = row.get('user_id') or ''
                channel_id = row.get('channel_id') or ''

                formatted_reminders.append({
                    'id': row.get('id'),
                    'channel_id': channel_id,
                    'channel_name': _get_channel_name(channel_id) if channel_id else None,
                    'thread_ts': row.get('thread_ts'),
                    'user_id': user_id,
                    'user_name': _get_user_name(user_id) if user_id else None,
                    'message_ts': row.get('message_ts'),
                    'deadline_text': row.get('deadline_text'),
                    'deadline_datetime': format_dt(row.get('deadline_datetime')),
                    'reminder_datetime': format_dt(row.get('reminder_datetime')),
                    'status': row.get('status'),
                    'created_at': format_dt(row.get('created_at')),
                    'updated_at': format_dt(row.get('updated_at')),
                    'sent_at': format_dt(row.get('sent_at')),
                    'retry_count': row.get('retry_count', 0),
                    'reschedule_count': row.get('reschedule_count', 0),
                    'previous_deadline': format_dt(row.get('previous_deadline'))
                })
            except Exception as e:
                logger.warning(f'Error formatting reminder row: {e}', exc=e)
                continue

        elapsed = time.time() - start_time
        logger.info(f'Returning {len(formatted_reminders)} reminders (total: {total}) in {elapsed:.3f}s')

        result = {
            'total': total,
            'limit': limit,
            'offset': offset,
            'reminders': formatted_reminders,
            'stats': status_counts
        }

        return jsonify(result), 200

    except ValueError as e:
        logger.error(f'Invalid parameter: {e}')
        return jsonify({'error': f'Invalid parameter: {str(e)}'}), 400
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f'Error listing reminders after {elapsed:.3f}s: {e}', exc=e)
        import traceback
        logger.error(f'Traceback: {traceback.format_exc()}')
        return jsonify({'error': 'Internal server error'}), 500


@reminder_bp.route('/api/reminders/<int:reminder_id>', methods=['GET'])
def get_reminder(reminder_id: int):
    """Get a single reminder by ID."""
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
    """Update a reminder."""
    try:
        reminder = _reminder_service.get_reminder(reminder_id)
        if not reminder:
            return jsonify({'error': 'Reminder not found'}), 404

        data = request.get_json() or {}
        updates = {}

        if 'status' in data:
            try:
                updates['status'] = ReminderStatus(data['status'])
            except ValueError:
                return jsonify({'error': f'Invalid status: {data["status"]}'}), 400

        if 'deadline_datetime' in data:
            try:
                updates['deadline_datetime'] = datetime.fromisoformat(data['deadline_datetime'])
            except ValueError:
                return jsonify({'error': 'Invalid deadline_datetime format'}), 400

        if 'reminder_datetime' in data:
            try:
                updates['reminder_datetime'] = datetime.fromisoformat(data['reminder_datetime'])
            except ValueError:
                return jsonify({'error': 'Invalid reminder_datetime format'}), 400

        if not updates:
            return jsonify({'error': 'No valid fields to update'}), 400

        if _reminder_service.reminder_repo.update(reminder_id, updates):
            reminder = _reminder_service.get_reminder(reminder_id)
            return jsonify(_format_reminder(reminder)), 200
        else:
            return jsonify({'error': 'Failed to update reminder'}), 500

    except Exception as e:
        logger.error(f'Error updating reminder {reminder_id}: {e}', exc=e)
        return jsonify({'error': str(e)}), 500


@reminder_bp.route('/api/reminders/<int:reminder_id>', methods=['DELETE'])
def delete_reminder(reminder_id: int):
    """Delete a reminder."""
    try:
        reminder = _reminder_service.get_reminder(reminder_id)
        if not reminder:
            return jsonify({'error': 'Reminder not found'}), 404

        if _reminder_service.delete_reminder(reminder_id, 'admin'):
            return jsonify({'success': True, 'message': 'Reminder deleted'}), 200
        else:
            return jsonify({'error': 'Failed to delete reminder'}), 500

    except Exception as e:
        logger.error(f'Error deleting reminder {reminder_id}: {e}', exc=e)
        return jsonify({'error': str(e)}), 500


@reminder_bp.route('/api/reminders/<int:reminder_id>/cancel', methods=['POST'])
def cancel_reminder(reminder_id: int):
    """Cancel a reminder."""
    try:
        reminder = _reminder_service.get_reminder(reminder_id)
        if not reminder:
            return jsonify({'error': 'Reminder not found'}), 404

        if _reminder_service.cancel(reminder_id, 'admin'):
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
    """Get all reminders for a specific user."""
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
    """Get all reminders for a specific channel."""
    try:
        thread_ts = request.args.get('thread_ts')
        if thread_ts:
            reminders = _reminder_service.get_thread_reminders(channel_id, thread_ts)
        else:
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
    """Get audit log for a reminder."""
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


@reminder_bp.route('/api/reminders/trigger-eod', methods=['POST'])
def trigger_eod_check():
    """Manually trigger EOD follow-up check."""
    try:
        if not _reminder_service or not _notification_service:
            return jsonify({'error': 'Services not initialized'}), 500

        logger.info('Manual EOD trigger requested via Admin API')
        count = _reminder_service.process_eod_followups(_notification_service)
        
        return jsonify({
            'success': True,
            'message': f'EOD check complete. Sent {count} follow-up(s).',
            'count': count
        }), 200

    except Exception as e:
        logger.error(f'Error triggering EOD check: {e}', exc=e)
        return jsonify({'error': str(e)}), 500


_BOT_PAUSE_FLAG = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.bot_paused')


@reminder_bp.route('/api/bot/status', methods=['GET'])
def bot_status():
    """Get current bot pause/resume status."""
    paused = os.path.exists(_BOT_PAUSE_FLAG)
    return jsonify({'paused': paused, 'status': 'paused' if paused else 'running'}), 200


@reminder_bp.route('/api/bot/pause', methods=['POST'])
def pause_bot():
    """Pause the bot (stops processing new Slack messages)."""
    try:
        with open(_BOT_PAUSE_FLAG, 'w') as f:
            f.write('paused')
        logger.info('Bot paused via admin panel')
        return jsonify({'success': True, 'status': 'paused'}), 200
    except Exception as e:
        logger.error(f'Error pausing bot: {e}', exc=e)
        return jsonify({'error': str(e)}), 500


@reminder_bp.route('/api/bot/resume', methods=['POST'])
def resume_bot():
    """Resume the bot (resumes processing Slack messages)."""
    try:
        if os.path.exists(_BOT_PAUSE_FLAG):
            os.remove(_BOT_PAUSE_FLAG)
        logger.info('Bot resumed via admin panel')
        return jsonify({'success': True, 'status': 'running'}), 200
    except Exception as e:
        logger.error(f'Error resuming bot: {e}', exc=e)
        return jsonify({'error': str(e)}), 500


def _format_reminder(reminder) -> dict:
    """Format reminder for JSON response."""
    return {
        'id': reminder.id,
        'channel_id': reminder.channel_id,
        'channel_name': _get_channel_name(reminder.channel_id) if reminder.channel_id else None,
        'thread_ts': reminder.thread_ts,
        'user_id': reminder.user_id,
        'user_name': _get_user_name(reminder.user_id) if reminder.user_id else None,
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


def _format_audit_log(audit_log) -> dict:
    """Format audit log for JSON response."""
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
