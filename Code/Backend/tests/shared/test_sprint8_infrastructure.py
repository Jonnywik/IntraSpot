"""Coordinator-owned migration preservation, identity gating and notification context."""
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import select, text

from app.core.config import ROOT
from app.db.session import engine
from app.domains.organizations.models import OrgMembership
from app.domains.registrations.models import RegistrationReceipt
from app.domains.registrations.service import submit_registration
from app.notifications import Notification, notify_in_app


def test_sprint8_migration_preserves_existing_outcomes(db, make_event, make_user):
    event, attendee = make_event(), make_user()
    event_id, title, user_id = event.id, event.title, attendee.id
    outcome = submit_registration(user_id, event_id, 's8-preserved-original')
    original = db.scalar(select(RegistrationReceipt.result))
    config = Config(str(ROOT / 'alembic.ini'))
    db.rollback()
    try:
        command.downgrade(config, 'mvp_0005')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT title FROM events WHERE id=:id'), {'id': event_id}) == title
            assert connection.scalar(text('SELECT result FROM registration_receipts')) == original
            assert connection.scalar(text('SELECT COUNT(*) FROM org_memberships')) == 1
        command.upgrade(config, 'head')
        assert submit_registration(user_id, event_id, 's8-preserved-original') == outcome
    finally:
        db.rollback()
        command.upgrade(config, 'head')


def test_sprint8_downgrade_refuses_membership_history(db, make_org):
    from app.domains.memberships.models import MembershipAudit
    org = make_org()
    db.add(MembershipAudit(org_id=org.id, actor_id=org.created_by, user_id=org.created_by,
                           action='role_changed', old_role='member', new_role='moderator'))
    db.commit()
    with pytest.raises(RuntimeError, match='Sprint 8 data exists'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0005')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini'))).get_current_head()
        assert connection.scalar(text('SELECT COUNT(*) FROM membership_audits')) == 1


