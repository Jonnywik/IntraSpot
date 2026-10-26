"""Hosted configuration must fail closed without reading local dotenv files."""
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import URL, make_url

from app.core.config import Settings, get_settings


def database_url(*, host='aws-0-us-east-1.pooler.supabase.com', username='intraspot_runtime.projectref12345678',
                 port=5432, database='postgres', sslmode='verify-full', sslrootcert,
                 password='configuration-test-only'):
    return URL.create(
        'postgresql+psycopg', username=username, password=password, host=host, port=port,
        database=database, query={'sslmode': sslmode, 'sslrootcert': str(sslrootcert)},
    ).render_as_string(hide_password=False)


def hosted_settings(tmp_path, **changes):
    ca_file = tmp_path / 'supabase-ca.pem'
    if 'database_url' not in changes:
        ca_file.touch(exist_ok=True)
    values = {
        'environment': 'hosted',
        'auth_provider': 'supabase',
        'fixture_auth': False,
        'database_url': database_url(sslrootcert=ca_file),
        'migration_database_url': None,
        'supabase_url': 'https://projectref12345678.supabase.co',
        'supabase_publishable_key': 'sb_publishable_configuration_test_key',
        'public_api_url': 'https://api.intraspot.example',
        'cors_origins': ['https://intraspot.example'],
    }
    return Settings(_env_file=None, **(values | changes))


def test_default_production_profile_remains_rejected():
    assert Settings.model_fields['environment'].default == 'production'
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment='production',
                 database_url='postgresql+psycopg://unit@127.0.0.1:5433/intraspot_mvp')


def test_hosted_settings_require_supabase_and_exact_https_origins(tmp_path):
    configured = hosted_settings(tmp_path)
    assert configured.environment == 'hosted'
    assert configured.auth_provider == 'supabase'
    assert configured.fixture_auth is False
    assert configured.public_api_url == 'https://api.intraspot.example'
    assert configured.cors_origins == ['https://intraspot.example']


@pytest.mark.parametrize('changes', [
    {'fixture_auth': True},
    {'auth_provider': 'fixture'},
    {'supabase_url': 'http://projectref12345678.supabase.co'},
    {'supabase_url': 'https://projectref12345678.supabase.co.evil.invalid'},
    {'supabase_url': 'https://projectref12345678.supabase.co/auth/v1'},
    {'supabase_publishable_key': 'sb_secret_not_publishable'},
    {'public_api_url': 'http://api.intraspot.example'},
    {'public_api_url': 'https://127.0.0.1'},
    {'public_api_url': 'https://api.intraspot.example/v1'},
    {'cors_origins': ['*']},
    {'cors_origins': ['http://localhost:3000']},
    {'cors_origins': ['https://localhost']},
    {'cors_origins': ['https://192.0.2.10']},
    {'cors_origins': ['https://intraspot.example/callback']},
])
def test_hosted_rejects_mixed_auth_and_non_exact_or_private_origins(tmp_path, changes):
    with pytest.raises(ValidationError):
        hosted_settings(tmp_path, **changes)


@pytest.mark.parametrize('database_changes', [
    {'host': 'pooler.supabase.com'},
    {'host': 'aws-0-us-east-1.pooler.supabase.com.evil.invalid'},
    {'port': 6543},
    {'database': 'intraspot_real_dev'},
    {'username': 'postgres.projectref12345678'},
    {'username': 'intraspot_admin.projectref12345678'},
    {'username': 'intraspot_runtime.otherproject'},
    {'password': ''},
    {'sslmode': 'require'},
])
def test_hosted_runtime_database_rejects_wrong_pooler_or_privileged_settings(tmp_path, database_changes):
    ca_file = tmp_path / 'supabase-ca.pem'
    ca_file.touch(exist_ok=True)
    with pytest.raises(ValidationError):
        hosted_settings(tmp_path, database_url=database_url(sslrootcert=ca_file, **database_changes))


