"""Attendance migration is additive and never silently erases staff records."""
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import ROOT
from app.db.session import engine


def test_attendance_roundtrip_preserves_existing_events(db, make_event):
    event = make_event()
    event_id, title = event.id, event.title
    db.rollback()
    config = Config(str(ROOT / 'alembic.ini'))
    try:
        command.downgrade(config, 'mvp_0015')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT title FROM events WHERE id=:id'), {'id': event_id}) == title
            assert connection.scalar(text("SELECT to_regclass('attendance_sessions')")) is None
        command.upgrade(config, 'head')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0017'
            assert connection.scalar(text('SELECT count(*) FROM attendance_audits')) == 0
    finally:
        command.upgrade(config, 'head')


def test_new_attendance_session_defaults_closed_and_version_zero(db, make_event):
    event = make_event()
    db.execute(text('INSERT INTO attendance_sessions(event_id) VALUES (:id)'), {'id': event.id})
    assert db.execute(text('SELECT is_open,version FROM attendance_sessions WHERE event_id=:id'), {'id': event.id}).one() == (False, 0)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text('UPDATE attendance_sessions SET version=-1 WHERE event_id=:id'), {'id': event.id})


def test_attendance_downgrade_refuses_to_discard_even_session_data(db, make_event):
    event = make_event()
    db.execute(text('INSERT INTO attendance_sessions(event_id) VALUES (:id)'), {'id': event.id})
    db.commit()
    with pytest.raises(RuntimeError, match='Attendance data exists'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0015')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0017'
        assert connection.scalar(text('SELECT count(*) FROM attendance_sessions')) == 1
