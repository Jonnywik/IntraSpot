from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.organizations.models import OrgMembership
from app.domains.registrations import service
from app.domains.registrations.models import Registration, RegistrationReceipt
from app.notifications import Notification


def _approval_event(make_event, **fields):
    return make_event(
        registration_mode='approval',
        review_window_minutes=30,
        **fields,
    )


def _grant_reviewer(db, event, user, role='moderator'):
    db.add(OrgMembership(
        id=uid(),
        org_id=event.org_id,
        user_id=user.id,
        role=role,
        active=True,
    ))
    db.commit()


def _force_review_deadline(db, registration_id, *, stage=0, ago=timedelta(hours=2)):
    registration = db.get(Registration, registration_id)
    registration.review_stage = stage
    registration.review_deadline = now() - ago
    db.commit()
    db.expire_all()


def _apply_material_change(db, event_id, fields, deadline, mode, selected, *, call_twice=False):
    db.rollback()
    with db.begin():
        event = db.scalar(select(Event).where(Event.id == event_id).with_for_update())
        revision = service.reconcile_material_change(
            db,
            event,
            fields,
            deadline,
            mode,
            selected,
        )
        if call_twice:
            repeated_revision = service.reconcile_material_change(
                db,
                event,
                fields,
                deadline,
                mode,
                [],
            )
            assert repeated_revision == revision
        for name, value in fields.items():
            setattr(event, name, value)
        event.material_revision = revision
    return revision


def test_approval_reserves_capacity_and_receipt_is_immutable_on_decision(db, make_user, make_event):
    event = _approval_event(make_event, capacity=1)
    attendee, queued = make_user(), make_user()

    first = service.submit_registration(
        attendee.id,
        event.id,
        'approval-key-0001',
        persona_shared=True,
    )
    second = service.submit_registration(queued.id, event.id, 'approval-key-0002')

    assert first.result['status'] == 'pending'
    assert first.result['review_stage'] == 0
    assert first.result['review_deadline'].endswith('+00:00')
    assert second.result['status'] == 'waitlisted'
    db.expire_all()
    receipt = db.scalar(select(RegistrationReceipt).where(
        RegistrationReceipt.user_id == attendee.id,
        RegistrationReceipt.idempotency_key == 'approval-key-0001',
    ))
    original_result = dict(receipt.result)
    assert receipt.persona_shared is True

    decided = service.decide_registration(
        event.created_by,
        event.id,
        first.result['id'],
        'approve',
    )
    assert decided['status'] == 'confirmed'
    replay = service.submit_registration(
        attendee.id,
        event.id,
        'approval-key-0001',
        persona_shared=True,
    )
    assert replay.result == original_result
    with pytest.raises(DomainError) as mismatch:
        service.submit_registration(
            attendee.id,
            event.id,
            'approval-key-0001',
            persona_shared=False,
        )
    assert (mismatch.value.code, mismatch.value.status) == ('idempotency_key_reused', 409)
    db.expire_all()
    assert db.get(RegistrationReceipt, receipt.id).result == original_result
    assert db.scalar(select(func.count(Registration.id)).where(
        Registration.event_id == event.id,
        Registration.status.in_(('confirmed', 'pending', 'reconfirmation_required')),
    )) == 1


def test_any_active_reviewer_can_decide_until_escalation_excludes_first(db, make_user, make_event):
    event = _approval_event(make_event, capacity=3)
    moderator = make_user()
    _grant_reviewer(db, event, moderator, 'moderator')
    first_attendee, second_attendee = make_user(), make_user()

    first = service.submit_registration(first_attendee.id, event.id, 'any-reviewer-0001')
    approved_by_moderator = service.decide_registration(
        moderator.id,
        event.id,
        first.result['id'],
        'approve',
    )
    assert approved_by_moderator['status'] == 'confirmed'

    second = service.submit_registration(second_attendee.id, event.id, 'escalation-key-01')
    _force_review_deadline(db, second.result['id'], stage=1, ago=timedelta(seconds=1))
    service.catch_up_event(event.id)
    db.expire_all()
    escalated = db.get(Registration, second.result['id'])
    assert escalated.status == 'pending'
    assert escalated.review_stage == 2
    assert escalated.first_reviewer_id == event.created_by
    assert escalated.reviewer_id == moderator.id

    with pytest.raises(DomainError) as excluded:
        service.decide_registration(
            event.created_by,
            event.id,
            second.result['id'],
            'approve',
        )
    assert (excluded.value.code, excluded.value.status) == ('registration_reviewer_unassigned', 403)
    assert service.decide_registration(
        moderator.id,
        event.id,
        second.result['id'],
        'reject',
    )['status'] == 'rejected'


