"""Opt-in actual communication/moderation browser journeys on scratch PostgreSQL."""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import timedelta
from uuid import uuid4

import pytest

from app.core.communication_schemas import ContentCreate
from app.core.config import ROOT, get_settings
from app.db.models import now
from app.domains.chat.service import send_chat_message
from app.domains.identity.models import User
from app.domains.organizations.models import OrgMembership
from app.domains.registrations.service import submit_registration
from app.domains.social.service import create_comment
from app.local_identities import ensure_users, fixture_id
from tests.conftest import assert_test_target
from tests.shared.test_sprint5_browser import wait_for


@pytest.mark.skipif(os.environ.get('RUN_SPRINT7_BROWSER') != '1', reason='Opt-in Sprint 7 browser gate')
def test_communication_and_safety_browser_journeys(db, make_org, make_event):
    assert_test_target()
    ensure_users(db); db.commit()
    owner = db.get(User, fixture_id('Fictional student 4'))
    moderator = db.get(User, fixture_id('Fictional student 5'))
    student = db.get(User, fixture_id('Fictional student 1'))
    faculty = db.get(User, fixture_id('Fictional faculty'))
    org = make_org(owner=owner, name='Fictional Community Society')
    db.add(OrgMembership(org_id=org.id, user_id=moderator.id, role='moderator', active=True)); db.commit()
    event = make_event(org=org, title='Fictional Community Gathering', capacity=2)
    created = create_comment(db, event.id, student.id,
                             ContentCreate(body='Public fictional welcome', client_key=uuid4()))
    db.commit()
    archive = make_event(org=org, title='Fictional Archived Gathering', capacity=2)
    expired = make_event(org=org, title='Fictional Expired Gathering', capacity=2)
    for room in (archive, expired):
        for attendee in (student, faculty):
            submit_registration(attendee.id, room.id, f's7-fixture-{room.id}-{attendee.id}')
        send_chat_message(db, room.id, student.id, ContentCreate(body='Historical fictional discussion', client_key=uuid4()))
        db.commit()
    archive.starts_at, archive.ends_at = now() - timedelta(hours=3), now() - timedelta(hours=1)
    expired.starts_at, expired.ends_at = now() - timedelta(hours=75), now() - timedelta(hours=73)
    db.commit()
    project = ROOT.parents[1]
    driver = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'
    environment = os.environ | {'ENVIRONMENT': 'local', 'FIXTURE_AUTH': 'true',
        'DATABASE_URL': get_settings().database_url, 'SPRINT7_PLAYWRIGHT': str(driver),
        'SPRINT7_FIXTURES': json.dumps({'eventId': event.id, 'archiveId': archive.id,
                                     'expiredId': expired.id, 'orgId': org.id, 'commentId': created.id})}
    processes = []
    try:
        api = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                                '--port', '8002', '--no-access-log', '--log-level', 'warning'],
                               cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(api); wait_for('http://127.0.0.1:8002/ready', api)
        web = subprocess.Popen(['node', 'scripts/serve-static.mjs'], cwd=project / 'Code/Frontend',
                               env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(web); wait_for('http://127.0.0.1:3000', web)
        subprocess.run(['node', 'docs/validation/sprint7-browser-check.mjs'], cwd=project,
                       env=environment, check=True, timeout=300)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
