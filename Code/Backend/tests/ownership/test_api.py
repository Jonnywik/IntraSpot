from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select
import pytest

from app.db.models import now, uid
from app.domains.memberships.models import MembershipAudit
from app.domains.organizations.models import OrgMembership, Organization
from app.domains.ownership.models import OwnershipTransfer, OwnershipTransferAudit
from app.domains.ownership import service as ownership_service
from app.notifications import Notification


def auth(user, token_for):
    return {"Authorization": f"Bearer {token_for(user)}"}


def add_membership(db, org, user, role="admin", active=True):
    membership = OrgMembership(
        id=uid(), org_id=org.id, user_id=user.id, role=role, active=active,
    )
    db.add(membership)
    db.commit()
    return membership


def create_offer(client, org, owner, nominee, token_for, *, client_key=None):
    return client.post(
        f"/api/v1/organizations/{org.id}/ownership-transfers",
        json={
            "nominee_id": nominee.id,
            "client_key": str(client_key or uuid4()),
        },
        headers=auth(owner, token_for),
    )


def decision(client, org, transfer_id, actor, token_for, action, version=1):
    return client.post(
        f"/api/v1/organizations/{org.id}/ownership-transfers/{transfer_id}/decision",
        json={"action": action, "version": version},
        headers=auth(actor, token_for),
    )


EXPECTED_TRANSFER_FIELDS = {
    "id", "org_id", "from_user_id", "nominee_id", "status", "version",
    "created_at", "expires_at", "resolved_at", "decided_by",
}


