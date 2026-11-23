"""EOD follow-up selection (ReminderRepository.get_pending_followups).

Runs on SQLite always. Also runs on PostgreSQL when a throwaway local server is
provided through ETC_TEST_PG_HOST / ETC_TEST_PG_PORT / ETC_TEST_PG_DB / ETC_TEST_PG_USER
(production uses PostgreSQL, where the old SQLite-only query failed).
"""
import os
from datetime import datetime, timedelta

import pytest

from src.core.models import Reminder, ReminderStatus
from src.database.db_manager import DBManager
from src.database.migrations.migration_manager import MigrationManager
from src.database.repositories.reminder_repository import ReminderRepository

_counter = [0]


def _make_reminder(status=ReminderStatus.PENDING) -> Reminder:
    _counter[0] += 1
    when = datetime.now() - timedelta(hours=1)
    return Reminder(
        channel_id='C_TEST', thread_ts=f'1763600000.{_counter[0]:06d}', user_id=f'U{_counter[0]}',
        message_ts=f'1763600001.{_counter[0]:06d}', deadline_text='by 5pm',
        deadline_datetime=when, reminder_datetime=when, status=status,
    )


def _sent(repo, hours_ago, **extra) -> int:
    rid = repo.create(_make_reminder())
    sent_at = datetime.now() - timedelta(hours=hours_ago)
    repo.update(rid, {'status': ReminderStatus.SENT, 'sent_at': sent_at, 'reminder_sent_at': sent_at, **extra})
    return rid


def _sqlite_repo(settings, tmp_path):
    settings.database_type = 'sqlite'
    settings.database_path = str(tmp_path / 'eod.db')
    return DBManager(settings)


def _postgres_repo(settings, tmp_path):
    env = {k: os.environ.get(f'ETC_TEST_PG_{k}') for k in ('HOST', 'PORT', 'DB', 'USER')}
    if not all(env.values()):
        pytest.skip('set ETC_TEST_PG_HOST/PORT/DB/USER to run against a throwaway PostgreSQL')
    settings.database_type = 'postgresql'
    settings.database_host = env['HOST']
    settings.database_port = int(env['PORT'])
    settings.database_name = env['DB']
    settings.database_user = env['USER']
    settings.database_password = 'unused-trust-auth'
    db = DBManager(settings)
    db.execute('DROP TABLE IF EXISTS audit_logs, reminders, schema_migrations, schema_version CASCADE')
    return db


@pytest.fixture(params=['sqlite', 'postgresql'])
def repo(request, mock_settings, tmp_path):
    make = _sqlite_repo if request.param == 'sqlite' else _postgres_repo
    db = make(mock_settings, tmp_path)
    MigrationManager(db).run_pending()
    yield ReminderRepository(db)
    db.close_all()


def test_includes_reminder_sent_recently_without_reply(repo):
    rid = _sent(repo, 1)
    assert [r.id for r in repo.get_pending_followups()] == [rid]


def test_excludes_reminder_sent_more_than_24h_ago(repo):
    _sent(repo, 30)
    assert repo.get_pending_followups() == []


def test_excludes_when_followup_already_sent(repo):
    _sent(repo, 1, followup_sent_at=datetime.now())
    assert repo.get_pending_followups() == []


def test_excludes_when_user_replied_after_reminder(repo):
    _sent(repo, 2, last_user_update_at=datetime.now() - timedelta(hours=1))
    assert repo.get_pending_followups() == []


def test_excludes_pending_reminders(repo):
    repo.create(_make_reminder(status=ReminderStatus.PENDING))
    assert repo.get_pending_followups() == []
