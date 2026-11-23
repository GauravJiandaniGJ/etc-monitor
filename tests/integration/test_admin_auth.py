"""Integration tests for the admin panel login.

The credentials come from .env (ADMIN_USERNAME / ADMIN_PASSWORD). The shared
mock_settings fixture sets them to test_admin / test_password.
"""
import os
from datetime import timedelta

import pytest

from src.admin import app as admin_app
from src.admin.app import LoginThrottle, create_app
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


def _login_from(client, ip, password='wrong', remote_addr='127.0.0.1'):
    """Log in as if through nginx/Cloudflare from `ip` (or directly from remote_addr)."""
    return client.post(
        '/login',
        data={'username': USERNAME, 'password': password},
        headers={'CF-Connecting-IP': ip},
        environ_base={'REMOTE_ADDR': remote_addr},
    )


@pytest.mark.integration
class TestBruteForceProtection:
    def test_client_is_locked_out_after_too_many_failures(self, client):
        for _ in range(admin_app.MAX_FAILURES_PER_CLIENT):
            assert _login_from(client, '198.51.100.1').status_code == 401
        # Even the right password is refused while locked out.
        response = _login_from(client, '198.51.100.1', password=PASSWORD)
        assert response.status_code == 429
        assert 'Too many failed attempts' in response.get_data(as_text=True)
        assert client.get('/api/bot/status').status_code == 401

    def test_other_clients_can_still_log_in(self, client):
        for _ in range(admin_app.MAX_FAILURES_PER_CLIENT):
            _login_from(client, '198.51.100.1')
        assert _login_from(client, '198.51.100.2', password=PASSWORD).status_code == 302

    def test_successful_login_clears_earlier_failures(self, client):
        ip = '198.51.100.3'
        for _ in range(admin_app.MAX_FAILURES_PER_CLIENT - 1):
            _login_from(client, ip)
        assert _login_from(client, ip, password=PASSWORD).status_code == 302
        client.get('/logout')
        for _ in range(admin_app.MAX_FAILURES_PER_CLIENT - 1):
            assert _login_from(client, ip).status_code == 401
        assert _login_from(client, ip, password=PASSWORD).status_code == 302

    def test_total_cap_stops_attackers_rotating_addresses(self, client, monkeypatch):
        monkeypatch.setattr(admin_app, 'MAX_FAILURES_TOTAL', 6)
        for i in range(6):
            assert _login_from(client, f'203.0.113.{i}').status_code == 401
        assert _login_from(client, '203.0.113.200', password=PASSWORD).status_code == 429

    def test_direct_connection_cannot_forge_its_address(self, client):
        # Not via nginx: CF-Connecting-IP is ignored, the socket address counts.
        for i in range(admin_app.MAX_FAILURES_PER_CLIENT):
            response = _login_from(client, f'192.0.2.{i}', remote_addr='203.0.113.50')
            assert response.status_code == 401
        response = _login_from(client, '192.0.2.99', password=PASSWORD, remote_addr='203.0.113.50')
        assert response.status_code == 429


class TestLoginThrottleWindow:
    def test_lockout_ends_when_failures_age_out(self):
        throttle = LoginThrottle()
        start = 1000.0
        for i in range(admin_app.MAX_FAILURES_PER_CLIENT):
            throttle.record_failure('client', now=start + i)
        window = admin_app.FAILURE_WINDOW_SECONDS
        assert throttle.is_blocked('client', now=start + window - 1)
        assert not throttle.is_blocked('client', now=start + window)

    def test_unknown_client_is_not_blocked(self):
        assert not LoginThrottle().is_blocked('nobody', now=0.0)
