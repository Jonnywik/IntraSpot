from hashlib import sha256

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.models import uid
from app.domains.identity.models import User
from app.domains.identity.service import email_is_eligible
from app.domains.organizations.models import Organization, OrgMembership
from .models import MembershipAudit


def lock_client_key(db: Session, actor_id: str, key: str) -> None:
    lock_id = int.from_bytes(
        sha256(f'intraspot:membership:{actor_id}:{key}'.encode('utf-8')).digest()[:8],
        byteorder='big',
        signed=True,
    )
    db.execute(text('SELECT pg_advisory_xact_lock(:lock_id)'), {'lock_id': lock_id})


def get_org(db: Session, org_id: str, *, lock: bool = False, approved: bool = False) -> Organization:
    query = select(Organization).where(Organization.id == str(org_id))
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    organization = db.scalar(query)
    if organization is None:
        raise DomainError('organization_not_found', 'Organization was not found.', 404)
    if approved and organization.accreditation_status != 'approved':
        raise DomainError('organization_not_approved', 'Approved organization access is required.', 403)
    return organization


def get_user(db: Session, user_id: str) -> User | None:
    return db.scalar(
        select(User)
        .where(User.id == str(user_id), User.active.is_(True))
        .execution_options(populate_existing=True)
    )


def eligible_user(db: Session, user_id: str) -> bool:
    user = get_user(db, user_id)
    return user is not None and email_is_eligible(user.email, user.email_verified)


def membership_for(db: Session, org_id: str, user_id: str) -> OrgMembership | None:
    return db.scalar(
        select(OrgMembership)
        .where(OrgMembership.org_id == str(org_id), OrgMembership.user_id == str(user_id))
        .execution_options(populate_existing=True)
    )


def require_staff(
    db: Session,
    user_id: str,
    org_id: str,
    *,
    roles=('owner', 'admin', 'moderator'),
    lock: bool = False,
) -> tuple[Organization, OrgMembership]:
    organization = get_org(db, org_id, lock=lock, approved=True)
    if not eligible_user(db, user_id):
        raise DomainError('plm_email_required', 'A verified PLM account is required for organization access.', 403)
    membership = db.scalar(
        select(OrgMembership)
        .where(
            OrgMembership.org_id == organization.id,
            OrgMembership.user_id == str(user_id),
            OrgMembership.active.is_(True),
            OrgMembership.role.in_(tuple(roles)),
        )
        .execution_options(populate_existing=True)
    )
    if membership is None:
        raise DomainError('organization_forbidden', 'You do not have permission to manage this organization.', 403)
    return organization, membership


def access_ready(db: Session, org_id: str, user_id: str) -> bool:
    organization = db.scalar(
        select(Organization)
        .where(Organization.id == str(org_id))
        .execution_options(populate_existing=True)
    )
    membership = membership_for(db, org_id, user_id)
    return bool(
        organization is not None
        and organization.accreditation_status == 'approved'
        and membership is not None
        and membership.active
        and eligible_user(db, user_id)
    )


def joined_at(db: Session, org_id: str, user_id: str):
    return db.scalar(
        select(MembershipAudit.created_at)
        .where(
            MembershipAudit.org_id == str(org_id),
            MembershipAudit.user_id == str(user_id),
            MembershipAudit.action == 'membership_granted',
        )
        .order_by(MembershipAudit.created_at.desc(), MembershipAudit.id.desc())
        .limit(1)
    )


def audit(
    db: Session,
    org_id: str,
    actor_id: str | None,
    user_id: str,
    action: str,
    at,
    *,
    old_role: str | None = None,
    new_role: str | None = None,
) -> MembershipAudit:
    row = MembershipAudit(
        id=uid(),
        org_id=str(org_id),
        actor_id=str(actor_id) if actor_id is not None else None,
        user_id=str(user_id),
        action=action,
        old_role=old_role,
        new_role=new_role,
        created_at=at,
    )
    db.add(row)
    return row


def notice(db: Session, org_id: str, user_id: str, kind: str, dedupe_key: str) -> None:
    from app.notifications import notify_in_app

    messages = {
        'membership_approved': 'Your organization membership request was approved.',
        'membership_rejected': 'Your organization membership request was not approved.',
        'membership_invitation': 'You have a new organization membership invitation.',
        'membership_invitation_accepted': 'An organization membership invitation was accepted.',
        'membership_invitation_declined': 'An organization membership invitation was declined.',
        'membership_invitation_revoked': 'An organization membership invitation is no longer available.',
        'membership_left': 'You have left the organization.',
        'membership_removed': 'Your organization membership was removed.',
        'membership_role_changed': 'Your organization membership role was updated.',
    }
    message = messages.get(kind)
    if message is None:
        raise ValueError(f'Unsupported membership notice kind: {kind}')
    notify_in_app(
        db,
        user_id=str(user_id),
        org_id=str(org_id),
        kind=kind,
        message=message,
        dedupe_key=dedupe_key,
    )


def grant_member_locked(db: Session, org_id: str, user_id: str, actor_id: str, at) -> OrgMembership:
    if get_user(db, user_id) is None:
        raise DomainError('membership_user_unavailable', 'This account is no longer available.', 409)
    membership = membership_for(db, org_id, user_id)
    if membership is not None and membership.active:
        return membership
    if membership is None:
        membership = OrgMembership(
            id=uid(),
            org_id=str(org_id),
            user_id=str(user_id),
            role='member',
            active=True,
        )
        db.add(membership)
    else:
        membership.role = 'member'
        membership.active = True
    audit(db, org_id, actor_id, user_id, 'membership_granted', at)
    db.flush()
    return membership
