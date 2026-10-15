"""Bounded API regressions for the frozen Sprint 8 membership contract.

The shared fixtures truncate ``intraspot_mvp_test`` before each test. Run this
module only in the coordinator-granted serial PostgreSQL slot.
"""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.db.models import now
from app.domains.organizations.models import OrgMembership
from app.domains.registrations.models import Registration, RegistrationReceipt


API = "/api/v1"
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _key():
    return str(uuid4())


def _apply(client, token_for, org, user, *, persona_shared=False, key=None):
    return client.post(
        f"{API}/organizations/{org.id}/membership-applications",
        headers=_auth(token_for(user)),
        json={"client_key": key or _key(), "persona_shared": persona_shared},
    )


def _decide(client, token_for, org, application, outcome, reason=None, *, actor):
    return client.post(
        f"{API}/organizations/{org.id}/membership-applications/{application}/decision",
        headers=_auth(token_for(actor)),
        json={"outcome": outcome, "reason": reason},
    )


def _invite(client, token_for, org, recipient, *, actor, key=None):
    return client.post(
        f"{API}/organizations/{org.id}/membership-invitations",
        headers=_auth(token_for(actor)),
        json={"recipient_id": recipient.id, "client_key": key or _key()},
    )


def _register(client, token_for, event, user, *, key=None):
    return client.post(
        f"{API}/events/{event.id}/registrations",
        headers=_auth(token_for(user)) | {"Idempotency-Key": key or _key()},
        json={"persona_shared": False},
    )


def _add_membership(db, org, user, role="member"):
    membership = OrgMembership(
        id=_key(), org_id=org.id, user_id=user.id, role=role, active=True
    )
    db.add(membership)
    db.commit()
    return membership


def _membership(db, org, user):
    return db.scalar(
        select(OrgMembership).where(
            OrgMembership.org_id == org.id,
            OrgMembership.user_id == user.id,
        )
    )


def _deny(response):
    assert response.status_code in {401, 403, 404}


