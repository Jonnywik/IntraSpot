from datetime import datetime, timezone
import re
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import event, func, select

from app.domains.events.models import Event
from app.domains.identity.models import User
from app.domains.identity.service import actor_for_user
from app.domains.organizations import service as organization_service
from app.domains.organizations.models import AccreditationDecision, Organization, OrgMembership
from app.domains.registrations.models import Registration
from app.local_identities import ensure_users, fixture_id
from app.local_organizations import (
    ORGANIZATION_FIXTURE_IDS,
    ensure_organizations,
    main,
    membership_fixture_id,
)


def _seed_local_identities(db):
    ensure_users(db)
    db.commit()


def _membership(db, organization_id, label):
    return db.scalar(select(OrgMembership).where(
        OrgMembership.org_id == organization_id,
        OrgMembership.user_id == fixture_id(label),
    ))


def _count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_ensure_organizations_creates_audited_fixtures_without_other_table_writes(db):
    _seed_local_identities(db)
    users_before = [
        (user.id, user.email, user.email_verified, user.active, user.platform_admin, user.nickname,
         user.age_bracket, user.tags, user.persona_visible)
        for user in db.scalars(select(User).order_by(User.id))
    ]
    writes = set()

    def capture_write(_connection, _cursor, statement, _parameters, _context, _executemany):
        match = re.match(r"\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([^\s(]+)", statement, re.IGNORECASE)
        if match:
            writes.add(match.group(1).strip('"').split(".")[-1].strip('"').lower())

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", capture_write)
    try:
        ensure_organizations(db)
        db.commit()
    finally:
        event.remove(bind, "before_cursor_execute", capture_write)

    organizations = {
        key: db.get(Organization, organization_id)
        for key, organization_id in ORGANIZATION_FIXTURE_IDS.items()
    }
    assert {key: org.name for key, org in organizations.items()} == {
        "pending": "Fictional Phase 2 Pending Organization",
        "approved": "Fictional Phase 2 Approved Organization",
        "rejected": "Fictional Phase 2 Rejected Organization",
    }
    assert {key: org.accreditation_status for key, org in organizations.items()} == {
        "pending": "pending",
        "approved": "approved",
        "rejected": "rejected",
    }
    decisions = list(db.scalars(select(AccreditationDecision)))
    assert len(decisions) == 2
    assert {(decision.org_id, decision.outcome, decision.admin_id) for decision in decisions} == {
        (ORGANIZATION_FIXTURE_IDS["approved"], "approved", fixture_id("Fictional platform admin")),
        (ORGANIZATION_FIXTURE_IDS["rejected"], "rejected", fixture_id("Fictional platform admin")),
    }

    grants = list(db.scalars(select(OrgMembership)))
    assert len(grants) == 12
    assert {grant.role for grant in grants} == {"owner", "admin", "moderator", "member"}
    assert all(grant.active for grant in grants)
    faculty_grant = _membership(db, ORGANIZATION_FIXTURE_IDS["approved"], "Fictional faculty")
    assert faculty_grant is not None and faculty_grant.role == "member" and faculty_grant.active
    student = db.get(User, fixture_id("Fictional student 1"))
    assert set(organization_service.active_club_ids(db, actor_for_user(db, student))) == {
        ORGANIZATION_FIXTURE_IDS["pending"], ORGANIZATION_FIXTURE_IDS["approved"],
    }
    assert set(writes) == {"organizations", "org_memberships", "accreditation_decisions"}
    assert _count(db, Event) == 0
    assert _count(db, Registration) == 0
    users_after = [
        (user.id, user.email, user.email_verified, user.active, user.platform_admin, user.nickname,
         user.age_bracket, user.tags, user.persona_visible)
        for user in db.scalars(select(User).order_by(User.id))
    ]
    assert users_after == users_before


def test_rerun_preserves_fixture_decision_and_membership_edits(db):
    _seed_local_identities(db)
    ensure_organizations(db)
    db.commit()

    approved = db.get(Organization, ORGANIZATION_FIXTURE_IDS["approved"])
    decision = db.scalar(select(AccreditationDecision).where(
        AccreditationDecision.org_id == approved.id,
    ))
    decision_id = decision.id
    decision_time = datetime(2025, 1, 2, tzinfo=timezone.utc)
    approved.accreditation_status = "rejected"
    decision.outcome = "rejected"
    decision.decided_at = decision_time

    student_grant = _membership(db, ORGANIZATION_FIXTURE_IDS["pending"], "Fictional student 3")
    student_grant.role = "moderator"
    student_grant.active = False
    removed_grant = _membership(db, ORGANIZATION_FIXTURE_IDS["rejected"], "Fictional student 9")
    db.delete(removed_grant)
    db.commit()

    ensure_organizations(db)
    db.commit()

    assert approved.accreditation_status == "rejected"
    preserved_decision = db.get(AccreditationDecision, decision_id)
    assert preserved_decision.outcome == "rejected"
    assert preserved_decision.decided_at == decision_time
    assert preserved_decision.admin_id == fixture_id("Fictional platform admin")
    preserved_grant = _membership(db, ORGANIZATION_FIXTURE_IDS["pending"], "Fictional student 3")
    assert preserved_grant.role == "moderator" and not preserved_grant.active
    assert _membership(db, ORGANIZATION_FIXTURE_IDS["rejected"], "Fictional student 9") is None
    assert _count(db, Organization) == 3
    assert _count(db, OrgMembership) == 11
    assert _count(db, AccreditationDecision) == 2


