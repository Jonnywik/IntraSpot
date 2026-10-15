"""Membership status, staff access, role changes, and departures."""
from hashlib import sha256
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.identity.models import User
from app.domains.organizations.models import OrgMembership, Organization
from app.domains.registrations import service as registration_service
from . import policy
from .models import MembershipAudit, MembershipOperation
from .schemas import (
    MembershipAuditOut,
    MembershipChangeOut,
    MembershipRoleInput,
    MembershipRosterItem,
    MembershipSelfOut,
)

STAFF_ROLES = ("owner", "admin", "moderator")
MANAGE_ROLES = ("owner", "admin")
PRIVILEGED_ROLES = ("admin", "moderator")


def list_self_memberships(db: Session, user_id: str) -> list[MembershipSelfOut]:
    rows = db.execute(
        select(Organization, OrgMembership)
        .join(OrgMembership, OrgMembership.org_id == Organization.id)
        .where(OrgMembership.user_id == user_id)
        .order_by(Organization.name, Organization.id)
    ).tuples()
    return [
        MembershipSelfOut(
            id=membership.id,
            org_id=membership.org_id,
            organization_name=organization.name,
            role=membership.role,
            active=membership.active,
            access_ready=membership.active and policy.access_ready(db, membership.org_id, user_id),
            joined_at=policy.joined_at(db, membership.org_id, user_id),
        )
        for organization, membership in rows
    ]


def list_roster(db: Session, actor_id: str, org_id: str) -> list[MembershipRosterItem]:
    policy.require_staff(db, actor_id, org_id, roles=STAFF_ROLES, lock=False)
    rows = db.execute(
        select(OrgMembership, User.id)
        .join(User, User.id == OrgMembership.user_id)
        .where(OrgMembership.org_id == org_id, OrgMembership.active.is_(True))
        .order_by(OrgMembership.role, OrgMembership.user_id)
    ).tuples()
    roster = []
    for membership, user_id in rows:
        code = user_id.replace("-", "")[-6:].upper()
        roster.append(MembershipRosterItem(
            id=membership.id,
            user_id=user_id,
            label=f"{'You' if user_id == actor_id else 'Member'} · {code}",
            role=membership.role,
            eligible=policy.eligible_user(db, user_id),
            access_ready=policy.access_ready(db, org_id, user_id),
            joined_at=policy.joined_at(db, org_id, user_id),
        ))
    return roster


def list_audit(db: Session, actor_id: str, org_id: str) -> list[MembershipAuditOut]:
    policy.require_staff(db, actor_id, org_id, roles=STAFF_ROLES)
    rows = db.scalars(
        select(MembershipAudit)
        .where(MembershipAudit.org_id == org_id)
        .order_by(MembershipAudit.created_at.desc(), MembershipAudit.id.desc())
        .limit(100)
    )
    return [MembershipAuditOut(
        id=row.id,
        actor_id=row.actor_id,
        user_id=row.user_id,
        action=row.action,
        old_role=row.old_role,
        new_role=row.new_role,
        created_at=row.created_at,
    ) for row in rows]


