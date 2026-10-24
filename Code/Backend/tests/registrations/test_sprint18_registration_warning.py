from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from app.core.errors import DomainError
from app.db.models import now
from app.domains.events.models import Event
from app.domains.memberships.models import EventAccessRevocation
from app.domains.registrations import service
from app.domains.registrations.models import Registration, RegistrationReceipt


def _insert_block(db, blocker_id, target_id):
    db.execute(
        text(
            'INSERT INTO user_blocks (blocker_id, target_id, created_at) '
            'VALUES (:blocker_id, :target_id, :created_at)'
        ),
        {'blocker_id': blocker_id, 'target_id': target_id, 'created_at': now()},
    )
    db.commit()


def _confirmed_registration(event, attendee):
    outcome = service.submit_registration(
        attendee.id,
        event.id,
        f'confirmed-target-{attendee.id[:8]}',
    )
    if event.registration_mode == 'approval':
        assert outcome.result['status'] == 'pending'
        return service.decide_registration(
            event.created_by,
            event.id,
            outcome.result['id'],
            'approve',
        )
    return outcome.result


@pytest.mark.parametrize(
    ('registration_mode', 'expected_status'),
    [('instant', 'confirmed'), ('approval', 'pending')],
)
def test_warning_requires_ack_before_receipt_then_uses_normal_admission(
    db,
    make_event,
    make_user,
    registration_mode,
    expected_status,
):
    event = make_event(
        capacity=3,
        registration_mode=registration_mode,
        review_window_minutes=60 if registration_mode == 'approval' else None,
    )
    blocker = make_user()
    target = make_user(nickname='Private blocked attendee')
    _confirmed_registration(event, target)
    _insert_block(db, blocker.id, target.id)

    assert service.registration_block_warning(blocker.id, event.id) is True
    db.expire_all()
    order_before = db.scalar(select(Event.next_admission).where(Event.id == event.id))
    receipts_before = db.scalar(select(func.count(RegistrationReceipt.id)))

    with pytest.raises(DomainError) as warning:
        service.submit_registration(blocker.id, event.id, 'dismiss-warning-01')

    assert (warning.value.code, warning.value.status) == ('blocked_attendee_warning', 409)
    assert target.id not in warning.value.message
    assert target.nickname not in warning.value.message
    db.expire_all()
    assert db.scalar(select(Event.next_admission).where(Event.id == event.id)) == order_before
    assert db.scalar(select(func.count(RegistrationReceipt.id))) == receipts_before

    outcome = service.submit_registration(
        blocker.id,
        event.id,
        'acknowledged-warning-01',
        blocked_attendee_acknowledged=True,
    )
    assert outcome.http_status == 201
    assert outcome.result['status'] == expected_status
    db.expire_all()
    receipt = db.scalar(
        select(RegistrationReceipt).where(
            RegistrationReceipt.user_id == blocker.id,
            RegistrationReceipt.idempotency_key == 'acknowledged-warning-01',
        )
    )
    assert receipt.blocked_attendee_acknowledged is True
    assert receipt.event_order == order_before + 1


def test_warning_route_returns_only_boolean_without_attendee_identity(
    client,
    db,
    make_event,
    make_user,
    token_for,
):
    event = make_event()
    blocker = make_user()
    target = make_user(nickname='Private blocked attendee')
    _confirmed_registration(event, target)
    _insert_block(db, blocker.id, target.id)

    response = client.get(
        f'/api/v1/events/{event.id}/registration-block-warning',
        headers={'Authorization': f'Bearer {token_for(blocker)}'},
    )

    assert response.status_code == 200
    assert response.json() == {'warning': True}
    assert target.id not in response.text
    assert target.email not in response.text
    assert target.nickname not in response.text


def test_incoming_block_does_not_trigger_warning(db, make_event, make_user):
    event = make_event()
    caller = make_user()
    incoming_blocker = make_user()
    _confirmed_registration(event, incoming_blocker)
    _insert_block(db, incoming_blocker.id, caller.id)

    assert service.registration_block_warning(caller.id, event.id) is False


def test_revoked_confirmed_registration_does_not_trigger_warning(db, make_event, make_user):
    event = make_event()
    caller = make_user()
    target = make_user()
    registration = _confirmed_registration(event, target)
    _insert_block(db, caller.id, target.id)
    db.add(EventAccessRevocation(
        event_id=event.id,
        user_id=target.id,
        cutoff_order=registration['admission_order'],
    ))
    db.commit()

    assert service.registration_block_warning(caller.id, event.id) is False


@pytest.mark.parametrize('context', ['draft', 'unapproved', 'ended'])
def test_warning_is_unavailable_outside_public_approved_future_events(
    db,
    make_event,
    make_org,
    make_user,
    context,
):
    if context == 'draft':
        event = make_event(status='draft')
    elif context == 'unapproved':
        event = make_event(org=make_org(accreditation_status='pending'))
    else:
        at = now()
        event = make_event(
            starts_at=at - timedelta(days=2),
            ends_at=at - timedelta(days=1),
        )
    from app.domains.identity.models import User
    caller = db.get(User, event.created_by) if context == 'draft' else make_user()

    with pytest.raises(DomainError) as unavailable:
        service.registration_block_warning(caller.id, event.id)

    assert (unavailable.value.code, unavailable.value.status) == ('event_not_found', 404)


