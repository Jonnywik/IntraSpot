from datetime import timedelta
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.models import now
from app.db.session import engine
from app.domains.events import service as event_service
from app.domains.events.models import Event
from app.domains.identity.models import User
from app.domains.organizations.models import Organization, OrgMembership
from app.domains.registrations.models import Registration, RegistrationReceipt
from app.local_events import EVENT_FIXTURE_IDS, ensure_events, main
from app.local_identities import ensure_users, fixture_id
from app.local_organizations import ORGANIZATION_FIXTURE_IDS, ensure_organizations


def _seed_phase_two(db):
    ensure_users(db)
    db.commit()
    ensure_organizations(db)
    db.commit()


def _count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def _event_snapshot(event):
    fields = (
        "org_id", "created_by", "title", "summary", "description", "starts_at", "ends_at",
        "venue_name", "venue_address", "capacity", "banner_key", "cost_label", "status",
        "registration_mode", "event_type", "published_at",
        "tags", "coarse_area",
    )
    return tuple(getattr(event, field) for field in fields)


def test_ensure_events_creates_pending_draft_and_approved_public_events_without_registrations(db):
    _seed_phase_two(db)

    ensure_events(db)
    db.commit()

    assert _count(db, Event) == 3
    draft = db.get(Event, EVENT_FIXTURE_IDS["pending_draft"])
    assert draft.org_id == ORGANIZATION_FIXTURE_IDS["pending"]
    assert draft.created_by == fixture_id("Fictional organizer")
    assert draft.status == "draft" and draft.published_at is None
    assert draft.title is None and draft.description is None and draft.summary == ""
    assert draft.starts_at is None and draft.ends_at is None
    assert draft.venue_name is None and draft.venue_address is None

    public_events = [
        db.get(Event, EVENT_FIXTURE_IDS[key])
        for key in ("heritage_walk", "garden_workday")
    ]
    assert {event.org_id for event in public_events} == {ORGANIZATION_FIXTURE_IDS["approved"]}
    assert {event.status for event in public_events} == {"published"}
    assert all(event.published_at is not None for event in public_events)
    assert all(event.starts_at > now() and event.ends_at > event.starts_at for event in public_events)
    assert all(event.registration_mode == "instant" and event.event_type == "scheduled" for event in public_events)
    assert {event.title for event in public_events} == {"Community Heritage Walk", "Campus Garden Workday"}
    assert _count(db, Registration) == 0
    assert _count(db, RegistrationReceipt) == 0


def test_rerun_preserves_draft_edits_public_lifecycle_and_all_fixture_rows(db):
    _seed_phase_two(db)
    ensure_events(db)
    db.commit()

    draft = db.get(Event, EVENT_FIXTURE_IDS["pending_draft"])
    draft.title = "Organizer-edited local draft"
    draft.summary = "Keep this draft edit."
    ended = db.get(Event, EVENT_FIXTURE_IDS["heritage_walk"])
    ended.starts_at = now() - timedelta(days=2)
    ended.ends_at = ended.starts_at + timedelta(hours=2)
    ended.summary = "Keep this published event history."
    ended.tags = ["organizer-chosen"]
    ended.coarse_area = "chosen broad area"
    db.commit()
    before = {
        key: _event_snapshot(db.get(Event, event_id))
        for key, event_id in EVENT_FIXTURE_IDS.items()
    }

    ensure_events(db)
    db.commit()

    after = {
        key: _event_snapshot(db.get(Event, event_id))
        for key, event_id in EVENT_FIXTURE_IDS.items()
    }
    assert after == before
    assert _count(db, Event) == 3
    assert db.get(Event, EVENT_FIXTURE_IDS["pending_draft"]).status == "draft"
    assert db.get(Event, EVENT_FIXTURE_IDS["heritage_walk"]).status == "published"


def test_fixed_event_id_collision_is_rejected_before_any_fixture_creation(db):
    _seed_phase_two(db)
    collision = Event(
        id=EVENT_FIXTURE_IDS["heritage_walk"],
        org_id=ORGANIZATION_FIXTURE_IDS["pending"],
        created_by=fixture_id("Fictional student 4"),
        title="Preserve this unrelated row",
        summary="",
        status="draft",
    )
    db.add(collision)
    db.commit()

    with pytest.raises(RuntimeError, match="event ID collision"):
        ensure_events(db)

    assert _count(db, Event) == 1
    assert db.get(Event, collision.id).title == "Preserve this unrelated row"


def test_phase_two_organization_id_collision_is_not_overwritten(db):
    ensure_users(db)
    db.commit()
    collision = Organization(
        id=ORGANIZATION_FIXTURE_IDS["pending"],
        name="Unrelated fictional organization",
        description="Preserve this row.",
        accreditation_status="pending",
        created_by=fixture_id("Fictional organizer"),
    )
    db.add(collision)
    db.commit()

    with pytest.raises(RuntimeError, match="organization ID collision"):
        ensure_events(db)

    assert db.get(Organization, collision.id).name == "Unrelated fictional organization"
    assert _count(db, Event) == 0


