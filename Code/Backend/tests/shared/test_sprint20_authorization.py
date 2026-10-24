"""Ownership changes must fence an already-loaded former-owner membership."""
from uuid import uuid4

import pytest

from app.core.errors import DomainError
from app.db.models import uid
from app.domains.identity.service import actor_for_user
from app.domains.organizations.models import OrgMembership
from app.domains.organizations.service import require_manager_membership


def test_loaded_old_owner_membership_cannot_authorize_after_transfer(client, db, make_user, make_org, token_for):
    owner, nominee = make_user(), make_user()
    organization = make_org(owner=owner)
    db.add(OrgMembership(id=uid(), org_id=organization.id, user_id=nominee.id, role='admin', active=True))
    db.commit()
    owner_headers = {'Authorization': f'Bearer {token_for(owner)}'}
    nominee_headers = {'Authorization': f'Bearer {token_for(nominee)}'}
    path = f'/api/v1/organizations/{organization.id}/ownership-transfers'
    created = client.post(path, headers=owner_headers, json={'nominee_id': nominee.id, 'client_key': str(uuid4())})
    assert created.status_code in (200, 201)
    offer = created.json()
    stale_actor = actor_for_user(db, owner)
    _, cached = require_manager_membership(db, stale_actor, organization.id)
    assert cached.role == 'owner'
    accepted = client.post(f'{path}/{offer["id"]}/decision', headers=nominee_headers,
                           json={'action': 'accept', 'version': offer['version']})
    assert accepted.status_code == 200
    with pytest.raises(DomainError) as denied:
        require_manager_membership(db, stale_actor, organization.id, lock=True)
    assert (denied.value.code, denied.value.status) == ('organization_forbidden', 403)
