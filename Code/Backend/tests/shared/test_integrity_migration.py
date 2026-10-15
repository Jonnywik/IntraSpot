"""Verify the additive constraint without deleting or rewriting existing rows."""
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import ROOT
from app.db.session import engine
from app.domains.events.models import Event


def test_integrity_migration_is_reversible_and_preserves_events(db, make_event):
    make_event()
    make_event(status='draft', published_at=None, title=None, starts_at=None, ends_at=None)
    before = db.execute(select(Event.__table__).order_by(Event.id)).all()
    db.rollback()
    config = Config(str(ROOT / 'alembic.ini'))
    try:
        command.downgrade(config, 'mvp_0001')
        command.upgrade(config, 'head')
        assert db.execute(select(Event.__table__).order_by(Event.id)).all() == before
    finally:
        db.rollback()
        command.upgrade(config, 'head')


def test_integrity_migration_rejects_invalid_existing_rows_without_rewriting(db, make_event):
    event = make_event()
    event_id, title = event.id, event.title
    config = Config(str(ROOT / 'alembic.ini'))
    db.rollback()
    command.downgrade(config, 'mvp_0001')
    try:
        # The older schema intentionally lacks Sprint 6 columns; use its own shape.
        db.execute(text('UPDATE events SET title=NULL WHERE id=:id'), {'id': event_id})
        db.commit()
        with pytest.raises(IntegrityError):
            command.upgrade(config, 'head')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0001'
        assert db.scalar(text('SELECT title FROM events WHERE id=:id'), {'id': event_id}) is None
    finally:
        db.rollback()
        db.execute(text('UPDATE events SET title=:title WHERE id=:id'), {'title': title, 'id': event_id})
        db.commit()
        command.upgrade(config, 'head')
