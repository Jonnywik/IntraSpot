"""Opt-in Sprint 12 browser journeys against the isolated serial test database."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import text

from app.core.config import ROOT, get_settings
from app.db.models import uid
from app.domains.events.schemas import EventDraftInput
from app.domains.identity.models import User
from app.domains.organizations.models import OrgMembership
from app.local_identities import ensure_users, fixture_id
from tests.conftest import assert_test_target
from tests.shared.test_sprint5_browser import wait_for


MANILA = timezone(timedelta(hours=8), "Asia/Manila")


def _fixed_manila_time(day_offset: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2030, 1, 7, hour, minute, tzinfo=MANILA) + timedelta(days=day_offset)


def _published_at(day: int) -> datetime:
    return datetime(2020, 1, day, 12, tzinfo=MANILA)


@pytest.mark.skipif(
    os.environ.get("RUN_SPRINT12_BROWSER") != "1",
    reason="Opt-in Sprint 12 Edge gate; requires the coordinator's isolated serial database slot and frontend export",
)
def test_sprint12_discovery_browser_quality(db, make_org, make_event):
    assert_test_target()
    assert db.scalar(text("SELECT current_database()")) == "intraspot_mvp_test"
    assert _fixed_manila_time(0, 9).weekday() == 0
    ensure_users(db)
    db.commit()

    organizer = db.get(User, fixture_id("Fictional organizer"))
    student = db.get(User, fixture_id("Fictional student 1"))
    second_student = db.get(User, fixture_id("Fictional student 2"))
    faculty = db.get(User, fixture_id("Fictional faculty"))
    assert all((organizer, student, second_student, faculty))

    club = make_org(
        owner=organizer,
        name="Fictional Sprint 12 Intramuros Club",
        description="Fictional organization for isolated discovery checks.",
    )
    other_org = make_org(
        owner=faculty,
        name="Fictional Sprint 12 Global Society",
        description="Second fictional organization for search and ranking checks.",
    )
    student.tags = ["music", "art", "campus walks"]
    db.add(OrgMembership(
        id=uid(), org_id=club.id, user_id=student.id, role="member", active=True,
    ))
    db.commit()

    def event(name, *, org, start, end, published_day, tags=(), coarse_area=None, status="published"):
        metadata = EventDraftInput.model_validate({
            "tags": list(tags),
            "coarse_area": coarse_area,
        })
        return make_event(
            org=org,
            title=f"Fictional Sprint 12 {name}",
            summary="A fictional event for the Sprint 12 local discovery gate.",
            description="No real participants or production data are involved.",
            starts_at=start,
            ends_at=end,
            venue_name="Fictional Campus Hall",
            venue_address="Intramuros, Manila",
            capacity=6,
            banner_key="heritage",
            cost_label="Free",
            registration_mode="instant",
            status=status,
            published_at=_published_at(published_day) if published_day else None,
            tags=metadata.tags,
            coarse_area=metadata.coarse_area,
        )

    events = {
        "club": event(
            "Club First Gathering", org=club,
            start=_fixed_manila_time(0, 15), end=_fixed_manila_time(0, 16),
            published_day=1, tags=[],
        ),
        "three_interests": event(
            "Three Interest Match", org=other_org,
            start=_fixed_manila_time(0, 9), end=_fixed_manila_time(0, 11),
            published_day=2, tags=[" music ", "ART", "Campus   Walks"], coarse_area="Intramuros",
        ),
        "one_interest": event(
            "Normalized Duplicate Tags", org=other_org,
            start=_fixed_manila_time(0, 10), end=_fixed_manila_time(0, 11),
            published_day=3, tags=["Music", " music ", "MUSIC"],
        ),
        "area": event(
            "Area Match Outside Window", org=other_org,
            start=_fixed_manila_time(0, 12), end=_fixed_manila_time(0, 13),
            published_day=4, coarse_area="Intramuros",
        ),
        "whole_window": event(
            "Whole Window Fit", org=other_org,
            start=_fixed_manila_time(0, 11), end=_fixed_manila_time(0, 12),
            published_day=5,
        ),
        "partial_window": event(
            "Partial Window Does Not Fit", org=other_org,
            start=_fixed_manila_time(0, 11, 30), end=_fixed_manila_time(0, 12, 30),
            published_day=5,
        ),
        "week_wrap": event(
            "Sunday Monday Window Fit", org=other_org,
            start=_fixed_manila_time(-1, 23, 30), end=_fixed_manila_time(0, 0, 30),
            published_day=7,
        ),
    }
    draft = event(
        "Optional Metadata Draft", org=club,
        start=_fixed_manila_time(7, 9), end=_fixed_manila_time(7, 11),
        published_day=None, status="draft",
    )

    expected_for_you_default = [
        events[key].id for key in (
            "club", "three_interests", "one_interest", "week_wrap", "whole_window", "partial_window", "area",
        )
    ]
    expected_for_you = [
        events[key].id for key in (
            "club", "three_interests", "one_interest", "area", "week_wrap", "whole_window", "partial_window",
        )
    ]
    expected_upcoming = [
        row.id for row in sorted(events.values(), key=lambda row: (row.starts_at, row.id))
    ]
    expected_newest = [
        row.id for row in sorted(
            events.values(), key=lambda row: (-row.published_at.timestamp(), row.id)
        )
    ]
    expected_other_org = [
        row_id for row_id in expected_for_you_default if row_id != events["club"].id
    ]

    project = ROOT.parents[1]
    frontend = project / "Code/Frontend"
    driver = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"
    )
    assert driver.is_dir(), "The bundled Playwright driver is required for Sprint 12"
    assert (frontend / "out/index.html").is_file(), (
        "Prepare the frontend static export for the Sprint 12 browser gate"
    )
    bundle_root = frontend / "out/_next/static"
    bundles = list(bundle_root.rglob("*.js")) if bundle_root.is_dir() else []
    isolated_origins = ("http://127.0.0.1:8002", "http://localhost:8002")
    assert bundles and any(
        origin in bundle.read_text(encoding="utf-8", errors="ignore")
        for bundle in bundles for origin in isolated_origins
    ), "The exported frontend must target the isolated API on port 8002"

    evidence_root = project / "docs/validation/sprint12-browser-evidence"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    evidence = evidence_root / stamp
    evidence.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment.update({
        "ENVIRONMENT": "local",
        "FIXTURE_AUTH": "true",
        "DATABASE_URL": get_settings().database_url,
        "NEXT_PUBLIC_API_URL": "http://127.0.0.1:8002",
        "SPRINT12_API_BASE_URL": "http://127.0.0.1:8002/api/v1",
        "SPRINT12_PLAYWRIGHT": str(driver),
        "SPRINT12_EVIDENCE_DIR": str(evidence),
        "SPRINT12_FIXTURES": json.dumps({
            "clubOrganizationName": club.name,
            "otherOrganizationName": other_org.name,
            "titleSearch": "Fictional Sprint 12",
            "events": {key: {"id": row.id, "title": row.title} for key, row in events.items()},
            "draft": {"id": draft.id, "title": draft.title},
            "expectedForYouDefault": expected_for_you_default,
            "expectedForYou": expected_for_you,
            "expectedUpcoming": expected_upcoming,
            "expectedNewest": expected_newest,
            "expectedOtherOrganization": expected_other_org,
            "expectedReasons": {
                "club": ["club"],
                "three_interests": ["interests", "area", "availability"],
                "one_interest": ["interests", "availability"],
                "area": ["area"],
                "whole_window": ["availability"],
                "partial_window": [],
                "week_wrap": ["availability"],
            },
            "expectedReasonsDefault": {
                "club": ["club"],
                "three_interests": ["interests"],
                "one_interest": ["interests"],
                "area": [],
                "whole_window": [],
                "partial_window": [],
                "week_wrap": [],
            },
        }, ensure_ascii=True),
    })

    processes = []
    try:
        api_process = subprocess.Popen(
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
        processes.append(api_process)
        wait_for("http://127.0.0.1:8002/ready", api_process)

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
            ["node", "docs/validation/sprint12-browser-check.mjs"],
            cwd=project,
            env=environment,
            check=False,
            timeout=240,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert result.returncode == 0, (
            f"Sprint 12 browser checks failed; inspect sanitized evidence at {evidence}"
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
