"""Explicit saved-event migration preserves existing rows and refuses data loss."""
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.config import ROOT
from app.db.session import engine


def test_empty_saved_events_migration_round_trip_preserves_event(db, make_event):
    event = make_event()
    event_id, title = event.id, event.title
    db.rollback()
    config = Config(str(ROOT / 'alembic.ini'))
    try:
        command.downgrade(config, 'mvp_0011')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT title FROM events WHERE id=:id'), {'id': event_id}) == title
        command.upgrade(config, 'head')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM saved_events')) == 0
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0017'
    finally:
        db.rollback()
        command.upgrade(config, 'head')


def test_populated_saved_events_downgrade_refuses_loss(db, make_event, make_user):
    from app.db.models import now
    from app.domains.planning.models import SavedEvent
    event, user = make_event(), make_user()
    db.add(SavedEvent(user_id=user.id, event_id=event.id, saved_at=now()))
    db.commit()
    with pytest.raises(RuntimeError, match='Sprint 17 saved events exist'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0011')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM saved_events')) == 1
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0017'
