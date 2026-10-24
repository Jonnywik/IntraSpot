"""Focused regressions for the independent review's trust and retry boundaries."""
from datetime import timedelta
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.moderation.models import ContentReport
from app.domains.social import service
from app.domains.social.models import EventComment, EventReaction


@pytest.mark.parametrize('action', ['comment', 'reaction'])
def test_social_clock_is_sampled_after_event_lock(client, db, make_event, make_user, token_for, monkeypatch, action):
    event, user = make_event(), make_user()
    boundary = event.starts_at
    monkeypatch.setattr(service, 'now', lambda: boundary - timedelta(seconds=1))
    original = service._published_event
    def advance_clock_after_lock(session, event_id, *, lock=False, **visibility):
        result = original(session, event_id, lock=lock, **visibility)
        if lock:
            monkeypatch.setattr(service, 'now', lambda: boundary)
        return result
    monkeypatch.setattr(service, '_published_event', advance_clock_after_lock)
    payload = {'body': 'crossed start boundary', 'client_key': str(uuid4())} if action == 'comment' else {'reaction': 'support'}
    endpoint = 'comments' if action == 'comment' else 'reactions'
    response = client.post(f'/api/v1/events/{event.id}/{endpoint}',
                           headers={'Authorization': f'Bearer {token_for(user)}'}, json=payload)
    assert response.status_code == 409
    assert db.scalar(select(func.count()).select_from(EventComment)) == 0
    assert db.scalar(select(func.count()).select_from(EventReaction)) == 0


def test_report_retry_recovers_receipt_after_personal_hide(client, db, make_event, make_user, token_for):
    event, author, reporter = make_event(), make_user(), make_user()
    headers = {'Authorization': f'Bearer {token_for(reporter)}'}
    created = client.post(f'/api/v1/events/{event.id}/comments',
                         headers={'Authorization': f'Bearer {token_for(author)}'},
                         json={'body': 'reportable text', 'client_key': str(uuid4())}).json()
    payload = {'kind': 'comment', 'target_id': created['id'], 'reason': 'spam'}
    first = client.post(f'/api/v1/events/{event.id}/reports', headers=headers, json=payload)
    assert first.status_code == 201
    assert client.post('/api/v1/me/content-hides', headers=headers,
                       json={'event_id': event.id, 'kind': 'comment', 'target_id': created['id'], 'hidden': True}).status_code == 200
    retry = client.post(f'/api/v1/events/{event.id}/reports', headers=headers, json=payload)
    assert retry.status_code == 201 and retry.json() == first.json()
    assert db.scalar(select(func.count()).select_from(ContentReport)) == 1


def test_chat_route_ids_are_validated_before_domain_lookup(client, make_user, token_for):
    headers = {'Authorization': f'Bearer {token_for(make_user())}'}
    assert client.get('/api/v1/events/not-a-uuid/chat', headers=headers).status_code == 422
    assert client.post('/api/v1/events/not-a-uuid/chat/messages', headers=headers,
                       json={'body': 'invalid path', 'client_key': str(uuid4())}).status_code == 422


def test_personal_review_flag_cannot_be_changed_by_profile_or_token_claims(client, make_event, make_user, token_for):
    event, subject, reporter = make_event(), make_user(), make_user()
    subject_headers = {'Authorization': f'Bearer {token_for(subject)}'}
    created = client.post(f'/api/v1/events/{event.id}/comments', headers=subject_headers,
                         json={'body': 'visible report context', 'client_key': str(uuid4())})
    assert created.status_code == 200
    report = client.post(f'/api/v1/events/{event.id}/reports',
                         headers={'Authorization': f'Bearer {token_for(reporter)}'},
                         json={'kind': 'person', 'target_id': subject.id, 'reason': 'impersonation'})
    assert report.status_code == 201
    forged_metadata = {'Authorization': f'Bearer {token_for(subject, communication_restricted=False, platform_admin=True)}'}
    actor = client.get('/api/v1/me', headers=forged_metadata).json()
    assert actor['communication_restricted'] is True and actor['platform_admin'] is False
    assert client.patch('/api/v1/me/profile', headers=subject_headers,
                        json={'communication_restricted': False}).status_code == 422
    assert client.get('/api/v1/me', headers=subject_headers).json()['communication_restricted'] is True


def test_non_key_user_locks_allow_peer_notification_foreign_keys(db, make_event, make_user):
    from app.db.session import engine
    from app.core.communication_schemas import ContentCreate
    from app.domains.identity.models import User
    from app.domains.chat.service import send_chat_message
    from app.domains.registrations.service import submit_registration
    event, sender, peer = make_event(), make_user(), make_user()
    submit_registration(sender.id, event.id, 's7-lock-sender')
    submit_registration(peer.id, event.id, 's7-lock-peer')
    event_id, sender_id, peer_id = event.id, sender.id, peer.id
    db.rollback()
    def send():
        with Session(engine()) as session, session.begin():
            return send_chat_message(session, event_id, sender_id,
                                     ContentCreate(body='safe generic notice', client_key=uuid4())).id
    with Session(engine()) as held, ThreadPoolExecutor(max_workers=1) as pool:
        # Authorization/profile locks serialize metadata writes, not user-key
        # changes; notification FK reads must remain compatible across events.
        held.scalar(select(User).where(User.id == peer_id).with_for_update(key_share=True))
        future = pool.submit(send)
        try:
            assert future.result(timeout=5)
        finally:
            held.rollback()