def _payload_hash(action: str, org_id: str, subject_id: str, role: str | None = None) -> str:
    body = json.dumps(
        {"action": action, "org_id": org_id, "subject_id": subject_id, "role": role},
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(body.encode("utf-8")).hexdigest()


def _replay(
    db: Session,
    actor_id: str,
    key: str,
    action: str,
    org_id: str,
    payload_hash: str,
) -> MembershipChangeOut | None:
    operation = db.scalar(select(MembershipOperation).where(
        MembershipOperation.actor_id == actor_id,
        MembershipOperation.client_key == key,
    ))
    if operation is None:
        return None
    if (operation.action, operation.org_id, operation.payload_hash) != (action, org_id, payload_hash):
        raise DomainError(
            "membership_operation_key_conflict",
            "This client key was already used for a different membership change.",
            409,
        )
    return MembershipChangeOut.model_validate(operation.result)


def _record_operation(
    db: Session,
    *,
    operation_id: str,
    actor_id: str,
    user_id: str,
    action: str,
    org_id: str,
    key: str,
    payload_hash: str,
    result: MembershipChangeOut,
    at,
) -> MembershipChangeOut:
    db.add(MembershipOperation(
        id=operation_id,
        org_id=org_id,
        actor_id=actor_id,
        user_id=user_id,
        action=action,
        client_key=key,
        payload_hash=payload_hash,
        result=result.model_dump(mode="json"),
        created_at=at,
    ))
    db.flush()
    return result


def _lock_org_and_authorize(
    db: Session,
    actor_id: str,
    org_id: str,
) -> OrgMembership:
    policy.get_org(db, org_id, lock=True, approved=True)
    _, staff = policy.require_staff(db, actor_id, org_id, roles=MANAGE_ROLES, lock=False)
    return staff


def _target_membership(db: Session, org_id: str, membership_id: str) -> OrgMembership:
    membership = db.scalar(
        select(OrgMembership)
        .where(OrgMembership.id == membership_id, OrgMembership.org_id == org_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if membership is None:
        raise DomainError("membership_not_found", "Membership was not found.", 404)
    return membership


def _change_result(
    org_id: str,
    membership: OrgMembership,
    cancelled: int = 0,
    chat_revoked: int = 0,
) -> MembershipChangeOut:
    return MembershipChangeOut(
        org_id=org_id,
        membership_id=membership.id,
        user_id=membership.user_id,
        role=membership.role,
        active=membership.active,
        cancelled_registrations=cancelled,
        chat_revoked=chat_revoked,
    )


def change_role(
    db: Session,
    actor_id: str,
    org_id: str,
    membership_id: str,
    payload: MembershipRoleInput,
) -> MembershipChangeOut:
    key = str(payload.client_key)
    policy.lock_client_key(db, actor_id, key)
    staff = _lock_org_and_authorize(db, actor_id, org_id)
    fingerprint = _payload_hash("role", org_id, membership_id, payload.role)
    replay = _replay(db, actor_id, key, "role", org_id, fingerprint)
    if replay is not None:
        return replay

    membership = _target_membership(db, org_id, membership_id)
    if not membership.active:
        raise DomainError("membership_not_found", "Membership was not found.", 404)
    if membership.role == "owner":
        raise DomainError("membership_owner_protected", "The organization owner cannot be changed here.", 409)
    if staff.role != "owner" and (
        staff.role != "admin"
        or membership.role == "admin"
        or payload.role == "admin"
    ):
        raise DomainError("membership_role_forbidden", "You cannot manage this membership role.", 403)
    if membership.user_id == actor_id and payload.role in PRIVILEGED_ROLES and payload.role != membership.role:
        raise DomainError("membership_self_promotion", "You cannot grant yourself a staff role.", 403)
    if payload.role in PRIVILEGED_ROLES and payload.role != membership.role:
        if not policy.eligible_user(db, membership.user_id):
            raise DomainError(
                "membership_staff_eligibility_required",
                "Only currently eligible active members may hold staff roles.",
                403,
            )

    at = now()
    operation_id = uid()
    old_role = membership.role
    if payload.role != old_role:
        membership.role = payload.role
        policy.audit(
            db, org_id, actor_id, membership.user_id, "membership_role_changed", at,
            old_role=old_role, new_role=payload.role,
        )
        policy.notice(db, org_id, membership.user_id, "membership_role_changed",
                      f"membership_role_changed:{operation_id}")
        db.flush()
    result = _change_result(org_id, membership)
    return _record_operation(
        db,
        operation_id=operation_id,
        actor_id=actor_id,
        user_id=membership.user_id,
        action="role",
        org_id=org_id,
        key=key,
        payload_hash=fingerprint,
        result=result,
        at=at,
    )


def _end_active_membership(
    db: Session,
    org_id: str,
    actor_id: str,
    membership: OrgMembership,
    *,
    action: str,
    key: str,
    fingerprint: str,
) -> MembershipChangeOut:
    at = now()
    operation_id = uid()
    if membership.active:
        old_role = membership.role
        membership.active = False
        policy.audit(
            db, org_id, actor_id, membership.user_id, action, at,
            old_role=old_role, new_role=None,
        )
        db.flush()
        cancelled, chat_revoked = registration_service.end_membership_attendance(
            db, org_id, membership.user_id,
        )
        policy.notice(db, org_id, membership.user_id, action, f"{action}:{operation_id}")
    else:
        cancelled = chat_revoked = 0
    result = _change_result(org_id, membership, cancelled, chat_revoked)
    return _record_operation(
        db,
        operation_id=operation_id,
        actor_id=actor_id,
        user_id=membership.user_id,
        action="leave" if action == "membership_left" else "remove",
        org_id=org_id,
        key=key,
        payload_hash=fingerprint,
        result=result,
        at=at,
    )


def leave(
    db: Session,
    actor_id: str,
    org_id: str,
    client_key: UUID,
) -> MembershipChangeOut:
    key = str(client_key)
    policy.lock_client_key(db, actor_id, key)
    policy.get_org(db, org_id, lock=True, approved=True)
    fingerprint = _payload_hash("leave", org_id, actor_id)
    replay = _replay(db, actor_id, key, "leave", org_id, fingerprint)
    if replay is not None:
        return replay

    membership = db.scalar(
        select(OrgMembership)
        .where(OrgMembership.org_id == org_id, OrgMembership.user_id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if membership is None:
        raise DomainError("membership_not_found", "Membership was not found.", 404)
    if membership.role == "owner":
        raise DomainError("membership_owner_protected", "The organization owner cannot leave.", 409)
    return _end_active_membership(
        db, org_id, actor_id, membership,
        action="membership_left", key=key, fingerprint=fingerprint,
    )


def remove(
    db: Session,
    actor_id: str,
    org_id: str,
    membership_id: str,
    client_key: UUID,
) -> MembershipChangeOut:
    key = str(client_key)
    policy.lock_client_key(db, actor_id, key)
    staff = _lock_org_and_authorize(db, actor_id, org_id)
    fingerprint = _payload_hash("remove", org_id, membership_id)
    replay = _replay(db, actor_id, key, "remove", org_id, fingerprint)
    if replay is not None:
        return replay

    membership = _target_membership(db, org_id, membership_id)
    if membership.role == "owner":
        raise DomainError("membership_owner_protected", "The organization owner cannot be removed.", 409)
    if staff.role != "owner" and membership.role == "admin":
        raise DomainError("membership_role_forbidden", "Only the owner may remove an admin.", 403)
    if not membership.active:
        raise DomainError("membership_not_found", "Membership was not found.", 404)
    return _end_active_membership(
        db, org_id, actor_id, membership,
        action="membership_removed", key=key, fingerprint=fingerprint,
    )
