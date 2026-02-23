"""Shared pytest fixtures for all tests.

This conftest.py provides fixtures that are available to all test files:
- mock_settings: Fake settings object (no real API keys needed)
- db_manager: In-memory SQLite database with migrations applied
- reminder_repo / audit_repo: Repository instances using in-memory DB
- mock_slack_client: Mocked Slack WebClient
- Sample data factories from fixtures.sample_data
"""
import pytest
import os
import tempfile
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta

# Import core modules
from src.config.settings import Settings
from src.database.db_manager import DBManager
from src.database.repositories.reminder_repository import ReminderRepository
from src.database.repositories.audit_repository import AuditRepository
from src.utils.timezone import now_ist

# Import sample data factories
from tests.fixtures.sample_data import (
    create_sample_reminder,
    create_sample_context,
    create_sample_deadline,
    create_sample_audit_log
)


@pytest.fixture
def mock_settings():
    """Create a mock Settings object with fake credentials.
    
    No real API keys needed - all values are fake but valid format.
    """
    # Create a temporary .env file for testing
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write('SLACK_BOT_TOKEN=xoxb-test-token-12345\n')
        f.write('SLACK_APP_TOKEN=xapp-test-token-12345\n')
        f.write('SLACK_SIGNING_SECRET=test-signing-secret\n')
        f.write('GEMINI_API_KEY=test-gemini-key-12345\n')
        f.write('FLASK_SECRET_KEY=test-flask-secret-key\n')
        f.write('ADMIN_USERNAME=test_admin\n')
        f.write('ADMIN_PASSWORD=test_password\n')
        f.write('DATABASE_TYPE=sqlite\n')
        f.write('DATABASE_PATH=:memory:\n')
        temp_env_path = f.name
    
    # Temporarily set environment variables
    old_env = os.environ.copy()
    os.environ.update({
        'SLACK_BOT_TOKEN': 'xoxb-test-token-12345',
        'SLACK_APP_TOKEN': 'xapp-test-token-12345',
        'SLACK_SIGNING_SECRET': 'test-signing-secret',
        'GEMINI_API_KEY': 'test-gemini-key-12345',
        'FLASK_SECRET_KEY': 'test-flask-secret-key',
        'ADMIN_USERNAME': 'test_admin',
        'ADMIN_PASSWORD': 'test_password',
        'DATABASE_TYPE': 'sqlite',
        'DATABASE_PATH': ':memory:',
    })
    
    try:
        settings = Settings()
        yield settings
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(old_env)
        # Clean up temp file
        try:
            os.unlink(temp_env_path)
        except:
            pass


@pytest.fixture
def db_manager(mock_settings):
    """Create an in-memory SQLite database with migrations applied.
    
    Returns:
        DBManager instance with schema initialized
    """
    # Override database path to use in-memory
    mock_settings.database_path = ':memory:'
    
    db = DBManager(mock_settings)
    
    # Run migrations to create schema
    from src.database.migrations.versions.001_initial_schema import upgrade as upgrade_001
    from src.database.migrations.versions.002_add_followup_fields import upgrade as upgrade_002
    
    with db.get_connection() as conn:
        upgrade_001(conn)
        upgrade_002(conn)
    
    yield db
    
    # Cleanup
    db.close_all()


@pytest.fixture
def reminder_repo(db_manager):
    """Create a ReminderRepository instance using in-memory DB.
    
    Returns:
        ReminderRepository instance
    """
    return ReminderRepository(db_manager)


@pytest.fixture
def audit_repo(db_manager):
    """Create an AuditRepository instance using in-memory DB.
    
    Returns:
        AuditRepository instance
    """
    return AuditRepository(db_manager)


@pytest.fixture
def mock_slack_client():
    """Create a mocked Slack WebClient.
    
    Returns:
        Mock WebClient with common methods stubbed
    """
    client = Mock()
    
    # Mock chat.postMessage
    client.chat_postMessage = Mock(return_value={
        'ok': True,
        'ts': '1234567890.123456',
        'channel': 'C123456'
    })
    
    # Mock users.info
    client.users_info = Mock(return_value={
        'ok': True,
        'user': {
            'id': 'U123456',
            'name': 'testuser',
            'real_name': 'Test User',
            'profile': {
                'display_name': 'Test User'
            }
        }
    })
    
    # Mock conversations.info
    client.conversations_info = Mock(return_value={
        'ok': True,
        'channel': {
            'id': 'C123456',
            'name': 'test-channel'
        }
    })
    
    # Mock chat.getPermalink
    client.chat_getPermalink = Mock(return_value={
        'ok': True,
        'permalink': 'https://test.slack.com/archives/C123456/p1234567890123456'
    })
    
    # Mock conversations.history
    client.conversations_history = Mock(return_value={
        'ok': True,
        'messages': [
            {
                'type': 'message',
                'user': 'U123456',
                'text': 'Test parent message',
                'ts': '1234567890.123456'
            }
        ]
    })
    
    return client


@pytest.fixture
def sample_reminder():
    """Factory fixture for creating sample Reminder objects.
    
    Returns:
        Function that creates Reminder objects
    """
    return create_sample_reminder


@pytest.fixture
def sample_context():
    """Factory fixture for creating sample ReminderContext objects.
    
    Returns:
        Function that creates ReminderContext objects
    """
    return create_sample_context


@pytest.fixture
def sample_deadline():
    """Factory fixture for creating sample ParsedDeadline objects.
    
    Returns:
        Function that creates ParsedDeadline objects
    """
    return create_sample_deadline


@pytest.fixture
def sample_audit_log():
    """Factory fixture for creating sample AuditLog objects.
    
    Returns:
        Function that creates AuditLog objects
    """
    return create_sample_audit_log


@pytest.fixture
def freeze_time():
    """Fixture to freeze time for testing.
    
    Returns:
        A frozen datetime that can be used consistently across a test
    """
    return now_ist()
