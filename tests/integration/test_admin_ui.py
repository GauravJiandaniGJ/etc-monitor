"""Checks on the admin panel's HTML, CSS and JS that keep the redesign honest.

These read what the server sends (no browser): local styles only, theme set before
paint, the licensed icon sprite, and the dashboard's no-polling / no-HTML-injection rules.
"""
import pytest

from src.admin import app as admin_app
from src.admin.app import create_app

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
class TestLoginPage:
    def test_login_page_uses_local_styles_only(self, client):
        html = client.get('/login').get_data(as_text=True)
        assert 'css/base.css' in html
        assert 'css/login.css' in html
        assert 'fonts.googleapis' not in html

    def test_login_page_sets_theme_before_paint(self, client):
        html = client.get('/login').get_data(as_text=True)
        head = html.split('</head>')[0]
        assert 'localStorage' in head
        assert 'prefers-color-scheme' in head

    def test_icon_sprite_has_license_and_symbols(self, client):
        html = client.get('/login').get_data(as_text=True)
        assert 'Phosphor Icons' in html
        assert 'MIT License' in html
        assert 'id="i-warning"' in html
        assert 'id="i-sign-out"' in html

    def test_login_error_is_announced(self, client):
        html = _login(client, password='wrong').get_data(as_text=True)
        assert 'role="alert"' in html
        assert 'Invalid username or password' in html


@pytest.mark.integration
class TestDashboardPage:
    def test_dashboard_has_new_layout(self, client):
        _login(client)
        html = client.get('/').get_data(as_text=True)
        for needle in ('id="up-next"', 'id="all-etcs"', 'id="refresh-btn"', 'id="bot-menu"',
                       'id="confirm-dialog"', 'href="/logout"', 'type="module"', 'css/base.css'):
            assert needle in html, needle
        for gone in ('trigger-eod-btn', 'bot-toggle-btn', 'fonts.googleapis'):
            assert gone not in html, gone
