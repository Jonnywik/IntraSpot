"""Sprint 4 quality gate: failing-path probes for concurrency, read-path,
published-row integrity, privacy, contract drift, and restart/recovery.

Conventions: shared fixtures (client, db, make_user, make_org, make_event,
token_for). No threads here; the coordinator runs this file SERIALLY against
real PostgreSQL 17 on loopback 5433 (intraspot_mvp_test). Existing threaded
race coverage lives in tests/registrations/test_service.py.

Regression checks for the defects in the initial quality review.
Fictional local data only.
"""

from datetime import timedelta

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import ROOT
from app.db.models import now, uid
from app.db.session import engine
from app.domains.events.models import Event
from app.domains.registrations import service
from app.domains.registrations.models import Registration, RegistrationReceipt
from app.notifications import Notification


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _pending_receipt(db, event, user, key="s4-pending-01", order=1):
    receipt = RegistrationReceipt(
        id=uid(),
        user_id=user.id,
        event_id=event.id,
        idempotency_key=key,
        event_order=order,
    )
    event.next_admission = order
    db.add(receipt)
    db.commit()
    return receipt


# --- D1: public reads must not perform registration writes (NOW-FAILS) ---


def test_public_detail_get_does_not_drain_pending_receipt(client, db, make_event, make_user):
    # NOW-FAILS (D1). Anonymous public detail must be a pure read.
    event = make_event(capacity=3)
    user = make_user()
    receipt = _pending_receipt(db, event, user)
    db.expire_all()

    response = client.get(f"/api/v1/events/{event.id}")

    assert response.status_code == 200
    assert response.json()["confirmed_count"] == 0
    db.expire_all()
    stored = db.get(RegistrationReceipt, receipt.id)
    assert stored.result is None and stored.processed_at is None
    assert (
        db.scalar(select(func.count(Registration.id)).where(Registration.event_id == event.id))
        == 0
    )


def test_public_list_get_does_not_drain_pending_receipt(client, db, make_event, make_user):
    # NOW-FAILS (D1). The discovery list fans the write out to every row.
    event = make_event(capacity=3)
    user = make_user()
    receipt = _pending_receipt(db, event, user)
    db.expire_all()

    response = client.get("/api/v1/events")

    assert response.status_code == 200
    db.expire_all()
    stored = db.get(RegistrationReceipt, receipt.id)
    assert stored.result is None and stored.processed_at is None


# --- D2: unbounded list endpoints and per-row counts (NOW-FAILS) ---


def test_event_list_honors_limit(client, make_event):
    # NOW-FAILS (D2). Discovery has no pagination; `limit` is ignored.
    for _ in range(5):
        make_event()

    response = client.get("/api/v1/events", params={"limit": 2})

    assert response.status_code == 200
    assert len(response.json()) <= 2


