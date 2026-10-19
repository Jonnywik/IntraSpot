"""Opt-in Sprint 13 Edge gate against the isolated serial test database."""

from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

import pytest
from sqlalchemy import text

from app.core.config import ROOT, get_settings
from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.identity.discovery_models import UserDiscoveryPreferences
from app.domains.identity.models import User
from app.domains.organizations.models import OrgMembership
from app.domains.registrations import service as registration_service
from app.local_identities import ensure_users, fixture_id
from tests.conftest import assert_test_target
from tests.shared.test_sprint5_browser import wait_for


@pytest.mark.skipif(
    os.environ.get("RUN_SPRINT13_BROWSER") != "1",
    reason="Opt-in Sprint 13 Edge gate; requires the coordinator's isolated serial database slot and frontend export",
)
def test_sprint13_flash_browser_quality(db, make_org, make_event):
    assert_test_target()
    assert db.scalar(text("SELECT current_database()")) == "intraspot_mvp_test"
    ensure_users(db)
    db.commit()

    organizer = db.get(User, fixture_id("Fictional organizer"))
    student = db.get(User, fixture_id("Fictional student 1"))
    second_student = db.get(User, fixture_id("Fictional student 2"))
    faculty = db.get(User, fixture_id("Fictional faculty"))
    assert all((organizer, student, second_student, faculty))

    club = make_org(
        owner=organizer,
        name="Fictional Sprint 13 QA Intramuros Club",
        description="Fictional organization for isolated Sprint 13 checks.",
    )
    other_org = make_org(
        owner=faculty,
        name="Fictional Sprint 13 QA Global Society",
        description="Second fictional organization for isolated Sprint 13 checks.",
    )
    student.tags = ["arts"]
    db.add_all(
        [
            OrgMembership(
                id=uid(), org_id=club.id, user_id=student.id, role="member", active=True
            ),
            UserDiscoveryPreferences(
                user_id=student.id,
                coarse_area="intramuros",
                availability=[],
            ),
        ]
    )

    boundary = now().replace(microsecond=0)
    title_prefix = "Fictional Sprint 13 QA"

    def published_event(
        name,
        *,
        organization,
        start_hours,
        publish_ago,
        event_type="flash",
        coarse_area=None,
        capacity=4,
        tags=("arts",),
    ):
        starts_at = boundary + timedelta(hours=start_hours)
        return make_event(
            org=organization,
            title=f"{title_prefix} {name}",
            summary="Fictional Sprint 13 browser fixture.",
            description="No real people or production records are involved.",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            venue_name="Fictional Campus Hall",
            venue_address="Intramuros, Manila",
            capacity=capacity,
            banner_key="heritage",
            cost_label="Free",
            registration_mode="instant",
            review_window_minutes=None,
            status="published",
            published_at=boundary - publish_ago,
            event_type=event_type,
            tags=list(tags),
            coarse_area=coarse_area,
        )

    events = {
        "club_scheduled": published_event(
            "Scheduled Club Priority",
            organization=club,
            start_hours=6,
            publish_ago=timedelta(days=1),
            event_type="scheduled",
            capacity=4,
            tags=(),
        ),
        "active_flash": published_event(
            "Fresh Matching Flash",
            organization=other_org,
            start_hours=6,
            publish_ago=timedelta(minutes=20),
            coarse_area="intramuros",
            capacity=4,
        ),
        "expired_area_flash": published_event(
            "Expired Area Flash",
            organization=other_org,
            start_hours=6,
            publish_ago=timedelta(hours=4),
            coarse_area="intramuros",
            capacity=1,
        ),
        "no_area_flash": published_event(
            "No Area Flash",
            organization=other_org,
            start_hours=6,
            publish_ago=timedelta(minutes=10),
            coarse_area=None,
            capacity=4,
        ),
        "other_area_flash": published_event(
            "Other Area Flash",
            organization=other_org,
            start_hours=6,
            publish_ago=timedelta(minutes=5),
            coarse_area="quezon city",
            capacity=4,
        ),
    }
    draft_start = boundary + timedelta(hours=6)
    draft = make_event(
        org=club,
        title=f"{title_prefix} Authoring Draft",
        summary="Fictional private draft for the authoring journey.",
        description="No real people or production records are involved.",
        starts_at=draft_start,
        ends_at=draft_start + timedelta(hours=1),
        venue_name="Fictional Campus Hall",
        venue_address="Intramuros, Manila",
        capacity=4,
        banner_key="heritage",
        cost_label="Free",
        registration_mode="approval",
        review_window_minutes=15,
        status="draft",
        published_at=None,
        event_type="scheduled",
        tags=["arts"],
        coarse_area="intramuros",
    )
    db.commit()

    occupied = registration_service.submit_registration(
        second_student.id, events["expired_area_flash"].id, "s13-fixture-seat-01"
    )
    assert occupied.result["status"] == "confirmed"

    expected_for_you = [
        events["club_scheduled"].id,
        events["active_flash"].id,
        events["expired_area_flash"].id,
        *sorted(
            (events["no_area_flash"].id, events["other_area_flash"].id)
        ),
    ]
    expected_upcoming = [
        row.id for row in sorted(events.values(), key=lambda row: (row.starts_at, row.id))
    ]
    expected_newest = [
        row.id
        for row in sorted(
            events.values(), key=lambda row: (-row.published_at.timestamp(), row.id)
        )
    ]
    expected_reasons = {
        events["club_scheduled"].id: ["club"],
        events["active_flash"].id: ["flash", "interests", "area"],
        events["expired_area_flash"].id: ["interests", "area"],
        events["no_area_flash"].id: ["interests"],
        events["other_area_flash"].id: ["interests"],
    }

    project = ROOT.parents[1]
    frontend = project / "Code/Frontend"
    driver = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"
    )
    assert driver.is_dir(), "The bundled Playwright driver is required for Sprint 13"
    assert (frontend / "out/index.html").is_file(), (
        "Prepare the static frontend export before the Sprint 13 Edge gate"
    )
    bundle_root = frontend / "out/_next/static"
    bundles = list(bundle_root.rglob("*.js")) if bundle_root.is_dir() else []
    isolated_origins = ("http://127.0.0.1:8002", "http://localhost:8002")
    assert bundles and any(
        origin in bundle.read_text(encoding="utf-8", errors="ignore")
        for bundle in bundles
        for origin in isolated_origins
    ), "The exported frontend must target the isolated API on port 8002"

    evidence_root = project / "docs/validation/sprint13-browser-evidence"
    stamp = now().strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    evidence = evidence_root / stamp
    evidence.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment.update(
        {
            "ENVIRONMENT": "local",
            "FIXTURE_AUTH": "true",
            "DATABASE_URL": get_settings().database_url,
            "NEXT_PUBLIC_API_URL": "http://127.0.0.1:8002",
            "SPRINT13_API_BASE_URL": "http://127.0.0.1:8002/api/v1",
            "SPRINT13_PLAYWRIGHT": str(driver),
            "SPRINT13_EVIDENCE_DIR": str(evidence),
            "SPRINT13_FIXTURES": json.dumps(
                {
                    "titleSearch": title_prefix,
                    "clubOrganizationName": club.name,
                    "otherOrganizationName": other_org.name,
                    "events": {
                        key: {"id": row.id, "title": row.title}
                        for key, row in events.items()
                    },
                    "draft": {"id": draft.id, "title": draft.title},
                    "expectedForYou": expected_for_you,
                    "expectedUpcoming": expected_upcoming,
                    "expectedNewest": expected_newest,
                    "expectedHiddenFeed": [events["club_scheduled"].id],
                    "expectedReasons": expected_reasons,
                },
                ensure_ascii=True,
            ),
        }
    )

    processes = []
    try:
        api_process = subprocess.Popen(
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
        processes.append(api_process)
        wait_for("http://127.0.0.1:8002/ready", api_process)
        # Fail before opening Edge if a stale server or another test owns this DB.
        with urlopen("http://127.0.0.1:8002/api/v1/events", timeout=10) as response:
            public_ids = {row["id"] for row in json.load(response)}
        assert public_ids == {row.id for row in events.values()}, (
            "The isolated API does not contain this run's fixtures; do not overlap DB suites"
        )
        with urlopen("http://127.0.0.1:8002/api/v1/local-demo/accounts", timeout=10) as response:
            assert response.status == 200, "Renew the ignored local fictional catalog before Edge checks"

        web_process = subprocess.Popen(
            ["node", "scripts/serve-static.mjs"],
            cwd=frontend,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(web_process)
        wait_for("http://127.0.0.1:3000", web_process)

        result = subprocess.run(
            ["node", "docs/validation/sprint13-browser-check.mjs"],
            cwd=project,
            env=environment,
            check=False,
            timeout=300,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert result.returncode == 0, (
            f"Sprint 13 Edge checks failed; inspect sanitized evidence at {evidence}"
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
