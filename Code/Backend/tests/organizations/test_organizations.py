from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from sqlalchemy import select

from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.models import uid
from app.db.session import session_factory
from app.domains.identity.models import User
from app.domains.organizations.models import AccreditationDecision, Organization, OrgMembership
from app.domains.organizations.service import (
    active_club_ids,
    active_memberships,
    decide_accreditation,
    require_manager,
    require_platform_admin,
    require_publishing,
)


def auth(user, token_for):
    return {'Authorization': f'Bearer {token_for(user)}'}


def actor_for(user, *, eligible=True):
    return Actor(
        user_id=user.id,
        nickname=user.nickname,
        eligible=eligible,
        profile_complete=True,
        platform_admin=user.platform_admin,
    )


def test_creation_starts_pending_and_grants_owner_access(client, db, make_user, token_for):
    owner = make_user()
    response = client.post('/api/v1/organizations', headers=auth(owner, token_for), json={'name': '  Fictional club  '})

    assert response.status_code == 201
    body = response.json()
    assert body['name'] == 'Fictional club'
    assert body['description'] == ''
    assert body['accreditation_status'] == 'pending'
    assert body['logo_url'] is None
    assert set(body) == {'id', 'name', 'description', 'accreditation_status', 'created_at', 'logo_url'}

    membership = db.scalar(select(OrgMembership).where(
        OrgMembership.org_id == body['id'], OrgMembership.user_id == owner.id,
    ))
    assert membership is not None and membership.active and membership.role == 'owner'
    assert client.get(f"/api/v1/organizations/{body['id']}/workspace", headers=auth(owner, token_for)).status_code == 200


def test_pending_organization_cannot_publish_and_ineligible_actor_has_no_club_ids(db, make_user, make_org):
    owner = make_user()
    pending = make_org(owner=owner, accreditation_status='pending')

    with pytest.raises(DomainError) as denied:
        require_publishing(db, actor_for(owner), pending.id)
    assert denied.value.code == 'organization_not_approved'
    assert active_club_ids(db, replace(actor_for(owner), eligible=False)) == []

    approved = make_org(owner=owner, name='Another fictional club', accreditation_status='approved')
    assert require_publishing(db, actor_for(owner), approved.id).id == approved.id
    assert set(active_club_ids(db, actor_for(owner))) == {pending.id, approved.id}


def test_locked_manager_refreshes_organization_loaded_from_actor_grants(db, make_user, make_org):
    owner = make_user()
    admin = make_user(platform_admin=True)
    organization = make_org(owner=owner, accreditation_status='pending')
    actor = actor_for(owner)

    active_memberships(db, actor)
    assert organization.accreditation_status == 'pending'
    with session_factory()() as concurrent_db:
        current = concurrent_db.get(Organization, organization.id)
        current.accreditation_status = 'rejected'
        concurrent_db.add(AccreditationDecision(
            org_id=organization.id,
            outcome='rejected',
            admin_id=admin.id,
        ))
        concurrent_db.commit()

    locked = require_manager(db, actor, organization.id, lock=True)

    assert locked is organization
    assert locked.accreditation_status == 'rejected'


@pytest.mark.parametrize(
    ('initial_status', 'current_status'),
    [('pending', 'approved'), ('pending', 'rejected'), ('approved', 'rejected')],
)
def test_publishing_policy_uses_current_status_after_lock(
    db,
    make_user,
    make_org,
    initial_status,
    current_status,
):
    owner = make_user()
    admin = make_user(platform_admin=True)
    organization = make_org(owner=owner, accreditation_status=initial_status)
    actor = actor_for(owner)

    active_memberships(db, actor)
    with session_factory()() as concurrent_db:
        current = concurrent_db.get(Organization, organization.id)
        current.accreditation_status = current_status
        concurrent_db.add(AccreditationDecision(
            org_id=organization.id,
            outcome=current_status,
            admin_id=admin.id,
        ))
        concurrent_db.commit()

    if current_status == 'approved':
        assert require_publishing(db, actor, organization.id).accreditation_status == 'approved'
    else:
        with pytest.raises(DomainError) as denied:
            require_publishing(db, actor, organization.id)
        assert denied.value.code == 'organization_not_approved'
    assert organization.accreditation_status == current_status


