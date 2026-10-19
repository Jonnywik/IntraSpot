"""Opt-in Sprint 14 browser gate on the coordinator's serialized test database."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from urllib.request import urlopen

import pytest
from sqlalchemy import text

from app.core.config import ROOT, get_settings
from app.db.models import now, uid
from app.domains.identity.models import User
from app.domains.organizations.models import OrgMembership
from app.local_identities import ensure_users, fixture_id
from tests.conftest import assert_test_target
from tests.shared.test_sprint5_browser import wait_for


@pytest.mark.skipif(
    os.environ.get("RUN_SPRINT14_BROWSER") != "1",
    reason=(
        "Opt-in Sprint 14 Edge gate; requires the coordinator's exclusive test-DB slot, "
        "renewed fictional tokens, and frontend export"
    ),
)
def test_sprint14_announcement_browser_quality(db, make_org):
    assert_test_target()
    assert db.scalar(text("SELECT current_database()")) == "intraspot_mvp_test"
    ensure_users(db)
    db.commit()

    organizer = db.get(User, fixture_id("Fictional organizer"))
    student = db.get(User, fixture_id("Fictional student 1"))
    platform_admin = db.get(User, fixture_id("Fictional platform admin"))
    assert all((organizer, student, platform_admin))
    assert platform_admin.platform_admin is True

    organization = make_org(
        owner=organizer,
        name="Fictional Sprint 14 QA Announcement Club",
        description="Isolated fictional organization for the Sprint 14 browser gate.",
    )
    assert organization.accreditation_status == "approved"
    db.add(OrgMembership(
        id=uid(), org_id=organization.id, user_id=student.id,
        role="member", active=True,
    ))

    db.commit()

    project = ROOT.parents[1]
    frontend = project / "Code/Frontend"
    driver = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"
    )
    assert driver.is_dir(), "The bundled Playwright driver is required for Sprint 14"
    assert (frontend / "out/index.html").is_file(), (
        "Prepare the static frontend export before the Sprint 14 Edge gate"
    )
    bundle_root = frontend / "out/_next/static"
    bundles = list(bundle_root.rglob("*.js")) if bundle_root.is_dir() else []
    isolated_origins = ("http://127.0.0.1:8002", "http://localhost:8002")
    assert bundles and any(
        origin in bundle.read_text(encoding="utf-8", errors="ignore")
        for bundle in bundles
        for origin in isolated_origins
    ), "The exported frontend must target the isolated API on port 8002"

    # Never attach to or terminate a pre-existing process. The coordinator must
    # serialize this gate with other API/browser suites.
    for port in (8002, 3000):
        with socket.socket() as probe:
            probe.settimeout(0.25)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                pytest.fail(
                    f"Port {port} is already in use; refusing to attach to or stop another process"
                )

    evidence_root = project / "docs/validation/sprint14-browser-evidence"
    stamp = now().strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    evidence = evidence_root / stamp
    evidence.mkdir(parents=True, exist_ok=False)

    environment = os.environ.copy()
    environment.update({
        "ENVIRONMENT": "local",
        "FIXTURE_AUTH": "true",
        "DATABASE_URL": get_settings().database_url,
        "NEXT_PUBLIC_API_URL": "http://127.0.0.1:8002",
        "SPRINT14_API_BASE_URL": "http://127.0.0.1:8002/api/v1",
        "SPRINT14_WEB_BASE_URL": "http://127.0.0.1:3000",
        "SPRINT14_PLAYWRIGHT": str(driver),
        "SPRINT14_EVIDENCE_DIR": str(evidence),
        "SPRINT14_FIXTURES": json.dumps({
            "orgId": organization.id,
            "orgName": organization.name,
            "organizerId": organizer.id,
            "studentId": student.id,
            "platformAdminId": platform_admin.id,
        }),
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

        # Confirm that this is the API backed by this run's isolated fixture,
        # not an unrelated service that appeared after the port check.
        with urlopen("http://127.0.0.1:8002/api/v1/organizations", timeout=10) as response:
            organizations = json.load(response)
        assert any(row.get("id") == organization.id for row in organizations), (
            "The API on port 8002 does not contain this run's fixture organization"
        )

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
            ["node", "docs/validation/sprint14-browser-check.mjs"],
            cwd=project,
            env=environment,
            check=False,
            timeout=360,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert result.returncode == 0, (
            f"Sprint 14 Edge checks failed; inspect sanitized evidence at {evidence}"
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
