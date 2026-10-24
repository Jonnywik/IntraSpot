from concurrent.futures import ThreadPoolExecutor
from threading import Event as ThreadEvent
from time import monotonic, sleep
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.domains.eventsafety import service as eventsafety_service
from app.domains.eventsafety.models import EventControl, SafetyAudit
from app.domains.registrations import service as registration_service
from app.domains.registrations.models import Registration
from app.main import create_app


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _register(client, token, event_id, key):
    return client.post(
        f"/api/v1/events/{event_id}/registrations",
        headers=_auth(token) | {"Idempotency-Key": key},
    )


def _suspend(client, token, org_id):
    return client.post(
        f"/api/v1/organizations/{org_id}/suspension",
        headers=_auth(token),
        json={
            "action": "suspend",
            "version": 0,
            "days": 1,
            "client_key": str(uuid4()),
        },
    )


def test_draft_event_cannot_be_hidden_when_server_permission_denies_it(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org, status="draft", published_at=None)
    headers = {"Authorization": f"Bearer {token_for(owner)}"}
    url = f"/api/v1/events/{event.id}/safety"

    state = client.get(url, headers=headers)
    assert state.status_code == 200
    assert state.json()["can_hide"] is False

    hidden = client.post(
        url,
        headers=headers,
        json={
            "action": "hide",
            "version": state.json()["version"],
            "client_key": str(uuid4()),
        },
    )

    assert hidden.status_code == 409
    assert hidden.json()["error"]["code"] == "event_hide_unavailable"
    assert db.get(EventControl, event.id) is None
    assert db.scalar(
        select(func.count(SafetyAudit.id)).where(
            SafetyAudit.event_id == event.id,
            SafetyAudit.action == "hide",
        )
    ) == 0


def test_suspension_waits_for_inflight_admission_then_blocks_new_joins(
    client, db, make_user, make_org, make_event, token_for, monkeypatch,
):
    owner = make_user()
    org = make_org(owner=owner)
    platform_admin = make_user(platform_admin=True)
    confirmed_user, joining_user, outsider = (make_user() for _ in range(3))
    event = make_event(org=org, capacity=1)

    confirmed = _register(
        client, token_for(confirmed_user), event.id, "s23-confirmed-001",
    )
    assert confirmed.status_code == 201
    assert confirmed.json()["status"] == "confirmed"

    receipt_key = "s23-inflight-join-001"
    receipt_id = registration_service.intake_registration(
        joining_user.id, event.id, receipt_key,
    )
    availability_checked = ThreadEvent()
    release_registration = ThreadEvent()
    suspension_lock_started = ThreadEvent()
    registration_pid: dict[str, int] = {}
    suspension_pid: dict[str, int] = {}

    original_require_new = registration_service.require_new_registration

    def pause_after_availability_check(session, locked_event, *args, **kwargs):
        result = original_require_new(session, locked_event, *args, **kwargs)
        if locked_event.id == event.id:
            registration_pid["value"] = session.scalar(text("SELECT pg_backend_pid()"))
            availability_checked.set()
            if not release_registration.wait(timeout=10):
                raise TimeoutError("registration pause was not released")
        return result

    monkeypatch.setattr(
        registration_service, "require_new_registration", pause_after_availability_check,
    )
    original_event_locker = eventsafety_service._lock_published_events_for_suspension

    def record_suspension_lock(session, current_org_id):
        if current_org_id == org.id:
            suspension_pid["value"] = session.scalar(text("SELECT pg_backend_pid()"))
            suspension_lock_started.set()
        return original_event_locker(session, current_org_id)

    monkeypatch.setattr(
        eventsafety_service,
        "_lock_published_events_for_suspension",
        record_suspension_lock,
    )

    suspension_future = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        registration_future = pool.submit(registration_service.catch_up_event, event.id)
        try:
            assert availability_checked.wait(timeout=5)

            def suspend_in_separate_client():
                with TestClient(create_app()) as concurrent_client:
                    return _suspend(
                        concurrent_client, token_for(platform_admin), org.id,
                    )

            suspension_future = pool.submit(suspend_in_separate_client)
            assert suspension_lock_started.wait(timeout=5)

            deadline = monotonic() + 5
            blocked_by_registration = False
            while monotonic() < deadline:
                db.execute(text("SELECT pg_stat_clear_snapshot()"))
                blocked_by_registration = bool(db.scalar(
                    text("""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_stat_activity
                            WHERE pid = :suspension_pid
                              AND wait_event_type = 'Lock'
                              AND :registration_pid = ANY(pg_blocking_pids(pid))
                        )
                    """),
                    {
                        "suspension_pid": suspension_pid["value"],
                        "registration_pid": registration_pid["value"],
                    },
                ))
                if blocked_by_registration:
                    break
                sleep(0.02)
            assert blocked_by_registration, "suspension did not wait for the in-flight event lock"
        finally:
            release_registration.set()

        registration_future.result(timeout=10)
        assert suspension_future is not None
        suspended = suspension_future.result(timeout=10)

    assert suspended.status_code == 200
    assert suspended.json()["is_suspended"] is True

    db.expire_all()
    statuses = {
        row.user_id: row.status
        for row in db.scalars(
            select(Registration)
            .where(Registration.event_id == event.id)
            .order_by(Registration.admission_order)
        )
    }
    assert statuses == {
        confirmed_user.id: "confirmed",
        joining_user.id: "waitlisted",
    }

    denied = _register(
        client, token_for(outsider), event.id, "s23-after-suspend-001",
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "event_registration_unavailable"

    withdrawn = client.delete(
        f"/api/v1/events/{event.id}/registrations/me",
        headers=_auth(token_for(confirmed_user)),
    )
    assert withdrawn.status_code == 200
    db.expire_all()
    joining_registration = db.scalar(
        select(Registration).where(
            Registration.event_id == event.id,
            Registration.user_id == joining_user.id,
        )
    )
    assert joining_registration is not None
    assert joining_registration.status == "confirmed"

    replay = _register(client, token_for(joining_user), event.id, receipt_key)
    original_outcome = registration_service.registration_outcome(receipt_id)
    assert replay.status_code == original_outcome.http_status
    assert replay.json() == original_outcome.result
