"""Opt-in Sprint 11 mobile journeys against the isolated serial test database."""

from datetime import timedelta, datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.communication_schemas import ContentCreate
from app.core.config import ROOT, get_settings
from app.db.models import now, uid
from app.domains.chat.service import send_chat_message
from app.domains.identity.models import User
from app.domains.organizations.models import OrgMembership
from app.domains.registrations.service import submit_registration
from app.local_identities import ensure_users, fixture_id
from app.notifications import Notification
from tests.conftest import assert_test_target
from tests.shared.test_sprint5_browser import wait_for


@pytest.mark.skipif(
    os.environ.get("RUN_SPRINT11_BROWSER") != "1",
    reason="Opt-in Sprint 11 browser gate; requires the coordinator's isolated serial database slot and frontend export",
)
def test_sprint11_mobile_browser_journeys(db, make_org, make_event):
    assert_test_target()
    assert db.scalar(text("SELECT current_database()")) == "intraspot_mvp_test"
    ensure_users(db)
    db.commit()

    organizer = db.get(User, fixture_id("Fictional organizer"))
    student = db.get(User, fixture_id("Fictional student 1"))
    seat_holder = db.get(User, fixture_id("Fictional student 2"))
    waitlisted_student = db.get(User, fixture_id("Fictional student 3"))
    other_owner = db.get(User, fixture_id("Fictional student 4"))
    faculty = db.get(User, fixture_id("Fictional faculty"))
    assert all((organizer, student, seat_holder, waitlisted_student, other_owner, faculty))

    organization = make_org(
        owner=organizer,
        name="Fictional Sprint 11 Arts Society",
        description="Fictional organization for isolated mobile browser checks.",
    )
    other_organization = make_org(
        owner=other_owner,
        name="Fictional Sprint 11 Design Society",
        description="Second fictional organization for global and club search.",
    )
    db.add(OrgMembership(
        id=uid(), org_id=organization.id, user_id=student.id, role="member", active=True,
    ))
    db.commit()

    def event(title, *, org=organization, capacity=4, mode="instant"):
        starts = now() + timedelta(days=5)
        return make_event(
            org=org,
            title=title,
            summary="A fictional event for the Sprint 11 local browser gate.",
            description="No real participants or production data are involved.",
            starts_at=starts,
            ends_at=starts + timedelta(hours=2),
            venue_name="Fictional Campus Hall",
            venue_address="Fictional address, Manila",
            capacity=capacity,
            banner_key="heritage",
            cost_label="Free",
            status="published",
            published_at=now(),
            registration_mode=mode,
            review_window_minutes=60 if mode == "approval" else None,
        )

    search_event = event("Fictional Sprint 11 Arts Gathering")
    full_event = event("Fictional Sprint 11 Full Workshop", capacity=1)
    approval_event = event("Fictional Sprint 11 Faculty Request", mode="approval")
    withdrawal_event = event("Fictional Sprint 11 Withdrawal Check")
    archive_event = event("Fictional Sprint 11 Archived Chat")
    other_search_event = event(
        "Fictional Sprint 11 Design Gathering", org=other_organization,
    )

    filled = submit_registration(
        seat_holder.id, full_event.id, f"sprint11-full-{uuid4()}",
    )
    assert filled.result["status"] == "confirmed"

    archived_registration = submit_registration(
        faculty.id, archive_event.id, f"sprint11-archive-{uuid4()}",
    )
    assert archived_registration.result["status"] == "confirmed"
    db.expire_all()
    send_chat_message(
        db,
        archive_event.id,
        faculty.id,
        ContentCreate(body="Fictional archived discussion", client_key=uuid4()),
    )
    ended_at = now() - timedelta(hours=1)
    archive_event.starts_at = ended_at - timedelta(hours=2)
    archive_event.ends_at = ended_at
    db.commit()

    notice = Notification(
        user_id=faculty.id,
        event_id=search_event.id,
        org_id=organization.id,
        kind="registration_approved",
        message="A fictional registration update is ready to review.",
        dedupe_key=f"sprint11-browser:{uuid4()}",
    )
    db.add(notice)
    db.commit()
    for row in (organization, other_organization, search_event, full_event,
                approval_event, withdrawal_event, archive_event,
                other_search_event, notice):
        db.refresh(row)

    project = ROOT.parents[1]
    frontend = project / "Code/Frontend"
    driver = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"
    )
    assert driver.is_dir(), "The Sprint 10 bundled Playwright driver is required"
    assert (frontend / "out/index.html").is_file(), (
        "Build the frontend static export before running the Sprint 11 browser gate"
    )

    evidence_root = project / "docs/validation/sprint11-browser-evidence"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    evidence = evidence_root / stamp
    evidence.mkdir(parents=True, exist_ok=False)
    environment = os.environ | {
        "ENVIRONMENT": "local",
        "FIXTURE_AUTH": "true",
        "DATABASE_URL": get_settings().database_url,
        "SPRINT11_PLAYWRIGHT": str(driver),
        "SPRINT11_EVIDENCE_DIR": str(evidence),
        "SPRINT11_FIXTURES": json.dumps({
            "orgId": organization.id,
            "orgName": organization.name,
            "searchEventId": search_event.id,
            "searchEventTitle": search_event.title,
            "fullEventId": full_event.id,
            "fullEventTitle": full_event.title,
            "approvalEventId": approval_event.id,
            "approvalEventTitle": approval_event.title,
            "withdrawalEventId": withdrawal_event.id,
            "withdrawalEventTitle": withdrawal_event.title,
            "archiveEventId": archive_event.id,
            "archiveEventTitle": archive_event.title,
            "otherEventTitle": other_search_event.title,
            "noticeId": notice.id,
        }),
    }

    processes = []
    try:
        api = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "app.main:app",
                "--host", "127.0.0.1", "--port", "8002",
                "--no-access-log", "--log-level", "warning",
            ],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(api)
        wait_for("http://127.0.0.1:8002/ready", api)

        web = subprocess.Popen(
            ["node", "scripts/serve-static.mjs"],
            cwd=frontend,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(web)
        wait_for("http://127.0.0.1:3000", web)

        result = subprocess.run(
            ["node", "docs/validation/sprint11-browser-check.mjs"],
            cwd=project,
            env=environment,
            check=False,
            timeout=360,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert result.returncode == 0, (
            f"Sprint 11 browser checks failed; inspect sanitized evidence at {evidence}"
        )
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
