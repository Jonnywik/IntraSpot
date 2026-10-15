"""Opt-in membership journeys against rendered UI and isolated persisted PostgreSQL."""
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
from app.domains.registrations.models import Registration
from app.domains.memberships.models import MembershipApplication, MembershipInvitation, EventAccessRevocation
from sqlalchemy import select
from app.local_identities import ensure_users, fixture_id
from tests.conftest import assert_test_target
from tests.shared.test_sprint5_browser import wait_for


@pytest.mark.skipif(os.environ.get('RUN_SPRINT8_BROWSER') != '1', reason='Opt-in Sprint 8 browser gate')
def test_membership_browser_journeys(db, make_org, make_event):
    assert_test_target()
    ensure_users(db); db.commit()
    owner = db.get(User, fixture_id('Fictional student 4'))
    moderator = db.get(User, fixture_id('Fictional student 5'))
    admin = db.get(User, fixture_id('Fictional student 6'))
    student = db.get(User, fixture_id('Fictional student 1'))
    faculty = db.get(User, fixture_id('Fictional faculty'))
    org = make_org(owner=owner, name='Fictional Membership Society')
    for user, role in ((moderator, 'moderator'), (admin, 'admin'), (student, 'member')):
        db.add(OrgMembership(org_id=org.id, user_id=user.id, role=role, active=True))
    db.commit()
    event = make_event(org=org, title='Fictional Membership Gathering', capacity=1)
    submit_registration(student.id, event.id, 's8-existing-confirmed')
    submit_registration(faculty.id, event.id, 's8-existing-waiter')
    archive = make_event(org=org, title='Fictional Archived Member Gathering', capacity=2)
    for attendee in (student, faculty):
        submit_registration(attendee.id, archive.id, f's8-archive-{attendee.id}')
    send_chat_message(db, archive.id, student.id, ContentCreate(body='Preserved fictional past conversation', client_key=uuid4()))
    db.commit()
    archive.starts_at, archive.ends_at = now() - timedelta(hours=3), now() - timedelta(hours=1)
    db.commit()
    project = ROOT.parents[1]
    driver = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'
    environment = os.environ | {'ENVIRONMENT': 'local', 'FIXTURE_AUTH': 'true',
        'DATABASE_URL': get_settings().database_url, 'SPRINT8_PLAYWRIGHT': str(driver),
        'SPRINT8_FIXTURES': json.dumps({'orgId': org.id, 'eventId': event.id, 'archiveId': archive.id,
            'studentId': student.id, 'inviteeId': fixture_id('Fictional student 3'),
            'visitorId': fixture_id('Fictional visitor (not PLM)')})}
    processes = []
    try:
        api = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                                '--port', '8002', '--no-access-log', '--log-level', 'warning'],
                               cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(api); wait_for('http://127.0.0.1:8002/ready', api)
        web = subprocess.Popen(['node', 'scripts/serve-static.mjs'], cwd=project / 'Code/Frontend',
                               env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(web); wait_for('http://127.0.0.1:3000', web)
        subprocess.run(['node', 'docs/validation/sprint8-browser-check.mjs'], cwd=project,
                       env=environment, check=True, timeout=360)
        db.expire_all()
        visitor = fixture_id('Fictional visitor (not PLM)')
        visitor_request = db.scalar(select(MembershipApplication).where(MembershipApplication.user_id == visitor))
        assert visitor_request.status == 'approved'
        assert db.scalar(select(OrgMembership).where(OrgMembership.user_id == visitor)).active is True
        from app.domains.identity.service import actor_for_user
        visitor_actor = actor_for_user(db, db.get(User, visitor))
        assert visitor_actor.eligible is False and visitor_actor.grants == ()
        requests = list(db.scalars(select(MembershipApplication).where(
            MembershipApplication.user_id == fixture_id('Fictional student 2'))
            .order_by(MembershipApplication.created_at)))
        assert [row.status for row in requests] == ['rejected', 'withdrawn']
        assert requests[0].reason == 'requirements_not_met' and requests[1].resolved_at is not None
        invitee = fixture_id('Fictional student 3')
        assert db.scalar(select(MembershipInvitation.status).where(MembershipInvitation.recipient_id == invitee)) == 'accepted'
        assert db.scalar(select(OrgMembership).where(OrgMembership.user_id == invitee)).active is False
        active_rows = list(db.scalars(select(Registration).where(Registration.event_id == event.id)))
        assert {row.user_id: row.status for row in active_rows} == {student.id: 'cancelled', faculty.id: 'confirmed'}
        assert db.scalar(select(Registration.status).where(
            Registration.event_id == archive.id, Registration.user_id == student.id)) == 'confirmed'
        assert db.scalar(select(EventAccessRevocation.id).where(
            EventAccessRevocation.event_id == archive.id, EventAccessRevocation.user_id == student.id)) is not None
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
