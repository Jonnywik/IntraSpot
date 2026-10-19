"""Opt-in Sprint 10 management journeys on the isolated serial test database."""

from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.core.config import ROOT, get_settings
from app.db.models import now
from app.domains.identity.models import User
from app.domains.organizations.models import OrgMembership
from app.domains.registrations.models import Registration
from app.local_identities import ensure_users, fixture_id
from app.notifications import Notification
from tests.conftest import assert_test_target
from tests.shared.test_sprint5_browser import wait_for


@pytest.mark.skipif(
    os.environ.get("RUN_SPRINT10_BROWSER") != "1",
    reason="Opt-in Sprint 10 browser quality gate; requires the coordinator's serial database slot",
)
def test_sprint10_management_browser_quality(db, make_org, make_event):
    assert_test_target()
    ensure_users(db)
    db.commit()

    pending_owner = db.get(User, fixture_id("Fictional student 1"))
    moderator = db.get(User, fixture_id("Fictional student 2"))
    member = db.get(User, fixture_id("Fictional student 3"))
    approved_owner = db.get(User, fixture_id("Fictional student 4"))
    platform_admin = db.get(User, fixture_id("Fictional platform admin"))
    assert all((pending_owner, moderator, member, approved_owner, platform_admin))

    pending_org = make_org(
        owner=pending_owner,
        name="Fictional Sprint 10 Pending Society",
        description="Fictional organization for a local browser regression.",
        accreditation_status="pending",
    )
    pending_draft = make_event(
        org=pending_org,
        title="Fictional Pending Workshop",
        summary="A complete private draft for approval-gated authoring.",
        description="A fictional event used only in the isolated browser test.",
        starts_at=now() + timedelta(days=7),
        ends_at=now() + timedelta(days=7, hours=2),
        venue_name="Fictional Campus Hall",
        venue_address="Fictional address, Manila",
        capacity=24,
        banner_key="heritage",
        cost_label="Free",
        status="draft",
        published_at=None,
        registration_mode="instant",
        review_window_minutes=None,
    )

    approved_org = make_org(
        owner=approved_owner,
        name="Fictional Sprint 10 Approved Society",
        description="Fictional approved organization for scoped staff review.",
        accreditation_status="approved",
    )
    approved_draft = make_event(
        org=approved_org,
        title="Fictional Approved Owner Draft",
        summary="A complete draft for publish and stale-version checks.",
        description="A fictional event used only in the isolated browser test.",
        starts_at=now() + timedelta(days=8),
        ends_at=now() + timedelta(days=8, hours=2),
        venue_name="Fictional Arts Room",
        venue_address="Fictional address, Manila",
        capacity=18,
        banner_key="design",
        cost_label="Free",
        status="draft",
        published_at=None,
        registration_mode="instant",
        review_window_minutes=None,
    )
    review_event = make_event(
        org=approved_org,
        title="Fictional Staff Review Event",
        summary="A published event for the authorized review workflow.",
        description="A fictional event used only in the isolated browser test.",
        starts_at=now() + timedelta(days=9),
        ends_at=now() + timedelta(days=9, hours=2),
        venue_name="Fictional Arts Room",
        venue_address="Fictional address, Manila",
        capacity=18,
        banner_key="music",
        cost_label="Free",
        status="published",
        published_at=now(),
        registration_mode="approval",
        review_window_minutes=60,
    )

    db.add_all(
        [
            OrgMembership(org_id=approved_org.id, user_id=moderator.id, role="moderator", active=True),
            OrgMembership(org_id=approved_org.id, user_id=member.id, role="member", active=True),
            Registration(
                user_id=member.id,
                event_id=review_event.id,
                status="pending",
                admission_order=1,
                review_deadline=now() + timedelta(days=1),
                review_stage=0,
                reviewer_id=moderator.id,
                first_reviewer_id=moderator.id,
            ),
        ]
    )

    def notification(*, user, kind, message, key, event=None, organization=None, read=False):
        result = Notification(
            user_id=user.id,
            event_id=event.id if event else None,
            org_id=organization.id if organization else None,
            kind=kind,
            message=message,
            dedupe_key=f"sprint10-browser:{key}",
            read_at=now() if read else None,
        )
        db.add(result)
        return result

    member_event_notice = notification(
        user=member,
        kind="registration_approved",
        message="Your event registration was approved.",
        key="member-event",
        event=review_event,
    )
    member_club_notice = notification(
        user=member,
        kind="membership_approved",
        message="Your organization membership request was approved.",
        key="member-club",
        organization=approved_org,
    )
    member_chat_notice = notification(
        user=member,
        kind="chat_message",
        message="New message in an event chat.",
        key="member-chat",
        event=review_event,
        read=True,
    )
    moderator_notice = notification(
        user=moderator,
        kind="registration_review_requested",
        message="A registration is waiting for your event review.",
        key="moderator-review",
        event=review_event,
        organization=approved_org,
    )
    admin_notice = notification(
        user=platform_admin,
        kind="safety_report_received",
        message="A safety report requires review.",
        key="platform-safety",
        event=review_event,
        organization=approved_org,
    )
    db.commit()
    db.refresh(pending_org)
    db.refresh(approved_org)
    db.refresh(pending_draft)
    db.refresh(approved_draft)
    db.refresh(review_event)
    for notice in (member_event_notice, member_club_notice, member_chat_notice, moderator_notice, admin_notice):
        db.refresh(notice)

    project = ROOT.parents[1]
    driver = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"
    )
    assert driver.is_dir(), "The existing bundled Playwright driver is required"
    assert (project / "Code/Frontend/out/index.html").is_file(), (
        "Build the frontend static export before running the Sprint 10 browser gate"
    )

    environment = os.environ | {
        "ENVIRONMENT": "local",
        "FIXTURE_AUTH": "true",
        "DATABASE_URL": get_settings().database_url,
        "SPRINT10_PLAYWRIGHT": str(driver),
        "SPRINT10_FIXTURES": json.dumps(
            {
                "pendingOrgId": pending_org.id,
                "pendingOrgName": pending_org.name,
                "pendingDraftId": pending_draft.id,
                "pendingDraftTitle": pending_draft.title,
                "approvedOrgId": approved_org.id,
                "approvedOrgName": approved_org.name,
                "approvedDraftId": approved_draft.id,
                "approvedDraftTitle": approved_draft.title,
                "reviewEventId": review_event.id,
                "reviewEventTitle": review_event.title,
                "memberEventNoticeId": member_event_notice.id,
                "memberClubNoticeId": member_club_notice.id,
                "memberChatNoticeId": member_chat_notice.id,
                "moderatorNoticeId": moderator_notice.id,
                "adminNoticeId": admin_notice.id,
                "accounts": {
                    "pendingOwner": "Fictional student 1",
                    "moderator": "Fictional student 2",
                    "member": "Fictional student 3",
                    "approvedOwner": "Fictional student 4",
                    "platformAdmin": "Fictional platform admin",
                },
            }
        ),
    }
    processes = []
    try:
        api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8002",
                "--no-access-log",
                "--log-level",
                "warning",
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
            cwd=project / "Code/Frontend",
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(web)
        wait_for("http://127.0.0.1:3000", web)

        result = subprocess.run(
            ["node", "docs/validation/sprint10-browser-check.mjs"],
            cwd=project,
            env=environment,
            check=False,
            timeout=420,
        )
        assert result.returncode == 0, "Sprint 10 browser checks failed; inspect their sanitized evidence."
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
