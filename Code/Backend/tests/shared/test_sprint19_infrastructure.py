"""Additive feature migration, safe rollback, and native overlap enforcement."""
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import ROOT
from app.db.models import now, uid
from app.db.session import engine


def test_feature_migration_round_trip_preserves_existing_rows(db, make_event):
    event = make_event()
    event_id, title = event.id, event.title
    db.rollback()
    config = Config(str(ROOT / 'alembic.ini'))
    try:
        command.downgrade(config, 'mvp_0012')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT title FROM events WHERE id=:id'), {'id': event_id}) == title
            assert connection.scalar(text("SELECT to_regclass('featured_requests')")) is None
        command.upgrade(config, 'head')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM featured_requests')) == 0
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini'))).get_current_head()
    finally:
        command.upgrade(config, 'head')


def test_feature_history_downgrade_refuses_data_loss(db, make_event):
    event = make_event()
    db.execute(text('''INSERT INTO featured_requests
        (id,event_id,requested_by,requested_at,status,version,snapshot_hash)
        VALUES (:id,:event,:user,:at,'pending',1,:hash)'''),
        {'id': uid(), 'event': event.id, 'user': event.created_by, 'at': now(), 'hash': 'a' * 64})
    db.commit()
    with pytest.raises(RuntimeError, match='feature history exists'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0012')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM featured_requests')) == 1
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini'))).get_current_head()


def test_native_feature_exclusion_and_adjacent_windows(db, make_event):
    events = [make_event() for _ in range(3)]
    boundary = now() + timedelta(minutes=5)
    statement = text('''INSERT INTO featured_requests
        (id,event_id,requested_by,requested_at,status,version,snapshot_hash,starts_at,ends_at)
        VALUES (:id,:event,:user,:at,'approved',1,:hash,:start,:end)''')

    def params(event, start, end):
        return {'id': uid(), 'event': event.id, 'user': event.created_by, 'at': now(),
                'hash': 'a' * 64, 'start': start, 'end': end}

    db.execute(statement, params(events[0], boundary, boundary + timedelta(hours=1)))
    db.commit()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(statement, params(events[1], boundary, boundary + timedelta(minutes=30)))
    db.execute(statement, params(events[2], boundary + timedelta(hours=1), boundary + timedelta(hours=2)))
    db.commit()
    assert db.scalar(text('SELECT count(*) FROM featured_requests')) == 2
