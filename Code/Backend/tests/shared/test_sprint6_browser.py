"""Opt-in real browser approval, reduction and reconfirmation journeys."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import ROOT, get_settings
from app.domains.identity.models import User
from app.domains.organizations.models import OrgMembership
from app.local_identities import ensure_users, fixture_id
from tests.conftest import assert_test_target
from tests.shared.test_sprint5_browser import wait_for


@pytest.mark.skipif(os.environ.get('RUN_SPRINT6_BROWSER') != '1', reason='Opt-in Sprint 6 browser gate')
def test_approval_and_reconfirmation_browser_journeys(db, make_org, make_event):
    assert_test_target()
    ensure_users(db)
    db.commit()
    owner = db.get(User, fixture_id('Fictional student 4'))
    moderator = db.get(User, fixture_id('Fictional student 5'))
    org = make_org(owner=owner, name='Fictional Approval Society')
    db.add(OrgMembership(org_id=org.id, user_id=moderator.id, role='moderator', active=True))
    db.commit()
    event = make_event(org=org, title='Fictional Approval Gathering', capacity=2,
                       registration_mode='approval', review_window_minutes=15)
    pool_event = make_event(org=org, title='Fictional Pool Gathering', capacity=3)
    project = ROOT.parents[1]
    driver = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'
    environment = os.environ | {'ENVIRONMENT': 'local', 'FIXTURE_AUTH': 'true',
        'DATABASE_URL': get_settings().database_url, 'SPRINT6_PLAYWRIGHT': str(driver),
        'SPRINT6_FIXTURES': json.dumps({'eventId': event.id, 'poolEventId': pool_event.id, 'orgId': org.id})}
    processes = []
    try:
        api = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                                '--port', '8002', '--no-access-log', '--log-level', 'warning'],
                               cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(api)
        wait_for('http://127.0.0.1:8002/ready', api)
        web = subprocess.Popen(['node', 'scripts/serve-static.mjs'], cwd=project / 'Code/Frontend',
                               env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(web)
        wait_for('http://127.0.0.1:3000', web)
        subprocess.run(['node', 'docs/validation/sprint6-browser-check.mjs'], cwd=project,
                       env=environment, check=True, timeout=240)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
