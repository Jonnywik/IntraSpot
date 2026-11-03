"""Opt-in rendered registration journeys against the isolated PostgreSQL scratch DB."""
import json
import os
from datetime import timedelta
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from app.core.config import ROOT, get_settings
from app.db.models import now, uid
from app.domains.identity.models import User
from app.domains.registrations.models import Registration
from app.local_identities import ACCOUNTS, ensure_users, fixture_id
from tests.conftest import assert_test_target
from tests.shared.test_sprint5_browser import wait_for


@pytest.mark.skipif(os.environ.get('RUN_SPRINT29_BROWSER') != '1', reason='Opt-in rendered registration accessibility journeys')
def test_rendered_registration_accessibility_journeys(db, make_org, make_event, token_for, tmp_path):
    assert_test_target()
    ensure_users(db)
    db.commit()

    catalog = tmp_path / 'fictional-browser-catalog.json'
    catalog.write_text(json.dumps([
        {'label': label, 'token': token_for(fixture_id(label))}
        for label, _, _ in ACCOUNTS
    ]), encoding='utf-8')

    organizer = db.get(User, fixture_id('Fictional student 4'))
    attendee = db.get(User, fixture_id('Fictional student 1'))
    holder = db.get(User, fixture_id('Fictional student 2'))
    assert organizer is not None and attendee is not None and holder is not None
    organization = make_org(owner=organizer, name='Fictional Sprint 29 Society')
    confirmation_start = now() + timedelta(days=2)
    waitlist_start = now() + timedelta(days=3)
    retry_start = now() + timedelta(days=4)
    confirmation_event = make_event(
        org=organization, title='Fictional Sprint 29 Confirmation', capacity=3,
        starts_at=confirmation_start, ends_at=confirmation_start + timedelta(hours=2),
    )
    waitlist_event = make_event(
        org=organization, title='Fictional Sprint 29 Waitlist', capacity=1,
        starts_at=waitlist_start, ends_at=waitlist_start + timedelta(hours=2),
    )
    retry_event = make_event(
        org=organization, title='Fictional Sprint 29 Retry', capacity=3,
        starts_at=retry_start, ends_at=retry_start + timedelta(hours=2),
    )
    waitlist_event.next_admission = 1
    db.add(Registration(
        id=uid(), user_id=holder.id, event_id=waitlist_event.id,
        status='confirmed', admission_order=1, confirmed_at=now(),
    ))
    db.commit()

    project = ROOT.parents[1]
    frontend = project / 'Code/Frontend'
    driver = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'
    assert driver.is_dir(), 'Bundled local browser driver is required'
    export = frontend / 'out'
    assert any('http://127.0.0.1:8002' in file.read_text(encoding='utf8')
               for file in (export / '_next').rglob('*.js')), 'Build the isolated API 8002 browser export first'

    environment = os.environ | {
        'ENVIRONMENT': 'local',
        'FIXTURE_AUTH': 'true',
        'DATABASE_URL': get_settings().database_url,
        'SPRINT29_PLAYWRIGHT': str(driver),
        'SPRINT29_EVIDENCE_DIR': str(ROOT / '.cache/s29'),
        'SPRINT29_FIXTURES': json.dumps({
            'confirmation': {'id': confirmation_event.id, 'title': confirmation_event.title},
            'waitlist': {'id': waitlist_event.id, 'title': waitlist_event.title},
            'retry': {'id': retry_event.id, 'title': retry_event.title},
        }),
    }
    for port in (8002, 3000):
        with socket.socket() as probe:
            assert probe.connect_ex(('127.0.0.1', port)) != 0, 'Browser test ports must be unused'

    processes = []
    try:
        api = subprocess.Popen(
            [sys.executable, '-c',
             'import sys; from pathlib import Path; import app.local_demo as demo; '
             'demo.CATALOG_PATH=Path(sys.argv[1]); import uvicorn; '
             'uvicorn.run("app.main:app",host="127.0.0.1",port=8002,access_log=False,log_level="warning")',
             str(catalog)],
            cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        processes.append(api)
        wait_for('http://127.0.0.1:8002/ready', api)
        web = subprocess.Popen(
            ['node', 'scripts/serve-static.mjs'], cwd=frontend, env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        processes.append(web)
        wait_for('http://127.0.0.1:3000', web)
        subprocess.run(
            ['node', 'docs/validation/sprint29-accessibility-check.mjs'],
            cwd=project, env=environment, check=True, timeout=360,
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
