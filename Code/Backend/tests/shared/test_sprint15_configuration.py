"""Configuration transition must keep fictional and real development disjoint."""
import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings


def real_settings(**changes):
    source = get_settings()
    values = dict(environment='local', auth_provider='supabase', fixture_auth=False,
        database_url=make_url(source.database_url).set(database='intraspot_real_dev').render_as_string(hide_password=False),
        supabase_url='https://sprint15-test.supabase.co',
        supabase_publishable_key='sb_publishable_only_fictional_test_key',
        cors_origins=['http://127.0.0.1:3001'])
    return Settings(_env_file=None, **(values | changes))


def test_real_auth_configuration_is_explicit_and_separate():
    configured = real_settings()
    assert configured.supabase_issuer == 'https://sprint15-test.supabase.co/auth/v1'
    assert configured.fixture_auth is False
    assert configured.supabase_publishable_key not in repr(configured)
    assert configured.database_url not in repr(configured)


@pytest.mark.parametrize('changes', [
    {'fixture_auth': True}, {'environment': 'production'},
    {'supabase_url': 'http://sprint15-test.supabase.co'},
    {'supabase_url': 'https://sprint15-test.supabase.co.evil.invalid'},
    {'supabase_url': 'https://sprint15-test.supabase.co/auth/v1'},
    {'supabase_publishable_key': 'sb_secret_do_not_use_this'},
    {'supabase_publishable_key': 'eyJlegacy.role.token'},
    {'cors_origins': ['http://localhost:3000']}, {'cors_origins': ['*']},
    {'auth_provider': 'fixture'},
])
def test_invalid_or_mixed_real_configuration_fails_closed(changes):
    with pytest.raises(ValidationError):
        real_settings(**changes)


@pytest.mark.parametrize('database', ['intraspot_mvp', 'intraspot_mvp_test', 'postgres', 'intraspot_real_dev_test'])
def test_real_local_profile_cannot_target_fictional_or_test_database(database):
    target = make_url(get_settings().database_url).set(database=database)
    with pytest.raises(ValidationError):
        real_settings(database_url=target.render_as_string(hide_password=False))


def test_unknown_or_missing_real_profile_does_not_fall_back(monkeypatch, tmp_path):
    import app.core.config as configuration
    for profile in ('unknown', 'real'):
        monkeypatch.setenv('INTRASPOT_CONFIG', profile)
        monkeypatch.setattr(configuration, 'ROOT', tmp_path)
        get_settings.cache_clear()
        with pytest.raises(ValueError):
            get_settings()
    get_settings.cache_clear()
