from collections import Counter
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from app.db.models import now
from app.domains.events.models import Event
from app.domains.organizations.models import Organization
from app.main import create_app

from .conftest import (
    auth,
    decide_featured,
    decisions_for_request,
    iso,
    owned_event,
    request_featured,
    rows_for_event,
)


def active_ids(db, events, at=None):
    from app.domains.featured.service import active_featured_event_ids

    return active_featured_event_ids(db, events, at=at)


def test_material_event_change_pauses_and_allows_fresh_platform_review(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    admin = make_user(platform_admin=True)
    event = owned_event(make_event, make_org, owner)
    request = request_featured(client, event.id, owner, token_for)
    request_id = request.json()["id"]
    retry_while_pending = request_featured(client, event.id, owner, token_for)
    assert retry_while_pending.json()["id"] == request_id

    approved = decide_featured(
        client,
        request_id,
        admin,
        token_for,
        "approve",
        1,
        ends_at=now() + timedelta(hours=1),
    )
    assert approved.status_code == 200
    retry_while_approved = request_featured(client, event.id, owner, token_for)
    assert retry_while_approved.json()["id"] == request_id
    assert retry_while_approved.json()["status"] == "approved"

    changed = client.post(
        f"/api/v1/events/{event.id}/changes",
        headers=auth(token_for(owner)),
        json={
            "capacity": event.capacity + 1,
            "reconfirm_deadline": iso(now() + timedelta(days=1)),
        },
    )
    paused_rows = rows_for_event(db, event.id)
    assert changed.status_code == 200
    assert paused_rows[0]["status"] == "paused"
    assert paused_rows[0]["version"] > approved.json()["version"]
    assert not active_ids(db, [db.get(Event, event.id)], at=now())
    retry_while_paused = request_featured(client, event.id, owner, token_for)
    assert retry_while_paused.json()["id"] == request_id
    assert retry_while_paused.json()["status"] == "paused"
    assert len(rows_for_event(db, event.id)) == 1

    resumed = decide_featured(
        client,
        request_id,
        admin,
        token_for,
        "approve",
        paused_rows[0]["version"],
        starts_at=now() + timedelta(minutes=30),
        ends_at=now() + timedelta(hours=2),
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "approved"
    assert Counter(row["action"] for row in decisions_for_request(db, request_id)) == {
        "requested": 1,
        "approved": 2,
        "paused": 1,
    }
    pause_audit = [
        row for row in decisions_for_request(db, request_id) if row["action"] == "paused"
    ]
    assert pause_audit[0]["actor_id"] == owner.id


def test_noop_and_nonmaterial_changes_keep_the_approved_snapshot(
    client, db, make_event, make_org, make_user, token_for
):
    from app.domains.featured.service import pause_for_material_change

    owner = make_user()
    admin = make_user(platform_admin=True)
    event = owned_event(make_event, make_org, owner)
    request = request_featured(client, event.id, owner, token_for)
    request_id = request.json()["id"]
    approved = decide_featured(
        client,
        request_id,
        admin,
        token_for,
        "approve",
        1,
        ends_at=now() + timedelta(hours=1),
    )
    assert approved.status_code == 200

    current = db.get(Event, event.id)
    pause_for_material_change(db, current, owner.id)
    db.commit()
    current.title = "Updated nonmaterial title"
    current.summary = "Updated nonmaterial summary"
    db.commit()
    pause_for_material_change(db, current, owner.id)
    db.commit()

    assert rows_for_event(db, event.id)[0]["status"] == "approved"
    assert Counter(row["action"] for row in decisions_for_request(db, request_id)) == {
        "requested": 1,
        "approved": 1,
    }
    assert active_ids(db, [current], at=now()) == {event.id}


@pytest.mark.parametrize("changed_field", ["capacity", "status", "organization"])
def test_featured_lookup_fails_closed_on_fingerprint_or_eligibility_change(
    client, db, make_event, make_org, make_user, token_for, changed_field
):
    owner = make_user()
    admin = make_user(platform_admin=True)
    event = owned_event(make_event, make_org, owner)
    request = request_featured(client, event.id, owner, token_for)
    request_id = request.json()["id"]
    approved = decide_featured(
        client,
        request_id,
        admin,
        token_for,
        "approve",
        1,
        ends_at=now() + timedelta(hours=1),
    )
    assert approved.status_code == 200

    if changed_field == "capacity":
        event.capacity += 1
        db.commit()
    elif changed_field == "status":
        event.status = "draft"
        db.commit()
    else:
        organization = db.get(Organization, event.org_id)
        organization.accreditation_status = "pending"
        db.commit()

    assert active_ids(db, [event], at=now()) == set()
    assert rows_for_event(db, event.id)[0]["status"] == "approved"

def test_expiry_is_effective_on_reads_and_does_not_persist_or_add_a_decision(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    event = owned_event(make_event, make_org, owner)
    request = request_featured(client, event.id, owner, token_for)
    request_id = request.json()["id"]

    event.starts_at = now() - timedelta(minutes=1)
    event.ends_at = event.starts_at + timedelta(hours=2)
    db.commit()
    history = client.get(
        f"/api/v1/organizations/{event.org_id}/featured-requests",
        headers=auth(token_for(owner)),
    )

    assert history.status_code == 200
    assert next(row for row in history.json() if row["id"] == request_id)["status"] == "expired"
    assert rows_for_event(db, event.id)[0]["status"] == "pending"
    assert [row["action"] for row in decisions_for_request(db, request_id)] == ["requested"]


def test_approved_placement_persists_across_app_recreation_and_expires_half_open(
    db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    admin = make_user(platform_admin=True)
    event = owned_event(make_event, make_org, owner)
    path = f"/api/v1/events/{event.id}/featured-requests"
    with TestClient(create_app()) as first_app:
        request = first_app.post(path, headers=auth(token_for(owner)))
        request_id = request.json()["id"]
        end = now() + timedelta(hours=1)
        approved = decide_featured(
            first_app,
            request_id,
            admin,
            token_for,
            "approve",
            1,
            ends_at=end,
        )
    assert request.status_code in {200, 201}
    assert approved.status_code == 200
    start = datetime.fromisoformat(approved.json()["starts_at"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(approved.json()["ends_at"].replace("Z", "+00:00"))

    with TestClient(create_app()) as recreated_app:
        public_event = recreated_app.get(f"/api/v1/events/{event.id}")
        history = recreated_app.get(
            f"/api/v1/organizations/{event.org_id}/featured-requests",
            headers=auth(token_for(owner)),
        )
    assert public_event.status_code == history.status_code == 200
    assert public_event.json()["is_featured"] is True
    assert any(row["id"] == request_id and row["status"] == "approved" for row in history.json())

    stored_event = db.get(Event, event.id)
    assert active_ids(db, [stored_event], at=start) == {event.id}
    assert active_ids(db, [stored_event], at=end) == set()
    assert rows_for_event(db, event.id)[0]["status"] == "approved"
