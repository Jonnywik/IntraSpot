"""Public setup input must not replace existing private development settings."""
import sys

import pytest
from sqlalchemy.engine import make_url

from app import real_setup
from app.core.config import Settings, get_settings


def test_setup_write_is_repeatable_and_preserves_conflicting_file(tmp_path):
    path = tmp_path / '.env.real.local'
    real_setup.write_new_or_matching(path, 'public-settings\n')
    real_setup.write_new_or_matching(path, 'public-settings\n')
    with pytest.raises(RuntimeError, match='nothing was overwritten'):
        real_setup.write_new_or_matching(path, 'changed-settings\n')
    assert path.read_text() == 'public-settings\n'


@pytest.fixture
def isolated_setup(monkeypatch, tmp_path):
    backend = tmp_path / 'Backend'
    backend.mkdir()
    (tmp_path / 'Frontend').mkdir()
    source = make_url(get_settings().database_url).set(database='intraspot_mvp')
    base = Settings(_env_file=None, environment='local', fixture_auth=True,
        database_url=source.render_as_string(hide_password=False))
    monkeypatch.setattr(real_setup, 'ROOT', backend)
    monkeypatch.setattr(real_setup, 'Settings', lambda **kwargs: Settings(**kwargs) if kwargs else base)
    monkeypatch.setattr(sys, 'argv', ['setup', '--supabase-url', 'https://sprint15-test.supabase.co',
        '--publishable-key', 'sb_publishable_fictional_setup_test'])
    return backend


def test_setup_conflict_is_detected_before_any_database_access(monkeypatch, isolated_setup):
    path = isolated_setup.parent / 'Frontend/.env.real.local'
    path.write_text('user-owned configuration', encoding='utf-8')
    def forbidden(*args, **kwargs):
        pytest.fail('Conflicting configuration must not connect to a database')
    monkeypatch.setattr(real_setup, 'create_engine', forbidden)
    with pytest.raises(RuntimeError, match='nothing was overwritten'):
        real_setup.main()
    assert path.read_text() == 'user-owned configuration'
    assert not (isolated_setup / '.env.real.local').exists()


def test_setup_creates_only_the_explicit_database_without_seed_or_migration(monkeypatch, isolated_setup):
    calls = []
    class FakeConnection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def scalar(self, statement):
            calls.append(str(statement))
            return 'intraspot_mvp' if 'current_database' in str(statement) else None
        def execute(self, statement):
            calls.append(str(statement))
    class FakeEngine:
        def connect(self):
            return FakeConnection()
        def dispose(self):
            calls.append('dispose')
    monkeypatch.setattr(real_setup, 'create_engine', lambda *args, **kwargs: FakeEngine())
    real_setup.main()
    assert calls == ['SELECT current_database()',
        "SELECT 1 FROM pg_database WHERE datname='intraspot_real_dev'",
        'CREATE DATABASE intraspot_real_dev', 'dispose']
    backend = (isolated_setup / '.env.real.local').read_text()
    frontend = (isolated_setup.parent / 'Frontend/.env.real.local').read_text()
    assert 'AUTH_PROVIDER=supabase\nFIXTURE_AUTH=false' in backend
    assert '/intraspot_real_dev\n' in backend
    assert 'NEXT_PUBLIC_LOCAL_DEMO=false' in frontend
    assert '8011' in frontend and '3000' not in frontend


def test_fixture_setup_refuses_the_real_profile(monkeypatch):
    from app import local_setup
    monkeypatch.setenv('INTRASPOT_CONFIG', 'real')
    with pytest.raises((RuntimeError, SystemExit)):
        local_setup.main()
