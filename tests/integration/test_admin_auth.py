"""Integration tests for the admin panel login.

The credentials come from .env (ADMIN_USERNAME / ADMIN_PASSWORD). The shared
mock_settings fixture sets them to test_admin / test_password.
"""
import os
from datetime import timedelta

import pytest

from src.admin import app as admin_app
from src.admin.app import create_app
from src.admin.routes import reminder_routes

USERNAME = 'test_admin'
PASSWORD = 'test_password'


def _build_app(settings, monkeypatch):
    monkeypatch.setattr(admin_app, 'FAILED_LOGIN_DELAY_SECONDS', 0)
    app = create_app(settings=settings)
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    return app


@pytest.fixture
def client(mock_settings, monkeypatch):
    return _build_app(mock_settings, monkeypatch).test_client()


def _login(client, username=USERNAME, password=PASSWORD):
    return client.post('/login', data={'username': username, 'password': password})


@pytest.mark.integration
class TestNotLoggedIn:
    def test_dashboard_redirects_to_login(self, client):
        response = client.get('/')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/login')

    def test_unknown_page_redirects_to_login(self, client):
        response = client.get('/anything')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/login')

    @pytest.mark.parametrize('path', ['/api/reminders', '/api/bot/status', '/api/reminders/1'])
    def test_api_returns_401(self, client, path):
        response = client.get(path)
        assert response.status_code == 401
        assert response.get_json() == {'error': 'Unauthorized'}

    def test_pause_is_blocked_and_flag_not_written(self, client):
        flag = os.path.abspath(reminder_routes._BOT_PAUSE_FLAG)
        if os.path.exists(flag):
            pytest.skip('.bot_paused already exists in this checkout')
        response = client.post('/api/bot/pause')
        assert response.status_code == 401
        assert not os.path.exists(flag)

    @pytest.mark.parametrize('method, path', [
        ('post', '/api/reminders/trigger-eod'),
        ('post', '/api/reminders/1/cancel'),
        ('delete', '/api/reminders/1'),
        ('put', '/api/reminders/1'),
        ('post', '/api/bot/resume'),
    ])
    def test_changing_actions_are_blocked(self, client, method, path):
        response = getattr(client, method)(path)
        assert response.status_code == 401

    @pytest.mark.parametrize('path', ['/health', '/static/css/dashboard.css', '/login'])
    def test_public_paths_stay_open(self, client, path):
        assert client.get(path).status_code == 200

    def test_login_page_has_only_username_and_password(self, client):
        html = client.get('/login').get_data(as_text=True)
        assert 'name="username"' in html
        assert 'name="password"' in html
        assert html.count('<input') == 2


@pytest.mark.integration
class TestLogin:
    def test_wrong_password_is_rejected(self, client):
        response = _login(client, password='wrong')
        assert response.status_code == 401
        assert 'Invalid username or password' in response.get_data(as_text=True)
        assert client.get('/api/bot/status').status_code == 401

    def test_wrong_username_is_rejected(self, client):
        response = _login(client, username='someone')
        assert response.status_code == 401
        assert client.get('/api/bot/status').status_code == 401

    def test_empty_form_is_rejected(self, client):
        assert client.post('/login', data={}).status_code == 401

    def test_right_credentials_open_dashboard_and_api(self, client):
        response = _login(client)
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/')
        assert client.get('/').status_code == 200
        assert client.get('/api/bot/status').status_code == 200

    def test_dashboard_shows_logout_link(self, client):
        _login(client)
        assert 'href="/logout"' in client.get('/').get_data(as_text=True)

    def test_login_page_redirects_when_already_logged_in(self, client):
        _login(client)
        response = client.get('/login')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/')

    def test_logout_ends_session(self, client):
        _login(client)
        response = client.get('/logout')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/login')
        assert client.get('/api/bot/status').status_code == 401
        assert client.get('/').status_code == 302

    def test_password_is_never_logged(self, client, capsys):
        _login(client, password='wrong-secret-123')
        _login(client)
        output = capsys.readouterr().out
        assert 'wrong-secret-123' not in output
        assert PASSWORD not in output


@pytest.mark.integration
class TestSessionCookie:
    def test_session_lasts_seven_days(self, mock_settings, monkeypatch):
        app = _build_app(mock_settings, monkeypatch)
        assert app.permanent_session_lifetime == timedelta(days=7)

    def test_cookie_flags_default_to_secure(self, mock_settings, monkeypatch):
        monkeypatch.delenv('ADMIN_COOKIE_SECURE', raising=False)
        monkeypatch.setattr(admin_app, 'FAILED_LOGIN_DELAY_SECONDS', 0)
        app = create_app(settings=mock_settings)
        app.config['TESTING'] = True
        response = app.test_client().post('/login', data={'username': USERNAME, 'password': PASSWORD})
        cookie = response.headers['Set-Cookie']
        assert 'Secure' in cookie
        assert 'HttpOnly' in cookie
        assert 'SameSite=Lax' in cookie
        assert 'Expires=' in cookie

    def test_secure_flag_can_be_disabled_for_local_http(self, mock_settings, monkeypatch):
        monkeypatch.setenv('ADMIN_COOKIE_SECURE', 'false')
        app = create_app(settings=mock_settings)
        assert app.config['SESSION_COOKIE_SECURE'] is False


@pytest.mark.integration
class TestLoginNotConfigured:
    @pytest.mark.parametrize('password', ['changeme', ''])
    def test_default_or_empty_password_refuses_every_login(self, mock_settings, monkeypatch, password):
        mock_settings.admin_password = password
        client = _build_app(mock_settings, monkeypatch).test_client()
        response = _login(client, password=password)
        assert response.status_code == 401
        assert 'not set up' in response.get_data(as_text=True)
        assert client.get('/api/bot/status').status_code == 401