def test_identity_collision_is_rejected_without_overwriting_or_creating_organizations(db):
    _seed_local_identities(db)
    student = db.get(User, fixture_id("Fictional student 1"))
    student.email = "different@example.invalid"
    db.commit()

    with pytest.raises(RuntimeError, match="identity collision"):
        ensure_organizations(db)

    assert student.email == "different@example.invalid"
    assert _count(db, Organization) == 0
    assert _count(db, OrgMembership) == 0
    assert _count(db, AccreditationDecision) == 0


@pytest.mark.parametrize(
    ("label", "field", "value", "message"),
    [
        ("Fictional faculty", "active", False, "inactive or ineligible"),
        ("Fictional faculty", "email_verified", False, "inactive or ineligible"),
        ("Fictional platform admin", "platform_admin", False, "privilege mismatch"),
    ],
)
def test_referenced_accounts_must_remain_eligible_and_admin_privileges_are_not_elevated(
    db, label, field, value, message,
):
    _seed_local_identities(db)
    account = db.get(User, fixture_id(label))
    setattr(account, field, value)
    db.commit()

    with pytest.raises(RuntimeError, match=message):
        ensure_organizations(db)

    assert getattr(account, field) == value
    assert _count(db, Organization) == 0
    assert _count(db, OrgMembership) == 0
    assert _count(db, AccreditationDecision) == 0


def test_missing_predefined_account_is_rejected_without_creating_organizations(db):
    _seed_local_identities(db)
    db.delete(db.get(User, fixture_id("Fictional faculty")))
    db.commit()

    with pytest.raises(RuntimeError, match="account is missing"):
        ensure_organizations(db)

    assert _count(db, Organization) == 0
    assert _count(db, OrgMembership) == 0
    assert _count(db, AccreditationDecision) == 0


def test_fixed_organization_id_collision_is_rejected_without_overwriting(db):
    _seed_local_identities(db)
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
        ensure_organizations(db)

    assert db.get(Organization, collision.id).name == "Unrelated fictional organization"
    assert _count(db, Organization) == 1
    assert _count(db, OrgMembership) == 0
    assert _count(db, AccreditationDecision) == 0


def test_fixed_membership_id_collision_is_rejected_without_overwriting(db):
    _seed_local_identities(db)
    decoy = Organization(
        name="Unrelated fictional organization",
        description="Preserve this row.",
        accreditation_status="pending",
        created_by=fixture_id("Fictional organizer"),
    )
    db.add(decoy)
    db.flush()
    collision = OrgMembership(
        id=membership_fixture_id("pending", "Fictional student 1"),
        org_id=decoy.id,
        user_id=fixture_id("Fictional student 1"),
        role="member",
        active=True,
    )
    db.add(collision)
    db.commit()

    with pytest.raises(RuntimeError, match="membership ID collision"):
        ensure_organizations(db)

    assert db.get(OrgMembership, collision.id).org_id == decoy.id
    assert _count(db, Organization) == 1
    assert _count(db, OrgMembership) == 1
    assert _count(db, AccreditationDecision) == 0


def test_fixture_creation_rolls_back_if_an_accreditation_decision_fails(db, monkeypatch):
    _seed_local_identities(db)
    decide = organization_service.decide_accreditation

    def fail_on_rejection(session, actor, org_id, outcome):
        if outcome == "rejected":
            raise RuntimeError("simulated decision failure")
        return decide(session, actor, org_id, outcome)

    monkeypatch.setattr(organization_service, "decide_accreditation", fail_on_rejection)
    with pytest.raises(RuntimeError, match="simulated decision failure"):
        ensure_organizations(db)

    assert _count(db, Organization) == 0
    assert _count(db, OrgMembership) == 0
    assert _count(db, AccreditationDecision) == 0


def test_main_rejects_arbitrary_cli_arguments_before_loading_settings(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["app.local_organizations", "--database-url", "postgresql://other"])
    monkeypatch.setattr("app.local_organizations.get_settings", lambda: pytest.fail("settings must not be loaded"))

    with pytest.raises(RuntimeError, match="accepts no organization, identity, or database arguments"):
        main()


@pytest.mark.parametrize(
    ("environment", "fixture_auth", "database_url"),
    [
        ("test", True, "postgresql+psycopg://local:local@127.0.0.1:5433/intraspot_mvp"),
        ("local", False, "postgresql+psycopg://local:local@127.0.0.1:5433/intraspot_mvp"),
        ("local", True, "postgresql+psycopg://local:local@127.0.0.1:5433/intraspot_mvp_test"),
        ("local", True, "postgresql+psycopg://local:local@db.example:5433/intraspot_mvp"),
    ],
)
def test_main_requires_explicit_local_fixture_mode_and_named_loopback_mvp_database(
    monkeypatch, environment, fixture_auth, database_url,
):
    monkeypatch.setattr(sys, "argv", ["app.local_organizations"])
    monkeypatch.setattr(
        "app.local_organizations.get_settings",
        lambda: SimpleNamespace(environment=environment, fixture_auth=fixture_auth, database_url=database_url),
    )
    monkeypatch.setattr("app.local_organizations.session_factory", lambda: pytest.fail("database must not be opened"))

    with pytest.raises(RuntimeError, match="explicit local fixture mode and the development MVP database"):
        main()
