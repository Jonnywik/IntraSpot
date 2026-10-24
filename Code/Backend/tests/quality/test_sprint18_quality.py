"""Independent Sprint 18 cross-boundary regression checks.

These cases target API/service seams not exercised by the focused persona and
registration-warning suites. The DB-backed tests are coordinator-run only.
"""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.communication_schemas import ContentCreate
from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.chat import service as chat_service
from app.domains.chat.models import ChatMessage
from app.domains.moderation.models import ContentReport
from app.domains.organizations.models import OrgMembership
from app.domains.personas import service as persona_service
from app.domains.personas.models import UserBlock
from app.domains.registrations.models import Registration
from app.domains.social import service as social_service
from app.domains.social.models import EventComment
from app.notifications import Notification


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _register(db, event, user, *, status='confirmed'):
    order = db.scalar(select(func.count(Registration.id)).where(
        Registration.event_id == event.id,
    )) or 0
    registration = Registration(
        id=uid(),
        user_id=user.id,
        event_id=event.id,
        status=status,
        admission_order=order + 1,
        persona_shared=False,
    )
    db.add(registration)
    db.commit()
    return registration


def _comment(db, event, author, body):
    return social_service.create_comment(
        db,
        event.id,
        author.id,
        ContentCreate(body=body, client_key=uuid4()),
        at=now(),
    )


def _message(db, event, author, body):
    return chat_service.send_chat_message(
        db,
        event.id,
        author.id,
        ContentCreate(body=body, client_key=uuid4()),
        at=now(),
    )


def test_persona_api_hides_pending_approval_applicant_and_keeps_unavailable_shape_private(
    client, db, make_event, make_user, token_for,
):
    viewer = make_user()
    applicant = make_user(
        email='fictional-pending-persona@students.plm.edu.ph',
        nickname='PENDING PRIVATE NICKNAME',
        age_bracket='18-24',
        tags=['private-tag'],
        pronouns='they/them',
        icebreaker='PRIVATE ICEBREAKER',
        persona_visible=True,
    )
    hidden = make_user(nickname='HIDDEN PRIVATE NICKNAME', persona_visible=False)
    event = make_event(registration_mode='approval', review_window_minutes=60)
    _register(db, event, viewer)
    applicant_registration = _register(db, event, applicant, status='pending')
    _register(db, event, hidden)
    _comment(db, event, applicant, 'Visible pending-applicant comment')
    _comment(db, event, hidden, 'Visible hidden-persona comment')
    headers = _auth(token_for(viewer))
    base = f'/api/v1/events/{event.id}/personas'

    pending = client.get(f'{base}/{applicant.id}', headers=headers)
    hidden_response = client.get(f'{base}/{hidden.id}', headers=headers)
    unknown = client.get(f'{base}/{uuid4()}', headers=headers)
    assert pending.status_code == hidden_response.status_code == unknown.status_code == 404
    assert pending.json()['error'] == hidden_response.json()['error'] == unknown.json()['error']
    assert applicant.nickname not in pending.text
    assert applicant.email not in pending.text

    # Once approved/confirmed, the HTTP response itself must remain the exact
    # public text allowlist, regardless of the richer User record.
    applicant_registration.status = 'confirmed'
    db.commit()
    visible = client.get(f'{base}/{applicant.id}', headers=headers)
    assert visible.status_code == 200
    assert set(visible.json()) == {'nickname', 'age_bracket', 'tags', 'pronouns', 'icebreaker'}
    assert visible.json() == {
        'nickname': applicant.nickname,
        'age_bracket': applicant.age_bracket,
        'tags': ['private-tag'],
        'pronouns': 'they/them',
        'icebreaker': 'PRIVATE ICEBREAKER',
    }
    assert applicant.email not in visible.text

    db.add(UserBlock(blocker_id=viewer.id, target_id=applicant.id))
    db.commit()
    blocked = client.get(f'{base}/{applicant.id}', headers=headers)
    assert blocked.status_code == 404
    assert blocked.json()['error'] == unknown.json()['error']
    assert applicant.nickname not in blocked.text


