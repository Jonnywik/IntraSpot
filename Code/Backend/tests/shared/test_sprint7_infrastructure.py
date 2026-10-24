"""Coordinator migration preservation and private notification read-state proof."""
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import select, text

from app.core.config import ROOT
from app.db.session import engine
from app.domains.registrations.models import RegistrationReceipt
from app.domains.registrations.service import submit_registration
from app.notifications import Notification


def test_sprint7_expansion_rollback_preserves_prior_data(db, make_event, make_user):
    event, attendee = make_event(), make_user()
    event_id, user_id, title = event.id, attendee.id, event.title
    result = submit_registration(user_id, event_id, 's7-preserved-retry')
    original = db.scalar(select(RegistrationReceipt.result))
    config = Config(str(ROOT / 'alembic.ini'))
    db.rollback()
    try:
        command.downgrade(config, 'mvp_0004')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT title FROM events WHERE id=:id'), {'id': event_id}) == title
            assert connection.scalar(text('SELECT result FROM registration_receipts')) == original
        command.upgrade(config, 'head')
        assert submit_registration(user_id, event_id, 's7-preserved-retry') == result
    finally:
        db.rollback()
        command.upgrade(config, 'head')


def test_sprint7_downgrade_refuses_safety_data(db, make_event, make_user):
    from app.domains.social.models import EventReaction
    event, user = make_event(), make_user()
    db.add(EventReaction(event_id=event.id, user_id=user.id, kind='support'))
    db.commit()
    db.rollback()
    with pytest.raises(RuntimeError, match='Sprint 7 data exists'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0004')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0016'


def test_notification_reads_are_private_idempotent_and_not_guest_writable(client, db, make_event, make_user, token_for):
    event, user, foreign = make_event(), make_user(), make_user()
    notice = Notification(event_id=event.id, user_id=user.id, kind='report_received',
                          message='A safety report was received.', dedupe_key='s7-notification-test')
    db.add(notice); db.commit()
    path = f'/api/v1/me/notifications/{notice.id}/read'
    assert client.post(path).status_code == 401
    assert client.post(path, headers={'Authorization': f'Bearer {token_for(foreign)}'}).status_code == 404
    headers = {'Authorization': f'Bearer {token_for(user)}'}
    first = client.post(path, headers=headers)
    assert first.status_code == 200 and first.json()['read_at'] is not None
    assert client.post(path, headers=headers).json()['read_at'] == first.json()['read_at']
    assert client.get('/api/v1/me/notifications', headers={'Authorization': f'Bearer {token_for(foreign)}'}).json() == []