def test_current_manager_membership_is_required_for_a_new_draft(db):
    _seed_phase_two(db)
    owner_membership = db.scalar(select(OrgMembership).where(
        OrgMembership.org_id == ORGANIZATION_FIXTURE_IDS["pending"],
        OrgMembership.user_id == fixture_id("Fictional organizer"),
    ))
    owner_membership.active = False
    db.commit()

    with pytest.raises(DomainError) as error:
        ensure_events(db)

    assert error.value.code == "organization_forbidden"
    assert _count(db, Event) == 0


def test_ineligible_predefined_owner_cannot_create_event_fixtures(db):
    _seed_phase_two(db)
    owner = db.get(User, fixture_id("Fictional student 4"))
    owner.email_verified = False
    db.commit()

    with pytest.raises(RuntimeError, match="inactive or ineligible"):
        ensure_events(db)

    assert _count(db, Event) == 0


def test_unapproved_organization_cannot_publish_fixture_events(db):
    _seed_phase_two(db)
    approved = db.get(Organization, ORGANIZATION_FIXTURE_IDS["approved"])
    approved.accreditation_status = "pending"
    db.commit()

    with pytest.raises(DomainError) as error:
        ensure_events(db)

    assert error.value.code == "organization_not_approved"
    assert _count(db, Event) == 0


def test_rejected_organization_cannot_receive_the_pending_draft_fixture(db):
    _seed_phase_two(db)
    pending = db.get(Organization, ORGANIZATION_FIXTURE_IDS["pending"])
    pending.accreditation_status = "rejected"
    db.commit()

    with pytest.raises(DomainError) as error:
        ensure_events(db)

    assert error.value.code == "organization_rejected_read_only"
    assert _count(db, Event) == 0


def test_pending_draft_rejects_concurrent_accreditation_change_after_lock_refresh(db):
    _seed_phase_two(db)
    pending = db.get(Organization, ORGANIZATION_FIXTURE_IDS["pending"])
    assert pending.accreditation_status == "pending"

    with Session(engine(), expire_on_commit=False) as concurrent_db:
        changed = concurrent_db.get(Organization, pending.id)
        changed.accreditation_status = "rejected"
        concurrent_db.commit()

    assert pending.accreditation_status == "pending"
    with pytest.raises(DomainError) as error:
        ensure_events(db)

    assert error.value.code == "organization_rejected_read_only"
    assert _count(db, Event) == 0


def test_publish_failure_rolls_back_all_missing_event_fixtures(db, monkeypatch):
    _seed_phase_two(db)
    original_publish = event_service.publish

    def fail_on_second_public_event(session, event):
        if event.id == EVENT_FIXTURE_IDS["garden_workday"]:
            raise RuntimeError("simulated publish failure")
        return original_publish(session, event)

    monkeypatch.setattr(event_service, "publish", fail_on_second_public_event)
    with pytest.raises(RuntimeError, match="simulated publish failure"):
        ensure_events(db)

    assert _count(db, Event) == 0


def test_main_rejects_arbitrary_cli_arguments_before_loading_settings(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["app.local_events", "--database-url", "postgresql://other"])
    monkeypatch.setattr("app.local_events.get_settings", lambda: pytest.fail("settings must not be loaded"))

    with pytest.raises(RuntimeError, match="accepts no event, organization, identity, or database arguments"):
        main()


@pytest.mark.parametrize(
    ("environment", "fixture_auth", "database_url"),
    [
        ("test", True, "postgresql+psycopg://local:local@127.0.0.1:5433/intraspot_mvp"),
        ("local", False, "postgresql+psycopg://local:local@127.0.0.1:5433/intraspot_mvp"),
        ("local", True, "postgresql://local:local@127.0.0.1:5433/intraspot_mvp"),
        ("local", True, "postgresql+psycopg://local:local@db.example:5433/intraspot_mvp"),
        ("local", True, "postgresql+psycopg://local:local@127.0.0.1:5432/intraspot_mvp"),
        ("local", True, "postgresql+psycopg://local:local@127.0.0.1:5433/intraspot_mvp_test"),
        ("local", True, "postgresql+psycopg://local:local@127.0.0.1:5433/penpot"),
    ],
)
def test_main_requires_explicit_local_fixture_mode_and_development_loopback_database(
    monkeypatch, environment, fixture_auth, database_url,
):
    monkeypatch.setattr(sys, "argv", ["app.local_events"])
    monkeypatch.setattr(
        "app.local_events.get_settings",
        lambda: SimpleNamespace(environment=environment, fixture_auth=fixture_auth, database_url=database_url),
    )
    monkeypatch.setattr("app.local_events.session_factory", lambda: pytest.fail("database must not be opened"))

    with pytest.raises(RuntimeError, match="explicit local fixture mode and the development MVP database"):
        main()
