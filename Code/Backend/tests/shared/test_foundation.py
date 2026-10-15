import json
import logging
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.core.config import ROOT, Settings


def test_configuration_paths():
    settings = Settings()
    assert settings.jwt_public_key_file == ROOT / '.local/public.pem'
    assert Settings.model_config['env_file'] == ROOT / '.env.local'


@pytest.mark.parametrize('overrides', [
    {'environment': 'production'}, {'fixture_auth': False},
    {'database_url': 'postgresql+psycopg://u:p@localhost:5432/penpot'},
    {'database_url': 'postgresql+psycopg://u:p@remote.example:5433/intraspot_mvp'},
    {'cors_origins': ['*']},
])
def test_configuration_rejects_unsafe_targets(overrides):
    with pytest.raises(ValidationError):
        Settings(**overrides)


def test_health_ready_and_generated_correlation_id(client, caplog):
    with caplog.at_level(logging.INFO, logger='intraspot.actions'):
        response = client.get('/health', headers={'X-Request-ID': 'private@example.invalid?token=secret'})
        assert response.status_code == 200
        UUID(response.headers['X-Request-ID'])
        assert client.get('/ready').status_code == 200
        client.get('/no-route?email=private@example.invalid&token=secret')
    records = [json.loads(r.message) for r in caplog.records if r.name == 'intraspot.actions']
    assert records and all(set(row) == {'request_id', 'action', 'status'} for row in records)
    assert not any('private@' in r.message or 'secret' in r.message or '?' in r.message for r in caplog.records if r.name == 'intraspot.actions')


def test_explicit_cors_allowlist(client):
    allowed = client.options('/api/v1/events', headers={'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'GET'})
    denied = client.options('/api/v1/events', headers={'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'GET'})
    assert allowed.headers['access-control-allow-origin'] == 'http://localhost:3000'
    assert 'access-control-allow-origin' not in denied.headers


def test_failed_commit_never_returns_write_success(client, make_user, token_for, db, monkeypatch, caplog):
    from app.domains.organizations.models import Organization
    user = make_user()
    original_commit = Session.commit
    def track_write(session, flush_context):
        if any(isinstance(row, Organization) for row in session.new | session.dirty):
            session.info['write_failure_probe'] = True
    def fail_commit(self):
        if self.info.get('write_failure_probe'):
            raise RuntimeError('synthetic-secret-commit-failure')
        return original_commit(self)
    event.listen(Session, 'after_flush', track_write)
    try:
        with monkeypatch.context() as patch, caplog.at_level(logging.INFO, logger='intraspot.actions'):
            patch.setattr(Session, 'commit', fail_commit)
            response = client.post('/api/v1/organizations', json={'name': 'Must not persist'},
                                   headers={'Authorization': f'Bearer {token_for(user)}'})
    finally:
        event.remove(Session, 'after_flush', track_write)
    assert response.status_code == 500
    assert 'synthetic-secret' not in response.text
    assert not any('synthetic-secret' in record.message for record in caplog.records)
    assert db.scalar(select(func.count(Organization.id))) == 0
