from datetime import timedelta

import pytest
from sqlalchemy import text

from app.db.models import now, uid
from app.domains.organizations.models import OrgMembership

from .conftest import (
    auth,
    decide_featured,
    decisions_for_request,
    owned_event,
    request_featured,
    rows_for_event,
)


def test_only_active_organization_owners_and_admins_can_request(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    admin = make_user()
    moderator = make_user()
    member = make_user()
    inactive_admin = make_user()
    db.add_all(
        [
            OrgMembership(id=uid(), org_id=organization.id, user_id=admin.id, role="admin", active=True),
            OrgMembership(id=uid(), org_id=organization.id, user_id=moderator.id, role="moderator", active=True),
            OrgMembership(id=uid(), org_id=organization.id, user_id=member.id, role="member", active=True),
            OrgMembership(id=uid(), org_id=organization.id, user_id=inactive_admin.id, role="admin", active=False),
        ]
    )
    db.commit()
    owner_event = make_event(org=organization)
    admin_event = make_event(org=organization)

    owner_result = request_featured(client, owner_event.id, owner, token_for)
    admin_result = request_featured(client, admin_event.id, admin, token_for)
    denied = [
        request_featured(client, owner_event.id, moderator, token_for),
        request_featured(client, owner_event.id, member, token_for),
        request_featured(client, owner_event.id, inactive_admin, token_for),
    ]

    assert owner_result.status_code in {200, 201}
    assert admin_result.status_code in {200, 201}
    assert all(response.status_code == 403 for response in denied)
    assert rows_for_event(db, owner_event.id)[0]["requested_by"] == owner.id
    assert rows_for_event(db, admin_event.id)[0]["requested_by"] == admin.id


def test_request_requires_published_future_event_and_approved_organization(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    approved = make_org(owner=owner)
    pending = make_org(owner=owner, accreditation_status="pending")
    draft = make_event(org=approved, status="draft", published_at=None)
    started = make_event(
        org=approved,
        starts_at=now() - timedelta(hours=2),
        ends_at=now() - timedelta(hours=1),
    )
    pending_org_event = make_event(org=pending)

    results = [
        request_featured(client, event.id, owner, token_for)
        for event in (draft, started, pending_org_event)
    ]

    assert all(response.status_code in {403, 404, 409} for response in results)
    assert all(not rows_for_event(db, event.id) for event in (draft, started, pending_org_event))


def test_request_and_history_are_isolated_to_the_organization_manager(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    other_owner = make_user()
    member = make_user()
    organization = make_org(owner=owner)
    other_organization = make_org(owner=other_owner)
    event = make_event(org=organization)
    other_event = make_event(org=other_organization)
    db.add(OrgMembership(id=uid(), org_id=organization.id, user_id=member.id, role="member", active=True))
    db.commit()
    created = request_featured(client, event.id, owner, token_for)
    assert created.status_code in {200, 201}

    own_history = client.get(
        f"/api/v1/organizations/{organization.id}/featured-requests",
        headers=auth(token_for(owner)),
    )
    member_history = client.get(
        f"/api/v1/organizations/{organization.id}/featured-requests",
        headers=auth(token_for(member)),
    )
    cross_org_history = client.get(
        f"/api/v1/organizations/{other_organization.id}/featured-requests",
        headers=auth(token_for(owner)),
    )
    cross_org_request = request_featured(client, other_event.id, owner, token_for)

    assert own_history.status_code == 200
    assert [row["id"] for row in own_history.json()] == [created.json()["id"]]
    assert member_history.status_code == 403
    assert cross_org_history.status_code == 403
    assert cross_org_request.status_code == 403
    assert rows_for_event(db, other_event.id) == []


def test_platform_review_requires_database_admin_authority(
    client, make_event, make_org, make_user, token_for
):
    owner = make_user()
    event = owned_event(make_event, make_org, owner)
    request = request_featured(client, event.id, owner, token_for)
    request_id = request.json()["id"]
    ordinary_user = make_user()
    real_admin = make_user(platform_admin=True)
    forged_headers = auth(token_for(ordinary_user, platform_admin=True))

    denied_list = client.get("/api/v1/platform-admin/featured-requests", headers=forged_headers)
    denied_decision = client.post(
        f"/api/v1/platform-admin/featured-requests/{request_id}/decisions",
        headers=forged_headers,
        json={"action": "reject", "version": 1},
    )
    owner_decision = decide_featured(
        client, request_id, owner, token_for, "reject", 1
    )
    allowed_list = client.get(
        "/api/v1/platform-admin/featured-requests", headers=auth(token_for(real_admin))
    )

    assert denied_list.status_code == 403
    assert denied_decision.status_code == 403
    assert owner_decision.status_code == 403
    assert allowed_list.status_code == 200
    assert any(row["id"] == request_id for row in allowed_list.json())


def test_pending_retry_returns_same_request_and_does_not_duplicate_audit(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    event = owned_event(make_event, make_org, owner)

    first = request_featured(client, event.id, owner, token_for)
    retry = request_featured(client, event.id, owner, token_for)

    assert first.status_code in {200, 201}
    assert retry.status_code in {200, 201}
    assert set(first.json()) == {
        "id",
        "event_id",
        "requested_by",
        "requested_at",
        "status",
        "version",
        "starts_at",
        "ends_at",
        "event",
        "decisions",
    }
    assert retry.json()["id"] == first.json()["id"]
    assert retry.json()["requested_at"] == first.json()["requested_at"]
    assert first.json()["event"]["is_featured"] is False
    assert set(first.json()["decisions"][0]) == {
        "id",
        "actor_id",
        "action",
        "created_at",
        "starts_at",
        "ends_at",
    }
    assert len(rows_for_event(db, event.id)) == 1
    audit = decisions_for_request(db, first.json()["id"])
    assert [row["action"] for row in audit] == ["requested"]
    assert audit[0]["actor_id"] == owner.id


def test_decisions_are_strict_server_audited_and_version_checked(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    admin = make_user(platform_admin=True)
    event = owned_event(make_event, make_org, owner)
    request = request_featured(client, event.id, owner, token_for)
    request_id = request.json()["id"]

    forged_audit = decide_featured(
        client,
        request_id,
        admin,
        token_for,
        "reject",
        1,
        extra={"actor_id": owner.id, "decided_at": "2000-01-01T00:00:00Z"},
    )
    stale = decide_featured(client, request_id, admin, token_for, "reject", 2)
    accepted = decide_featured(client, request_id, admin, token_for, "reject", 1)

    assert forged_audit.status_code == 422
    assert stale.status_code == 409
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "rejected"
    audit = decisions_for_request(db, request_id)
    assert {row["action"] for row in audit} == {"requested", "rejected"}
    assert len(audit) == 2
    rejected = next(row for row in audit if row["action"] == "rejected")
    assert rejected["actor_id"] == admin.id
    assert rejected["created_at"].year > 2020


@pytest.mark.parametrize("action", ["reject", "revoke"])
def test_terminal_requests_remain_historical_and_can_be_requested_again(
    client, db, make_event, make_org, make_user, token_for, action
):
    owner = make_user()
    admin = make_user(platform_admin=True)
    event = owned_event(make_event, make_org, owner)
    first = request_featured(client, event.id, owner, token_for)
    request_id = first.json()["id"]
    version = 1
    if action == "revoke":
        approved = decide_featured(
            client,
            request_id,
            admin,
            token_for,
            "approve",
            version,
            ends_at=event.starts_at - timedelta(hours=1),
        )
        assert approved.status_code == 200
        version = approved.json()["version"]

    terminal = decide_featured(client, request_id, admin, token_for, action, version)
    again = request_featured(client, event.id, owner, token_for)

    assert terminal.status_code == 200
    assert terminal.json()["status"] == ("rejected" if action == "reject" else "revoked")
    assert again.status_code in {200, 201}
    assert again.json()["id"] != request_id
    assert len(rows_for_event(db, event.id)) == 2


def test_platform_history_is_bounded_to_one_hundred_rows(
    client, db, make_org, make_user, token_for
):
    from app.domains.events.models import Event

    owner = make_user()
    admin = make_user(platform_admin=True)
    organization = make_org(owner=owner)
    event_start = now() + timedelta(days=2)
    events = [
        Event(
            id=uid(),
            org_id=organization.id,
            created_by=owner.id,
            title=f"Featured queue event {index}",
            summary="",
            description="A bounded history fixture.",
            starts_at=event_start,
            ends_at=event_start + timedelta(hours=1),
            venue_name="PLM courtyard",
            venue_address="Intramuros, Manila",
            capacity=2,
            banner_key="heritage",
            cost_label="Free",
            status="published",
            registration_mode="instant",
            event_type="scheduled",
            published_at=now(),
            next_admission=0,
            interest_count=0,
        )
        for index in range(101)
    ]
    db.add_all(events)
    db.flush()
    db.execute(
        text(
            "INSERT INTO featured_requests "
            "(id,event_id,requested_by,requested_at,status,version,snapshot_hash) "
            "VALUES (:id,:event_id,:requested_by,:requested_at,'pending',1,:snapshot_hash)"
        ),
        [
            {
                "id": uid(),
                "event_id": event.id,
                "requested_by": owner.id,
                "requested_at": now(),
                "snapshot_hash": "a" * 64,
            }
            for event in events
        ],
    )
    db.commit()

    response = client.get(
        "/api/v1/platform-admin/featured-requests", headers=auth(token_for(admin))
    )

    assert response.status_code == 200
    assert len(response.json()) == 100
