"""Coordinator-owned API isolation and additive recovery metadata checks."""
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from app.core.config import ROOT
from app.erasure_models import ErasureRequest
from app.recovery_models import BackupSnapshot


def test_receipt_is_private_and_caller_derived(client, db, make_user, token_for):
    requester = make_user(email='fictional-personal@example.invalid')
    another = make_user()
    auth = {'Authorization': f'Bearer {token_for(requester)}'}
    assert client.post('/api/v1/me/erasure-request').status_code == 401
    assert client.get('/api/v1/me/erasure-request', headers=auth).json() is None
    first = client.post('/api/v1/me/erasure-request', headers=auth, json={'user_id': another.id})
    assert first.status_code == 200
    receipt = first.json()
    assert not {'user_id','email','nickname'} & receipt.keys()
    assert receipt['id'] and receipt['status'] in {'pending','blocked'}
    assert db.scalar(select(ErasureRequest.user_id).where(ErasureRequest.id == receipt['id'])) == requester.id
    assert client.post('/api/v1/me/erasure-request', headers=auth).json()['id'] == receipt['id']
    other_auth = {'Authorization': f'Bearer {token_for(another)}'}
    assert client.get('/api/v1/me/erasure-request', headers=other_auth).json() is None
    assert client.get('/api/v1/me/erasure-request', headers=auth).json()['id'] == receipt['id']


def test_empty_additive_metadata_rollback_preserves_user(db, make_user):
    user = make_user()
    identity = user.id
    db.rollback()
    config = Config(str(ROOT / 'alembic.ini'))
    command.downgrade(config, 'mvp_0019')
    command.upgrade(config, 'head')
    from app.domains.identity.models import User
    assert db.get(User, identity).active
    assert db.scalar(select(BackupSnapshot.id)) is None
