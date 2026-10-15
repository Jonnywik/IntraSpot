from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.models import now, uid
from .models import AccreditationDecision, Organization, OrgMembership

MANAGER_ROLES = ('owner', 'admin')


def _require_eligible(actor: Actor) -> None:
    if not actor.eligible:
        raise DomainError('organization_forbidden', 'Eligible IntraSpot access is required.', 403)


def get_organization(db: Session, org_id: str, *, lock: bool = False) -> Organization:
    if lock:
        organization = db.scalar(
            select(Organization)
            .where(Organization.id == org_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    else:
        organization = db.get(Organization, org_id)
    if organization is None:
        raise DomainError('organization_not_found', 'Organization was not found.', 404)
    return organization


def require_manager_membership(
    db: Session,
    actor: Actor,
    org_id: str,
    *,
    lock: bool = False,
) -> tuple[Organization, OrgMembership]:
    _require_eligible(actor)
    organization = get_organization(db, org_id, lock=lock)
    membership = db.scalar(select(OrgMembership).where(
        OrgMembership.org_id == org_id,
        OrgMembership.user_id == actor.user_id,
        OrgMembership.active.is_(True),
        OrgMembership.role.in_(MANAGER_ROLES),
    ))
    if membership is None:
        raise DomainError('organization_forbidden', 'You do not have access to this organization workspace.', 403)
    return organization, membership


def require_manager(db: Session, actor: Actor, org_id: str, *, lock: bool = False) -> Organization:
    return require_manager_membership(db, actor, org_id, lock=lock)[0]


def active_club_ids(db: Session, actor: Actor) -> list[str]:
    if not actor.eligible:
        return []
    return list(db.scalars(select(OrgMembership.org_id).where(
        OrgMembership.user_id == actor.user_id,
        OrgMembership.active.is_(True),
    ).order_by(OrgMembership.org_id)))


def require_publishing(db: Session, actor: Actor, org_id: str) -> Organization:
    organization = require_manager(db, actor, org_id, lock=True)
    if organization.accreditation_status != 'approved':
        raise DomainError('organization_not_approved', 'Organization approval is required to publish.', 403)
    return organization


def create_organization(db: Session, actor: Actor, *, name: str, description: str) -> Organization:
    _require_eligible(actor)
    organization = Organization(
        id=uid(),
        name=name,
        description=description,
        accreditation_status='pending',
        created_by=actor.user_id,
    )
    db.add(organization)
    db.flush()
    db.add(OrgMembership(
        id=uid(), org_id=organization.id, user_id=actor.user_id,
        role='owner', active=True,
    ))
    db.flush()
    return organization


def active_memberships(db: Session, actor: Actor) -> list[tuple[Organization, OrgMembership]]:
    if not actor.eligible:
        return []
    return list(db.execute(
        select(Organization, OrgMembership)
        .join(OrgMembership, OrgMembership.org_id == Organization.id)
        .where(OrgMembership.user_id == actor.user_id, OrgMembership.active.is_(True))
        .order_by(Organization.name, Organization.id)
    ).tuples())


def require_platform_admin(db: Session, actor: Actor):
    _require_eligible(actor)
    from app.domains.identity.models import User
    from app.domains.identity.service import email_is_eligible

    user = db.scalar(
        select(User)
        .where(User.id == actor.user_id)
        .execution_options(populate_existing=True)
    )
    if (
        user is None
        or not user.active
        or not user.platform_admin
        or not email_is_eligible(user.email, user.email_verified)
    ):
        raise DomainError('platform_admin_required', 'Platform admin access is required.', 403)
    return user


def list_applications(db: Session, actor: Actor) -> list[Organization]:
    require_platform_admin(db, actor)
    return list(db.scalars(select(Organization).order_by(Organization.created_at.desc(), Organization.id)))


def decisions_for(db: Session, org_id: str) -> list[AccreditationDecision]:
    return list(db.scalars(select(AccreditationDecision).where(
        AccreditationDecision.org_id == org_id,
    ).order_by(AccreditationDecision.decided_at, AccreditationDecision.id)))


def decide_accreditation(db: Session, actor: Actor, org_id: str, outcome: str) -> Organization:
    require_platform_admin(db, actor)
    if outcome not in {'approved', 'rejected'}:
        raise DomainError('invalid_accreditation_outcome', 'Choose an approval or rejection outcome.', 422)

    organization = db.scalar(
        select(Organization)
        .where(Organization.id == org_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if organization is None:
        raise DomainError('organization_not_found', 'Organization was not found.', 404)
    if organization.accreditation_status != 'pending':
        raise DomainError('accreditation_decision_closed', 'This organization already has a terminal decision.', 409)

    organization.accreditation_status = outcome
    db.add(AccreditationDecision(
        id=uid(),
        org_id=organization.id,
        outcome=outcome,
        admin_id=actor.user_id,
        decided_at=now(),
    ))
    db.flush()
    return organization
