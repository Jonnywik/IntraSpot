from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.errors import DomainError
from app.db.models import now
from app.domains.events.models import Event
from app.domains.organizations.models import Organization
from app.domains.registrations.models import Registration
from app.local_flash import FLASH_EVENT_ID, ensure_flash_fixture, main
from app.local_identities import ensure_users
from app.local_organizations import ORGANIZATION_FIXTURE_IDS, ensure_organizations


def seed_organizations(db):
    ensure_users(db)
    db.flush()
    ensure_organizations(db)
    db.commit()


def test_local_flash_is_additive_and_does_not_renew_or_overwrite(db):
    seed_organizations(db)
    ensure_flash_fixture(db)
    db.commit()
    event = db.get(Event, FLASH_EVENT_ID)
    assert event.event_type == "flash" and event.registration_mode == "instant"
    assert event.review_window_minutes is None
    assert timedelta(0) < event.starts_at - event.published_at <= timedelta(hours=24)
    assert event.tags == ["community"] and event.coarse_area == "intramuros"
    event.title = "Fictional preserved owner edit"
    event.published_at = now() - timedelta(hours=4)
    db.commit()
    original = (event.title, event.starts_at, event.ends_at, event.published_at)
    ensure_flash_fixture(db)
    db.commit()
    db.refresh(event)
    assert (event.title, event.starts_at, event.ends_at, event.published_at) == original
    assert db.scalar(select(func.count()).select_from(Event)) == 1
    assert db.scalar(select(func.count()).select_from(Registration)) == 0


def test_local_flash_rejects_foreign_fixed_id(db, make_event):
    seed_organizations(db)
    event = make_event(id=FLASH_EVENT_ID)
    original = (event.org_id, event.created_by, event.title)
    with pytest.raises(RuntimeError, match="collision"):
        ensure_flash_fixture(db)
    db.refresh(event)
    assert (event.org_id, event.created_by, event.title) == original


def test_local_flash_never_bypasses_accreditation(db):
    seed_organizations(db)
    organization = db.get(Organization, ORGANIZATION_FIXTURE_IDS["approved"])
    organization.accreditation_status = "pending"
    db.commit()
    with pytest.raises(DomainError):
        ensure_flash_fixture(db)
    assert db.get(Event, FLASH_EVENT_ID) is None


def test_local_flash_cli_refuses_the_test_environment(monkeypatch):
    monkeypatch.setattr("sys.argv", ["local_flash"])
    with pytest.raises(RuntimeError, match="explicit local mode"):
        main()