@pytest.mark.parametrize('block_direction', ['reviewer_blocks_applicant', 'applicant_blocks_reviewer'])
def test_membership_review_route_masks_consented_persona_for_either_block_direction(
    client, db, make_user, make_org, token_for, block_direction,
):
    reviewer = make_user()
    applicant = make_user(
        email='fictional-membership-persona@example.test',
        nickname='CONSENTED PRIVATE LABEL',
        tags=['private-review-tag'],
    )
    organization = make_org(owner=reviewer)
    submitted = client.post(
        f'/api/v1/organizations/{organization.id}/membership-applications',
        headers=_auth(token_for(applicant)),
        json={'client_key': str(uuid4()), 'persona_shared': True},
    )
    assert submitted.status_code == 200
    assert submitted.json()['status'] == 'pending'

    if block_direction == 'reviewer_blocks_applicant':
        block = UserBlock(blocker_id=reviewer.id, target_id=applicant.id)
    else:
        block = UserBlock(blocker_id=applicant.id, target_id=reviewer.id)
    db.add(block)
    db.commit()

    review = client.get(
        f'/api/v1/organizations/{organization.id}/membership-applications',
        headers=_auth(token_for(reviewer)),
    )
    assert review.status_code == 200
    row = next(item for item in review.json() if item['id'] == submitted.json()['id'])
    assert row['user_id'] == applicant.id
    assert row['applicant_label'] == 'Applicant'
    assert row['persona'] is None
    assert applicant.nickname not in review.text
    assert applicant.email not in review.text
    assert 'private-review-tag' not in review.text


def test_chat_context_and_persona_access_expire_at_the_same_retention_cutoff(
    db, make_event, make_user,
):
    viewer = make_user()
    author = make_user(nickname='Retained chat persona', persona_visible=True)
    event = make_event()
    _register(db, event, viewer)
    _register(db, event, author)
    _message(db, event, author, 'Retained fictional message')
    cutoff = event.ends_at + chat_service.CHAT_RETENTION
    immediately_before = cutoff - timedelta(microseconds=1)

    persona = persona_service.get_event_persona(
        db, event.id, author.id, viewer.id, at=immediately_before,
    )
    thread = chat_service.get_chat_thread(
        db, event.id, viewer.id, at=immediately_before,
    )
    assert persona.nickname == 'Retained chat persona'
    assert [item.body for item in thread.items] == ['Retained fictional message']

    with pytest.raises(DomainError) as persona_expired:
        persona_service.get_event_persona(db, event.id, author.id, viewer.id, at=cutoff)
    assert (persona_expired.value.code, persona_expired.value.status) == ('persona_unavailable', 404)
    with pytest.raises(DomainError) as chat_expired:
        chat_service.get_chat_thread(db, event.id, viewer.id, at=cutoff)
    assert (chat_expired.value.code, chat_expired.value.status) == ('chat_expired', 404)


def test_block_hides_identity_without_deleting_registration_membership_evidence_or_notice(
    client, db, make_event, make_user, token_for,
):
    viewer = make_user()
    target = make_user(nickname='Blocked but retained')
    event = make_event()
    viewer_registration = _register(db, event, viewer)
    target_registration = _register(db, event, target)
    comment = _comment(db, event, target, 'A fictional comment enabling a block.')
    message = _message(db, event, target, 'A fictional retained group-chat message.')
    membership = OrgMembership(
        id=uid(), org_id=event.org_id, user_id=target.id, role='member', active=True,
    )
    report = ContentReport(
        id=uid(), event_id=event.id, org_id=event.org_id,
        reporter_id=viewer.id, subject_user_id=target.id, kind='message',
        target_id=message.id, reason='harassment', status='open', stage='organization',
        evidence='Bounded fictional moderation evidence.', deadline=event.ends_at + timedelta(days=7),
    )
    notification = Notification(
        id=uid(), user_id=target.id, event_id=event.id, org_id=event.org_id,
        kind='chat_message', message='New message in an event chat.',
        dedupe_key=f'sprint18-quality:{uid()}',
    )
    db.add_all([membership, report, notification])
    db.commit()

    blocked = client.put(
        f'/api/v1/events/{event.id}/blocks/{target.id}',
        headers=_auth(token_for(viewer)),
    )
    assert blocked.status_code == 200
    db.expire_all()

    assert db.get(Registration, viewer_registration.id).status == 'confirmed'
    assert db.get(Registration, target_registration.id).status == 'confirmed'
    assert db.get(OrgMembership, membership.id).active is True
    retained_report = db.get(ContentReport, report.id)
    assert retained_report is not None
    assert retained_report.evidence == 'Bounded fictional moderation evidence.'
    assert db.get(Notification, notification.id).message == 'New message in an event chat.'
    assert db.get(ChatMessage, message.id).body == 'A fictional retained group-chat message.'
    assert db.get(EventComment, comment.id).body == 'A fictional comment enabling a block.'