def test_workspace_is_private_to_eligible_owner_or_admin(client, db, make_user, make_org, token_for):
    owner_a = make_user()
    owner_b = make_user()
    outsider = make_org(owner=owner_a)
    target = make_org(owner=owner_b)
    manager = make_user()
    moderator = make_user()
    member = make_user()
    ineligible_manager = make_user(email_verified=False)
    inactive_manager = make_user()
    db.add(OrgMembership(id=uid(), org_id=target.id, user_id=manager.id, role='admin', active=True))
    db.add(OrgMembership(id=uid(), org_id=target.id, user_id=moderator.id, role='moderator', active=True))
    db.add(OrgMembership(id=uid(), org_id=target.id, user_id=member.id, role='member', active=True))
    db.add(OrgMembership(id=uid(), org_id=target.id, user_id=ineligible_manager.id, role='admin', active=True))
    db.add(OrgMembership(id=uid(), org_id=target.id, user_id=inactive_manager.id, role='admin', active=False))
    db.commit()

    outsider_response = client.get(f'/api/v1/organizations/{target.id}/workspace', headers=auth(owner_a, token_for))
    manager_response = client.get(f'/api/v1/organizations/{target.id}/workspace', headers=auth(manager, token_for))
    moderator_response = client.get(f'/api/v1/organizations/{target.id}/workspace', headers=auth(moderator, token_for))
    member_response = client.get(f'/api/v1/organizations/{target.id}/workspace', headers=auth(member, token_for))
    ineligible_response = client.get(
        f'/api/v1/organizations/{target.id}/workspace', headers=auth(ineligible_manager, token_for),
    )
    inactive_response = client.get(
        f'/api/v1/organizations/{target.id}/workspace', headers=auth(inactive_manager, token_for),
    )
    owner_response = client.get(f'/api/v1/organizations/{target.id}/workspace', headers=auth(owner_b, token_for))

    assert outsider_response.status_code == 403
    assert moderator_response.status_code == 403
    assert member_response.status_code == 403
    assert ineligible_response.status_code == 403
    assert inactive_response.status_code == 403
    assert manager_response.status_code == 200
    assert manager_response.json()['role'] == 'admin'
    assert owner_response.status_code == 200
    assert owner_response.json()['role'] == 'owner'
    assert 'created_by' not in owner_response.json()
    assert 'email' not in owner_response.text.lower()


def test_public_profile_does_not_expose_roster_persona_or_email(client, db, make_user, make_org):
    owner = make_user(email='owner-private@example.invalid', persona_visible=True)
    member = make_user(email='member-private@example.invalid', persona_visible=True)
    organization = make_org(owner=owner)
    db.add(OrgMembership(id=uid(), org_id=organization.id, user_id=member.id, role='member', active=True))
    db.commit()

    response = client.get(f'/api/v1/organizations/{organization.id}')

    assert response.status_code == 200
    assert response.json()['logo_url'] is None
    assert set(response.json()) == {'id', 'name', 'description', 'accreditation_status', 'created_at', 'logo_url'}
    body = response.text.lower()
    for private_value in ('owner-private@example.invalid', 'member-private@example.invalid', owner.id, member.id,
                          'persona_visible', 'roster', 'members'):
        assert private_value.lower() not in body


def test_public_organization_hides_pending_and_rejected_but_keeps_reads(client, make_user, make_org, token_for):
    owner = make_user()
    pending = make_org(owner=owner, accreditation_status='pending')
    rejected = make_org(owner=owner, name='Another fictional club', accreditation_status='rejected')
    approved = make_org(owner=owner, name='Approved fictional club', accreditation_status='approved')

    pending_response = client.get(f'/api/v1/organizations/{pending.id}')
    rejected_response = client.get(f'/api/v1/organizations/{rejected.id}')
    approved_response = client.get(f'/api/v1/organizations/{approved.id}')
    manager_workspace = client.get(f'/api/v1/organizations/{pending.id}/workspace', headers=auth(owner, token_for))
    manager_grants = client.get('/api/v1/me/organizations', headers=auth(owner, token_for))

    assert pending_response.status_code == 404
    assert pending_response.json()['error']['code'] == 'organization_not_found'
    assert rejected_response.status_code == 404
    assert rejected_response.json()['error']['code'] == 'organization_not_found'
    assert approved_response.status_code == 200
    assert approved_response.json()['logo_url'] is None
    assert set(approved_response.json()) == {'id', 'name', 'description', 'accreditation_status', 'created_at', 'logo_url'}
    assert manager_workspace.status_code == 200
    assert manager_grants.status_code == 200
    assert {grant['org_id'] for grant in manager_grants.json()['grants']} == {pending.id, rejected.id, approved.id}


def test_database_admin_privilege_cannot_be_spoofed_by_token_or_body(client, make_user, make_org, token_for):
    attacker = make_user()
    real_admin = make_user(platform_admin=True)
    owner = make_user()
    organization = make_org(owner=owner, accreditation_status='pending')
    forged_headers = {'Authorization': f"Bearer {token_for(attacker, platform_admin=True)}"}

    queue = client.get('/api/v1/platform-admin/organizations', headers=forged_headers)
    decision = client.post(
        f'/api/v1/platform-admin/organizations/{organization.id}/accreditation-decision',
        headers=forged_headers,
        json={'outcome': 'approved'},
    )
    forged_body = client.post(
        f'/api/v1/platform-admin/organizations/{organization.id}/accreditation-decision',
        headers=auth(real_admin, token_for),
        json={'outcome': 'approved', 'admin_id': attacker.id, 'decided_at': '2000-01-01T00:00:00Z'},
    )
    invalid_outcome = client.post(
        f'/api/v1/platform-admin/organizations/{organization.id}/accreditation-decision',
        headers=auth(real_admin, token_for),
        json={'outcome': 'pending'},
    )

    assert queue.status_code == 403
    assert decision.status_code == 403
    assert forged_body.status_code == 422
    assert invalid_outcome.status_code == 422


