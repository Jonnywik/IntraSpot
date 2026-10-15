import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts import Actor, OrgGrant
from app.domains.identity.models import User


_PLM_EMAIL_DOMAIN = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*plm\.edu\.ph\Z", re.ASCII)


def email_is_eligible(email: str | None, email_verified: bool) -> bool:
    if email_verified is not True or not isinstance(email, str) or email.count("@") != 1:
        return False
    local_part, domain = email.strip().rsplit("@", 1)
    return bool(local_part and _PLM_EMAIL_DOMAIN.fullmatch(domain.casefold()))


def profile_is_complete(user: User) -> bool:
    tags = user.tags if isinstance(user.tags, list) else []
    return bool(
        isinstance(user.nickname, str)
        and user.nickname.strip()
        and isinstance(user.age_bracket, str)
        and user.age_bracket.strip()
        and any(isinstance(tag, str) and tag.strip() for tag in tags)
    )


def active_grants(db: Session, user_id: str) -> tuple[OrgGrant, ...]:
    # Imported at request time to keep identity independent of organization startup order.
    from app.domains.organizations.models import OrgMembership, Organization

    user = db.get(User, user_id)
    if user is None or not user.active or not email_is_eligible(user.email, user.email_verified):
        return ()
    rows = db.execute(
        select(Organization, OrgMembership)
        .join(OrgMembership, OrgMembership.org_id == Organization.id)
        .where(OrgMembership.user_id == user_id, OrgMembership.active.is_(True))
        .order_by(Organization.name, Organization.id)
    ).all()
    return tuple(
        OrgGrant(
            org_id=str(organization.id),
            org_name=organization.name,
            role=membership.role,
            accreditation_status=organization.accreditation_status,
        )
        for organization, membership in rows
    )


def actor_for_user(db: Session, user: User) -> Actor:
    from app.domains.moderation.service import has_pending_person_report

    return Actor(
        user_id=user.id,
        nickname=user.nickname,
        eligible=email_is_eligible(user.email, user.email_verified),
        profile_complete=profile_is_complete(user),
        platform_admin=bool(user.platform_admin),
        grants=active_grants(db, user.id),
        communication_restricted=has_pending_person_report(db, user.id),
    )


def get_active_user(db: Session, user_id: str) -> User | None:
    user = db.get(User, user_id)
    return user if user is not None and user.active else None


def get_profile_user(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def update_profile(db: Session, user_id: str, changes: dict[str, object]) -> User | None:
    user = get_active_user(db, user_id)
    if user is None:
        return None
    for field, value in changes.items():
        setattr(user, field, value)
    return user