def test_org_notifications_have_private_real_context(client, db, make_org, make_user, token_for):
    org, recipient, foreign = make_org(), make_user(), make_user()
    notify_in_app(db, user_id=recipient.id, org_id=org.id, kind='membership_approved',
                  message='Your club membership status changed.', dedupe_key='s8-org-context')
    db.commit()
    own = client.get('/api/v1/me/notifications', headers={'Authorization': f'Bearer {token_for(recipient)}'})
    assert own.status_code == 200
    row = own.json()[0]
    assert row['event_id'] is None and row['org_id'] == org.id
    assert 'email' not in row and 'registration_id' not in row
    assert client.get('/api/v1/me/notifications', headers={'Authorization': f'Bearer {token_for(foreign)}'}).json() == []
    assert client.get('/api/v1/me/notifications').status_code == 401
    db.rollback()
    with pytest.raises(RuntimeError, match='Sprint 8 data exists'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0005')


def test_approved_grant_does_not_bypass_trusted_eligibility(client, db, make_org, make_event, make_user, token_for):
    org = make_org()
    user = make_user(email='fictional-pre-eligibility@example.test', email_verified=True)
    db.add(OrgMembership(org_id=org.id, user_id=user.id, role='member', active=True))
    db.commit()
    headers = {'Authorization': f'Bearer {token_for(user, eligible=True, platform_admin=True)}'}
    actor = client.get('/api/v1/me', headers=headers).json()
    assert actor['eligible'] is False and actor['grants'] == [] and actor['platform_admin'] is False
    assert client.get('/api/v1/me/organizations', headers=headers).json()['grants'] == []
    assert client.get(f'/api/v1/organizations/{org.id}/workspace', headers=headers).status_code == 403
    assert client.get(f'/api/v1/organizations/{org.id}/members', headers=headers).status_code == 403
    status = client.get('/api/v1/me/memberships', headers=headers)
    assert status.status_code == 200 and status.json()[0]['access_ready'] is False
    assert client.patch('/api/v1/me/profile', headers=headers, json={'email_verified': True}).status_code == 422
    from app.domains.registrations.models import Registration
    event = make_event(org=org, next_admission=1)
    db.add(Registration(user_id=user.id, event_id=event.id, admission_order=1, status='confirmed'))
    db.commit()
    assert client.get('/api/v1/me/chats', headers=headers).status_code == 403
    assert client.get(f'/api/v1/events/{event.id}/chat', headers=headers).status_code == 403


def test_public_club_listing_never_contains_private_applications(client, make_org):
    approved = make_org(name='Approved public fictional club')
    make_org(name='Pending private fictional club', accreditation_status='pending')
    make_org(name='Rejected private fictional club', accreditation_status='rejected')
    response = client.get('/api/v1/organizations')
    assert response.status_code == 200
    assert [row['id'] for row in response.json()] == [approved.id]
    assert all('created_by' not in row and 'members' not in row and 'decisions' not in row for row in response.json())


def test_departure_preserves_legacy_orders_without_receipts(db, make_org, make_event, make_user):
    from app.domains.registrations.models import Registration
    from app.domains.registrations.service import end_membership_attendance
    from app.domains.memberships.models import EventAccessRevocation
    org, user = make_org(), make_user()
    event = make_event(org=org, capacity=1, next_admission=0)
    legacy = Registration(user_id=user.id, event_id=event.id, status='confirmed', admission_order=9)
    db.add(legacy); db.commit()
    db.scalar(select(type(org)).where(type(org).id == org.id).with_for_update())
    cancelled, revoked = end_membership_attendance(db, org.id, user.id)
    db.commit()
    assert cancelled == revoked == 1
    assert db.get(Registration, legacy.id).status == 'cancelled'
    assert db.scalar(select(EventAccessRevocation.cutoff_order)) == 9
    db.rollback()
    result = submit_registration(user.id, event.id, 's8-after-legacy-departure')
    assert result.result['status'] == 'confirmed' and result.result['admission_order'] > 9


def test_ineligible_accounts_do_not_receive_or_read_chat_activity(client, db, make_event, make_user, token_for):
    from uuid import uuid4
    event, author, recipient = make_event(), make_user(), make_user()
    for user in (author, recipient):
        assert submit_registration(user.id, event.id, f's8-chat-fixture-{user.id}').http_status < 300
    path = f'/api/v1/events/{event.id}/chat/messages'
    author_headers = {'Authorization': f'Bearer {token_for(author)}'}
    recipient_headers = {'Authorization': f'Bearer {token_for(recipient)}'}
    assert client.post(path, headers=author_headers,
                       json={'client_key': str(uuid4()), 'body': 'First fictional chat message.'}).status_code == 200
    notices = list(db.scalars(select(Notification).where(Notification.user_id == recipient.id)))
    assert len(notices) == 1 and notices[0].kind == 'chat_message'
    notice_id = notices[0].id
    recipient.email_verified = False; db.commit()
    assert client.get('/api/v1/me/notifications', headers=recipient_headers).json() == []
    assert client.post(f'/api/v1/me/notifications/{notice_id}/read', headers=recipient_headers).status_code == 404
    assert client.post(path, headers=author_headers,
                       json={'client_key': str(uuid4()), 'body': 'Second fictional chat message.'}).status_code == 200
    db.expire_all()
    assert len(list(db.scalars(select(Notification).where(Notification.user_id == recipient.id)))) == 1
    db.get(type(recipient), recipient.id).email_verified = True; db.commit()
    restored = client.get('/api/v1/me/notifications', headers=recipient_headers)
    assert restored.status_code == 200 and restored.json()[0]['id'] == notice_id


def test_unavailable_invitee_is_not_a_sender_auth_failure_and_preserves_retries(client, db, make_org, make_user, token_for):
    from uuid import uuid4
    org, recipient = make_org(), make_user()
    headers = {'Authorization': f'Bearer {token_for(org.created_by)}'}
    path = f'/api/v1/organizations/{org.id}/membership-invitations'
    body = {'recipient_id': recipient.id, 'client_key': str(uuid4())}
    initial = client.post(path, headers=headers, json=body)
    assert initial.status_code == 200
    recipient.active = False; db.commit()
    retry = client.post(path, headers=headers, json=body)
    assert retry.status_code == 200 and retry.json()['id'] == initial.json()['id']
    for target_id in (recipient.id, str(uuid4())):
        unavailable = client.post(path, headers=headers, json={'recipient_id': target_id, 'client_key': str(uuid4())})
        assert unavailable.status_code == 404 and unavailable.json()['error']['code'] == 'membership_invitee_unavailable'
    conflict = client.post(path, headers=headers, json=body | {'recipient_id': str(uuid4())})
    assert conflict.status_code == 409
    assert client.get('/api/v1/me', headers=headers).status_code == 200
