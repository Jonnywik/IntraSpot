from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.db.models import now, uid
from app.domains.memberships.models import MembershipAudit, MembershipOperation
from app.domains.organizations.models import OrgMembership
from app.domains.registrations import service as registration_service
from app.domains.registrations.models import Registration


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def add_membership(db, org, user, role="member", active=True):
    membership = OrgMembership(
        id=uid(), org_id=org.id, user_id=user.id, role=role, active=active,
    )
    db.add(membership)
    db.commit()
    return membership


def test_self_status_is_private_and_available_while_access_is_locked(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    second_owner = make_user()
    second_org = make_org(owner=second_owner)
    locked_user = make_user(email="fictional-locked@example.test", nickname="PRIVATE LOCKED NICKNAME")
    other_user = make_user(nickname="PRIVATE OTHER NICKNAME")
    locked_grant = add_membership(db, org, locked_user)
    inactive_grant = add_membership(db, second_org, locked_user, active=False)
    add_membership(db, org, other_user)

    response = client.get(
        "/api/v1/me/memberships",
        headers=auth(token_for(locked_user)),
    )

    assert response.status_code == 200
    assert len(response.json()) == 2
    item = next(row for row in response.json() if row["id"] == locked_grant.id)
    assert item["id"] == locked_grant.id
    assert item["org_id"] == org.id
    assert item["active"] is True
    assert item["access_ready"] is False
    assert item["joined_at"] is None
    inactive_item = next(row for row in response.json() if row["id"] == inactive_grant.id)
    assert inactive_item["active"] is False and inactive_item["access_ready"] is False
    assert other_user.id not in response.text
    assert other_user.email not in response.text
    assert other_user.nickname not in response.text
    assert locked_user.email not in response.text
    assert locked_user.nickname not in response.text


def test_roster_is_staff_only_generic_and_active_grants_only(
    client, db, make_user, make_org, token_for,
):
    owner = make_user(nickname="PRIVATE OWNER NICKNAME")
    org = make_org(owner=owner)
    member = make_user(email="fictional-roster@example.test", nickname="PRIVATE MEMBER NICKNAME")
    inactive = make_user(nickname="PRIVATE INACTIVE NICKNAME")
    member_grant = add_membership(db, org, member)
    add_membership(db, org, inactive, active=False)
    owner_grant = db.scalar(select(OrgMembership).where(
        OrgMembership.org_id == org.id, OrgMembership.user_id == owner.id,
    ))

    response = client.get(
        f"/api/v1/organizations/{org.id}/members",
        headers=auth(token_for(owner)),
    )

    assert response.status_code == 200
    roster = response.json()
    assert {item["id"] for item in roster} == {owner_grant.id, member_grant.id}
    member_item = next(item for item in roster if item["id"] == member_grant.id)
    assert member_item["label"] == f"Member · {member.id.replace('-', '')[-6:].upper()}"
    assert set(member_item) == {
        "id", "user_id", "label", "role", "eligible", "access_ready", "joined_at",
    }
    assert "PRIVATE OWNER NICKNAME" not in response.text
    assert member.nickname not in response.text
    assert member.email not in response.text
    assert inactive.id not in response.text

    member_response = client.get(
        f"/api/v1/organizations/{org.id}/members",
        headers=auth(token_for(member)),
    )
    assert member_response.status_code == 403
    assert client.get(
        f"/api/v1/organizations/{org.id}/membership-audit",
        headers=auth(token_for(member)),
    ).status_code == 403


def test_ineligible_owner_cannot_open_staff_roster(client, make_user, make_org, token_for):
    owner = make_user(email="fictional-ineligible-owner@example.test")
    org = make_org(owner=owner)

    response = client.get(
        f"/api/v1/organizations/{org.id}/members",
        headers=auth(token_for(owner)),
    )

    assert response.status_code == 403


def test_audit_is_staff_only_and_returns_latest_100(client, db, make_user, make_org, token_for):
    owner = make_user(nickname="PRIVATE AUDIT NICKNAME")
    org = make_org(owner=owner)
    base = now()
    db.add_all([
        MembershipAudit(
            id=uid(), org_id=org.id, actor_id=owner.id, user_id=owner.id,
            action="membership_role_changed", old_role="member", new_role="moderator",
            created_at=base + timedelta(seconds=index),
        )
        for index in range(105)
    ])
    db.commit()

    response = client.get(
        f"/api/v1/organizations/{org.id}/membership-audit",
        headers=auth(token_for(owner)),
    )

    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 100
    assert entries[0]["created_at"].startswith((base + timedelta(seconds=104)).isoformat()[:19])
    assert set(entries[0]) == {
        "id", "actor_id", "user_id", "action", "old_role", "new_role", "created_at",
    }
    assert owner.nickname not in response.text
    assert owner.email not in response.text


def test_role_change_receipt_replays_and_same_key_conflict_is_409(
    client, db, make_user, make_org, token_for, monkeypatch,
):
    owner = make_user()
    org = make_org(owner=owner)
    member = make_user()
    grant = add_membership(db, org, member)
    key = str(uuid4())
    url = f"/api/v1/organizations/{org.id}/members/{grant.id}/role"
    headers = auth(token_for(owner))
    payload = {"client_key": key, "role": "moderator"}
    attendance_calls = []
    monkeypatch.setattr(
        registration_service,
        "end_membership_attendance",
        lambda *args: attendance_calls.append(args),
    )

    first = client.patch(url, json=payload, headers=headers)
    replay = client.patch(url, json=payload, headers=headers)
    conflict = client.patch(url, json={"client_key": key, "role": "member"}, headers=headers)

    assert first.status_code == 200
    assert first.json()["role"] == "moderator"
    assert first.json()["active"] is True
    assert first.json()["cancelled_registrations"] == first.json()["chat_revoked"] == 0
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert attendance_calls == []
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "membership_operation_key_conflict"
    assert db.scalar(select(OrgMembership.role).where(OrgMembership.id == grant.id)) == "moderator"
    assert db.scalar(select(func.count(MembershipOperation.id)).where(
        MembershipOperation.actor_id == owner.id,
        MembershipOperation.client_key == key,
    )) == 1
    audit = db.scalar(select(MembershipAudit).where(
        MembershipAudit.org_id == org.id,
        MembershipAudit.user_id == member.id,
        MembershipAudit.action == "membership_role_changed",
    ))
    assert audit.actor_id == owner.id
    assert audit.old_role == "member" and audit.new_role == "moderator"
    assert audit.created_at is not None


def test_role_hierarchy_protects_owner_and_requires_eligibility_for_staff(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    admin = make_user()
    moderator = make_user()
    ineligible = make_user(email="fictional-ineligible@example.test")
    admin_grant = add_membership(db, org, admin, role="admin")
    moderator_grant = add_membership(db, org, moderator, role="moderator")
    ineligible_grant = add_membership(db, org, ineligible)
    owner_grant = db.scalar(select(OrgMembership).where(
        OrgMembership.org_id == org.id, OrgMembership.user_id == owner.id,
    ))
    owner_headers = auth(token_for(owner))
    admin_headers = auth(token_for(admin))
    moderator_headers = auth(token_for(moderator))

    admin_promotion = client.patch(
        f"/api/v1/organizations/{org.id}/members/{moderator_grant.id}/role",
        json={"client_key": str(uuid4()), "role": "admin"},
        headers=admin_headers,
    )
    admin_changes_admin = client.patch(
        f"/api/v1/organizations/{org.id}/members/{admin_grant.id}/role",
        json={"client_key": str(uuid4()), "role": "member"},
        headers=admin_headers,
    )
    owner_changes_admin = client.patch(
        f"/api/v1/organizations/{org.id}/members/{admin_grant.id}/role",
        json={"client_key": str(uuid4()), "role": "member"},
        headers=owner_headers,
    )
    ineligible_promotion = client.patch(
        f"/api/v1/organizations/{org.id}/members/{ineligible_grant.id}/role",
        json={"client_key": str(uuid4()), "role": "moderator"},
        headers=owner_headers,
    )
    owner_change = client.patch(
        f"/api/v1/organizations/{org.id}/members/{owner_grant.id}/role",
        json={"client_key": str(uuid4()), "role": "member"},
        headers=owner_headers,
    )
    moderator_change = client.patch(
        f"/api/v1/organizations/{org.id}/members/{ineligible_grant.id}/role",
        json={"client_key": str(uuid4()), "role": "member"},
        headers=moderator_headers,
    )

    assert admin_promotion.status_code == 403
    assert admin_changes_admin.status_code == 403
    assert owner_changes_admin.status_code == 200
    assert owner_changes_admin.json()["role"] == "member"
    assert ineligible_promotion.status_code == 403
    assert owner_change.status_code == 409
    assert moderator_change.status_code == 403


def test_admin_can_change_moderator_and_member_roles(client, db, make_user, make_org, token_for):
    owner = make_user()
    org = make_org(owner=owner)
    admin = make_user()
    moderator = make_user()
    admin_grant = add_membership(db, org, admin, role="admin")
    moderator_grant = add_membership(db, org, moderator, role="moderator")

    response = client.patch(
        f"/api/v1/organizations/{org.id}/members/{moderator_grant.id}/role",
        json={"client_key": str(uuid4()), "role": "member"},
        headers=auth(token_for(admin)),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "member"
    assert response.json()["membership_id"] == moderator_grant.id
    assert admin_grant.role == "admin"


def test_removal_hierarchy_and_attendance_seam_are_atomic(
    client, db, make_user, make_org, token_for, monkeypatch,
):
    owner = make_user()
    org = make_org(owner=owner)
    admin = make_user()
    moderator = make_user()
    admin_grant = add_membership(db, org, admin, role="admin")
    moderator_grant = add_membership(db, org, moderator, role="moderator")
    calls = []

    def end_attendance(request_db, org_id, user_id):
        assert request_db.scalar(select(OrgMembership.active).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
        )) is False
        calls.append((org_id, user_id))
        return 3, 2

    monkeypatch.setattr(registration_service, "end_membership_attendance", end_attendance)
    admin_headers = auth(token_for(admin))
    owner_headers = auth(token_for(owner))
    admin_url = f"/api/v1/organizations/{org.id}/members/{admin_grant.id}/remove"
    moderator_url = f"/api/v1/organizations/{org.id}/members/{moderator_grant.id}/remove"
    moderator_key = str(uuid4())
    moderator_payload = {"client_key": moderator_key}

    denied_admin_remove = client.post(
        admin_url,
        json={"client_key": str(uuid4())},
        headers=admin_headers,
    )
    removed_moderator = client.post(
        moderator_url,
        json=moderator_payload,
        headers=admin_headers,
    )
    replayed_moderator = client.post(
        moderator_url,
        json=moderator_payload,
        headers=admin_headers,
    )
    removed_admin = client.post(
        admin_url,
        json={"client_key": str(uuid4())},
        headers=owner_headers,
    )

    assert denied_admin_remove.status_code == 403
    assert removed_moderator.status_code == 200
    assert removed_moderator.json()["active"] is False
    assert removed_moderator.json()["cancelled_registrations"] == 3
    assert removed_moderator.json()["chat_revoked"] == 2
    assert replayed_moderator.status_code == 200
    assert replayed_moderator.json() == removed_moderator.json()
    assert removed_admin.status_code == 200
    assert calls == [(org.id, moderator.id), (org.id, admin.id)]
    audits = list(db.scalars(select(MembershipAudit).where(
        MembershipAudit.org_id == org.id,
        MembershipAudit.action == "membership_removed",
    )))
    assert {audit.actor_id for audit in audits} == {owner.id, admin.id}
    assert all(audit.created_at is not None for audit in audits)


def test_leave_replay_does_not_cancel_public_registration_created_after_departure(
    client, db, make_user, make_org, make_event, token_for, monkeypatch,
):
    owner = make_user()
    org = make_org(owner=owner)
    member = make_user()
    grant = add_membership(db, org, member)
    event = make_event(org=org, capacity=3)
    calls = []

    def end_attendance(request_db, org_id, user_id):
        assert request_db.scalar(select(OrgMembership.active).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
        )) is False
        calls.append((org_id, user_id))
        return 2, 1

    monkeypatch.setattr(registration_service, "end_membership_attendance", end_attendance)
    headers = auth(token_for(member))
    leave_url = f"/api/v1/organizations/{org.id}/membership/leave"
    first_key = str(uuid4())
    first_payload = {"client_key": first_key}

    first = client.post(leave_url, json=first_payload, headers=headers)
    registration = client.post(
        f"/api/v1/events/{event.id}/registrations",
        headers=headers | {"Idempotency-Key": str(uuid4())},
    )
    replay = client.post(leave_url, json=first_payload, headers=headers)
    later_leave = client.post(leave_url, json={"client_key": str(uuid4())}, headers=headers)

    assert first.status_code == 200
    assert first.json()["active"] is False
    assert first.json()["cancelled_registrations"] == 2
    assert first.json()["chat_revoked"] == 1
    assert registration.status_code == 201
    assert replay.status_code == 200 and replay.json() == first.json()
    assert later_leave.status_code == 200
    assert later_leave.json()["cancelled_registrations"] == 0
    assert later_leave.json()["chat_revoked"] == 0
    assert calls == [(org.id, member.id)]
    assert db.scalar(select(Registration.status).where(
        Registration.event_id == event.id,
        Registration.user_id == member.id,
    )) == "confirmed"
    audit = db.scalar(select(MembershipAudit).where(
        MembershipAudit.org_id == org.id,
        MembershipAudit.user_id == member.id,
        MembershipAudit.action == "membership_left",
    ))
    assert audit.actor_id == member.id and audit.created_at is not None
    assert db.scalar(select(func.count(MembershipOperation.id)).where(
        MembershipOperation.actor_id == member.id,
    )) == 2
    assert grant.id == first.json()["membership_id"]


def test_ineligible_member_can_leave_an_approved_organization(
    client, db, make_user, make_org, token_for, monkeypatch,
):
    owner = make_user()
    org = make_org(owner=owner)
    locked_member = make_user(email="fictional-locked-leaver@example.test")
    grant = add_membership(db, org, locked_member)
    calls = []

    def end_attendance(request_db, org_id, user_id):
        assert request_db.scalar(select(OrgMembership.active).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
        )) is False
        calls.append((org_id, user_id))
        return 0, 0

    monkeypatch.setattr(registration_service, "end_membership_attendance", end_attendance)
    response = client.post(
        f"/api/v1/organizations/{org.id}/membership/leave",
        json={"client_key": str(uuid4())},
        headers=auth(token_for(locked_member)),
    )

    assert response.status_code == 200
    assert response.json()["membership_id"] == grant.id
    assert response.json()["active"] is False
    assert calls == [(org.id, locked_member.id)]


def test_role_target_in_another_organization_is_not_found(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    other_owner = make_user()
    other_org = make_org(owner=other_owner)
    target = make_user()
    grant = add_membership(db, other_org, target)

    response = client.patch(
        f"/api/v1/organizations/{org.id}/members/{grant.id}/role",
        json={"client_key": str(uuid4()), "role": "moderator"},
        headers=auth(token_for(owner)),
    )

    assert response.status_code == 404
