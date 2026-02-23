"""Integration tests for admin API routes.

Tests Flask admin panel routes with real test client and in-memory database.
"""
import pytest
import json
from unittest.mock import Mock, patch
from src.admin.app import create_app
from src.core.models import ReminderStatus


@pytest.fixture
def app(db_manager, mock_settings):
    """Create Flask app for testing."""
    app = create_app(settings=mock_settings, db_manager=db_manager)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.mark.integration
class TestReminderRoutes:
    """Integration tests for reminder API routes."""
    
    def test_list_reminders(self, client, reminder_repo, sample_reminder):
        """Test GET /api/reminders - list all reminders."""
        # Create test reminders
        reminder_repo.create(sample_reminder())
        reminder_repo.create(sample_reminder(message_ts="9999999999.999999"))
        
        response = client.get('/api/reminders')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'reminders' in data
        assert len(data['reminders']) >= 2
    
    def test_get_reminder_by_id(self, client, reminder_repo, sample_reminder):
        """Test GET /api/reminders/<id> - get single reminder."""
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        response = client.get(f'/api/reminders/{reminder_id}')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['id'] == reminder_id
        assert data['channel_id'] == reminder.channel_id
    
    def test_get_nonexistent_reminder(self, client):
        """Test GET /api/reminders/<id> with non-existent ID."""
        response = client.get('/api/reminders/99999')
        
        assert response.status_code == 404
    
    def test_update_reminder(self, client, reminder_repo, sample_reminder):
        """Test PUT /api/reminders/<id> - update reminder."""
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        update_data = {
            'deadline_text': '5 hours'
        }
        
        response = client.put(
            f'/api/reminders/{reminder_id}',
            data=json.dumps(update_data),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        
        # Verify update
        updated = reminder_repo.get_by_id(reminder_id)
        assert updated.deadline_text == '5 hours'
    
    def test_delete_reminder(self, client, reminder_repo, sample_reminder):
        """Test DELETE /api/reminders/<id> - delete reminder."""
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        response = client.delete(f'/api/reminders/{reminder_id}')
        
        assert response.status_code == 200
        
        # Verify deletion
        deleted = reminder_repo.get_by_id(reminder_id)
        assert deleted is None
    
    def test_cancel_reminder(self, client, reminder_repo, sample_reminder):
        """Test POST /api/reminders/<id>/cancel - cancel reminder."""
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        response = client.post(f'/api/reminders/{reminder_id}/cancel')
        
        assert response.status_code == 200
        
        # Verify cancellation
        cancelled = reminder_repo.get_by_id(reminder_id)
        assert cancelled.status == ReminderStatus.CANCELLED
    
    def test_get_user_reminders(self, client, reminder_repo, sample_reminder):
        """Test GET /api/reminders/user/<user_id> - get user's reminders."""
        user_id = "U123456"
        reminder_repo.create(sample_reminder(user_id=user_id))
        reminder_repo.create(sample_reminder(user_id=user_id, message_ts="9999999999.999999"))
        
        response = client.get(f'/api/reminders/user/{user_id}')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data['reminders']) >= 2
        assert all(r['user_id'] == user_id for r in data['reminders'])


@pytest.mark.integration
class TestAuditRoutes:
    """Integration tests for audit API routes."""
    
    def test_get_reminder_audit_log(self, client, reminder_repo, audit_repo, sample_reminder, sample_audit_log):
        """Test GET /api/audit/<reminder_id> - get audit log for reminder."""
        # Create reminder
        reminder = sample_reminder()
        reminder_id = reminder_repo.create(reminder)
        
        # Create audit logs
        audit_repo.log(sample_audit_log(reminder_id=reminder_id))
        
        response = client.get(f'/api/audit/{reminder_id}')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'audit_logs' in data
        assert len(data['audit_logs']) >= 1


@pytest.mark.integration
class TestBotStatusRoutes:
    """Integration tests for bot status API routes."""
    
    @patch('src.admin.routes.reminder_routes.bot_paused', False)
    def test_get_bot_status(self, client):
        """Test GET /api/bot/status - get bot status."""
        response = client.get('/api/bot/status')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'paused' in data
    
    @patch('src.admin.routes.reminder_routes.bot_paused', False)
    def test_pause_bot(self, client):
        """Test POST /api/bot/pause - pause bot."""
        response = client.post('/api/bot/pause')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['paused'] is True
    
    @patch('src.admin.routes.reminder_routes.bot_paused', True)
    def test_resume_bot(self, client):
        """Test POST /api/bot/resume - resume bot."""
        response = client.post('/api/bot/resume')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['paused'] is False