@pytest.mark.parametrize(('field', 'value'), [('platform_admin', False), ('email_verified', False)])
def test_platform_admin_authority_refreshes_database_state(db, make_user, field, value):
    admin = make_user(platform_admin=True)
    actor = actor_for(admin)

    with session_factory()() as concurrent_db:
        current = concurrent_db.get(User, admin.id)
        setattr(current, field, value)
        concurrent_db.commit()

    with pytest.raises(DomainError) as denied:
        require_platform_admin(db, actor)
    assert denied.value.code == 'platform_admin_required'


def test_admin_decision_is_server_audited_atomic_and_terminal(client, db, make_user, make_org, token_for):
    admin = make_user(platform_admin=True)
    second_admin = make_user(platform_admin=True)
    owner = make_user()
    organization = make_org(owner=owner, accreditation_status='pending')

    rejected = client.post(
        f'/api/v1/platform-admin/organizations/{organization.id}/accreditation-decision',
        headers=auth(admin, token_for), json={'outcome': 'rejected'},
    )
    assert rejected.status_code == 200
    assert rejected.json()['accreditation_status'] == 'rejected'
    assert len(rejected.json()['decisions']) == 1
    audit = rejected.json()['decisions'][0]
    assert audit['admin_id'] == admin.id
    assert audit['outcome'] == 'rejected'
    assert audit['decided_at'].endswith('+00:00') or audit['decided_at'].endswith('Z')

    retry = client.post(
        f'/api/v1/platform-admin/organizations/{organization.id}/accreditation-decision',
        headers=auth(second_admin, token_for), json={'outcome': 'approved'},
    )
    db.refresh(organization)
    decisions = list(db.scalars(select(AccreditationDecision).where(AccreditationDecision.org_id == organization.id)))

    assert retry.status_code == 409
    assert organization.accreditation_status == 'rejected'
    assert len(decisions) == 1
    assert decisions[0].admin_id == admin.id


def test_conflicting_admin_decisions_serialize_on_independent_sessions(db, make_user, make_org):
    owner = make_user()
    admins = [make_user(platform_admin=True), make_user(platform_admin=True)]
    organization = make_org(owner=owner, accreditation_status='pending')
    for admin in admins:
        db.add(OrgMembership(id=uid(), org_id=organization.id, user_id=admin.id, role='admin', active=True))
    db.commit()

    barrier = Barrier(2)

    def decide(admin, outcome):
        with session_factory()() as decision_db:
            actor = actor_for(admin)
            grants = active_memberships(decision_db, actor)
            assert any(org.id == organization.id for org, _ in grants)
            assert decision_db.get(Organization, organization.id).accreditation_status == 'pending'
            barrier.wait(timeout=10)
            try:
                decided = decide_accreditation(decision_db, actor, organization.id, outcome)
                decision_db.commit()
                return 'success', admin.id, decided.accreditation_status, None
            except DomainError as error:
                decision_db.rollback()
                return error.status, admin.id, None, error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(decide, admins, ('approved', 'rejected')))

    successes = [item for item in outcomes if item[0] == 'success']
    conflicts = [item for item in outcomes if item[0] == 409]
    assert len(successes) == len(conflicts) == 1
    assert conflicts[0][3] == 'accreditation_decision_closed'

    with session_factory()() as verify_db:
        final_organization = verify_db.get(Organization, organization.id)
        decisions = list(verify_db.scalars(
            select(AccreditationDecision).where(AccreditationDecision.org_id == organization.id),
        ))
    assert final_organization.accreditation_status in {'approved', 'rejected'}
    assert len(decisions) == 1
    assert decisions[0].outcome == final_organization.accreditation_status == successes[0][2]
    assert decisions[0].admin_id == successes[0][1]


def test_admin_queue_includes_decision_audit(client, make_user, make_org, token_for):
    admin = make_user(platform_admin=True)
    owner = make_user()
    organization = make_org(owner=owner, accreditation_status='pending')
    decision = client.post(
        f'/api/v1/platform-admin/organizations/{organization.id}/accreditation-decision',
        headers=auth(admin, token_for), json={'outcome': 'approved'},
    )
    assert decision.status_code == 200

    queue = client.get('/api/v1/platform-admin/organizations', headers=auth(admin, token_for))
    listed = next(item for item in queue.json() if item['id'] == organization.id)

    assert listed['accreditation_status'] == 'approved'
    assert len(listed['decisions']) == 1
    assert listed['decisions'][0]['admin_id'] == admin.id


def test_me_organizations_returns_active_grants_and_manager_workspaces(client, db, make_user, make_org, token_for):
    owner = make_user()
    member = make_user()
    organization = make_org(owner=owner, accreditation_status='pending')
    db.add(OrgMembership(id=uid(), org_id=organization.id, user_id=member.id, role='member', active=True))
    db.commit()

    response = client.get('/api/v1/me/organizations', headers=auth(owner, token_for))

    assert response.status_code == 200
    assert response.json()['grants'] == [{
        'org_id': organization.id,
        'org_name': organization.name,
        'role': 'owner',
        'accreditation_status': 'pending',
    }]
    assert response.json()['owned_workspaces'][0]['role'] == 'owner'