def test_inactive_caller_cannot_query_warning(db, make_event, make_user):
    event = make_event()
    caller = make_user(active=False)

    with pytest.raises(DomainError) as unavailable:
        service.registration_block_warning(caller.id, event.id)

    assert (unavailable.value.code, unavailable.value.status) == ('registration_ineligible', 403)


def test_same_key_retry_keeps_original_result_after_block_is_added(db, make_event, make_user):
    event = make_event()
    caller = make_user()
    original = service.submit_registration(caller.id, event.id, 'stable-retry-001')
    target = make_user()
    _confirmed_registration(event, target)
    _insert_block(db, caller.id, target.id)
    db.expire_all()
    order_before = db.scalar(select(Event.next_admission).where(Event.id == event.id))
    receipts_before = db.scalar(select(func.count(RegistrationReceipt.id)))

    retry = service.submit_registration(caller.id, event.id, 'stable-retry-001')
    assert retry == original

    with pytest.raises(DomainError) as conflict:
        service.submit_registration(
            caller.id,
            event.id,
            'stable-retry-001',
            blocked_attendee_acknowledged=True,
        )
    assert (conflict.value.code, conflict.value.status) == ('idempotency_key_reused', 409)
    db.expire_all()
    assert db.scalar(select(Event.next_admission).where(Event.id == event.id)) == order_before
    assert db.scalar(select(func.count(RegistrationReceipt.id))) == receipts_before


def test_registration_acknowledgement_requires_a_json_boolean(
    client,
    make_event,
    make_user,
    token_for,
):
    event = make_event()
    caller = make_user()
    response = client.post(
        f'/api/v1/events/{event.id}/registrations',
        headers={
            'Authorization': f'Bearer {token_for(caller)}',
            'Idempotency-Key': 'strict-ack-0001',
        },
        json={'blocked_attendee_acknowledged': 'true'},
    )

    assert response.status_code == 422
    assert response.json()['error']['code'] == 'validation_error'


def test_acknowledged_concurrent_attempts_never_exceed_capacity(db, make_event, make_user):
    event = make_event(capacity=3)
    blocker = make_user()
    target = make_user()
    _confirmed_registration(event, target)
    callers = [make_user() for _ in range(8)]
    for caller in callers:
        _insert_block(db, caller.id, target.id)

    with ThreadPoolExecutor(max_workers=len(callers)) as pool:
        outcomes = list(pool.map(
            lambda item: service.submit_registration(
                item.id,
                event.id,
                f'capacity-ack-{item.id[:12]}',
                blocked_attendee_acknowledged=True,
            ),
            callers,
        ))

    assert all(outcome.http_status == 201 for outcome in outcomes)
    assert sum(outcome.result['status'] == 'confirmed' for outcome in outcomes) == 2
    assert sum(outcome.result['status'] == 'waitlisted' for outcome in outcomes) == 6
    db.expire_all()
    confirmed = db.scalar(
        select(func.count(Registration.id)).where(
            Registration.event_id == event.id,
            Registration.status == 'confirmed',
        )
    )
    assert confirmed == event.capacity
    assert confirmed <= event.capacity


def test_registration_review_masks_personas_for_blocks_in_either_direction(
    db,
    make_event,
    make_user,
):
    event = make_event(
        capacity=5,
        registration_mode='approval',
        review_window_minutes=60,
    )
    from app.domains.identity.models import User
    reviewer = db.get(User, event.created_by)
    blocked_by_reviewer = make_user(nickname='Blocked by reviewer')
    reviewer_blocked_by_applicant = make_user(nickname='Reviewer blocked by applicant')
    visible_with_review_consent = make_user(
        nickname='Review consent only',
        persona_visible=False,
    )
    attendee_opt_in_only = make_user(
        nickname='Event opt-in only',
        persona_visible=True,
    )
    attendees = [
        blocked_by_reviewer,
        reviewer_blocked_by_applicant,
        visible_with_review_consent,
        attendee_opt_in_only,
    ]
    for index, attendee in enumerate(attendees):
        service.submit_registration(
            attendee.id,
            event.id,
            f'review-consent-{index:02d}',
            persona_shared=index != 3,
        )
    _insert_block(db, reviewer.id, blocked_by_reviewer.id)
    _insert_block(db, reviewer_blocked_by_applicant.id, reviewer.id)

    reviews = service.list_registration_reviews(reviewer.id, event.id)
    by_user = {review['user_id']: review for review in reviews}

    assert by_user[blocked_by_reviewer.id]['persona'] is None
    assert by_user[reviewer_blocked_by_applicant.id]['persona'] is None
    assert by_user[visible_with_review_consent.id]['persona']['nickname'] == 'Review consent only'
    assert by_user[attendee_opt_in_only.id]['persona'] is None
    assert set(by_user) == {attendee.id for attendee in attendees}
