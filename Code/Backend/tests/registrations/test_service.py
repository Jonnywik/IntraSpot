from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from app.core.errors import DomainError
from app.db.models import now
from app.domains.events.models import Event
from app.domains.registrations import service
from app.domains.registrations.models import Registration, RegistrationReceipt
from app.notifications import Notification


def test_ten_independent_attempts_obey_three_seat_capacity(db, make_event, make_user):
    event = make_event(capacity=3)
    users = [make_user() for _ in range(10)]

    def submit(item):
        index, user = item
        return service.submit_registration(user.id, event.id, f'admission-key-{index:02d}')

    with ThreadPoolExecutor(max_workers=10) as pool:
        outcomes = list(pool.map(submit, enumerate(users)))

    results = [outcome.result for outcome in outcomes]
    assert Counter(result['status'] for result in results) == {'confirmed': 3, 'waitlisted': 7}
    assert sorted(result['admission_order'] for result in results) == list(range(1, 11))
    by_event_order = sorted(results, key=lambda result: result['admission_order'])
    assert [result['status'] for result in by_event_order] == ['confirmed'] * 3 + ['waitlisted'] * 7
    queued = sorted((r for r in results if r['status'] == 'waitlisted'), key=lambda r: r['admission_order'])
    assert [r['waitlist_position'] for r in queued] == list(range(1, 8))
    assert all(r['waitlist_message'] == service.WAITLIST_MESSAGE for r in queued)

    db.expire_all()
    assert db.scalar(select(Event.next_admission).where(Event.id == event.id)) == 10
    assert db.scalar(
        select(func.count(Registration.id)).where(Registration.event_id == event.id, Registration.status == 'confirmed')
    ) == 3


def test_concurrent_same_key_commits_one_receipt_and_one_attempt(db, make_event, make_user):
    event = make_event(capacity=3)
    user = make_user()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(
            lambda _: service.submit_registration(user.id, event.id, 'same-key-0001'),
            range(2),
        ))

    assert outcomes[0].http_status == outcomes[1].http_status == 201
    assert outcomes[0].result == outcomes[1].result
    db.expire_all()
    assert db.scalar(select(Event.next_admission).where(Event.id == event.id)) == 1
    assert db.scalar(select(func.count(RegistrationReceipt.id)).where(RegistrationReceipt.event_id == event.id)) == 1
    assert db.scalar(select(func.count(Registration.id)).where(Registration.event_id == event.id)) == 1


def test_explicit_none_receipt_remains_pending_and_recovers(db, make_event, make_user):
    event = make_event(capacity=1)
    user = make_user()
    receipt_id = service.intake_registration(user.id, event.id, 'explicit-null-key')

    receipt = db.get(RegistrationReceipt, receipt_id)
    assert db.scalar(
        select(RegistrationReceipt.id).where(
            RegistrationReceipt.id == receipt_id,
            RegistrationReceipt.result.is_(None),
        )
    ) == receipt_id

    receipt.result = None
    flag_modified(receipt, 'result')
    db.commit()
    db.expire_all()

    assert db.scalar(
        select(RegistrationReceipt.id).where(
            RegistrationReceipt.id == receipt_id,
            RegistrationReceipt.result.is_(None),
        )
    ) == receipt_id

    service.drain_event(event.id)

    db.expire_all()
    recovered = db.get(RegistrationReceipt, receipt_id)
    assert recovered.http_status == 201
    assert recovered.result['status'] == 'confirmed'
    assert recovered.processed_at is not None


def test_same_key_replays_immutable_result_and_cannot_move_to_another_event(db, make_event, make_user):
    user = make_user()
    event = make_event(capacity=1)
    other_event = make_event(capacity=1)
    holder = make_user()

    service.submit_registration(holder.id, event.id, 'holder-key-001')
    first = service.submit_registration(user.id, event.id, 'retry-key-0001')
    assert first.result['status'] == 'waitlisted'
    assert first.result['waitlist_position'] == 1

    service.withdraw_registration(holder.id, event.id)
    current = service.list_my_registrations(user.id)
    assert current[0]['status'] == 'confirmed'

    event.starts_at = now() - timedelta(minutes=1)
    db.commit()
    replay = service.submit_registration(user.id, event.id, 'retry-key-0001')
    assert replay.http_status == first.http_status
    assert replay.result == first.result

    new_key_after_start = service.submit_registration(user.id, event.id, 'after-start-key')
    assert new_key_after_start.http_status == 409
    assert new_key_after_start.result['error']['code'] == 'event_started'

    db.expire_all()
    assert db.scalar(select(Event.next_admission).where(Event.id == event.id)) == 3
    with pytest.raises(DomainError) as error:
        service.submit_registration(user.id, other_event.id, 'retry-key-0001')
    assert (error.value.code, error.value.status) == ('idempotency_key_reused', 409)
    db.expire_all()
    assert db.scalar(select(Event.next_admission).where(Event.id == other_event.id)) == 0


def test_different_key_for_active_registration_returns_current_without_a_second_seat(db, make_event, make_user):
    event = make_event(capacity=1)
    user = make_user()

    first = service.submit_registration(user.id, event.id, 'first-key-0001')
    duplicate = service.submit_registration(user.id, event.id, 'different-key-001')

    assert first.result['status'] == duplicate.result['status'] == 'confirmed'
    assert first.result['id'] == duplicate.result['id']
    assert first.result['admission_order'] == duplicate.result['admission_order']
    db.expire_all()
    assert db.scalar(select(func.count(Registration.id)).where(Registration.event_id == event.id)) == 1
    assert db.scalar(select(Event.next_admission).where(Event.id == event.id)) == 2


