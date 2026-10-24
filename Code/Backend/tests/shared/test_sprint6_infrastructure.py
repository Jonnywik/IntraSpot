"""Coordinator-owned migration preservation and explicit restart catch-up proof."""
import os
import subprocess
import sys
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text

from app.core.config import ROOT, get_settings
from app.db.models import now
from app.db.session import engine
from app.domains.events.models import Event
from app.domains.registrations.models import Registration, RegistrationReceipt
from app.domains.registrations.service import submit_registration
from app.notifications import Notification


def test_sprint6_migration_preserves_instant_events_and_stored_retries(db, make_event, make_user):
    event, user = make_event(), make_user()
    outcome = submit_registration(user.id, event.id, 'migration-preserve-1')
    event_id, event_title, user_id = event.id, event.title, user.id
    before = db.scalar(select(RegistrationReceipt.result))
    config = Config(str(ROOT / 'alembic.ini'))
    db.rollback()
    try:
        command.downgrade(config, 'mvp_0002')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT title FROM events WHERE id=:id'), {'id': event_id}) == event_title
            assert connection.scalar(text('SELECT result FROM registration_receipts')) == before
        command.upgrade(config, 'head')
        db.expire_all()
        assert db.get(Event, event_id).registration_mode == 'instant'
        assert db.scalar(select(RegistrationReceipt.result)) == before
        assert submit_registration(user_id, event_id, 'migration-preserve-1') == outcome
    finally:
        db.rollback()
        command.upgrade(config, 'head')


def test_downgrade_refuses_to_discard_approval_data(db, make_event):
    event = make_event(registration_mode='approval', review_window_minutes=15)
    event_id = event.id
    db.rollback()
    with pytest.raises(RuntimeError, match='Sprint 6 data exists'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0002')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0015'
    db.expire_all()
    assert db.get(Event, event_id).registration_mode == 'approval'


def test_deadlines_catch_up_in_independent_process_without_duplicate_notices(db, make_event, make_user):
    event = make_event(registration_mode='approval', review_window_minutes=15)
    attendee = make_user()
    result = submit_registration(attendee.id, event.id, 'deadline-worker-1')
    assert result.result['status'] == 'pending'
    registration = db.get(Registration, result.result['id'])
    registration.review_deadline = now() - timedelta(hours=2)
    db.commit()
    environment = os.environ | {'ENVIRONMENT': 'test', 'FIXTURE_AUTH': 'true',
                                 'DATABASE_URL': get_settings().database_url}
    for attempt in range(2):
        # Cold imports in the synced Windows checkout consumed 24 s before worker startup.
        subprocess.run([sys.executable, '-m', 'app.deadlines', '--once'], cwd=ROOT,
                       env=environment, check=True, capture_output=True, timeout=90)
        db.expire_all()
        assert db.get(Registration, registration.id).status != 'pending'
        notices = db.scalar(select(func.count(Notification.id)))
        if attempt == 0:
            first_notices = notices
        else:
            assert notices == first_notices
    assert db.scalar(select(func.count(Registration.id)).where(Registration.status == 'confirmed')) == 0