def test_deadline_runner_catches_up_historical_stages_without_approval_or_duplicate_notices(
    db,
    make_user,
    make_event,
):
    event = _approval_event(make_event, capacity=1)
    attendee = make_user()
    pending = service.submit_registration(attendee.id, event.id, 'historic-deadline-01')
    _force_review_deadline(db, pending.result['id'], ago=timedelta(hours=2))

    service.catch_up_event(event.id)
    db.expire_all()
    registration = db.get(Registration, pending.result['id'])
    assert registration.status == 'cancelled'
    assert registration.timeout_count == 1
    assert registration.review_deadline is None
    assert registration.status != 'confirmed'

    first_notice_count = db.scalar(select(func.count(Notification.id)).where(
        Notification.registration_id == registration.id,
    ))
    service.catch_up_event(event.id)
    db.expire_all()
    assert db.get(Registration, registration.id).status == 'cancelled'
    assert db.scalar(select(func.count(Notification.id)).where(
        Notification.registration_id == registration.id,
    )) == first_notice_count
    assert first_notice_count == 6


def test_waitlist_approval_timeout_requeues_once_with_new_order_and_keeps_receipt(
    db,
    make_user,
    make_event,
):
    event = _approval_event(make_event, capacity=1)
    holder, first_waitlisted, second_waitlisted = [make_user() for _ in range(3)]
    holder_outcome = service.submit_registration(holder.id, event.id, 'timeout-holder-01')
    first_outcome = service.submit_registration(first_waitlisted.id, event.id, 'timeout-first-01')
    second_outcome = service.submit_registration(second_waitlisted.id, event.id, 'timeout-second-01')
    assert holder_outcome.result['status'] == 'pending'
    assert first_outcome.result['status'] == second_outcome.result['status'] == 'waitlisted'

    service.decide_registration(event.created_by, event.id, holder_outcome.result['id'], 'reject')
    db.expire_all()
    first_registration = db.get(Registration, first_outcome.result['id'])
    assert first_registration.status == 'pending' and first_registration.from_waitlist
    _force_review_deadline(db, first_registration.id, ago=timedelta(hours=2))
    service.catch_up_event(event.id)
    db.expire_all()

    first_registration = db.get(Registration, first_registration.id)
    second_registration = db.get(Registration, second_outcome.result['id'])
    assert first_registration.status == 'waitlisted'
    assert first_registration.timeout_count == 1
    assert first_registration.admission_order > second_registration.admission_order
    assert second_registration.status == 'pending'
    receipt = db.scalar(select(RegistrationReceipt).where(
        RegistrationReceipt.user_id == first_waitlisted.id,
        RegistrationReceipt.idempotency_key == 'timeout-first-01',
    ))
    original_receipt_result = dict(receipt.result)
    assert original_receipt_result['status'] == 'waitlisted'
    assert original_receipt_result['admission_order'] == first_outcome.result['admission_order']

    service.decide_registration(event.created_by, event.id, second_registration.id, 'reject')
    db.expire_all()
    first_registration = db.get(Registration, first_registration.id)
    assert first_registration.status == 'pending'
    _force_review_deadline(db, first_registration.id, ago=timedelta(hours=2))
    service.catch_up_event(event.id)
    db.expire_all()
    first_registration = db.get(Registration, first_registration.id)
    assert first_registration.status == 'cancelled'
    assert first_registration.timeout_count == 2

    replay = service.submit_registration(first_waitlisted.id, event.id, 'timeout-first-01')
    assert replay.result == original_receipt_result
    notices = list(db.scalars(select(Notification).where(
        Notification.registration_id == first_registration.id,
        Notification.kind == 'registration_waitlist_timeout',
    )))
    assert len(notices) == 2
    assert {notice.dedupe_key.rsplit(':', 1)[-1] for notice in notices} == {'1', '2'}