def test_pending_receipt_recovers_before_withdrawal_and_promotes_once(db, make_event, make_user):
    event = make_event(capacity=1)
    holder, earliest, later = [make_user() for _ in range(3)]
    service.submit_registration(holder.id, event.id, 'holder-key-002')
    service.submit_registration(earliest.id, event.id, 'early-key-0001')

    # Simulate a process stopping after the durable intake commit and before its drain.
    receipt_id = service.intake_registration(later.id, event.id, 'late-key-0001')
    db.expire_all()
    pending = db.get(RegistrationReceipt, receipt_id)
    assert pending.result is None and pending.processed_at is None
    assert pending.event_order == 3

    # Duplicate withdrawals race on separate transactions; only one can promote.
    with ThreadPoolExecutor(max_workers=2) as pool:
        withdrawals = list(pool.map(lambda _: service.withdraw_registration(holder.id, event.id), range(2)))

    assert all(r['status'] == 'cancelled' for r in withdrawals)
    assert withdrawals[0]['id'] == withdrawals[1]['id']
    early_state = service.list_my_registrations(earliest.id)[0]
    later_state = service.list_my_registrations(later.id)[0]
    assert early_state['status'] == 'confirmed'
    assert later_state['status'] == 'waitlisted'
    assert later_state['waitlist_position'] == 1

    db.expire_all()
    pending = db.get(RegistrationReceipt, receipt_id)
    assert pending.result['status'] == 'waitlisted'
    assert pending.processed_at is not None
    assert db.scalar(select(func.count(Notification.id)).where(Notification.event_id == event.id)) == 1

    event.starts_at = now() - timedelta(minutes=1)
    db.commit()
    retry = service.withdraw_registration(holder.id, event.id)
    assert retry['status'] == 'cancelled'
    assert retry['id'] == withdrawals[0]['id']
    db.expire_all()
    assert db.scalar(select(func.count(Notification.id)).where(Notification.event_id == event.id)) == 1


def test_withdrawal_after_start_does_not_promote(db, make_event, make_user):
    event = make_event(capacity=1)
    holder, queued = make_user(), make_user()
    service.submit_registration(holder.id, event.id, 'holder-key-003')
    service.submit_registration(queued.id, event.id, 'queue-key-0001')
    event.starts_at = now() - timedelta(minutes=1)
    db.commit()

    with pytest.raises(DomainError) as error:
        service.withdraw_registration(holder.id, event.id)
    assert (error.value.code, error.value.status) == ('event_started', 409)

    current = service.list_my_registrations(queued.id)[0]
    assert current['status'] == 'waitlisted'
    db.expire_all()
    assert db.scalar(select(func.count(Notification.id)).where(Notification.event_id == event.id)) == 0


def test_withdrawing_waitlisted_registration_does_not_open_or_promote_a_seat(db, make_event, make_user):
    event = make_event(capacity=1)
    holder, first_waitlisted, second_waitlisted = [make_user() for _ in range(3)]
    service.submit_registration(holder.id, event.id, 'holder-key-004')
    service.submit_registration(first_waitlisted.id, event.id, 'first-queue-key')
    service.submit_registration(second_waitlisted.id, event.id, 'second-queue-key')

    withdrawn = service.withdraw_registration(first_waitlisted.id, event.id)

    assert withdrawn['status'] == 'cancelled'
    assert service.list_my_registrations(holder.id)[0]['status'] == 'confirmed'
    remaining = service.list_my_registrations(second_waitlisted.id)[0]
    assert remaining['status'] == 'waitlisted'
    assert remaining['waitlist_position'] == 1
    db.expire_all()
    assert db.scalar(select(func.count(Notification.id)).where(Notification.event_id == event.id)) == 0


def test_published_event_without_positive_capacity_is_rejected_by_database(db, make_event):
    event = make_event()
    event.capacity = None
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.refresh(event)
    assert event.capacity == 3


def test_notification_failure_rolls_back_withdrawal_and_promotion(db, make_event, make_user, monkeypatch):
    import app.notifications as notifications

    event = make_event(capacity=1)
    holder, queued = make_user(), make_user()
    service.submit_registration(holder.id, event.id, 'rollback-holder-01')
    service.submit_registration(queued.id, event.id, 'rollback-queued-01')

    def fail_notification(*args):
        raise RuntimeError('simulated notification failure')

    monkeypatch.setattr(notifications, 'notify_promotion', fail_notification)
    with pytest.raises(RuntimeError, match='simulated notification failure'):
        service.withdraw_registration(holder.id, event.id)

    assert service.list_my_registrations(holder.id)[0]['status'] == 'confirmed'
    assert service.list_my_registrations(queued.id)[0]['status'] == 'waitlisted'
    db.expire_all()
    assert db.scalar(select(func.count(Notification.id))) == 0


def test_withdrawal_commits_bounded_backlog_before_promoting(db, make_event, make_user, monkeypatch):
    monkeypatch.setattr(service, 'DRAIN_BATCH_SIZE', 1)
    event = make_event(capacity=1)
    holder, first, second = [make_user() for _ in range(3)]
    service.submit_registration(holder.id, event.id, 'batch-holder-01')
    service.intake_registration(first.id, event.id, 'batch-first-01')
    service.intake_registration(second.id, event.id, 'batch-second-01')

    service.withdraw_registration(holder.id, event.id)

    assert service.list_my_registrations(holder.id)[0]['status'] == 'cancelled'
    assert service.list_my_registrations(first.id)[0]['status'] == 'confirmed'
    remaining = service.list_my_registrations(second.id)[0]
    assert remaining['status'] == 'waitlisted' and remaining['waitlist_position'] == 1
    db.expire_all()
    assert db.scalar(select(func.count(Notification.id))) == 1