def _safe_response_summary(response):
    try:
        payload = response.json()
    except ValueError:
        payload = None
    error = payload.get("error") if isinstance(payload, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return {
        "status": response.status_code,
        "error_code": code if isinstance(code, str) else None,
    }


def _run_together(actions):
    barrier = Barrier(len(actions))

    def run(action):
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        futures = [pool.submit(run, action) for action in actions]
        return [future.result(timeout=30) for future in futures]


def _restart_receipt_drain(event_id):
    """Drain receipts in a fresh process using only the guarded scratch database."""
    env = os.environ.copy()
    assert env.get("ENVIRONMENT") == "test"
    assert env.get("FIXTURE_AUTH", "").lower() == "true"
    target = make_url(env["DATABASE_URL"])
    assert (
        target.drivername == "postgresql+psycopg"
        and target.database == "intraspot_mvp_test"
        and target.host in {"127.0.0.1", "localhost"}
        and target.port == 5433
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from app.domains.registrations.service import catch_up_event; catch_up_event(sys.argv[1])",
            event_id,
        ],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_unverified_approval_stays_locked_until_trusted_identity_is_eligible(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    org = make_org(owner=owner)
    applicant = make_user(nickname="s8-private-pending-persona")
    event = make_event(org=org, capacity=2)
    initial_key = _key()
    registration = _register(client, token_for, event, applicant, key=initial_key)
    assert registration.status_code < 300
    assert registration.json()["status"] == "confirmed"

    # Trusted eligibility comes from the stored identity, not the token or request.
    applicant.email_verified = False
    db.commit()
    application = _apply(client, token_for, org, applicant, persona_shared=True)
    assert application.status_code < 300

    approved = _decide(
        client, token_for, org, application.json()["id"], "approved", actor=owner
    )
    assert approved.status_code < 300
    assert approved.json()["access_ready"] is False
    assert approved.json()["persona"] is None

    own_requests = client.get(
        f"{API}/me/membership-applications", headers=_auth(token_for(applicant))
    )
    assert own_requests.status_code == 200
    own_application = next(
        row for row in own_requests.json() if row["id"] == application.json()["id"]
    )
    assert own_application["status"] == "approved"
    assert own_application["access_ready"] is False

    own_grants = client.get(f"{API}/me/memberships", headers=_auth(token_for(applicant)))
    assert own_grants.status_code == 200
    grant = next(row for row in own_grants.json() if row["org_id"] == org.id)
    assert grant["access_ready"] is False
    assert grant["role"] == "member"

    # A previously confirmed event seat must not turn an ineligible approval into chat access.
    _deny(client.get(f"{API}/me/chats", headers=_auth(token_for(applicant))))
    _deny(client.get(f"{API}/events/{event.id}/chat", headers=_auth(token_for(applicant))))

    applicant.email_verified = True
    db.commit()
    own_grants = client.get(f"{API}/me/memberships", headers=_auth(token_for(applicant)))
    grant = next(row for row in own_grants.json() if row["org_id"] == org.id)
    assert grant["access_ready"] is True
    inbox = client.get(f"{API}/me/chats", headers=_auth(token_for(applicant)))
    assert inbox.status_code == 200
    assert any(row["event_id"] == event.id for row in inbox.json())
    assert client.get(
        f"{API}/events/{event.id}/chat", headers=_auth(token_for(applicant))
    ).status_code == 200

    db.expire_all()
    assert _membership(db, org, applicant).role == "member"


def test_membership_review_persona_is_separately_consented_and_expires_on_resolution(
    client, make_org, make_user, token_for
):
    owner = make_user()
    org = make_org(owner=owner)
    ambient_only = make_user(
        nickname="s8-global-consent-must-not-carry",
        persona_visible=True,
        tags=["ambient-tag"],
    )
    explicitly_consented = make_user(
        nickname="s8-membership-consent",
        persona_visible=False,
        tags=["explicit-tag"],
    )
    ambient_application = _apply(client, token_for, org, ambient_only)
    consented_application = _apply(
        client, token_for, org, explicitly_consented, persona_shared=True
    )
    assert ambient_application.status_code < 300
    assert consented_application.status_code < 300

    reviews_response = client.get(
        f"{API}/organizations/{org.id}/membership-applications",
        headers=_auth(token_for(owner)),
    )
    assert reviews_response.status_code == 200
    reviews = {row["user_id"]: row for row in reviews_response.json()}
    assert reviews[ambient_only.id]["persona"] is None
    assert ambient_only.nickname not in str(reviews[ambient_only.id])
    assert ambient_only.email not in str(reviews[ambient_only.id])
    persona = reviews[explicitly_consented.id]["persona"]
    assert persona == {"nickname": explicitly_consented.nickname, "tags": ["explicit-tag"]}
    assert set(persona) == {"nickname", "tags"}

    approved = _decide(
        client,
        token_for,
        org,
        consented_application.json()["id"],
        "approved",
        actor=owner,
    )
    rejected = _decide(
        client,
        token_for,
        org,
        ambient_application.json()["id"],
        "rejected",
        reason="requirements_not_met",
        actor=owner,
    )
    assert approved.status_code < 300 and rejected.status_code < 300
    assert approved.json()["persona"] is None
    assert rejected.json()["persona"] is None

    closed_reviews = client.get(
        f"{API}/organizations/{org.id}/membership-applications",
        headers=_auth(token_for(owner)),
    )
    assert closed_reviews.status_code == 200
    closed = {row["user_id"]: row for row in closed_reviews.json()}
    assert closed[explicitly_consented.id]["persona"] is None
    assert closed[ambient_only.id]["persona"] is None


def test_rejection_allows_immediate_retry_but_withdrawal_starts_24_hour_cooldown(
    client, make_org, make_user, token_for
):
    owner = make_user()
    applicant = make_user()
    org = make_org(owner=owner)
    first = _apply(client, token_for, org, applicant)
    assert first.status_code < 300

    rejected = _decide(
        client,
        token_for,
        org,
        first.json()["id"],
        "rejected",
        reason="applications_closed",
        actor=owner,
    )
    assert rejected.status_code < 300
    assert rejected.json()["can_reapply_at"] is None

    retry = _apply(client, token_for, org, applicant)
    assert retry.status_code < 300
    assert retry.json()["id"] != first.json()["id"]
    assert retry.json()["status"] == "pending"

    withdrawn = client.post(
        f"{API}/membership-applications/{retry.json()['id']}/withdraw",
        headers=_auth(token_for(applicant)),
    )
    assert withdrawn.status_code < 300
    assert withdrawn.json()["status"] == "withdrawn"
    resolved_at = datetime.fromisoformat(withdrawn.json()["resolved_at"].replace("Z", "+00:00"))
    can_reapply_at = datetime.fromisoformat(
        withdrawn.json()["can_reapply_at"].replace("Z", "+00:00")
    )
    assert abs((can_reapply_at - resolved_at - timedelta(hours=24)).total_seconds()) <= 1

    blocked = _apply(client, token_for, org, applicant)
    assert 400 <= blocked.status_code < 500


def test_invitation_is_recipient_bound_single_use_and_enforces_expiry_and_revocation(
    client, db, make_org, make_user, token_for
):
    from app.domains.memberships.models import MembershipInvitation

    owner = make_user()
    recipient = make_user()
    other_user = make_user()
    org = make_org(owner=owner)
    sent = _invite(client, token_for, org, recipient, actor=owner)
    assert sent.status_code < 300
    invitation_id = sent.json()["id"]

    own_invitations = client.get(
        f"{API}/me/membership-invitations", headers=_auth(token_for(recipient))
    )
    other_invitations = client.get(
        f"{API}/me/membership-invitations", headers=_auth(token_for(other_user))
    )
    assert own_invitations.status_code == other_invitations.status_code == 200
    assert any(row["id"] == invitation_id for row in own_invitations.json())
    assert all(row["id"] != invitation_id for row in other_invitations.json())
    _deny(
        client.post(
            f"{API}/membership-invitations/{invitation_id}/accept",
            headers=_auth(token_for(other_user)),
        )
    )

    accepted = client.post(
        f"{API}/membership-invitations/{invitation_id}/accept",
        headers=_auth(token_for(recipient)),
    )
    assert accepted.status_code < 300
    assert accepted.json()["status"] == "accepted"
    grant = _membership(db, org, recipient)
    assert grant is not None and grant.active and grant.role == "member"

    left = client.post(
        f"{API}/organizations/{org.id}/membership/leave",
        headers=_auth(token_for(recipient)),
        json={"client_key": _key()},
    )
    assert left.status_code < 300
    db.expire_all()
    assert _membership(db, org, recipient).active is False

    # Replaying an accepted invitation after departure cannot restore the grant.
    replay = client.post(
        f"{API}/membership-invitations/{invitation_id}/accept",
        headers=_auth(token_for(recipient)),
    )
    assert replay.status_code < 500
    db.expire_all()
    assert _membership(db, org, recipient).active is False

    expired_org = make_org(owner=owner)
    expired_recipient = make_user()
    expired = _invite(client, token_for, expired_org, expired_recipient, actor=owner)
    assert expired.status_code < 300
    expired_row = db.get(MembershipInvitation, expired.json()["id"])
    expired_row.expires_at = now()
    db.commit()
    projected = client.get(
        f"{API}/me/membership-invitations",
        headers=_auth(token_for(expired_recipient)),
    )
    assert projected.status_code == 200
    assert next(row for row in projected.json() if row["id"] == expired.json()["id"])["status"] == "expired"
    expired_accept = client.post(
        f"{API}/membership-invitations/{expired.json()['id']}/accept",
        headers=_auth(token_for(expired_recipient)),
    )
    assert 400 <= expired_accept.status_code < 500
    assert _membership(db, expired_org, expired_recipient) is None

    revoked_org = make_org(owner=owner)
    revoked_recipient = make_user()
    pending = _invite(client, token_for, revoked_org, revoked_recipient, actor=owner)
    assert pending.status_code < 300
    revoked = client.post(
        f"{API}/organizations/{revoked_org.id}/membership-invitations/{pending.json()['id']}/revoke",
        headers=_auth(token_for(owner)),
    )
    assert revoked.status_code < 300
    assert revoked.json()["status"] == "revoked"
    revoked_accept = client.post(
        f"{API}/membership-invitations/{pending.json()['id']}/accept",
        headers=_auth(token_for(revoked_recipient)),
    )
    assert revoked_accept.status_code == 409
    assert _membership(db, revoked_org, revoked_recipient) is None


def test_staff_role_isolation_and_owner_cannot_be_changed_or_removed(
    client, db, make_org, make_user, token_for
):
    owner, admin, second_admin, moderator, member = [make_user() for _ in range(5)]
    org = make_org(owner=owner)
    owner_membership = _membership(db, org, owner)
    _add_membership(db, org, admin, "admin")
    second_admin_membership = _add_membership(db, org, second_admin, "admin")
    _add_membership(db, org, moderator, "moderator")
    _add_membership(db, org, member, "member")

    owner_role_change = client.patch(
        f"{API}/organizations/{org.id}/members/{owner_membership.id}/role",
        headers=_auth(token_for(owner)),
        json={"client_key": _key(), "role": "admin"},
    )
    assert 400 <= owner_role_change.status_code < 500
    owner_removal = client.post(
        f"{API}/organizations/{org.id}/members/{owner_membership.id}/remove",
        headers=_auth(token_for(owner)),
        json={"client_key": _key()},
    )
    assert 400 <= owner_removal.status_code < 500
    owner_leave = client.post(
        f"{API}/organizations/{org.id}/membership/leave",
        headers=_auth(token_for(owner)),
        json={"client_key": _key()},
    )
    assert 400 <= owner_leave.status_code < 500

    _deny(client.get(f"{API}/organizations/{org.id}/members", headers=_auth(token_for(member))))
    _deny(
        client.get(
            f"{API}/organizations/{org.id}/membership-audit",
            headers=_auth(token_for(member)),
        )
    )
    _deny(
        _invite(client, token_for, org, make_user(), actor=moderator)
    )
    _deny(
        client.patch(
            f"{API}/organizations/{org.id}/members/{_membership(db, org, member).id}/role",
            headers=_auth(token_for(moderator)),
            json={"client_key": _key(), "role": "moderator"},
        )
    )
    admin_cannot_change_admin = client.patch(
        f"{API}/organizations/{org.id}/members/{second_admin_membership.id}/role",
        headers=_auth(token_for(admin)),
        json={"client_key": _key(), "role": "member"},
    )
    assert 400 <= admin_cannot_change_admin.status_code < 500

    db.expire_all()
    assert _membership(db, org, owner).active is True
    assert _membership(db, org, owner).role == "owner"
    assert _membership(db, org, second_admin).role == "admin"


def test_departure_cancels_promotes_revokes_active_and_archived_chat_and_drains_old_receipt_after_restart(
    client, db, make_event, make_org, make_user, token_for
):
    owner, departing, waiter = make_user(), make_user(), make_user()
    org = make_org(owner=owner)
    _add_membership(db, org, departing)

    active = make_event(org=org, capacity=1)
    active_key = _key()
    active_registration = _register(client, token_for, active, departing, key=active_key)
    assert active_registration.status_code < 300
    assert active_registration.json()["status"] == "confirmed"
    waiting_registration = _register(client, token_for, active, waiter)
    assert waiting_registration.status_code < 300
    assert waiting_registration.json()["status"] == "waitlisted"

    reentry = make_event(org=org, capacity=1)
    reentry_registration = _register(client, token_for, reentry, departing)
    assert reentry_registration.status_code < 300
    assert reentry_registration.json()["status"] == "confirmed"

    archived = make_event(org=org, capacity=1)
    archived_registration = _register(client, token_for, archived, departing)
    assert archived_registration.status_code < 300
    archived.starts_at = now() - timedelta(days=1)
    archived.ends_at = now() - timedelta(hours=12)
    db.commit()

    db.refresh(active)
    pending_order = active.next_admission + 1
    active.next_admission = pending_order
    pending_receipt = RegistrationReceipt(
        id=_key(),
        user_id=departing.id,
        event_id=active.id,
        idempotency_key=f"s8-undrained-{_key()}",
        event_order=pending_order,
        result=None,
        http_status=None,
        created_at=now(),
        processed_at=None,
        persona_shared=False,
    )
    db.add(pending_receipt)
    db.commit()

    leave = client.post(
        f"{API}/organizations/{org.id}/membership/leave",
        headers=_auth(token_for(departing)),
        json={"client_key": _key()},
    )
    assert leave.status_code < 300
    assert leave.json()["cancelled_registrations"] == 2
    assert leave.json()["chat_revoked"] == 3

    db.expire_all()
    active_rows = list(
        db.scalars(
            select(Registration).where(
                Registration.event_id == active.id,
                Registration.user_id.in_([departing.id, waiter.id]),
            )
        )
    )
    assert {row.user_id: row.status for row in active_rows} == {
        departing.id: "cancelled",
        waiter.id: "confirmed",
    }
    assert db.get(Registration, archived_registration.json()["id"]).status == "confirmed"
    assert db.get(RegistrationReceipt, pending_receipt.id).result is None
    initial_receipt = db.scalar(
        select(RegistrationReceipt).where(
            RegistrationReceipt.user_id == departing.id,
            RegistrationReceipt.event_id == active.id,
            RegistrationReceipt.idempotency_key == active_key,
        )
    )
    initial_result = dict(initial_receipt.result)

    for event in (active, reentry, archived):
        _deny(client.get(f"{API}/events/{event.id}/chat", headers=_auth(token_for(departing))))

    _restart_receipt_drain(active.id)
    db.expire_all()
    drained = db.get(RegistrationReceipt, pending_receipt.id)
    assert drained.result["error"]["code"] == "membership_ended"
    assert drained.http_status == 409
    assert drained.processed_at is not None
    drained_result = dict(drained.result)
    _restart_receipt_drain(active.id)
    db.expire_all()
    assert db.get(RegistrationReceipt, pending_receipt.id).result == drained_result
    assert db.get(RegistrationReceipt, initial_receipt.id).result == initial_result

    # A later public registration receives an order beyond the durable cutoff and can restore chat.
    later = _register(client, token_for, reentry, departing)
    assert later.status_code < 300
    assert later.json()["status"] == "confirmed"
    assert client.get(
        f"{API}/events/{reentry.id}/chat", headers=_auth(token_for(departing))
    ).status_code == 200


def test_operation_key_reuse_is_immutable_and_concurrent_exits_preserve_capacity(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    org = make_org(owner=owner)
    departing = [make_user() for _ in range(3)]
    waiters = [make_user() for _ in range(3)]
    memberships = [_add_membership(db, org, user) for user in departing]
    event = make_event(org=org, capacity=3)

    for user in departing:
        response = _register(client, token_for, event, user)
        assert response.status_code < 300
        assert response.json()["status"] == "confirmed"
    for user in waiters:
        response = _register(client, token_for, event, user)
        assert response.status_code < 300
        assert response.json()["status"] == "waitlisted"

    retry_key = _key()
    first = client.post(
        f"{API}/organizations/{org.id}/members/{memberships[0].id}/remove",
        headers=_auth(token_for(owner)),
        json={"client_key": retry_key},
    )
    assert first.status_code < 300
    assert first.json()["cancelled_registrations"] == 1
    assert first.json()["chat_revoked"] == 1
    replay = client.post(
        f"{API}/organizations/{org.id}/members/{memberships[0].id}/remove",
        headers=_auth(token_for(owner)),
        json={"client_key": retry_key},
    )
    assert replay.status_code == first.status_code
    assert replay.json() == first.json()

    incompatible = client.post(
        f"{API}/organizations/{org.id}/members/{memberships[1].id}/remove",
        headers=_auth(token_for(owner)),
        json={"client_key": retry_key},
    )
    assert incompatible.status_code == 409

    concurrent_indexes = (1, 2)
    responses = _run_together(
        [
            lambda index=index: client.post(
                f"{API}/organizations/{org.id}/members/{memberships[index].id}/remove",
                headers=_auth(token_for(owner)),
                json={"client_key": _key()},
            )
            for index in concurrent_indexes
        ]
    )
    summaries = [
        {"target_index": index, **_safe_response_summary(response)}
        for index, response in zip(concurrent_indexes, responses)
    ]
    assert all(response.status_code < 300 for response in responses), summaries
    assert all(response.json()["cancelled_registrations"] == 1 for response in responses)
    assert all(response.json()["chat_revoked"] == 1 for response in responses)

    for user in departing:
        _deny(client.get(f"{API}/events/{event.id}/chat", headers=_auth(token_for(user))))

    db.expire_all()
    current = list(
        db.scalars(
            select(Registration).where(
                Registration.event_id == event.id,
                Registration.status.in_(("confirmed", "pending", "reconfirmation_required")),
            )
        )
    )
    assert len(current) == event.capacity == 3
    assert {row.user_id for row in current} == {user.id for user in waiters}
    assert all(_membership(db, org, user).active is False for user in departing)

