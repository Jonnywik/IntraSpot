"""PostgreSQL API regressions for private saved events and conflict warnings."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import func, select, text

from app.db.models import now, uid
from app.db.session import engine
from app.domains.events.models import Event
from app.domains.organizations.models import Organization
from app.domains.planning.models import SavedEvent
from app.domains.registrations.models import Registration


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _saved_count(db, user_id, event_id):
    return db.scalar(
        text("SELECT count(*) FROM saved_events WHERE user_id = :user_id AND event_id = :event_id"),
        {"user_id": user_id, "event_id": event_id},
    )


def _register(db, event, user, status="confirmed"):
    previous = db.scalar(
        select(func.max(Registration.admission_order)).where(Registration.event_id == event.id)
    )
    registration = Registration(
        id=uid(),
        user_id=user.id,
        event_id=event.id,
        status=status,
        admission_order=(previous or 0) + 1,
        confirmed_at=now() if status == "confirmed" else None,
    )
    db.add(registration)
    db.commit()
    return registration


def _parallel_request(method, path, headers, barrier):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as request_client:
        barrier.wait(timeout=10)
        return getattr(request_client, method)(path, headers=headers)


def test_any_active_account_can_save_without_gaining_registration_eligibility(
    client, db, make_event, make_user, token_for
):
    user = make_user(email_verified=False, nickname=None, age_bracket=None, tags=[])
    event = make_event()
    headers = auth(token_for(user))
    original_capacity = (event.capacity, event.interest_count, event.next_admission)

    saved = client.put(f"/api/v1/me/saved-events/{event.id}", headers=headers)

    assert saved.status_code == 200
    assert saved.json()["event_id"] == event.id
    assert saved.json()["saved"] is True
    assert saved.json()["saved_at"]
    assert set(saved.json()) == {"event_id", "saved", "saved_at"}

    # Saving is separate from registration intake and must not mutate event counters.
    db.refresh(event)
    assert (event.capacity, event.interest_count, event.next_admission) == original_capacity
    assert (
        db.scalar(
            select(func.count(Registration.id)).where(
                Registration.event_id == event.id
            )
        )
        == 0
    )
    assert _saved_count(db, user.id, event.id) == 1

    registration = client.post(
        f"/api/v1/events/{event.id}/registrations",
        headers=headers | {"Idempotency-Key": "sprint17-ineligible-save"},
    )
    assert registration.status_code == 403
    assert registration.json()["error"]["code"] == "registration_ineligible"


def test_saved_event_survives_application_recreation(db, make_event, make_user, token_for):
    from fastapi.testclient import TestClient

    from app.main import create_app

    user = make_user()
    event = make_event()
    headers = auth(token_for(user))
    path = f"/api/v1/me/saved-events/{event.id}"

    with TestClient(create_app()) as first_app:
        saved = first_app.put(path, headers=headers)
    assert saved.status_code == 200
    original_saved_at = saved.json()["saved_at"]

    with TestClient(create_app()) as recreated_app:
        state = recreated_app.get(path, headers=headers)
        saved_events = recreated_app.get("/api/v1/me/saved-events", headers=headers)

    assert state.status_code == 200
    assert state.json() == {
        "event_id": event.id,
        "saved": True,
        "saved_at": original_saved_at,
    }
    assert saved_events.status_code == 200
    assert [row["event_id"] for row in saved_events.json()] == [event.id]
    assert saved_events.json()[0]["saved_at"] == original_saved_at


def test_saved_events_list_query_count_stays_bounded_with_unavailable_rows(
    client, db, make_event, make_org, make_user, token_for
):
    user = make_user()
    visible_events = [make_event() for _ in range(4)]
    pending_org = make_org(accreditation_status="pending")
    rejected_org = make_org(accreditation_status="rejected")
    unavailable_events = [
        make_event(org=pending_org),
        make_event(org=pending_org),
        make_event(org=rejected_org),
        make_event(org=rejected_org),
    ]
    db.add_all(
        SavedEvent(user_id=user.id, event_id=event.id)
        for event in visible_events + unavailable_events
    )
    db.commit()
    db.expire_all()

    statements = []

    def count_statement(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ):
        statements.append(statement)

    database_engine = engine()
    sqlalchemy_event.listen(
        database_engine, "before_cursor_execute", count_statement
    )
    try:
        response = client.get(
            "/api/v1/me/saved-events", headers=auth(token_for(user))
        )
    finally:
        sqlalchemy_event.remove(
            database_engine, "before_cursor_execute", count_statement
        )

    assert response.status_code == 200
    rows = {row["event_id"]: row for row in response.json()}
    assert set(rows) == {event.id for event in visible_events + unavailable_events}
    assert all(
        rows[event.id]["event"] is not None for event in visible_events
    )
    assert all(
        rows[event.id]["event"] is None for event in unavailable_events
    )
    assert len(statements) <= 8, (
        f"saved-events list issued {len(statements)} SQL statements"
    )


def test_guests_forged_or_inactive_callers_are_rejected_and_accounts_are_isolated(
    client, db, make_event, make_user, token_for
):
    owner = make_user()
    other = make_user()
    inactive = make_user(active=False)
    event = make_event()
    saved = client.put(
        f"/api/v1/me/saved-events/{event.id}", headers=auth(token_for(owner))
    )
    assert saved.status_code == 200

    rejected = [
        client.put(f"/api/v1/me/saved-events/{event.id}"),
        client.put(f"/api/v1/me/saved-events/{event.id}", headers=auth("forged.token")),
        client.put(
            f"/api/v1/me/saved-events/{event.id}",
            headers=auth(token_for(str(uuid4()))),
        ),
        client.put(
            f"/api/v1/me/saved-events/{event.id}", headers=auth(token_for(inactive))
        ),
    ]
    assert all(response.status_code == 401 for response in rejected)
    assert all(
        response.json()["error"]["code"] == "authentication_required"
        for response in rejected
    )

    other_headers = auth(token_for(other))
    other_list = client.get(
        "/api/v1/me/saved-events",
        params={"user_id": owner.id},
        headers=other_headers,
    )
    other_state = client.get(
        f"/api/v1/me/saved-events/{event.id}",
        params={"user_id": owner.id},
        headers=other_headers,
    )
    other_remove = client.delete(
        f"/api/v1/me/saved-events/{event.id}",
        params={"user_id": owner.id},
        headers=other_headers,
    )

    assert other_list.status_code == 200
    assert other_list.json() == []
    assert other_state.status_code == 200
    assert other_state.json() == {"event_id": event.id, "saved": False, "saved_at": None}
    assert other_remove.status_code == 200
    assert other_remove.json()["saved"] is False
    assert client.get(
        f"/api/v1/me/saved-events/{event.id}", headers=auth(token_for(owner))
    ).json()["saved"] is True
    assert _saved_count(db, owner.id, event.id) == 1


@pytest.mark.parametrize(
    ("event_status", "organization_status"),
    [
        pytest.param("draft", "approved", id="draft"),
        pytest.param("published", "pending", id="pending-organization"),
        pytest.param("published", "rejected", id="rejected-organization"),
    ],
)
def test_saving_and_conflict_lookup_require_current_public_visibility(
    client, db, make_event, make_org, make_user, token_for, event_status, organization_status
):
    user = make_user()
    organization = make_org(accreditation_status=organization_status)
    event = make_event(
        org=organization,
        status=event_status,
        published_at=None if event_status == "draft" else now(),
    )
    headers = auth(token_for(user))

    saved = client.put(f"/api/v1/me/saved-events/{event.id}", headers=headers)
    public_read = client.get(f"/api/v1/events/{event.id}")
    conflicts = client.get(f"/api/v1/me/event-conflicts/{event.id}", headers=headers)

    assert saved.status_code == 404
    assert public_read.status_code == 404
    assert conflicts.status_code == 404
    assert _saved_count(db, user.id, event.id) == 0


def test_ended_public_event_is_saved_idempotently_then_redacted_and_removable(
    client, db, make_event, make_user, token_for
):
    user = make_user()
    private_title = "Hidden saved event title sentinel"
    event = make_event(
        title=private_title,
        banner_key="music",
        starts_at=now() - timedelta(days=3),
        ends_at=now() - timedelta(days=3) + timedelta(hours=2),
    )
    headers = auth(token_for(user))
    path = f"/api/v1/me/saved-events/{event.id}"

    first = client.put(path, headers=headers)
    retry = client.put(path, headers=headers)
    public_event = client.get(f"/api/v1/events/{event.id}")
    saved_list = client.get("/api/v1/me/saved-events", headers=headers)

    assert first.status_code == retry.status_code == 200
    assert retry.json()["saved_at"] == first.json()["saved_at"]
    assert public_event.status_code == 200
    assert saved_list.status_code == 200
    assert len(saved_list.json()) == 1
    row = saved_list.json()[0]
    assert set(row) == {"event_id", "saved_at", "event"}
    assert row["event_id"] == event.id
    assert row["event"]["id"] == event.id
    assert row["event"]["title"] == private_title
    assert user.id not in saved_list.text
    assert user.email not in saved_list.text
    assert user.nickname not in saved_list.text

    organization = db.get(Organization, event.org_id)
    organization.accreditation_status = "pending"
    db.commit()

    unavailable = client.get("/api/v1/me/saved-events", headers=headers)
    assert unavailable.status_code == 200
    unavailable_row = unavailable.json()[0]
    assert unavailable_row["event_id"] == event.id
    assert unavailable_row["saved_at"] == first.json()["saved_at"]
    assert unavailable_row["event"] is None
    assert private_title not in unavailable.text
    assert "music" not in unavailable.text
    assert "/api/v1/media/" not in unavailable.text
    assert _saved_count(db, user.id, event.id) == 1

    removed = client.delete(path, headers=headers)
    assert removed.status_code == 200
    assert removed.json() == {"event_id": event.id, "saved": False, "saved_at": None}
    assert _saved_count(db, user.id, event.id) == 0


def test_saved_event_is_redacted_after_event_returns_to_draft(
    client, db, make_event, make_user, token_for
):
    user = make_user()
    event = make_event(title="Withdrawn public event")
    headers = auth(token_for(user))
    path = f"/api/v1/me/saved-events/{event.id}"

    saved = client.put(path, headers=headers)
    assert saved.status_code == 200
    saved_at = saved.json()["saved_at"]

    event.status = "draft"
    event.published_at = None
    db.commit()

    listed = client.get("/api/v1/me/saved-events", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == [{"event_id": event.id, "saved_at": saved_at, "event": None}]
    assert _saved_count(db, user.id, event.id) == 1


def test_concurrent_identical_saves_share_one_saved_at_and_one_reference(
    client, db, make_event, make_user, token_for
):
    user = make_user()
    event = make_event()
    headers = auth(token_for(user))
    path = f"/api/v1/me/saved-events/{event.id}"
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _index: _parallel_request("put", path, headers, barrier), range(2)
            )
        )

    assert [response.status_code for response in responses] == [200, 200]
    states = [response.json() for response in responses]
    assert all(state["saved"] is True for state in states)
    assert len({state["saved_at"] for state in states}) == 1
    assert len(client.get("/api/v1/me/saved-events", headers=headers).json()) == 1
    assert _saved_count(db, user.id, event.id) == 1


def test_concurrent_removals_are_idempotent(client, db, make_event, make_user, token_for):
    user = make_user()
    event = make_event()
    headers = auth(token_for(user))
    path = f"/api/v1/me/saved-events/{event.id}"
    assert client.put(path, headers=headers).status_code == 200
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _index: _parallel_request("delete", path, headers, barrier), range(2)
            )
        )

    assert [response.status_code for response in responses] == [200, 200]
    assert all(
        response.json() == {"event_id": event.id, "saved": False, "saved_at": None}
        for response in responses
    )
    assert _saved_count(db, user.id, event.id) == 0


def test_conflicts_use_half_open_utc_intervals_and_only_current_confirmed_public_events(
    client, db, make_event, make_org, make_user, token_for
):
    user = make_user()
    start_utc = (now() + timedelta(days=10)).replace(second=0, microsecond=0)
    end_utc = start_utc + timedelta(hours=2)
    manila = timezone(timedelta(hours=8), name="Asia/Manila")
    target = make_event(
        starts_at=start_utc.astimezone(manila),
        ends_at=end_utc.astimezone(manila),
    )

    touches_start = make_event(
        starts_at=start_utc - timedelta(hours=1), ends_at=start_utc
    )
    touches_end = make_event(
        starts_at=end_utc, ends_at=end_utc + timedelta(hours=1)
    )
    overlaps_early = make_event(
        starts_at=start_utc + timedelta(minutes=30),
        ends_at=start_utc + timedelta(minutes=55),
    )
    overlaps_same_start = make_event(
        starts_at=start_utc + timedelta(minutes=30),
        ends_at=start_utc + timedelta(minutes=70),
    )
    overlaps_late = make_event(
        starts_at=start_utc + timedelta(hours=1, minutes=20),
        ends_at=start_utc + timedelta(hours=1, minutes=40),
    )
    excluded = [
        make_event(
            starts_at=start_utc + timedelta(minutes=20),
            ends_at=start_utc + timedelta(hours=1),
        )
        for _ in range(5)
    ]
    pending_organization = make_org(accreditation_status="pending")
    unapproved_event = make_event(
        org=pending_organization,
        starts_at=start_utc + timedelta(minutes=25),
        ends_at=start_utc + timedelta(hours=1),
    )

    _register(db, target, user)
    _register(db, touches_start, user)
    _register(db, touches_end, user)
    for event in (overlaps_early, overlaps_same_start, overlaps_late):
        _register(db, event, user)
    for event, status in zip(
        excluded,
        ("pending", "waitlisted", "reconfirmation_required", "cancelled", "rejected"),
    ):
        _register(db, event, user, status=status)
    _register(db, unapproved_event, user)

    tracked_events = [
        target,
        touches_start,
        touches_end,
        overlaps_early,
        overlaps_same_start,
        overlaps_late,
        *excluded,
        unapproved_event,
    ]
    event_ids = [event.id for event in tracked_events]
    capacity_before = {
        event.id: (event.capacity, event.interest_count, event.next_admission)
        for event in tracked_events
    }
    registrations_before = [
        tuple(row)
        for row in db.execute(
            select(Registration.event_id, Registration.status, Registration.admission_order)
            .where(Registration.event_id.in_(event_ids))
            .order_by(Registration.event_id, Registration.admission_order)
        )
    ]

    response = client.get(
        f"/api/v1/me/event-conflicts/{target.id}", headers=auth(token_for(user))
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"event_id", "conflicts"}
    assert body["event_id"] == target.id
    expected = sorted(
        (overlaps_early, overlaps_same_start, overlaps_late),
        key=lambda event: (event.starts_at.astimezone(timezone.utc), event.id),
    )
    conflicts = body["conflicts"]
    assert [item["event_id"] for item in conflicts] == [event.id for event in expected]
    assert all(
        set(item) == {"event_id", "title", "organization_name", "starts_at", "ends_at"}
        for item in conflicts
    )
    assert datetime.fromisoformat(conflicts[0]["starts_at"]).astimezone(timezone.utc) == (
        start_utc + timedelta(minutes=30)
    )
    assert user.email not in response.text
    assert user.nickname not in response.text

    db.expire_all()
    for event_id in event_ids:
        event = db.get(Event, event_id)
        assert (event.capacity, event.interest_count, event.next_admission) == capacity_before[
            event_id
        ]
    registrations_after = [
        tuple(row)
        for row in db.execute(
            select(Registration.event_id, Registration.status, Registration.admission_order)
            .where(Registration.event_id.in_(event_ids))
            .order_by(Registration.event_id, Registration.admission_order)
        )
    ]
    assert registrations_after == registrations_before


def test_conflicts_ignore_other_events_that_have_ended(
    client, db, make_event, make_user, token_for
):
    user = make_user()
    target_start = now() - timedelta(hours=1)
    target_end = now() + timedelta(hours=3)
    target = make_event(starts_at=target_start, ends_at=target_end)
    ended_event = make_event(
        starts_at=target_start - timedelta(hours=1),
        ends_at=now() - timedelta(minutes=5),
    )
    _register(db, ended_event, user)

    response = client.get(
        f"/api/v1/me/event-conflicts/{target.id}", headers=auth(token_for(user))
    )

    assert response.status_code == 200
    assert response.json() == {"event_id": target.id, "conflicts": []}


def test_conflicts_are_empty_for_an_ended_target_even_with_current_overlap(
    client, db, make_event, make_user, token_for
):
    user = make_user()
    instant = now()
    target = make_event(
        starts_at=instant - timedelta(hours=3),
        ends_at=instant - timedelta(minutes=5),
    )
    overlapping_current_event = make_event(
        starts_at=instant - timedelta(hours=1),
        ends_at=instant + timedelta(hours=1),
    )
    _register(db, overlapping_current_event, user)

    response = client.get(
        f"/api/v1/me/event-conflicts/{target.id}", headers=auth(token_for(user))
    )

    assert response.status_code == 200
    assert response.json() == {"event_id": target.id, "conflicts": []}


def test_planning_routes_validate_event_ids_as_uuids(client, make_user, token_for):
    headers = auth(token_for(make_user()))
    invalid_id = "not-a-uuid"
    responses = [
        client.get(f"/api/v1/me/saved-events/{invalid_id}", headers=headers),
        client.put(f"/api/v1/me/saved-events/{invalid_id}", headers=headers),
        client.delete(f"/api/v1/me/saved-events/{invalid_id}", headers=headers),
        client.get(f"/api/v1/me/event-conflicts/{invalid_id}", headers=headers),
    ]
    assert all(response.status_code == 422 for response in responses)