def test_hosted_database_requires_an_existing_ca_and_hides_connection_urls(tmp_path):
    ca_file = tmp_path / 'supabase-ca.pem'
    migration_url = database_url(sslrootcert=ca_file, host='aws-0-us-east-1.pooler.supabase.com',
                                username='intraspot_migrator.projectref12345678', password='migration-test-only')
    runtime_url = database_url(sslrootcert=ca_file)
    with pytest.raises(ValidationError):
        hosted_settings(tmp_path, database_url=runtime_url)

    ca_file.touch()
    configured = hosted_settings(tmp_path, database_url=runtime_url, migration_database_url=migration_url)
    representation = repr(configured)
    assert runtime_url not in representation
    assert migration_url not in representation
    assert 'configuration-test-only' not in representation
    assert 'migration-test-only' not in representation
    assert make_url(configured.migration_database_url).username == 'intraspot_migrator.projectref12345678'


@pytest.mark.parametrize('migration_changes', [
    {'host': 'aws-1-us-east-1.pooler.supabase.com'},
    {'port': 6543},
    {'database': 'intraspot_real_dev'},
    {'username': 'intraspot_migrator.otherproject'},
    {'username': 'intraspot_runtime.projectref12345678'},
    {'password': ''},
    {'sslmode': 'require'},
    {'sslrootcert': '/different/supabase-ca.pem'},
])
def test_hosted_migration_url_must_be_separate_and_match_runtime_endpoint(tmp_path, migration_changes):
    ca_file = tmp_path / 'supabase-ca.pem'
    ca_file.touch()
    migration_values = {
        'username': 'intraspot_migrator.projectref12345678',
        'password': 'migration-test-only',
        **migration_changes,
    }
    migration_url = database_url(**({'sslrootcert': ca_file} | migration_values))
    with pytest.raises(ValidationError):
        hosted_settings(tmp_path, migration_database_url=migration_url)


def test_hosted_profile_reads_process_environment_without_dotenv(monkeypatch, tmp_path):
    import app.core.config as configuration

    monkeypatch.setenv('INTRASPOT_CONFIG', 'hosted')
    monkeypatch.setenv('AUTH_PROVIDER', 'supabase')
    monkeypatch.setenv('FIXTURE_AUTH', 'false')
    monkeypatch.setenv('DATABASE_URL', database_url(sslrootcert=tmp_path / 'ca.pem'))
    monkeypatch.setenv('SUPABASE_URL', 'https://projectref12345678.supabase.co')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_configuration_test_key')
    monkeypatch.setenv('PUBLIC_API_URL', 'https://api.intraspot.example')
    monkeypatch.setenv('CORS_ORIGINS', json.dumps(['https://intraspot.example']))
    monkeypatch.delenv('MIGRATION_DATABASE_URL', raising=False)
    (tmp_path / 'ca.pem').touch()

    observed = {}
    original_settings = configuration.Settings

    class SettingsSpy(original_settings):
        def __init__(self, *args, **kwargs):
            observed['env_file'] = kwargs.get('_env_file', 'not-passed')
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(configuration, 'Settings', SettingsSpy)
    get_settings.cache_clear()
    try:
        configured = get_settings()
        assert configured.environment == 'hosted'
        assert observed['env_file'] is None
        assert configured.migration_database_url is None
    finally:
        get_settings.cache_clear()


def test_hosted_runtime_pool_is_three_plus_two_and_local_pool_is_unchanged(monkeypatch, tmp_path):
    import app.db.session as session

    settings = hosted_settings(tmp_path)
    monkeypatch.setattr(session, 'get_settings', lambda: settings)
    session.engine.cache_clear()
    try:
        hosted_engine = session.engine()
        assert hosted_engine.pool.size() == 3
        assert hosted_engine.pool._max_overflow == 2
        hosted_engine.dispose()
        session.engine.cache_clear()
        local_settings = SimpleNamespace(
            environment='local',
            database_url='postgresql+psycopg://unit:unit@127.0.0.1:5433/intraspot_mvp',
        )
        monkeypatch.setattr(session, 'get_settings', lambda: local_settings)
        local_engine = session.engine()
        assert local_engine.pool.size() == 15
        assert local_engine.pool._max_overflow == 5
        local_engine.dispose()
    finally:
        session.engine.cache_clear()
