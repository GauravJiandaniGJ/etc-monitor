"""Checks on the admin panel's HTML, CSS and JS that keep the redesign honest.

These read what the server sends (no browser): local styles only, theme set before
paint, the licensed icon sprite, and the dashboard's no-polling / no-HTML-injection rules.
"""
from pathlib import Path

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


JS_DIR = Path(__file__).resolve().parents[2] / 'src' / 'admin' / 'static' / 'js'


def _js_lines():
    for path in sorted(JS_DIR.glob('*.js')):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            yield path.name, number, line


@pytest.mark.integration
class TestDashboardScripts:
    def test_dashboard_js_never_polls(self):
        intervals = [(f, n, line) for f, n, line in _js_lines() if 'setInterval(' in line]
        assert len(intervals) == 1, intervals
        assert 'updateRelativeTimes' in intervals[0][2]
        for f, n, line in _js_lines():
            if 'setTimeout(' in line:
                # Only one-shot UI timers: hiding a toast, or ending the "Refreshing…" state.
                assert 'hideToast' in line or 'setBusy(false)' in line, f'{f}:{n}: {line.strip()}'
                for loader in ('loadAll', 'loadMore', 'fetch', 'getReminders', 'getBotStatus'):
                    assert loader not in line, f'{f}:{n}: a timer must never load data: {line.strip()}'
            assert 'location.reload' not in line, f'{f}:{n}'

    def test_js_never_injects_html(self):
        for f, n, line in _js_lines():
            for bad in ('innerHTML', 'outerHTML', 'insertAdjacentHTML'):
                assert bad not in line, f'{f}:{n}: {line.strip()}'

    @pytest.mark.parametrize('name', ['dashboard.js', 'format.js', 'api.js'])
    def test_js_served_as_javascript(self, client, name):
        response = client.get(f'/static/js/{name}')
        assert response.status_code == 200
        assert 'javascript' in response.mimetype


def _function_body(source, name):
    start = source.index(f'function {name}(')
    end = source.find('\nasync function ', start + 1)
    end2 = source.find('\nfunction ', start + 1)
    ends = [e for e in (end, end2) if e != -1]
    return source[start:min(ends) if ends else len(source)]


@pytest.mark.integration
def test_every_action_runs_through_the_one_at_a_time_gate():
    source = (JS_DIR / 'dashboard.js').read_text()
    for handler in ('handleCancel', 'handleBotToggle', 'handleEod'):
        assert 'actionGate.run(' in _function_body(source, handler), handler
