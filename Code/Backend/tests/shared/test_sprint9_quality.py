"""Opt-in Sprint 9 preferences journey using the isolated serial test database."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.core.config import ROOT, get_settings
from app.domains.identity.models import User
from app.domains.registrations.models import Registration
from app.local_identities import ensure_users, fixture_id
from tests.conftest import assert_test_target
from tests.shared.test_sprint5_browser import wait_for


@pytest.mark.skipif(
    os.environ.get("RUN_SPRINT9_BROWSER") != "1",
    reason="Opt-in Sprint 9 browser quality gate; requires the serial database slot",
)
def test_sprint9_preferences_browser_quality(db, make_org, make_event):
    assert_test_target()
    ensure_users(db)
    db.commit()

    account_a = db.get(User, fixture_id("Fictional student 1"))
    account_b = db.get(User, fixture_id("Fictional student 2"))
    assert account_a is not None and account_b is not None

    org = make_org(owner=account_a, name="Fictional Sprint 9 Quality Society")
    event = make_event(org=org, title="Fictional Sprint 9 Keyboard Event",
                       summary="Meet your campus community through shared stories.")
    db.add(Registration(
        user_id=account_b.id,
        event_id=event.id,
        status="confirmed",
        admission_order=1,
    ))
    db.commit()

    project = ROOT.parents[1]
    driver = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"
    )
    assert driver.is_dir(), "The existing bundled Playwright driver is required"
    assert (project / "Code/Frontend/out/index.html").is_file(), (
        "Build the frontend static export before running the Sprint 9 browser gate"
    )

    environment = os.environ | {
        "ENVIRONMENT": "local",
        "FIXTURE_AUTH": "true",
        "DATABASE_URL": get_settings().database_url,
        "SPRINT9_PLAYWRIGHT": str(driver),
        "SPRINT9_FIXTURES": json.dumps(
            {
                "eventId": event.id,
                "orgName": org.name,
                "privateEventTitle": event.title,
                "accountAId": account_a.id,
                "accountBId": account_b.id,
                "accountALabel": "Fictional student 1",
                "accountBLabel": "Fictional student 2",
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

        subprocess.run(
            ["node", "docs/validation/sprint9-geometry-check.mjs"],
            cwd=project,
            env=environment,
            check=True,
            timeout=120,
        )
        subprocess.run(
            ["node", "docs/validation/sprint9-browser-check.mjs"],
            cwd=project,
            env=environment,
            check=True,
            timeout=360,
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
