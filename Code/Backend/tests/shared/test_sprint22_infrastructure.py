"""Safety migration preserves old data and refuses destructive downgrade."""
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import ROOT
from app.db.session import engine


def test_safety_roundtrip_preserves_existing_event(db, make_event):
    event = make_event()
    event_id, title = event.id, event.title
    db.rollback()
    config = Config(str(ROOT / 'alembic.ini'))
    try:
        command.downgrade(config, 'mvp_0016')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT title FROM events WHERE id=:id'), {'id': event_id}) == title
            assert connection.scalar(text("SELECT to_regclass('event_controls')")) is None
        command.upgrade(config, 'head')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0017'
            assert connection.scalar(text('SELECT count(*) FROM safety_audits')) == 0
    finally:
        command.upgrade(config, 'head')


def test_safety_control_defaults_and_constraint(db, make_event):
    event = make_event()
    db.execute(text('INSERT INTO event_controls(event_id) VALUES (:id)'), {'id': event.id})
    assert db.execute(text('SELECT org_hidden,platform_hidden,removed,cancelled,version FROM event_controls '
                           'WHERE event_id=:id'), {'id': event.id}).one() == (False, False, False, False, 0)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text('UPDATE event_controls SET version=-1 WHERE event_id=:id'), {'id': event.id})


def test_safety_downgrade_refuses_nonempty_control(db, make_event):
    event = make_event()
    db.execute(text('INSERT INTO event_controls(event_id) VALUES (:id)'), {'id': event.id})
    db.commit()
    with pytest.raises(RuntimeError, match='Safety data exists'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0016')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0017'
        assert connection.scalar(text('SELECT count(*) FROM event_controls')) == 1
