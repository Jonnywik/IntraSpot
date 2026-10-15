"""Opt-in rendered browser journeys against the isolated PostgreSQL scratch DB."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, urlopen

import pytest

from app.core.config import ROOT, get_settings
from app.domains.identity.models import User
from app.domains.organizations.models import OrgMembership
from app.local_identities import ensure_users, fixture_id
from tests.conftest import assert_test_target


def wait_for(url, process):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        assert process.poll() is None, 'Local journey server stopped'
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(.2)
    raise AssertionError('Local journey server did not become ready')


@pytest.mark.skipif(os.environ.get('RUN_SPRINT5_BROWSER') != '1', reason='Opt-in local browser gate')
def test_four_persisted_browser_journeys(db, make_org, make_event):
    assert_test_target()
    ensure_users(db)
    db.commit()
    owner = db.get(User, fixture_id('Fictional student 4'))
    org = make_org(owner=owner, name='Fictional Arts Society')
    student = db.get(User, fixture_id('Fictional student 1'))
    db.add(OrgMembership(user_id=student.id, org_id=org.id, role='member', active=True))
    db.commit()
    event = make_event(org=org, title='Fictional Heritage Gathering', capacity=1)
    retry_event = make_event(org=org, title='Fictional Retry Gathering', capacity=3)
    project = ROOT.parents[1]
    frontend = project / 'Code/Frontend'
    assert (frontend / 'out/index.html').is_file(), 'Build frontend for API port 8002 first'
    driver = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'
    assert driver.is_dir(), 'Bundled local browser driver is required'
    environment = os.environ | {
        'ENVIRONMENT': 'local', 'FIXTURE_AUTH': 'true',
        'DATABASE_URL': get_settings().database_url,
        'SPRINT5_FIXTURES': json.dumps({'eventId': event.id, 'retryEventId': retry_event.id, 'orgId': org.id}),
        'SPRINT5_PLAYWRIGHT': str(driver),
    }
    processes = []
    try:
        api = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                                '--port', '8002', '--no-access-log'], cwd=ROOT, env=environment,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(api)
        wait_for('http://127.0.0.1:8002/health', api)
        web = subprocess.Popen(['node', 'scripts/serve-static.mjs'], cwd=frontend, env=environment,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(web)
        wait_for('http://127.0.0.1:3000', web)
        subprocess.run(['node', 'docs/validation/sprint5-browser-check.mjs'], cwd=project,
                       env=environment, check=True, timeout=240)
        manifest = json.loads((ROOT / '.local/accounts.json').read_text(encoding='utf-8'))
        faculty_token = next(item['token'] for item in manifest if item['label'] == 'Fictional faculty')
        request = Request('http://127.0.0.1:8002/api/v1/me/registrations',
                          headers={'Authorization': f'Bearer {faculty_token}'})
        with urlopen(request, timeout=5) as response:
            before = json.load(response)
        assert len(before) == 1 and before[0]['status'] == 'confirmed'
        api.terminate()
        api.wait(timeout=10)
        restarted = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                                      '--port', '8002', '--no-access-log'], cwd=ROOT, env=environment,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(restarted)
        wait_for('http://127.0.0.1:8002/ready', restarted)
        with urlopen(request, timeout=5) as response:
            after = json.load(response)
        assert after == before, 'Persisted browser outcome changed across API restart'
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
