"""Additive fictional Phase 2 organizations for explicit local development."""
import sys

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import session_factory
from app.domains.identity.models import User
from app.domains.identity.service import actor_for_user, email_is_eligible
from app.domains.organizations import service as organization_service
from app.domains.organizations.models import AccreditationDecision, Organization, OrgMembership
from app.local_identities import ACCOUNTS, fixture_id


_ADMIN_LABEL = "Fictional platform admin"

ORGANIZATION_FIXTURE_IDS = {
    state: fixture_id(f"phase2:organization:{state}")
    for state in ("pending", "approved", "rejected")
}

_FIXTURES = (
    (
        "pending",
        "Fictional Phase 2 Pending Organization",
        "Fictional organizer",
        None,
        (
            ("Fictional organizer", "owner"),
            ("Fictional student 1", "admin"),
            ("Fictional student 2", "moderator"),
            ("Fictional student 3", "member"),
        ),
    ),
    (
        "approved",
        "Fictional Phase 2 Approved Organization",
        "Fictional student 4",
        "approved",
        (
            ("Fictional student 4", "owner"),
            ("Fictional student 5", "admin"),
            ("Fictional faculty", "member"),
            ("Fictional student 1", "member"),
        ),
    ),
    (
        "rejected",
        "Fictional Phase 2 Rejected Organization",
        "Fictional student 6",
        "rejected",
        (
            ("Fictional student 6", "owner"),
            ("Fictional student 7", "admin"),
            ("Fictional student 8", "moderator"),
            ("Fictional student 9", "member"),
        ),
    ),
)


def membership_fixture_id(organization_key: str, user_label: str) -> str:
    return fixture_id(f"phase2:membership:{organization_key}:{user_label}")


def _fixture_users(db: Session) -> dict[str, User]:
    expected_accounts = {label: (email, admin) for label, email, admin in ACCOUNTS}
    labels = {_ADMIN_LABEL}
    for _, _, owner_label, _, grants in _FIXTURES:
        labels.add(owner_label)
        labels.update(label for label, _ in grants)

    users = {}
    for label in sorted(labels):
        email, expected_admin = expected_accounts[label]
        user = db.get(User, fixture_id(label))
        if user is None:
            raise RuntimeError(f"Predefined local fixture account is missing: {label}")
        if user.email != email:
            raise RuntimeError(f"Fictional fixture identity collision for {label}; account was not changed")
        if user.platform_admin != expected_admin:
            raise RuntimeError(f"Fictional fixture privilege mismatch for {label}; privileges were not changed")
        if user.active is not True or not email_is_eligible(user.email, user.email_verified):
            raise RuntimeError(f"Predefined local fixture account is inactive or ineligible: {label}")
        users[label] = user
    return users


def _preflight(db: Session, users: dict[str, User]):
    organizations = {}
    decisions = {}

    for key, name, owner_label, _, grants in _FIXTURES:
        org_id = ORGANIZATION_FIXTURE_IDS[key]
        organization = db.get(Organization, org_id)
        if organization is not None and (organization.name != name or organization.created_by != users[owner_label].id):
            raise RuntimeError(f"Fictional Phase 2 organization ID collision for {key}; no rows were changed")

        same_name_ids = db.scalars(select(Organization.id).where(Organization.name == name)).all()
        if any(existing_id != org_id for existing_id in same_name_ids):
            raise RuntimeError(f"Fictional Phase 2 organization name collision for {key}; no rows were changed")

        rows = db.scalars(
            select(AccreditationDecision).where(AccreditationDecision.org_id == org_id)
        ).all()
        if len(rows) > 1 or (rows and organization is None):
            raise RuntimeError(f"Fictional Phase 2 decision collision for {key}; no rows were changed")
        decision = rows[0] if rows else None
        if decision is not None:
            admin = db.get(User, decision.admin_id)
            if (
                admin is None
                or admin.active is not True
                or not email_is_eligible(admin.email, admin.email_verified)
                or admin.platform_admin is not True
            ):
                raise RuntimeError("Existing fixture decision does not reference an active eligible platform admin")

        organizations[key] = organization
        decisions[key] = decision

        for label, _ in grants:
            membership = db.get(OrgMembership, membership_fixture_id(key, label))
            if membership is not None and (membership.org_id != org_id or membership.user_id != users[label].id):
                raise RuntimeError(f"Fictional Phase 2 membership ID collision for {key}; no rows were changed")

    return organizations, decisions


def ensure_organizations(db: Session) -> None:
    """Ensure the fixed fixture set without committing or replacing existing state."""
    with db.begin_nested():
        users = _fixture_users(db)
        organizations, decisions = _preflight(db, users)
        new_keys = set()

        for key, name, owner_label, _, _ in _FIXTURES:
            if organizations[key] is None:
                organizations[key] = Organization(
                    id=ORGANIZATION_FIXTURE_IDS[key],
                    name=name,
                    description=f"{name}, used only for local Phase 2 checks.",
                    accreditation_status="pending",
                    created_by=users[owner_label].id,
                )
                db.add(organizations[key])
                new_keys.add(key)

        for key, _, _, _, grants in _FIXTURES:
            if key not in new_keys:
                # A missing grant on an existing fixture can be an intentional removal.
                continue
            org_id = ORGANIZATION_FIXTURE_IDS[key]
            for label, role in grants:
                existing = db.scalar(
                    select(OrgMembership).where(
                        OrgMembership.org_id == org_id,
                        OrgMembership.user_id == users[label].id,
                    )
                )
                if existing is None:
                    db.add(OrgMembership(
                        id=membership_fixture_id(key, label),
                        org_id=org_id,
                        user_id=users[label].id,
                        role=role,
                        active=True,
                    ))

        db.flush()
        admin_actor = actor_for_user(db, users[_ADMIN_LABEL])
        for key, _, _, outcome, _ in _FIXTURES:
            organization = organizations[key]
            if outcome is not None and organization.accreditation_status == "pending" and decisions[key] is None:
                organization_service.decide_accreditation(db, admin_actor, organization.id, outcome)


def main() -> None:
    if len(sys.argv) != 1:
        raise RuntimeError("This command accepts no organization, identity, or database arguments")

    settings = get_settings()
    url = make_url(settings.database_url)
    if (
        settings.environment != "local"
        or settings.fixture_auth is not True
        or url.drivername != "postgresql+psycopg"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.port != 5433
        or url.database != "intraspot_mvp"
    ):
        raise RuntimeError("Organization fixtures require explicit local fixture mode and the development MVP database")

    with session_factory()() as db, db.begin():
        ensure_organizations(db)
    print("Three fixed fictional Phase 2 organizations are ready.")


if __name__ == "__main__":
    main()
