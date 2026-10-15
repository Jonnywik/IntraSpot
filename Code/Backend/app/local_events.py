"""Additive fictional Sprint 3 events for explicit local development."""
import sys
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.config import get_settings
from app.db.models import now
from app.db.session import session_factory
from app.domains.events import service as event_service
from app.domains.events.models import Event
from app.domains.identity.models import User
from app.domains.identity.service import actor_for_user, email_is_eligible
from app.domains.organizations import service as organization_service
from app.domains.organizations.models import Organization
from app.local_identities import ACCOUNTS, fixture_id
from app.local_organizations import ORGANIZATION_FIXTURE_IDS


_ORGANIZATIONS = {
    "pending": ("Fictional Phase 2 Pending Organization", "Fictional organizer"),
    "approved": ("Fictional Phase 2 Approved Organization", "Fictional student 4"),
    "rejected": ("Fictional Phase 2 Rejected Organization", "Fictional student 6"),
}

_EVENT_FIXTURES = (
    {
        "key": "pending_draft",
        "organization": "pending",
        "owner": "Fictional organizer",
        "fields": {
            "title": None,
            "summary": "",
            "description": None,
            "starts_at": None,
            "ends_at": None,
            "venue_name": None,
            "venue_address": None,
            "capacity": None,
            "banner_key": None,
        },
    },
    {
        "key": "heritage_walk",
        "organization": "approved",
        "owner": "Fictional student 4",
        "starts_in_days": 14,
        "duration": timedelta(hours=2),
        "fields": {
            "title": "Community Heritage Walk",
            "summary": "",
            "description": "A fictional scheduled event for the local discovery demonstration.",
            "venue_name": "Sample Heritage Courtyard",
            "venue_address": "Fictional local-demo address, Manila",
            "capacity": 24,
            "banner_key": "heritage",
            "cost_label": "Free",
        },
    },
    {
        "key": "garden_workday",
        "organization": "approved",
        "owner": "Fictional student 4",
        "starts_in_days": 28,
        "duration": timedelta(hours=3),
        "fields": {
            "title": "Campus Garden Workday",
            "summary": "A small fictional community event for public discovery.",
            "description": "A fictional scheduled garden activity used in the local demo.",
            "venue_name": "Sample Community Garden",
            "venue_address": "Fictional local-demo address, Manila",
            "capacity": 16,
            "banner_key": "garden",
            "cost_label": "Free",
        },
    },
)

EVENT_FIXTURE_IDS = {
    fixture["key"]: fixture_id(f"sprint3:event:{fixture['key']}")
    for fixture in _EVENT_FIXTURES
}


def _preflight_organizations(db: Session) -> dict[str, Organization]:
    organizations = {}
    for key, (name, owner_label) in _ORGANIZATIONS.items():
        org_id = ORGANIZATION_FIXTURE_IDS[key]
        organization = db.get(Organization, org_id)
        if organization is None:
            raise RuntimeError(f"Predefined Phase 2 organization is missing: {key}")
        if organization.name != name or organization.created_by != fixture_id(owner_label):
            raise RuntimeError(f"Fictional Phase 2 organization ID collision for {key}; no events were changed")

        same_name_ids = db.scalars(select(Organization.id).where(Organization.name == name)).all()
        if any(existing_id != org_id for existing_id in same_name_ids):
            raise RuntimeError(f"Fictional Phase 2 organization name collision for {key}; no events were changed")
        organizations[key] = organization
    return organizations


def _fixture_user(db: Session, label: str) -> User:
    account = next((account for account in ACCOUNTS if account[0] == label), None)
    if account is None:
        raise RuntimeError(f"Unknown predefined fixture identity: {label}")
    _, email, platform_admin = account
    user = db.get(User, fixture_id(label))
    if user is None:
        raise RuntimeError(f"Predefined local fixture account is missing: {label}")
    if user.email != email or user.platform_admin is not platform_admin:
        raise RuntimeError(f"Fictional fixture identity collision or privilege mismatch for {label}")
    if user.active is not True or not email_is_eligible(user.email, user.email_verified):
        raise RuntimeError(f"Predefined local fixture account is inactive or ineligible: {label}")
    return user


def _preflight_events(db: Session, organizations: dict[str, Organization]):
    missing = []
    for fixture in _EVENT_FIXTURES:
        key = fixture["key"]
        org_id = organizations[fixture["organization"]].id
        creator_id = fixture_id(fixture["owner"])
        event = db.get(Event, EVENT_FIXTURE_IDS[key])
        if event is not None:
            if event.org_id != org_id or event.created_by != creator_id:
                raise RuntimeError(f"Fictional event ID collision for {key}; no events were changed")
            continue

        title = fixture["fields"].get("title")
        if title is not None:
            same_title_ids = db.scalars(
                select(Event.id).where(Event.org_id == org_id, Event.title == title)
            ).all()
            if same_title_ids:
                raise RuntimeError(f"Fictional event title collision for {key}; no events were changed")
        missing.append(fixture)
    return missing


def ensure_events(db: Session) -> None:
    """Add missing fixed fixtures while preserving every existing event field."""
    with db.begin_nested():
        organizations = _preflight_organizations(db)
        missing = _preflight_events(db, organizations)
        if not missing:
            return

        users = {label: _fixture_user(db, label) for label in {fixture["owner"] for fixture in missing}}
        actors = {label: actor_for_user(db, user) for label, user in users.items()}

        for fixture in missing:
            organization = organizations[fixture["organization"]]
            actor = actors[fixture["owner"]]
            if fixture["key"] == "pending_draft":
                organization = organization_service.require_manager(
                    db, actor, organization.id, lock=True
                )
                if organization.accreditation_status == "rejected":
                    raise DomainError(
                        "organization_rejected_read_only",
                        "Rejected organizations cannot change event drafts.",
                        409,
                    )
                if organization.accreditation_status != "pending":
                    raise RuntimeError("The incomplete draft fixture requires the predefined pending organization")
            else:
                organization_service.require_publishing(db, actor, organization.id)

        seeded_at = now()
        for fixture in missing:
            organization = organizations[fixture["organization"]]
            fields = dict(fixture["fields"])
            if "starts_in_days" in fixture:
                fields["starts_at"] = seeded_at + timedelta(days=fixture["starts_in_days"])
                fields["ends_at"] = fields["starts_at"] + fixture["duration"]
            event = Event(
                id=EVENT_FIXTURE_IDS[fixture["key"]],
                org_id=organization.id,
                created_by=actors[fixture["owner"]].user_id,
                status="draft",
                published_at=None,
                registration_mode="instant",
                event_type="scheduled",
                **fields,
            )
            db.add(event)
            if "starts_in_days" in fixture:
                event_service.publish(db, event)


def main() -> None:
    if len(sys.argv) != 1:
        raise RuntimeError("This command accepts no event, organization, identity, or database arguments")

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
        raise RuntimeError("Event fixtures require explicit local fixture mode and the development MVP database")

    with session_factory()() as db, db.begin():
        ensure_events(db)
    print("One fictional pending draft and two approved public event fixtures are ready.")


if __name__ == "__main__":
    main()