def test_reviewer_projection_requires_event_consent_and_never_contains_email(
    db,
    make_user,
    make_org,
    make_event,
):
    event = _approval_event(make_event, capacity=3)
    consented = make_user(
        nickname='Fictional opt-in',
        tags=['music', 'design'],
        pronouns='they/them',
        icebreaker='A fictional icebreaker.',
        persona_visible=False,
    )
    not_consented = make_user(
        nickname='Fictional private',
        persona_visible=True,
    )
    service.submit_registration(
        consented.id,
        event.id,
        'review-persona-001',
        persona_shared=True,
    )
    service.submit_registration(
        not_consented.id,
        event.id,
        'review-persona-002',
        persona_shared=False,
    )

    reviews = service.list_registration_reviews(event.created_by, event.id)
    by_user = {review['user_id']: review for review in reviews}
    assert by_user[consented.id]['persona'] == {
        'nickname': 'Fictional opt-in',
        'age_bracket': '18-24',
        'tags': ['music', 'design'],
        'pronouns': 'they/them',
        'icebreaker': 'A fictional icebreaker.',
    }
    assert by_user[not_consented.id]['persona'] is None
    assert all(set(review) == {'registration', 'user_id', 'persona'} for review in reviews)
    assert all('email' not in str(review).lower() for review in reviews)

    outsider = make_user()
    make_org(owner=outsider)
    db.expire_all()
    pending_registration = db.get(
        Registration,
        by_user[consented.id]['registration']['id'],
    )
    pending_registration.review_deadline = now() - timedelta(hours=1)
    db.commit()
    notices_before = db.scalar(select(func.count(Notification.id)))
    with pytest.raises(DomainError) as forbidden:
        service.list_registration_reviews(outsider.id, event.id)
    assert (forbidden.value.code, forbidden.value.status) == ('registration_reviewer_forbidden', 403)
    db.expire_all()
    assert db.get(Registration, pending_registration.id).status == 'pending'
    assert db.scalar(select(func.count(Notification.id))) == notices_before


def test_initial_expiry_notifies_attendee_and_assigned_reviewer_once_per_cycle(
    db,
    make_user,
    make_event,
):
    event = _approval_event(make_event, capacity=1)
    attendee = make_user()
    pending = service.submit_registration(attendee.id, event.id, 'review-warning-0001')
    _force_review_deadline(db, pending.result['id'], ago=timedelta(seconds=1))

    service.catch_up_event(event.id)
    service.catch_up_event(event.id)
    notices = list(db.scalars(select(Notification).where(
        Notification.registration_id == pending.result['id'],
        Notification.kind == 'registration_review_warning',
    )))
    assert len(notices) == 2
    assert {notice.user_id for notice in notices} == {attendee.id, event.created_by}
    assert any('assigned to you' in notice.message for notice in notices)


