"""Manual organization ownership transfers."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.identity.models import User
from app.domains.memberships import policy
from app.domains.organizations.models import OrgMembership
from app.notifications import notify_in_app

from .models import OwnershipTransfer, OwnershipTransferAudit
from .schemas import OwnershipTransferCreate, OwnershipTransferDecision, OwnershipTransferOut


TRANSFER_LIFETIME = timedelta(days=7)
NOTICE_CONTENT = {
    "requested": (
        "ownership_transfer_requested",
        "You have an organization ownership transfer offer.",
    ),
    "accepted": (
        "ownership_transfer_accepted",
        "Organization ownership was transferred. Review your current role.",
    ),
    "declined": (
        "ownership_transfer_declined",
        "An organization ownership transfer offer was declined.",
    ),
    "revoked": (
        "ownership_transfer_revoked",
        "An organization ownership transfer offer was revoked.",
    ),
    "expired": (
        "ownership_transfer_expired",
        "An organization ownership transfer offer expired.",
    ),
}


def _out(transfer: OwnershipTransfer, at) -> OwnershipTransferOut:
    status = transfer.status
    resolved_at = transfer.resolved_at
    if status == "pending" and at >= transfer.expires_at:
        status = "expired"
        resolved_at = transfer.expires_at
    return OwnershipTransferOut(
        id=transfer.id,
        org_id=transfer.org_id,
        from_user_id=transfer.from_user_id,
        nominee_id=transfer.nominee_id,
        status=status,
        version=transfer.version,
        created_at=transfer.created_at,
        expires_at=transfer.expires_at,
        resolved_at=resolved_at,
        decided_by=transfer.decided_by,
    )


def _audit(
    db: Session,
    transfer: OwnershipTransfer,
    action: str,
    actor_id: str | None,
    at,
) -> None:
    db.add(
        OwnershipTransferAudit(
            id=uid(),
            transfer_id=transfer.id,
            actor_id=actor_id,
            action=action,
            created_at=at,
        )
    )


def _notify(db: Session, transfer: OwnershipTransfer, action: str, user_id: str) -> None:
    kind, message = NOTICE_CONTENT[action]
    notify_in_app(
        db,
        user_id=user_id,
        org_id=transfer.org_id,
        kind=kind,
        message=message,
        dedupe_key=f"ownership_transfer:{transfer.id}:{action}:{user_id}",
    )


def _seal_expired(db: Session, transfer: OwnershipTransfer, at) -> bool:
    if transfer.status != "pending" or at < transfer.expires_at:
        return False
    transfer.status = "expired"
    transfer.version += 1
    transfer.resolved_at = transfer.expires_at
    transfer.decided_by = None
    _audit(db, transfer, "expired", None, at)
    for user_id in (transfer.from_user_id, transfer.nominee_id):
        _notify(db, transfer, "expired", user_id)
    return True


def _locked_transfer(db: Session, org_id: str, transfer_id: str) -> OwnershipTransfer | None:
    return db.scalar(
        select(OwnershipTransfer)
        .where(
            OwnershipTransfer.org_id == org_id,
            OwnershipTransfer.id == transfer_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _lock_memberships(db: Session, org_id: str, user_ids: list[str]) -> dict[str, OrgMembership]:
    rows = db.scalars(
        select(OrgMembership)
        .where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id.in_(tuple(sorted(set(user_ids)))),
        )
        .order_by(OrgMembership.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return {row.user_id: row for row in rows}


def _lock_users(db: Session, user_ids: list[str]) -> None:
    list(db.scalars(
        select(User)
        .where(User.id.in_(tuple(sorted(set(user_ids)))))
        .order_by(User.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))


def _require_eligible(db: Session, user_ids: list[str]) -> None:
    for user_id in sorted(set(user_ids)):
        if not policy.eligible_user(db, user_id):
            raise DomainError(
                "plm_email_required",
                "A verified PLM account is required for organization access.",
                403,
            )


def _require_active_role(
    memberships: dict[str, OrgMembership],
    user_id: str,
    role: str,
    *,
    status: int,
) -> OrgMembership:
    membership = memberships.get(user_id)
    if membership is None or not membership.active or membership.role != role:
        raise DomainError(
            "ownership_transfer_stale" if status == 409 else "ownership_transfer_forbidden",
            "Current organization roles do not permit this ownership transfer.",
            status,
        )
    return membership


def list_transfers(db: Session, actor_id: str, org_id: str) -> list[OwnershipTransferOut]:
    actor_id = str(actor_id)
    org_id = str(org_id)
    if not policy.eligible_user(db, actor_id):
        raise DomainError(
            "plm_email_required",
            "A verified PLM account is required for organization access.",
            403,
        )
    policy.get_org(db, org_id, approved=True)
    membership = policy.membership_for(db, org_id, actor_id)
    owner_view = membership is not None and membership.active and membership.role == "owner"
    query = select(OwnershipTransfer).where(OwnershipTransfer.org_id == org_id)
    if not owner_view:
        intended = db.scalar(
            select(OwnershipTransfer.id)
            .where(
                OwnershipTransfer.org_id == org_id,
                OwnershipTransfer.nominee_id == actor_id,
            )
            .limit(1)
        )
        if intended is None:
            raise DomainError(
                "ownership_transfer_forbidden",
                "You cannot view these ownership transfers.",
                403,
            )
        query = query.where(OwnershipTransfer.nominee_id == actor_id)
    rows = db.scalars(
        query.order_by(OwnershipTransfer.created_at.desc(), OwnershipTransfer.id.desc()).limit(100)
    )
    at = now()
    return [_out(transfer, at) for transfer in rows]


def create_transfer(
    db: Session,
    actor_id: str,
    org_id: str,
    payload: OwnershipTransferCreate,
) -> OwnershipTransferOut:
    actor_id = str(actor_id)
    org_id = str(org_id)
    nominee_id = str(payload.nominee_id)
    client_key = str(payload.client_key)

    if not policy.eligible_user(db, actor_id):
        raise DomainError(
            "plm_email_required",
            "A verified PLM account is required for organization access.",
            403,
        )
    policy.lock_client_key(db, actor_id, client_key)

    previous = db.scalar(
        select(OwnershipTransfer)
        .where(
            OwnershipTransfer.from_user_id == actor_id,
            OwnershipTransfer.client_key == client_key,
        )
        .execution_options(populate_existing=True)
    )
    if previous is not None:
        if previous.org_id != org_id or previous.nominee_id != nominee_id:
            raise DomainError(
                "ownership_transfer_key_reused",
                "This request key was already used for a different ownership transfer.",
                409,
            )
        policy.get_org(db, org_id, lock=True)
        transfer = _locked_transfer(db, org_id, previous.id)
        if transfer is None:
            raise DomainError(
                "ownership_transfer_not_found",
                "Ownership transfer was not found.",
                404,
            )
        _lock_users(db, [actor_id])
        _require_eligible(db, [actor_id])
        return _out(transfer, now())

    organization = policy.get_org(db, org_id, lock=True)
    if organization.accreditation_status != "approved":
        raise DomainError(
            "organization_not_approved",
            "Approved organization access is required.",
            403,
        )
    if not policy.eligible_user(db, actor_id):
        raise DomainError(
            "plm_email_required",
            "A verified PLM account is required for organization access.",
            403,
        )
    policy.require_staff(db, actor_id, org_id, roles=("owner",), lock=False)

    pending = db.scalar(
        select(OwnershipTransfer)
        .where(
            OwnershipTransfer.org_id == org_id,
            OwnershipTransfer.status == "pending",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    memberships = _lock_memberships(db, org_id, [actor_id, nominee_id])
    _lock_users(db, [actor_id, nominee_id])
    _require_eligible(db, [actor_id, nominee_id])
    _require_active_role(memberships, actor_id, "owner", status=403)
    if nominee_id == actor_id:
        raise DomainError(
            "ownership_transfer_forbidden",
            "You can nominate only an active eligible organization admin.",
            403,
        )
    _require_active_role(memberships, nominee_id, "admin", status=403)

    at = now()
    if pending is not None:
        if not _seal_expired(db, pending, at):
            raise DomainError(
                "ownership_transfer_pending",
                "Resolve the pending ownership transfer before making another offer.",
                409,
            )
        # Release the partial unique pending-org index before inserting its replacement.
        db.flush()

    transfer = OwnershipTransfer(
        id=uid(),
        org_id=org_id,
        from_user_id=actor_id,
        nominee_id=nominee_id,
        client_key=client_key,
        status="pending",
        version=1,
        created_at=at,
        expires_at=at + TRANSFER_LIFETIME,
    )
    db.add(transfer)
    _audit(db, transfer, "requested", actor_id, at)
    _notify(db, transfer, "requested", nominee_id)
    db.flush()
    return _out(transfer, at)


def decide_transfer(
    db: Session,
    actor_id: str,
    org_id: str,
    transfer_id: str,
    payload: OwnershipTransferDecision,
) -> OwnershipTransferOut:
    actor_id = str(actor_id)
    org_id = str(org_id)
    transfer_id = str(transfer_id)
    action = payload.action

    policy.get_org(db, org_id, lock=True, approved=True)
    transfer = _locked_transfer(db, org_id, transfer_id)
    if transfer is None:
        raise DomainError(
            "ownership_transfer_not_found",
            "Ownership transfer was not found.",
            404,
        )

    expected_actor = transfer.from_user_id if action == "revoke" else transfer.nominee_id
    if actor_id != expected_actor:
        raise DomainError(
            "ownership_transfer_forbidden",
            "You cannot decide this ownership transfer.",
            403,
        )

    if transfer.status != "pending":
        _lock_users(db, [actor_id])
        _require_eligible(db, [actor_id])
        terminal_status = {
            "accept": "accepted",
            "decline": "declined",
            "revoke": "revoked",
        }[action]
        if (
            transfer.status == terminal_status
            and transfer.decided_by == actor_id
            and payload.version + 1 == transfer.version
        ):
            return _out(transfer, now())
        raise DomainError(
            "ownership_transfer_closed",
            "This ownership transfer has already been resolved.",
            409,
        )

    participant_ids = (
        [transfer.from_user_id, transfer.nominee_id]
        if action == "accept"
        else [actor_id]
    )
    memberships = _lock_memberships(db, org_id, participant_ids) if action != "decline" else {}
    _lock_users(db, participant_ids)
    at = now()
    if _seal_expired(db, transfer, at):
        db.flush()
        # The 409 rolls this attempted seal back with the request transaction.
        # A later successful mutation, such as a replacement offer, seals it durably.
        raise DomainError(
            "ownership_transfer_expired",
            "This ownership transfer offer has expired.",
            409,
        )
    if payload.version != transfer.version:
        raise DomainError(
            "ownership_transfer_version_conflict",
            "Refresh the ownership transfer before deciding it.",
            409,
        )

    _require_eligible(db, participant_ids)
    if action == "accept":
        old_owner = _require_active_role(
            memberships, transfer.from_user_id, "owner", status=409
        )
        new_owner = _require_active_role(
            memberships, transfer.nominee_id, "admin", status=409
        )
        if not policy.eligible_user(db, transfer.from_user_id):
            raise DomainError(
                "ownership_transfer_stale",
                "The current owner is no longer eligible to transfer this organization.",
                409,
            )

        old_owner.role = "member"
        policy.audit(
            db,
            org_id,
            actor_id,
            old_owner.user_id,
            "ownership_transferred",
            at,
            old_role="owner",
            new_role="member",
        )
        db.flush()

        new_owner.role = "owner"
        policy.audit(
            db,
            org_id,
            actor_id,
            new_owner.user_id,
            "ownership_transferred",
            at,
            old_role="admin",
            new_role="owner",
        )
        transfer.status = "accepted"
        transfer.version += 1
        transfer.resolved_at = at
        transfer.decided_by = actor_id
        _audit(db, transfer, "accepted", actor_id, at)
        for user_id in (transfer.from_user_id, transfer.nominee_id):
            _notify(db, transfer, "accepted", user_id)
    elif action == "decline":
        transfer.status = "declined"
        transfer.version += 1
        transfer.resolved_at = at
        transfer.decided_by = actor_id
        _audit(db, transfer, "declined", actor_id, at)
        _notify(db, transfer, "declined", transfer.from_user_id)
    else:
        _require_active_role(memberships, transfer.from_user_id, "owner", status=403)
        transfer.status = "revoked"
        transfer.version += 1
        transfer.resolved_at = at
        transfer.decided_by = actor_id
        _audit(db, transfer, "revoked", actor_id, at)
        _notify(db, transfer, "revoked", transfer.nominee_id)

    db.flush()
    return _out(transfer, at)
