from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select

from app.domains.events.models import Event
from app.domains.registrations import service
from app.domains.registrations.models import Registration, RegistrationReceipt
from app.notifications import Notification


def _run_together(actions):
    barrier = Barrier(len(actions))

    def run(action):
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        futures = {name: pool.submit(run, action) for name, action in actions.items()}
        return {name: future.result(timeout=30) for name, future in futures.items()}


def test_withdrawal_races_with_new_admissions_and_idempotent_retries(
    db, make_event, make_user
):
    event = make_event(capacity=1)
    holder, first_waiter, new_a, new_b = [make_user() for _ in range(4)]

    holder_result = service.submit_registration(holder.id, event.id, "s4-race-holder-01")
    first_waiter_result = service.submit_registration(
        first_waiter.id, event.id, "s4-race-waiter-01"
    )
    assert holder_result.result["status"] == "confirmed"
    assert first_waiter_result.result["status"] == "waitlisted"

    raced = _run_together(
        {
            "withdrawal": lambda: service.withdraw_registration(holder.id, event.id),
            "new_a": lambda: service.submit_registration(
                new_a.id, event.id, "s4-race-new-a-01"
            ),
            "new_a_retry": lambda: service.submit_registration(
                new_a.id, event.id, "s4-race-new-a-01"
            ),
            "new_b": lambda: service.submit_registration(
                new_b.id, event.id, "s4-race-new-b-01"
            ),
            "waiter_retry": lambda: service.submit_registration(
                first_waiter.id, event.id, "s4-race-waiter-01"
            ),
        }
    )

    assert raced["withdrawal"]["status"] == "cancelled"
    assert raced["new_a"] == raced["new_a_retry"]
    assert raced["waiter_retry"] == first_waiter_result
    assert raced["waiter_retry"].result["status"] == "waitlisted"
    assert (
        raced["new_a"].result["status"]
        == raced["new_b"].result["status"]
        == "waitlisted"
    )

    db.expire_all()
    receipts = list(
        db.scalars(
            select(RegistrationReceipt)
            .where(RegistrationReceipt.event_id == event.id)
            .order_by(RegistrationReceipt.event_order)
        )
    )
    assert len(receipts) == 4  # The same-key retries did not create extra receipts.
    assert len({receipt.event_order for receipt in receipts}) == len(receipts)
    assert db.scalar(select(Event.next_admission).where(Event.id == event.id)) == 4

    receipt_by_user = {receipt.user_id: receipt for receipt in receipts}
    new_receipts = sorted(
        (receipt_by_user[user.id] for user in (new_a, new_b)),
        key=lambda receipt: receipt.event_order,
    )
    registrations = list(
        db.scalars(select(Registration).where(Registration.event_id == event.id))
    )
    registration_by_user = {
        registration.user_id: registration for registration in registrations
    }
    assert registration_by_user[holder.id].status == "cancelled"
    assert registration_by_user[first_waiter.id].status == "confirmed"
    assert [
        registration_by_user[receipt.user_id].admission_order
        for receipt in new_receipts
    ] == [receipt.event_order for receipt in new_receipts]
    current_waitlist = list(
        db.scalars(
            select(Registration)
            .where(
                Registration.event_id == event.id,
                Registration.status == "waitlisted",
            )
            .order_by(Registration.admission_order)
        )
    )
    assert [registration.user_id for registration in current_waitlist] == [
        receipt.user_id for receipt in new_receipts
    ]

    promotions = list(
        db.scalars(
            select(Notification).where(
                Notification.event_id == event.id,
                Notification.kind == "waitlist_promoted",
            )
        )
    )
    assert [notification.user_id for notification in promotions] == [first_waiter.id]


def test_simultaneous_confirmed_withdrawals_promote_earliest_waiters_once(
    db, make_event, make_user
):
    event = make_event(capacity=3)
    users = [make_user() for _ in range(7)]
    holders, waiters = users[:3], users[3:]
    initial_results = {}

    for index, user in enumerate(users):
        initial_results[user.id] = service.submit_registration(
            user.id, event.id, f"s4-multi-{index:02d}"
        )

    assert [initial_results[user.id].result["status"] for user in holders] == [
        "confirmed",
        "confirmed",
        "confirmed",
    ]
    assert [initial_results[user.id].result["status"] for user in waiters] == [
        "waitlisted",
        "waitlisted",
        "waitlisted",
        "waitlisted",
    ]

    raced_withdrawals = _run_together(
        {
            holder.id: lambda holder_id=holder.id: service.withdraw_registration(
                holder_id, event.id
            )
            for holder in holders
        }
    )
    assert all(
        result["status"] == "cancelled" for result in raced_withdrawals.values()
    )
    assert {
        user_id: result["id"] for user_id, result in raced_withdrawals.items()
    } == {
        holder.id: initial_results[holder.id].result["id"] for holder in holders
    }

    db.expire_all()
    receipts = list(
        db.scalars(
            select(RegistrationReceipt)
            .where(RegistrationReceipt.event_id == event.id)
            .order_by(RegistrationReceipt.event_order)
        )
    )
    waiter_ids = {waiter.id for waiter in waiters}
    holder_ids = {holder.id for holder in holders}
    waiters_by_receipt_order = [
        receipt.user_id for receipt in receipts if receipt.user_id in waiter_ids
    ]
    # Persisted receipt order is the admission oracle for concurrent outcomes.
    expected_promotions = waiters_by_receipt_order[: len(holders)]
    expected_remaining = waiters_by_receipt_order[len(holders) :]

    registrations = list(
        db.scalars(select(Registration).where(Registration.event_id == event.id))
    )
    confirmed = sorted(
        (
            registration
            for registration in registrations
            if registration.status == "confirmed"
        ),
        key=lambda registration: registration.admission_order,
    )
    waiting = sorted(
        (
            registration
            for registration in registrations
            if registration.status == "waitlisted"
        ),
        key=lambda registration: registration.admission_order,
    )
    assert [registration.user_id for registration in confirmed] == expected_promotions
    assert [registration.user_id for registration in waiting] == expected_remaining
    assert all(
        registration.status == "cancelled"
        for registration in registrations
        if registration.user_id in holder_ids
    )
    assert db.scalar(
        select(func.count(Registration.id)).where(
            Registration.event_id == event.id,
            Registration.status == "confirmed",
        )
    ) == event.capacity

    promotions = list(
        db.scalars(
            select(Notification).where(
                Notification.event_id == event.id,
                Notification.kind == "waitlist_promoted",
            )
        )
    )
    assert len(promotions) == len(holders)
    assert sorted(notification.user_id for notification in promotions) == sorted(
        expected_promotions
    )
    assert len({notification.registration_id for notification in promotions}) == len(holders)