def test_exact_material_selection_protects_unselected_and_reconfirmation_is_revision_bound(
    db,
    make_user,
    make_event,
):
    event = make_event(capacity=2)
    protected, selected, queued = [make_user() for _ in range(3)]
    protected_outcome = service.submit_registration(protected.id, event.id, 'material-protect-01')
    selected_outcome = service.submit_registration(selected.id, event.id, 'material-select-01')
    queued_outcome = service.submit_registration(queued.id, event.id, 'material-queue-01')
    assert protected_outcome.result['status'] == selected_outcome.result['status'] == 'confirmed'
    assert queued_outcome.result['status'] == 'waitlisted'

    with pytest.raises(DomainError) as insufficient:
        _apply_material_change(
            db,
            event.id,
            {'capacity': 1},
            now() + timedelta(days=1),
            'exact',
            [],
        )
    assert insufficient.value.code == 'event_selection_count_invalid'
    db.rollback()

    with pytest.raises(DomainError) as unnecessary:
        _apply_material_change(
            db,
            event.id,
            {'venue_name': 'No capacity reduction'},
            now() + timedelta(days=1),
            'newest_in_pool',
            [selected_outcome.result['id']],
        )
    assert unnecessary.value.code == 'event_selection_unnecessary'
    db.rollback()

    revision = _apply_material_change(
        db,
        event.id,
        {'capacity': 1, 'venue_name': 'Updated fictional venue'},
        now() + timedelta(days=1),
        'exact',
        [selected_outcome.result['id']],
        call_twice=True,
    )
    assert revision == 1
    db.expire_all()
    protected_registration = db.get(Registration, protected_outcome.result['id'])
    selected_registration = db.get(Registration, selected_outcome.result['id'])
    assert protected_registration.status == 'reconfirmation_required'
    assert protected_registration.reconfirm_revision == 1
    assert selected_registration.status == 'cancelled'
    assert db.scalar(select(func.count(Notification.id)).where(
        Notification.kind == 'event_material_change',
        Notification.dedupe_key.like(f'registration_material_change:{event.id}:revision:1:%'),
    )) == 3

    with pytest.raises(DomainError) as stale:
        service.reconfirm_registration(protected.id, event.id, True, 0)
    assert stale.value.code == 'registration_reconfirmation_stale'
    accepted = service.reconfirm_registration(protected.id, event.id, True, 1)
    assert accepted['status'] == 'confirmed'


def test_newest_in_pool_uses_confirmation_time_and_decline_promotes_waitlist(db, make_user, make_event):
    event = make_event(capacity=3)
    oldest, middle, newest, queued = [make_user() for _ in range(4)]
    oldest_result = service.submit_registration(oldest.id, event.id, 'pool-oldest-0001')
    middle_result = service.submit_registration(middle.id, event.id, 'pool-middle-0001')
    newest_result = service.submit_registration(newest.id, event.id, 'pool-newest-0001')
    queued_result = service.submit_registration(queued.id, event.id, 'pool-queued-0001')
    assert queued_result.result['status'] == 'waitlisted'

    revision = _apply_material_change(
        db,
        event.id,
        {'capacity': 1},
        now() + timedelta(days=1),
        'newest_in_pool',
        [
            oldest_result.result['id'],
            middle_result.result['id'],
            newest_result.result['id'],
        ],
    )
    assert revision == 1
    db.expire_all()
    assert db.get(Registration, newest_result.result['id']).status == 'cancelled'
    assert db.get(Registration, oldest_result.result['id']).status == 'reconfirmation_required'
    assert db.get(Registration, middle_result.result['id']).status == 'cancelled'

    declined = service.reconfirm_registration(oldest.id, event.id, False, 1)
    assert declined['status'] == 'cancelled'
    assert service.list_my_registrations(queued.id)[0]['status'] == 'confirmed'


def test_concurrent_approval_submissions_reserve_exact_capacity(make_user, make_event):
    event = _approval_event(make_event, capacity=2)
    users = [make_user() for _ in range(8)]

    def submit(index_user):
        index, user = index_user
        return service.submit_registration(user.id, event.id, f'parallel-approval-{index:03d}')

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(submit, enumerate(users)))

    assert sum(result.result['status'] == 'pending' for result in outcomes) == 2
    assert sum(result.result['status'] == 'waitlisted' for result in outcomes) == 6
    assert len({result.result['admission_order'] for result in outcomes}) == 8


def test_concurrent_opposite_decisions_leave_one_terminal_state(make_user, make_event):
    event = _approval_event(make_event, capacity=1)
    attendee = make_user()
    pending = service.submit_registration(attendee.id, event.id, 'decision-race-0001')

    def decide(decision):
        try:
            return service.decide_registration(
                event.created_by,
                event.id,
                pending.result['id'],
                decision,
            )['status']
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, ('approve', 'reject')))

    assert results.count('confirmed') + results.count('rejected') == 1
    assert sum(result == 'registration_decision_stale' for result in results) == 1