def test_create_accept_and_retry_preserve_memberships_and_emit_atomic_history(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    nominee = make_user()
    other_nominee = make_user()
    org = make_org(owner=owner)
    nominee_membership = add_membership(db, org, nominee, "admin")
    add_membership(db, org, other_nominee, "admin")
    client_key = uuid4()

    first = create_offer(
        client, org, owner, nominee, token_for, client_key=client_key,
    )
    assert first.status_code == 201
    original = first.json()
    assert set(original) == EXPECTED_TRANSFER_FIELDS
    assert original["status"] == "pending" and original["version"] == 1
    assert original["resolved_at"] is None and original["decided_by"] is None
    assert datetime.fromisoformat(original["expires_at"]) - datetime.fromisoformat(
        original["created_at"]
    ) == timedelta(days=7)

    replay = create_offer(
        client, org, owner, nominee, token_for, client_key=client_key,
    )
    conflict = create_offer(
        client, org, owner, other_nominee, token_for, client_key=client_key,
    )
    assert replay.status_code == 201 and replay.json() == original
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ownership_transfer_key_reused"
    assert db.scalar(select(func.count(OwnershipTransferAudit.id))) == 1
    assert db.scalar(select(func.count(Notification.id))) == 1

    accepted = decision(client, org, original["id"], nominee, token_for, "accept")
    accepted_replay = decision(
        client, org, original["id"], nominee, token_for, "accept", version=1,
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["version"] == 2
    assert accepted_replay.status_code == 200
    assert accepted_replay.json() == accepted.json()
    former_owner_retry = create_offer(
        client, org, owner, nominee, token_for, client_key=client_key,
    )
    assert former_owner_retry.status_code == 201
    assert former_owner_retry.json()["id"] == accepted.json()["id"]
    assert former_owner_retry.json()["status"] == "accepted"
    assert former_owner_retry.json()["version"] == 2

    former_owner_membership = db.scalar(
        select(OrgMembership)
        .where(OrgMembership.org_id == org.id, OrgMembership.user_id == owner.id)
        .execution_options(populate_existing=True)
    )
    promoted_membership = db.scalar(
        select(OrgMembership)
        .where(OrgMembership.org_id == org.id, OrgMembership.user_id == nominee.id)
        .execution_options(populate_existing=True)
    )
    assert former_owner_membership.active and former_owner_membership.role == "member"
    assert promoted_membership.active and promoted_membership.role == "owner"
    assert promoted_membership.id == nominee_membership.id
    assert db.scalar(
        select(Organization.created_by)
        .where(Organization.id == org.id)
        .execution_options(populate_existing=True)
    ) == owner.id

    membership_audits = list(db.scalars(select(MembershipAudit).where(
        MembershipAudit.org_id == org.id,
        MembershipAudit.action == "ownership_transferred",
    )))
    assert {(row.user_id, row.old_role, row.new_role) for row in membership_audits} == {
        (owner.id, "owner", "member"),
        (nominee.id, "admin", "owner"),
    }
    assert all(row.actor_id == nominee.id for row in membership_audits)
    assert db.scalar(select(func.count(OwnershipTransferAudit.id))) == 2
    assert db.scalar(select(func.count(OwnershipTransferAudit.id)).where(
        OwnershipTransferAudit.action == "accepted",
    )) == 1

    notices = list(db.scalars(select(Notification).where(Notification.org_id == org.id)))
    assert len(notices) == 3
    assert {(row.user_id, row.kind, row.message) for row in notices} == {
        (nominee.id, "ownership_transfer_requested",
         "You have an organization ownership transfer offer."),
        (owner.id, "ownership_transfer_accepted",
         "Organization ownership was transferred. Review your current role."),
        (nominee.id, "ownership_transfer_accepted",
         "Organization ownership was transferred. Review your current role."),
    }
    assert all(row.event_id is None and row.registration_id is None for row in notices)
    assert all(row.dedupe_key for row in notices)
    assert owner.email not in first.text and nominee.email not in first.text


def test_decline_retry_survives_role_change_but_conflicting_action_does_not(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    nominee = make_user()
    org = make_org(owner=owner)
    membership = add_membership(db, org, nominee, "admin")
    created = create_offer(client, org, owner, nominee, token_for)
    transfer_id = created.json()["id"]

    declined = decision(client, org, transfer_id, nominee, token_for, "decline")
    assert declined.status_code == 200
    assert declined.json()["status"] == "declined"

    changed = client.patch(
        f"/api/v1/organizations/{org.id}/members/{membership.id}/role",
        json={"client_key": str(uuid4()), "role": "member"},
        headers=auth(owner, token_for),
    )
    assert changed.status_code == 200
    retry = decision(client, org, transfer_id, nominee, token_for, "decline")
    conflict = decision(client, org, transfer_id, nominee, token_for, "accept")
    assert retry.status_code == 200 and retry.json() == declined.json()
    assert conflict.status_code == 409
    assert db.scalar(select(func.count(OwnershipTransferAudit.id)).where(
        OwnershipTransferAudit.action == "declined",
    )) == 1
    declined_notices = list(db.scalars(select(Notification).where(
        Notification.kind == "ownership_transfer_declined",
    )))
    assert len(declined_notices) == 1
    assert declined_notices[0].user_id == owner.id
    assert declined_notices[0].message == "An organization ownership transfer offer was declined."


def test_owner_can_revoke_and_terminal_replay_does_not_duplicate_effects(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    nominee = make_user()
    org = make_org(owner=owner)
    add_membership(db, org, nominee, "admin")
    created = create_offer(client, org, owner, nominee, token_for)
    transfer_id = created.json()["id"]

    wrong_actor = decision(client, org, transfer_id, owner, token_for, "accept")
    assert wrong_actor.status_code == 403
    revoked = decision(client, org, transfer_id, owner, token_for, "revoke")
    replay = decision(client, org, transfer_id, owner, token_for, "revoke")
    conflict = decision(client, org, transfer_id, nominee, token_for, "accept")
    assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
    assert replay.status_code == 200 and replay.json() == revoked.json()
    assert conflict.status_code == 409
    assert db.scalar(select(func.count(OwnershipTransferAudit.id)).where(
        OwnershipTransferAudit.action == "revoked",
    )) == 1
    notice = db.scalar(select(Notification).where(
        Notification.kind == "ownership_transfer_revoked",
    ))
    assert notice.user_id == nominee.id
    assert notice.message == "An organization ownership transfer offer was revoked."


def test_read_access_is_limited_to_current_owner_or_named_nominee(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    nominee = make_user()
    second_nominee = make_user()
    member = make_user()
    admin = make_user()
    moderator = make_user()
    outsider = make_user()
    org = make_org(owner=owner)
    add_membership(db, org, nominee, "admin")
    add_membership(db, org, second_nominee, "admin")
    add_membership(db, org, member, "member")
    add_membership(db, org, admin, "admin")
    add_membership(db, org, moderator, "moderator")
    created = create_offer(client, org, owner, nominee, token_for)
    first_id = created.json()["id"]

    # A separate terminal row proves nominee reads are filtered, not merely bounded.
    second = OwnershipTransfer(
        id=uid(), org_id=org.id, from_user_id=owner.id,
        nominee_id=second_nominee.id, client_key=str(uuid4()),
        status="declined", version=2, created_at=now() + timedelta(seconds=1),
        expires_at=now() + timedelta(days=7, seconds=1),
        resolved_at=now() + timedelta(seconds=2), decided_by=second_nominee.id,
    )
    db.add(second)
    db.commit()

    url = f"/api/v1/organizations/{org.id}/ownership-transfers"
    owner_read = client.get(url, headers=auth(owner, token_for))
    nominee_read = client.get(url, headers=auth(nominee, token_for))
    second_nominee_read = client.get(url, headers=auth(second_nominee, token_for))
    assert owner_read.status_code == 200
    assert {row["id"] for row in owner_read.json()} == {first_id, second.id}
    assert nominee_read.status_code == 200
    assert [row["id"] for row in nominee_read.json()] == [first_id]
    assert second_nominee_read.status_code == 200
    assert [row["id"] for row in second_nominee_read.json()] == [second.id]
    assert all(set(row) == EXPECTED_TRANSFER_FIELDS for row in owner_read.json())

    for user in (member, admin, moderator, outsider):
        denied = client.get(url, headers=auth(user, token_for))
        assert denied.status_code == 403


def test_owner_history_returns_only_latest_100_transfers(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    nominee = make_user()
    org = make_org(owner=owner)
    base = now() - timedelta(days=2)
    transfers = [
        OwnershipTransfer(
            id=uid(), org_id=org.id, from_user_id=owner.id, nominee_id=nominee.id,
            client_key=str(uuid4()), status="declined", version=2,
            created_at=base + timedelta(seconds=index),
            expires_at=base + timedelta(days=7, seconds=index),
            resolved_at=base + timedelta(seconds=index + 1), decided_by=nominee.id,
        )
        for index in range(101)
    ]
    db.add_all(transfers)
    db.commit()

    response = client.get(
        f"/api/v1/organizations/{org.id}/ownership-transfers",
        headers=auth(owner, token_for),
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 100
    assert rows[0]["id"] == transfers[-1].id
    assert rows[-1]["id"] == transfers[1].id


def test_create_rejects_self_wrong_role_cross_org_inactive_and_ineligible_nominees(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    wrong_role = make_user()
    inactive = make_user(active=False)
    ineligible = make_user(email="fictional-ineligible@example.test")
    non_owner_admin = make_user()
    cross_org_owner = make_user()
    cross_org_candidate = make_user()
    add_membership(db, org, wrong_role, "member")
    add_membership(db, org, inactive, "admin")
    add_membership(db, org, ineligible, "admin")
    add_membership(db, org, non_owner_admin, "admin")
    other_org = make_org(owner=cross_org_owner)
    add_membership(db, other_org, cross_org_candidate, "admin")

    candidates = (owner, wrong_role, inactive, ineligible, cross_org_candidate)
    for candidate in candidates:
        response = create_offer(client, org, owner, candidate, token_for)
        assert response.status_code == 403
        assert response.json()["error"]["code"] in {
            "ownership_transfer_forbidden", "plm_email_required",
        }
    non_owner_create = create_offer(
        client, org, non_owner_admin, wrong_role, token_for,
    )
    assert non_owner_create.status_code == 403


def test_stale_owner_token_cannot_create_after_acceptance(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    nominee = make_user()
    next_admin = make_user()
    org = make_org(owner=owner)
    owner_token = token_for(owner)
    add_membership(db, org, nominee, "admin")
    add_membership(db, org, next_admin, "admin")
    created = create_offer(client, org, owner, nominee, token_for)
    accepted = decision(
        client, org, created.json()["id"], nominee, token_for, "accept",
    )
    stale_create = client.post(
        f"/api/v1/organizations/{org.id}/ownership-transfers",
        json={"nominee_id": next_admin.id, "client_key": str(uuid4())},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert accepted.status_code == 200
    assert stale_create.status_code == 403
    former_owner = db.scalar(select(OrgMembership).where(
        OrgMembership.org_id == org.id,
        OrgMembership.user_id == owner.id,
    ).execution_options(populate_existing=True))
    assert former_owner.active and former_owner.role == "member"
    assert db.scalar(select(Organization.created_by).where(
        Organization.id == org.id,
    ).execution_options(populate_existing=True)) == owner.id


@pytest.mark.parametrize(
    ("changed_party", "expected_status"),
    (("former_owner", 409), ("nominee", 409), ("owner_ineligible", 403)),
)
def test_accept_rechecks_both_current_roles(
    client, db, make_user, make_org, token_for, changed_party, expected_status,
):
    owner = make_user()
    nominee = make_user()
    org = make_org(owner=owner)
    nominee_membership = add_membership(db, org, nominee, "admin")
    created = create_offer(client, org, owner, nominee, token_for)

    if changed_party == "nominee":
        nominee_membership.role = "member"
        db.commit()
    elif changed_party == "owner_ineligible":
        owner.active = False
        db.commit()
    else:
        replacement_owner = make_user()
        replacement_membership = add_membership(db, org, replacement_owner, "admin")
        owner_membership = db.scalar(select(OrgMembership).where(
            OrgMembership.org_id == org.id,
            OrgMembership.user_id == owner.id,
        ).execution_options(populate_existing=True))
        owner_membership.role = "member"
        db.flush()
        replacement_membership.role = "owner"
        db.commit()

    response = decision(
        client, org, created.json()["id"], nominee, token_for, "accept",
    )
    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == (
        "ownership_transfer_stale"
        if expected_status == 409
        else "plm_email_required"
    )
    assert db.scalar(select(OwnershipTransfer.status).where(
        OwnershipTransfer.id == created.json()["id"],
    ).execution_options(populate_existing=True)) == "pending"
    assert db.scalar(select(func.count(OwnershipTransferAudit.id)).where(
        OwnershipTransferAudit.action == "accepted",
    )) == 0


def test_expiry_reads_are_projection_and_later_committed_create_seals_once(
    client, db, make_user, make_org, token_for, monkeypatch,
):
    owner = make_user()
    nominee = make_user()
    replacement_nominee = make_user()
    org = make_org(owner=owner)
    add_membership(db, org, nominee, "admin")
    add_membership(db, org, replacement_nominee, "admin")
    base = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(ownership_service, "now", lambda: base)

    created = create_offer(client, org, owner, nominee, token_for)
    transfer_id = created.json()["id"]
    expires_at = datetime.fromisoformat(created.json()["expires_at"])
    assert expires_at == base + timedelta(days=7)

    monkeypatch.setattr(ownership_service, "now", lambda: expires_at)
    url = f"/api/v1/organizations/{org.id}/ownership-transfers"
    projected = client.get(url, headers=auth(nominee, token_for))
    assert projected.status_code == 200
    assert projected.json()[0]["status"] == "expired"
    assert projected.json()[0]["version"] == 1
    projected_resolved_at = datetime.fromisoformat(
        projected.json()[0]["resolved_at"].replace("Z", "+00:00")
    )
    assert projected_resolved_at == expires_at
    assert db.scalar(select(OwnershipTransfer.status).where(
        OwnershipTransfer.id == transfer_id,
    ).execution_options(populate_existing=True)) == "pending"
    assert db.scalar(select(func.count(OwnershipTransferAudit.id)).where(
        OwnershipTransferAudit.action == "expired",
    )) == 0
    assert db.scalar(select(func.count(Notification.id)).where(
        Notification.kind == "ownership_transfer_expired",
    )) == 0

    rejected_decision = decision(
        client, org, transfer_id, nominee, token_for, "accept",
    )
    assert rejected_decision.status_code == 409
    assert rejected_decision.json()["error"]["code"] == "ownership_transfer_expired"
    # The error rolls its attempted seal back; it is not a durable expiry mutation.
    assert db.scalar(select(OwnershipTransfer.status).where(
        OwnershipTransfer.id == transfer_id,
    ).execution_options(populate_existing=True)) == "pending"
    assert db.scalar(select(func.count(OwnershipTransferAudit.id)).where(
        OwnershipTransferAudit.action == "expired",
    )) == 0
    assert db.scalar(select(func.count(Notification.id)).where(
        Notification.kind == "ownership_transfer_expired",
    )) == 0

    monkeypatch.setattr(
        ownership_service, "now", lambda: expires_at + timedelta(microseconds=1),
    )
    replacement = create_offer(
        client, org, owner, replacement_nominee, token_for,
    )
    assert replacement.status_code == 201
    old = db.scalar(select(OwnershipTransfer).where(
        OwnershipTransfer.id == transfer_id,
    ).execution_options(populate_existing=True))
    assert old.status == "expired" and old.version == 2
    assert old.resolved_at == expires_at and old.decided_by is None
    assert db.scalar(select(func.count(OwnershipTransferAudit.id)).where(
        OwnershipTransferAudit.transfer_id == transfer_id,
        OwnershipTransferAudit.action == "expired",
    )) == 1
    expiry_notices = list(db.scalars(select(Notification).where(
        Notification.kind == "ownership_transfer_expired",
    )))
    assert {notice.user_id for notice in expiry_notices} == {owner.id, nominee.id}
    assert len(expiry_notices) == 2
    assert all(
        notice.message == "An organization ownership transfer offer expired."
        for notice in expiry_notices
    )


def test_decision_rejects_boolean_string_and_extra_version_fields(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    nominee = make_user()
    org = make_org(owner=owner)
    add_membership(db, org, nominee, "admin")
    created = create_offer(client, org, owner, nominee, token_for)
    url = (
        f"/api/v1/organizations/{org.id}/ownership-transfers/"
        f"{created.json()['id']}/decision"
    )

    for version in (True, "1", 0):
        response = client.post(
            url,
            json={"action": "accept", "version": version},
            headers=auth(nominee, token_for),
        )
        assert response.status_code == 422
    stale_version = decision(
        client, org, created.json()["id"], nominee, token_for, "accept", version=2,
    )
    assert stale_version.status_code == 409
    assert stale_version.json()["error"]["code"] == "ownership_transfer_version_conflict"
    extra = client.post(
        url,
        json={"action": "accept", "version": 1, "decided_by": owner.id},
        headers=auth(nominee, token_for),
    )
    assert extra.status_code == 422
