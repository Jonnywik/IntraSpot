import json

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.local_identities import ACCOUNTS, fixture_id
from app.main import create_app
import app.local_demo as demo


def local_catalog(monkeypatch, tmp_path, token_for):
    settings = get_settings().model_copy(update={'environment': 'local'})
    monkeypatch.setattr(demo, 'get_settings', lambda: settings)
    catalog = tmp_path / 'fixed-accounts.json'
    catalog.write_text(json.dumps([{'label': label, 'token': token_for(fixture_id(label))}
                                  for label, _, _ in ACCOUNTS]), encoding='utf-8')
    monkeypatch.setattr(demo, 'CATALOG_PATH', catalog)
    return catalog


def test_catalog_is_disabled_in_test_mode(client):
    assert client.get('/api/v1/local-demo/accounts').status_code == 404


def test_loopback_catalog_serves_only_fixed_verified_credentials(monkeypatch, tmp_path, token_for):
    local_catalog(monkeypatch, tmp_path, token_for)
    with TestClient(create_app(), base_url='http://127.0.0.1:8001', client=('127.0.0.1', 50000)) as client:
        result = client.get('/api/v1/local-demo/accounts', headers={'Origin': 'http://localhost:3000'})
        assert result.status_code == 200
        assert result.headers['cache-control'] == 'no-store'
        assert [row['label'] for row in result.json()] == [label for label, _, _ in ACCOUNTS]
        assert client.get('/api/v1/local-demo/accounts', headers={'Origin': 'https://example.test'}).status_code == 404
        assert client.get('/api/v1/local-demo/accounts', headers={'Host': 'example.test'}).status_code == 404
    with TestClient(create_app(), base_url='http://127.0.0.1:8001', client=('192.0.2.1', 50000)) as client:
        assert client.get('/api/v1/local-demo/accounts').status_code == 404


def test_catalog_rejects_wrong_subject_and_never_issues_replacement(monkeypatch, tmp_path, token_for):
    catalog = local_catalog(monkeypatch, tmp_path, token_for)
    rows = json.loads(catalog.read_text())
    rows[0]['token'] = token_for(fixture_id('Fictional student 2'))
    catalog.write_text(json.dumps(rows))
    before = catalog.read_bytes()
    with TestClient(create_app(), base_url='http://127.0.0.1:8001', client=('127.0.0.1', 50000)) as client:
        result = client.get('/api/v1/local-demo/accounts')
    assert result.status_code == 503
    assert catalog.read_bytes() == before
