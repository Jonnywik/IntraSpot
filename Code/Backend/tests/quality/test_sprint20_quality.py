"""Independent Sprint 20 boundary regressions; run DB cases in the coordinator's serial slot."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.db.models import now, uid
from app.db.session import session_factory
from app.domains.chat import service as chat_service
from app.domains.chat.schemas import ContentCreate
from app.domains.memberships.models import MembershipAudit
from app.domains.organizations.models import OrgMembership, Organization
from app.domains.registrations.models import Registration
from app.main import create_app
from app.notifications import Notification


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _add_membership(db, org, user, role='member', active=True):
    grant = OrgMembership(
        id=uid(), org_id=org.id, user_id=user.id, role=role, active=active,
    )
    db.add(grant)
    db.commit()
    return grant


def _offer(client, token, org_id, nominee_id, client_key=None):
    return client.post(
        f'/api/v1/organizations/{org_id}/ownership-transfers',
        headers=_auth(token),
        json={'nominee_id': nominee_id, 'client_key': str(client_key or uuid4())},
        timeout=10,
    )


def _decision(client, token, org_id, transfer_id, action, version=1):
    return client.post(
        f'/api/v1/organizations/{org_id}/ownership-transfers/{transfer_id}/decision',
        headers=_auth(token),
        json={'action': action, 'version': version},
        timeout=10,
    )


def _transfer_status(db, transfer_id):
    return db.execute(text(
        'SELECT status FROM ownership_transfers WHERE id = :transfer_id'
    ), {'transfer_id': transfer_id}).scalar_one()


def _transfer_audits(db, transfer_id):
    return db.execute(text(
        'SELECT action, actor_id FROM ownership_transfer_audits '
        'WHERE transfer_id = :transfer_id ORDER BY created_at, id'
    ), {'transfer_id': transfer_id}).mappings().all()


def _notification_count(db, org_id):
    return db.scalar(select(func.count(Notification.id)).where(
        Notification.org_id == org_id,
    )) or 0


def _seed_registration(db, event, user, status):
    previous = db.scalar(select(func.max(Registration.admission_order)).where(
        Registration.event_id == event.id,
    )) or 0
    registration = Registration(
        id=uid(), user_id=user.id, event_id=event.id, status=status,
        admission_order=previous + 1,
        confirmed_at=now() if status == 'confirmed' else None,
    )
    db.add(registration)
    db.commit()
    return registration


def _send_chat_message(db, event, user, body):
    return chat_service.send_chat_message(
        db, event.id, user.id,
        ContentCreate(body=body, client_key=uuid4()), at=now(),
    )


def test_nominee_resolution_and_transfer_history_stay_organization_scoped(
    client, db, make_user, make_org, token_for,
):
    owner_a = make_user()
    org_a = make_org(owner=owner_a)
    nominee = make_user()
    _add_membership(db, org_a, nominee, role='admin')
    peer_admin = make_user()
    _add_membership(db, org_a, peer_admin, role='admin')
    member = make_user()
    _add_membership(db, org_a, member)

    owner_b = make_user()
    org_b = make_org(owner=owner_b)
    foreign_admin = make_user()
    _add_membership(db, org_b, nominee, role='admin')
    _add_membership(db, org_b, foreign_admin, role='admin')

    owner_a_token = token_for(owner_a)
    foreign_target = _offer(
        client, owner_a_token, org_a.id, foreign_admin.id,
    )
    assert 400 <= foreign_target.status_code < 500
    assert db.execute(text(
        'SELECT count(*) FROM ownership_transfers WHERE org_id = :org_id'
    ), {'org_id': org_a.id}).scalar_one() == 0

    roster = client.get(
        f'/api/v1/organizations/{org_a.id}/members',
        headers=_auth(owner_a_token),
    )
    assert roster.status_code == 200
    assert foreign_admin.id not in {item['user_id'] for item in roster.json()}

    offer_a = _offer(client, owner_a_token, org_a.id, nominee.id)
    offer_b = _offer(
        client, token_for(owner_b), org_b.id, nominee.id,
    )
    assert offer_a.status_code == offer_b.status_code == 201
    transfer_a, transfer_b = offer_a.json()['id'], offer_b.json()['id']

    owner_history = client.get(
        f'/api/v1/organizations/{org_a.id}/ownership-transfers',
        headers=_auth(owner_a_token),
    )
    nominee_history = client.get(
        f'/api/v1/organizations/{org_a.id}/ownership-transfers',
        headers=_auth(token_for(nominee)),
    )
    assert owner_history.status_code == nominee_history.status_code == 200
    assert [item['id'] for item in owner_history.json()] == [transfer_a]
    assert [item['id'] for item in nominee_history.json()] == [transfer_a]

    for actor in (peer_admin, member, owner_b, foreign_admin):
        denied = client.get(
            f'/api/v1/organizations/{org_a.id}/ownership-transfers',
            headers=_auth(token_for(actor)),
        )
        assert denied.status_code == 403
        assert transfer_a not in denied.text
    assert client.get(
        f'/api/v1/organizations/{org_a.id}/ownership-transfers',
    ).status_code == 401


def test_only_current_eligible_owner_can_offer_to_self_org_active_eligible_admin(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    owner_token = token_for(owner)
    member = make_user()
    _add_membership(db, org, member)
    moderator = make_user()
    _add_membership(db, org, moderator, role='moderator')
    admin = make_user()
    _add_membership(db, org, admin, role='admin')
    inactive_admin = make_user()
    _add_membership(db, org, inactive_admin, role='admin', active=False)
    ineligible_admin = make_user(email='fictional-ineligible-owner-target@example.test')
    _add_membership(db, org, ineligible_admin, role='admin')
    foreign_owner = make_user()
    foreign_org = make_org(owner=foreign_owner)
    foreign_admin = make_user()
    _add_membership(db, foreign_org, foreign_admin, role='admin')

    for target in (owner, member, moderator, inactive_admin, ineligible_admin, foreign_admin):
        rejected = _offer(client, owner_token, org.id, target.id)
        assert 400 <= rejected.status_code < 500
    assert db.execute(text(
        'SELECT count(*) FROM ownership_transfers WHERE org_id = :org_id'
    ), {'org_id': org.id}).scalar_one() == 0

    for actor in (admin, moderator, member):
        rejected = _offer(client, token_for(actor), org.id, admin.id)
        assert rejected.status_code == 403

    ineligible_owner = make_user(email='fictional-locked-owner@example.test')
    locked_org = make_org(owner=ineligible_owner)
    locked_admin = make_user()
    _add_membership(db, locked_org, locked_admin, role='admin')
    locked_attempt = _offer(
        client, token_for(ineligible_owner), locked_org.id, locked_admin.id,
    )
    assert locked_attempt.status_code == 403

    valid = _offer(client, owner_token, org.id, admin.id)
    assert valid.status_code == 201
    assert valid.json()['nominee_id'] == admin.id


@pytest.mark.parametrize(
    'revocation',
    [
        'nominee_ineligible', 'nominee_role', 'nominee_inactive',
        'owner_ineligible', 'owner_role', 'owner_inactive',
    ],
)
def test_accept_rechecks_current_eligibility_and_active_roles(
    client, db, make_user, make_org, token_for, revocation,
):
    owner = make_user()
    org = make_org(owner=owner)
    nominee = make_user()
    nominee_grant = _add_membership(db, org, nominee, role='admin')
    owner_grant = db.scalar(select(OrgMembership).where(
        OrgMembership.org_id == org.id,
        OrgMembership.user_id == owner.id,
    ))
    offer = _offer(client, token_for(owner), org.id, nominee.id)
    assert offer.status_code == 201

    stale_nominee_token = token_for(nominee, role='admin', eligible=True)
    if revocation.endswith('_ineligible'):
        user = nominee if revocation.startswith('nominee') else owner
        user.email = 'fictional-no-longer-eligible@example.test'
        user.email_verified = True
    elif revocation.endswith('_role'):
        grant = nominee_grant if revocation.startswith('nominee') else owner_grant
        grant.role = 'member'
    else:
        grant = nominee_grant if revocation.startswith('nominee') else owner_grant
        grant.active = False
    db.commit()

    denied = _decision(
        client, stale_nominee_token, org.id, offer.json()['id'], 'accept',
        version=offer.json()['version'],
    )
    assert denied.status_code == (403 if revocation.endswith('_ineligible') else 409)
    db.expire_all()
    assert _transfer_status(db, offer.json()['id']) == 'pending'
    assert db.scalar(select(func.count(OrgMembership.id)).where(
        OrgMembership.org_id == org.id,
        OrgMembership.role == 'owner',
        OrgMembership.active.is_(True),
    )) == (0 if revocation == 'owner_inactive' or revocation == 'owner_role' else 1)


def test_only_named_same_org_nominee_can_accept_or_decision_path_transfer(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    nominee = make_user()
    _add_membership(db, org, nominee, role='admin')
    other_admin = make_user()
    _add_membership(db, org, other_admin, role='admin')
    other_owner = make_user()
    other_org = make_org(owner=other_owner)
    foreign_admin = make_user()
    _add_membership(db, other_org, foreign_admin, role='admin')

    offer = _offer(client, token_for(owner), org.id, nominee.id)
    assert offer.status_code == 201
    transfer_id = offer.json()['id']

    for actor in (owner, other_admin, foreign_admin):
        denied = _decision(
            client, token_for(actor), org.id, transfer_id, 'accept',
            version=offer.json()['version'],
        )
        assert denied.status_code == 403
    wrong_org = _decision(
        client, token_for(nominee), other_org.id, transfer_id, 'accept',
        version=offer.json()['version'],
    )
    assert wrong_org.status_code == 404
    assert _transfer_status(db, transfer_id) == 'pending'


def test_transfer_is_role_change_and_preserves_participation_chat_and_review_queue(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    nominee = make_user()
    _add_membership(db, org, nominee, role='admin')

    chat_event = make_event(org=org, capacity=2)
    confirmed = _seed_registration(db, chat_event, owner, 'confirmed')
    retained_message = _send_chat_message(
        db, chat_event, owner, 'Existing event chat remains available.',
    )

    waitlist_event = make_event(org=org, capacity=1)
    seat_holder = make_user()
    _seed_registration(db, waitlist_event, seat_holder, 'confirmed')
    waitlisted = _seed_registration(db, waitlist_event, owner, 'waitlisted')

    review_event = make_event(
        org=org, registration_mode='approval', review_window_minutes=60,
    )
    applicant = make_user()
    pending = Registration(
        id=uid(), user_id=applicant.id, event_id=review_event.id,
        status='pending', admission_order=1,
        review_deadline=now() + timedelta(minutes=30), review_stage=0,
        reviewer_id=owner.id, first_reviewer_id=owner.id,
    )
    db.add(pending)
    db.commit()

    owner_token, nominee_token = token_for(owner), token_for(nominee)
    before_queue = client.get(
        f'/api/v1/events/{review_event.id}/registration-review',
        headers=_auth(owner_token),
    )
    assert before_queue.status_code == 200
    assert pending.id in before_queue.text

    offer = _offer(client, owner_token, org.id, nominee.id)
    accepted = _decision(
        client, nominee_token, org.id, offer.json()['id'], 'accept',
        version=offer.json()['version'],
    )
    assert accepted.status_code == 200

    old_review = client.get(
        f'/api/v1/events/{review_event.id}/registration-review',
        headers=_auth(owner_token),
    )
    old_decision = client.post(
        f'/api/v1/events/{review_event.id}/registrations/{pending.id}/decision',
        headers=_auth(owner_token), json={'decision': 'approve'},
    )
    assert old_review.status_code == old_decision.status_code == 403
    assert db.get(Registration, pending.id).status == 'pending'

    new_review = client.get(
        f'/api/v1/events/{review_event.id}/registration-review',
        headers=_auth(nominee_token),
    )
    assert new_review.status_code == 200
    assert pending.id in new_review.text
    new_decision = client.post(
        f'/api/v1/events/{review_event.id}/registrations/{pending.id}/decision',
        headers=_auth(nominee_token), json={'decision': 'approve'},
    )
    assert new_decision.status_code == 200
    assert new_decision.json()['status'] == 'confirmed'

    db.expire_all()
    old_owner_membership = db.scalar(select(OrgMembership).where(
        OrgMembership.org_id == org.id, OrgMembership.user_id == owner.id,
    ))
    new_owner_membership = db.scalar(select(OrgMembership).where(
        OrgMembership.org_id == org.id, OrgMembership.user_id == nominee.id,
    ))
    assert (old_owner_membership.role, old_owner_membership.active) == ('member', True)
    assert (new_owner_membership.role, new_owner_membership.active) == ('owner', True)
    assert db.get(Organization, org.id).created_by == owner.id
    assert db.get(Registration, confirmed.id).status == 'confirmed'
    assert db.get(Registration, waitlisted.id).status == 'waitlisted'

    chat = client.get(
        f'/api/v1/events/{chat_event.id}/chat', headers=_auth(owner_token),
    )
    assert chat.status_code == 200
    assert any(item['id'] == retained_message.id for item in chat.json()['items'])

    role_audits = list(db.scalars(select(MembershipAudit).where(
        MembershipAudit.org_id == org.id,
        MembershipAudit.action == 'ownership_transferred',
    )))
    assert {(item.user_id, item.old_role, item.new_role) for item in role_audits} == {
        (owner.id, 'owner', 'member'),
        (nominee.id, 'admin', 'owner'),
    }


def test_original_request_and_terminal_decision_retries_do_not_duplicate_audit_or_notice(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    nominee = make_user()
    _add_membership(db, org, nominee, role='admin')
    alternate = make_user()
    _add_membership(db, org, alternate, role='admin')
    key = uuid4()

    first = _offer(client, token_for(owner), org.id, nominee.id, key)
    assert first.status_code == 201
    transfer_id = first.json()['id']
    audit_count = len(_transfer_audits(db, transfer_id))
    notice_count = _notification_count(db, org.id)

    request_retry = _offer(client, token_for(owner), org.id, nominee.id, key)
    key_conflict = _offer(client, token_for(owner), org.id, alternate.id, key)
    assert request_retry.status_code == 201
    assert request_retry.json()['id'] == transfer_id
    assert key_conflict.status_code == 409
    assert len(_transfer_audits(db, transfer_id)) == audit_count
    assert _notification_count(db, org.id) == notice_count

    accepted = _decision(
        client, token_for(nominee), org.id, transfer_id, 'accept',
        version=first.json()['version'],
    )
    assert accepted.status_code == 200
    terminal_audits = len(_transfer_audits(db, transfer_id))
    terminal_notices = _notification_count(db, org.id)

    decision_retry = _decision(
        client, token_for(nominee), org.id, transfer_id, 'accept',
        version=first.json()['version'],
    )
    former_owner_accept = _decision(
        client, token_for(owner), org.id, transfer_id, 'accept',
        version=first.json()['version'],
    )
    creator_retry = _offer(client, token_for(owner), org.id, nominee.id, key)
    new_offer = _offer(client, token_for(owner), org.id, alternate.id)
    assert decision_retry.status_code == 200
    assert former_owner_accept.status_code == 403
    assert creator_retry.status_code == 201
    assert decision_retry.json() == accepted.json()
    assert creator_retry.json()['id'] == transfer_id
    assert new_offer.status_code == 403
    assert len(_transfer_audits(db, transfer_id)) == terminal_audits
    assert _notification_count(db, org.id) == terminal_notices
    assert db.scalar(select(OrgMembership.role).where(
        OrgMembership.org_id == org.id, OrgMembership.user_id == owner.id,
    )) == 'member'
    assert db.scalar(select(OrgMembership.user_id).where(
        OrgMembership.org_id == org.id,
        OrgMembership.role == 'owner',
        OrgMembership.active.is_(True),
    )) == nominee.id


def test_expiry_is_derived_after_restart_then_sealed_before_replacement_offer(
    db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    nominee = make_user()
    _add_membership(db, org, nominee, role='admin')
    replacement_nominee = make_user()
    _add_membership(db, org, replacement_nominee, role='admin')

    with TestClient(create_app()) as initial_client:
        offer = _offer(initial_client, token_for(owner), org.id, nominee.id)
        assert offer.status_code == 201
    transfer_id = offer.json()['id']
    boundary = now()
    db.execute(text(
        'UPDATE ownership_transfers SET expires_at = :boundary WHERE id = :transfer_id'
    ), {'boundary': boundary, 'transfer_id': transfer_id})
    db.commit()
    audit_count = len(_transfer_audits(db, transfer_id))

    with TestClient(create_app()) as restarted_client:
        projected = restarted_client.get(
            f'/api/v1/organizations/{org.id}/ownership-transfers',
            headers=_auth(token_for(owner)),
        )
        assert projected.status_code == 200
        assert next(item for item in projected.json() if item['id'] == transfer_id)['status'] == 'expired'
        assert _transfer_status(db, transfer_id) == 'pending'
        assert len(_transfer_audits(db, transfer_id)) == audit_count

        replacement = _offer(
            restarted_client, token_for(owner), org.id, replacement_nominee.id,
        )
        assert replacement.status_code == 201

    assert _transfer_status(db, transfer_id) == 'expired'
    assert len(_transfer_audits(db, transfer_id)) == audit_count + 1
    expired_audit = [item for item in _transfer_audits(db, transfer_id) if item['action'] == 'expired']
    assert len(expired_audit) == 1
    assert expired_audit[0]['actor_id'] is None
    assert _transfer_status(db, replacement.json()['id']) == 'pending'


def test_accept_rechecks_expiry_after_waiting_for_organization_lock(
    db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    nominee = make_user()
    _add_membership(db, org, nominee, role='admin')
    with TestClient(create_app()) as initial_client:
        offer = _offer(initial_client, token_for(owner), org.id, nominee.id)
        assert offer.status_code == 201
    transfer_id = offer.json()['id']

    blocker = session_factory()()
    blocker.execute(select(Organization).where(
        Organization.id == org.id,
    ).with_for_update())
    blocker_pid = blocker.scalar(text('SELECT pg_backend_pid()'))
    request_started = Event()

    def accept_while_locked():
        with TestClient(create_app()) as concurrent_client:
            request_started.set()
            return _decision(
                concurrent_client, token_for(nominee), org.id, transfer_id,
                'accept', version=offer.json()['version'],
            )

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(accept_while_locked)
            try:
                assert request_started.wait(timeout=5)
                deadline = monotonic() + 5
                waiting = False
                while monotonic() < deadline:
                    # The fixture's db Session can retain a transaction-level
                    # statistics snapshot across polls; force a fresh view.
                    db.execute(text('SELECT pg_stat_clear_snapshot()'))
                    waiting = bool(db.scalar(text("""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_stat_activity
                            WHERE datname = current_database()
                              AND pid <> pg_backend_pid()
                              AND wait_event_type = 'Lock'
                              AND :blocker_pid = ANY(pg_blocking_pids(pid))
                              AND query ILIKE '%organizations%'
                        )
                    """), {'blocker_pid': blocker_pid}))
                    if waiting:
                        break
                    sleep(0.02)
                assert waiting, 'accept request did not reach the organization lock'

                with session_factory()() as expiry_db:
                    expiry_db.execute(text("SET LOCAL lock_timeout = '2s'"))
                    expiry_db.execute(text(
                        'UPDATE ownership_transfers SET expires_at = :expired_at WHERE id = :transfer_id'
                    ), {'expired_at': now() - timedelta(microseconds=1), 'transfer_id': transfer_id})
                    expiry_db.commit()
            finally:
                blocker.commit()
            response = future.result(timeout=10)
    finally:
        blocker.rollback()
        blocker.close()

    assert response.status_code == 409
    assert _transfer_status(db, transfer_id) == 'pending'
    with TestClient(create_app()) as projection_client:
        projected = projection_client.get(
            f'/api/v1/organizations/{org.id}/ownership-transfers',
            headers=_auth(token_for(owner)),
            timeout=10,
        )
    assert projected.status_code == 200
    assert next(item for item in projected.json() if item['id'] == transfer_id)['status'] == 'expired'
    assert db.scalar(select(OrgMembership.role).where(
        OrgMembership.org_id == org.id, OrgMembership.user_id == owner.id,
    )) == 'owner'


def test_concurrent_accept_and_revoke_have_one_terminal_winner_and_one_owner(
    db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    nominee = make_user()
    _add_membership(db, org, nominee, role='admin')
    with TestClient(create_app()) as setup_client:
        offer = _offer(setup_client, token_for(owner), org.id, nominee.id)
    assert offer.status_code == 201
    transfer_id = offer.json()['id']
    barrier = Barrier(2)

    def decide(actor, action):
        with TestClient(create_app()) as concurrent_client:
            barrier.wait(timeout=10)
            return _decision(
                concurrent_client, token_for(actor), org.id, transfer_id,
                action, version=offer.json()['version'],
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        accept_future = pool.submit(decide, nominee, 'accept')
        revoke_future = pool.submit(decide, owner, 'revoke')
        outcomes = (accept_future.result(timeout=10), revoke_future.result(timeout=10))

    assert sum(response.status_code == 200 for response in outcomes) == 1
    assert all(response.status_code == 200 or 400 <= response.status_code < 500 for response in outcomes)
    db.expire_all()
    status = _transfer_status(db, transfer_id)
    assert status in {'accepted', 'revoked'}
    assert len([row for row in _transfer_audits(db, transfer_id) if row['action'] in {'accepted', 'revoked'}]) == 1
    assert db.scalar(select(func.count(OrgMembership.id)).where(
        OrgMembership.org_id == org.id,
        OrgMembership.role == 'owner',
        OrgMembership.active.is_(True),
    )) == 1
    expected_owner = nominee.id if status == 'accepted' else owner.id
    assert db.scalar(select(OrgMembership.user_id).where(
        OrgMembership.org_id == org.id,
        OrgMembership.role == 'owner',
        OrgMembership.active.is_(True),
    )) == expected_owner
