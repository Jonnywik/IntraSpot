from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.models import now
from app.main import create_app

from .conftest import auth, decide_featured, owned_event, request_featured, rows_for_event


def test_approval_requires_an_aware_valid_window_ending_by_event_start(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    admin = make_user(platform_admin=True)
    event = owned_event(make_event, make_org, owner)
    request = request_featured(client, event.id, owner, token_for)
    request_id = request.json()["id"]
    valid_start = now() + timedelta(minutes=30)
    valid_end = valid_start + timedelta(hours=1)

    invalid = [
        decide_featured(
            client,
            request_id,
            admin,
            token_for,
            "approve",
            1,
            starts_at=valid_start.replace(tzinfo=None).isoformat(),
            ends_at=valid_end,
        ),
        decide_featured(
            client,
            request_id,
            admin,
            token_for,
            "approve",
            1,
            starts_at=now() - timedelta(minutes=1),
            ends_at=valid_end,
        ),
        decide_featured(
            client,
            request_id,
            admin,
            token_for,
            "approve",
            1,
            starts_at=valid_start,
            ends_at=valid_start,
        ),
        decide_featured(
            client,
            request_id,
            admin,
            token_for,
            "approve",
            1,
            starts_at=valid_start,
            ends_at=event.starts_at + timedelta(seconds=1),
        ),
        decide_featured(
            client,
            request_id,
            admin,
            token_for,
            "approve",
            1,
            starts_at=valid_start,
        ),
    ]

    assert all(response.status_code == 422 for response in invalid)
    assert rows_for_event(db, event.id)[0]["status"] == "pending"


@pytest.mark.parametrize("starts_at", ["omit", None])
def test_omitted_or_null_approval_start_defaults_to_now(
    client, make_event, make_org, make_user, token_for, starts_at
):
    owner = make_user()
    admin = make_user(platform_admin=True)
    event = owned_event(make_event, make_org, owner)
    request = request_featured(client, event.id, owner, token_for)
    before = now()
    response = decide_featured(
        client,
        request.json()["id"],
        admin,
        token_for,
        "approve",
        1,
        starts_at=starts_at,
        ends_at=before + timedelta(hours=2),
    )
    after = now()

    assert response.status_code == 200
    saved_start = datetime.fromisoformat(
        response.json()["starts_at"].replace("Z", "+00:00")
    )
    assert before - timedelta(seconds=2) <= saved_start <= after + timedelta(seconds=2)


def test_windows_are_half_open_and_may_be_adjacent(client, make_event, make_org, make_user, token_for):
    owner = make_user()
    admin = make_user(platform_admin=True)
    organization = make_org(owner=owner)
    first_event, second_event = make_event(org=organization), make_event(org=organization)
    first_request = request_featured(client, first_event.id, owner, token_for)
    second_request = request_featured(client, second_event.id, owner, token_for)
    start = now() + timedelta(minutes=30)
    boundary = start + timedelta(hours=1)

    first = decide_featured(
        client,
        first_request.json()["id"],
        admin,
        token_for,
        "approve",
        1,
        starts_at=start,
        ends_at=boundary,
    )
    adjacent = decide_featured(
        client,
        second_request.json()["id"],
        admin,
        token_for,
        "approve",
        1,
        starts_at=boundary,
        ends_at=boundary + timedelta(hours=1),
    )

    assert first.status_code == adjacent.status_code == 200
    assert first.json()["status"] == adjacent.json()["status"] == "approved"


def test_overlapping_windows_conflict_and_nonapproval_rejects_schedule_fields(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    admin = make_user(platform_admin=True)
    organization = make_org(owner=owner)
    events = [make_event(org=organization) for _ in range(3)]
    requests = [request_featured(client, event.id, owner, token_for).json() for event in events]
    start = now() + timedelta(minutes=30)
    end = start + timedelta(hours=1)

    approved = decide_featured(
        client,
        requests[0]["id"],
        admin,
        token_for,
        "approve",
        1,
        starts_at=start,
        ends_at=end,
    )
    overlap = decide_featured(
        client,
        requests[1]["id"],
        admin,
        token_for,
        "approve",
        1,
        starts_at=start + timedelta(minutes=15),
        ends_at=end + timedelta(minutes=15),
    )
    scheduled_rejection = decide_featured(
        client,
        requests[2]["id"],
        admin,
        token_for,
        "reject",
        1,
        ends_at=None,
    )

    assert approved.status_code == 200
    assert overlap.status_code == 409
    assert scheduled_rejection.status_code == 422
    assert rows_for_event(db, events[1].id)[0]["status"] == "pending"
    assert rows_for_event(db, events[2].id)[0]["status"] == "pending"


def test_concurrent_global_approvals_of_overlapping_windows_have_one_winner(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    admins = [make_user(platform_admin=True), make_user(platform_admin=True)]
    organization = make_org(owner=owner)
    events = [make_event(org=organization), make_event(org=organization)]
    request_ids = [request_featured(client, event.id, owner, token_for).json()["id"] for event in events]
    start = now() + timedelta(minutes=30)
    end = start + timedelta(hours=1)
    barrier = Barrier(2)

    def approve(index):
        barrier.wait(timeout=10)
        with TestClient(create_app()) as client:
            return decide_featured(
                client,
                request_ids[index],
                admins[index],
                token_for,
                "approve",
                1,
                starts_at=start,
                ends_at=end,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(approve, range(2)))

    assert sorted(response.status_code for response in responses) == [200, 409]
    db.expire_all()
    statuses = [
        db.scalar(
            text("SELECT status FROM featured_requests WHERE id = :request_id"),
            {"request_id": request_id},
        )
        for request_id in request_ids
    ]
    assert statuses.count("approved") == 1
    assert statuses.count("pending") == 1


def test_concurrent_same_event_requests_create_one_pending_row(
    db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    event = owned_event(make_event, make_org, owner)
    barrier = Barrier(2)

    def request_once():
        barrier.wait(timeout=10)
        with TestClient(create_app()) as client:
            return request_featured(client, event.id, owner, token_for)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _index: request_once(), range(2)))

    assert all(response.status_code in {200, 201} for response in responses)
    assert len({response.json()["id"] for response in responses}) == 1
    requests = rows_for_event(db, event.id)
    assert len(requests) == 1
    assert requests[0]["status"] == "pending"