def test_event_list_statement_growth_is_bounded(client, db, make_event):
    # NOW-FAILS (D2). Each listed row costs per-event SELECTs (row lock,
    # pending scan, confirmed count): N+1 on a public anonymous endpoint.
    make_event()
    selects = []

    def before_cursor(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            selects.append(statement)

    eng = engine()
    sa_event.listen(eng, "before_cursor_execute", before_cursor)
    try:
        assert client.get("/api/v1/events").status_code == 200
        first = len(selects)
        for _ in range(9):
            make_event()
        db.expire_all()
        selects.clear()
        assert client.get("/api/v1/events").status_code == 200
        second = len(selects)
    finally:
        sa_event.remove(eng, "before_cursor_execute", before_cursor)

    # Event rows, aggregated attendance, and one batched Featured lookup.
    assert second == first == 3


# --- D3: unbounded summary payload (NOW-FAILS) ---


def test_publish_rejects_oversized_summary(client, db, make_user, make_org, make_event, token_for):
    # NOW-FAILS (D3). `summary` is unbounded Text, accepted at publish and
    # returned in full on every list row.
    owner = make_user()
    event = make_event(
        org=make_org(owner=owner), status="draft", published_at=None, summary="x" * 100_000
    )

    response = client.post(
        f"/api/v1/events/{event.id}/publish", headers=auth(token_for(owner))
    )

    assert response.status_code == 422


# --- D4: published rows depend on app-only validation (NOW-FAILS) ---


def test_published_null_title_rejected_by_database(db, make_event):
    # NOW-FAILS (D4). No DB guard: a published row with NULL title commits,
    # then breaks the EventPublic contract (title: str) on public reads.
    event = make_event(status="draft", published_at=None)
    event.status = "published"
    event.published_at = now()
    event.title = None

    with pytest.raises(IntegrityError):
        db.commit()


def test_published_null_times_rejected_by_database(db, make_event):
    # NOW-FAILS (D4). Same gap for NULL starts_at/ends_at on published rows.
    event = make_event(status="draft", published_at=None)
    event.status = "published"
    event.published_at = now()
    event.starts_at = None
    event.ends_at = None

    with pytest.raises(IntegrityError):
        db.commit()


# --- Privacy boundary locks (NOW-PASSES) ---


def test_public_organization_profile_exposes_no_private_ids(client, db, make_user, make_org):
    # NOW-PASSES. Public org profile carries no creator, membership, or
    # accreditation-actor identities.
    organization = make_org(owner=make_user(), accreditation_status="approved")

    response = client.get(f"/api/v1/organizations/{organization.id}")

    assert response.status_code == 200
    assert response.json()['logo_url'] is None
    assert set(response.json()) == {
        "id",
        "name",
        "description",
        "accreditation_status",
        "created_at",
        "logo_url",
    }
    assert organization.created_by not in response.text


def test_pending_and_rejected_org_drafts_are_undiscoverable(
    client, db, make_user, make_org, make_event, token_for
):
    # NOW-PASSES. Drafts under pending/rejected orgs never reach discovery.
    owner = make_user()
    pending_event = make_event(
        org=make_org(owner=owner, accreditation_status="pending"),
        status="draft",
        published_at=None,
    )
    rejected_event = make_event(
        org=make_org(owner=owner, accreditation_status="rejected"),
        status="draft",
        published_at=None,
    )

    listed = client.get("/api/v1/events")
    assert listed.status_code == 200
    ids = {row["id"] for row in listed.json()}
    assert pending_event.id not in ids
    assert rejected_event.id not in ids
    assert client.get(f"/api/v1/events/{pending_event.id}").status_code == 404
    assert client.get(f"/api/v1/events/{rejected_event.id}").status_code == 404


def test_withdraw_waitlisted_after_start_denied_without_promotion(
    client, db, make_event, make_user, token_for
):
    # NOW-PASSES. Post-start withdrawal is denied before any state change;
    # no seat opens, no notification is emitted.
    event = make_event(capacity=1)
    holder = make_user()
    queued = make_user()
    service.submit_registration(holder.id, event.id, "s4-holder-01")
    service.submit_registration(queued.id, event.id, "s4-queued-01")
    event.starts_at = now() - timedelta(minutes=1)
    db.commit()

    response = client.delete(
        f"/api/v1/events/{event.id}/registrations/me",
        headers=auth(token_for(queued)),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "event_started"
    db.expire_all()
    assert service.list_my_registrations(queued.id)[0]["status"] == "waitlisted"
    assert service.list_my_registrations(holder.id)[0]["status"] == "confirmed"
    assert (
        db.scalar(select(func.count(Notification.id)).where(Notification.event_id == event.id))
        == 0
    )


def test_withdraw_promotes_exactly_one_with_two_waitlisted(db, make_event, make_user):
    # NOW-PASSES. Single-seat release promotes only the earliest queue entry.
    event = make_event(capacity=1)
    holder, first, second = [make_user() for _ in range(3)]
    service.submit_registration(holder.id, event.id, "s4-multi-holder")
    service.submit_registration(first.id, event.id, "s4-multi-first")
    service.submit_registration(second.id, event.id, "s4-multi-second")

    withdrawn = service.withdraw_registration(holder.id, event.id)

    assert withdrawn["status"] == "cancelled"
    assert service.list_my_registrations(first.id)[0]["status"] == "confirmed"
    remaining = service.list_my_registrations(second.id)[0]
    assert remaining["status"] == "waitlisted"
    assert remaining["waitlist_position"] == 1
    db.expire_all()
    assert (
        db.scalar(select(func.count(Notification.id)).where(Notification.event_id == event.id))
        == 1
    )


def test_admission_order_gaps_do_not_shift_waitlist_positions(db, make_event, make_user):
    # NOW-PASSES. Duplicate-key receipts consume event orders without creating
    # registrations; positions must still count registrations, not orders.
    event = make_event(capacity=1)
    confirmed_user, queued_user, late_user = [make_user() for _ in range(3)]
    service.submit_registration(confirmed_user.id, event.id, "s4-gap-holder")
    first = service.submit_registration(queued_user.id, event.id, "s4-gap-key-1")
    assert first.result["waitlist_position"] == 1
    duplicate = service.submit_registration(queued_user.id, event.id, "s4-gap-key-2")
    assert duplicate.result["admission_order"] == first.result["admission_order"]
    late = service.submit_registration(late_user.id, event.id, "s4-gap-late")

    assert late.result["waitlist_position"] == 2
    db.expire_all()
    assert db.scalar(select(Event.next_admission).where(Event.id == event.id)) == 4


# --- Contract drift lock (outcome UNKNOWN until coordinator runs it live) ---


def test_committed_openapi_matches_live_schema():
    # UNKNOWN. Static review shows all 17 /api/v1 paths and all schemas
    # present on disk; this test proves freshness against the live app.
    import json

    disk = json.loads(
        (ROOT.parents[1] / "docs/backend/openapi.json").read_text(encoding="utf-8")
    )
    live = __import__("app.main", fromlist=["create_app"]).create_app().openapi()

    assert set(live["paths"]) == set(disk["paths"])
    assert set(live["components"]["schemas"]) == set(disk["components"]["schemas"])
    for path in live["paths"]:
        assert live["paths"][path] == disk["paths"][path], f"drift at {path}"
    for name in live["components"]["schemas"]:
        assert live["components"]["schemas"][name] == disk["components"]["schemas"][name], (
            f"drift at schema {name}"
        )
