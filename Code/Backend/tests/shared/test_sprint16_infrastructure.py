"""Media migration preservation and profile-separated persistent storage."""
import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from app.core.config import ROOT, Settings, get_settings
from app.db.models import uid
from app.db.session import engine


def test_media_roots_are_distinct_for_each_auth_and_environment(tmp_path):
    source = get_settings()
    roots = set()
    for provider, environment, database, origin in [
        ('fixture', 'local', 'intraspot_mvp', 'http://127.0.0.1:3000'),
        ('fixture', 'test', 'intraspot_mvp_test', 'http://127.0.0.1:3000'),
        ('supabase', 'local', 'intraspot_real_dev', 'http://127.0.0.1:3001'),
        ('supabase', 'test', 'intraspot_real_dev_test', 'http://127.0.0.1:3001'),
    ]:
        values = dict(environment=environment, auth_provider=provider,
            fixture_auth=provider == 'fixture', media_root=tmp_path,
            database_url=make_url(source.database_url).set(database=database).render_as_string(hide_password=False),
            cors_origins=[origin], jwt_public_key_file=source.jwt_public_key_file)
        if provider == 'supabase':
            values.update(supabase_url='https://sprint16-test.supabase.co',
                          supabase_publishable_key='sb_publishable_fictional_public_test_key')
        configured = Settings(_env_file=None, **values)
        assert configured.media_root.is_relative_to(tmp_path)
        roots.add(configured.media_root)
    assert len(roots) == 4
    with pytest.raises(ValidationError):
        Settings(media_root='relative-media')


def test_empty_media_migration_round_trip_preserves_existing_event(db, make_event):
    from app.domains.events.models import Event
    event = make_event()
    event_id, title = event.id, event.title
    db.rollback()
    config = Config(str(ROOT / 'alembic.ini'))
    try:
        command.downgrade(config, 'mvp_0010')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT title FROM events WHERE id=:id'), {'id': event_id}) == title
        command.upgrade(config, 'head')
        db.expire_all()
        preserved = db.get(Event, event_id)
        assert preserved.title == title
        assert preserved.banner_media_id is None
    finally:
        db.rollback()
        command.upgrade(config, 'head')


def test_media_downgrade_refuses_to_erase_existing_assets(db, make_org):
    from app.domains.media.models import MediaAsset
    org = make_org()
    asset = MediaAsset(id=uid(), org_id=org.id, kind='logo', width=1, height=1,
                       byte_size=1, created_by=org.created_by)
    db.add(asset)
    db.commit()
    asset_id = asset.id
    db.rollback()
    with pytest.raises(RuntimeError, match='Sprint 16 media data exists'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0010')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0016'
    assert db.scalar(select(MediaAsset.id).where(MediaAsset.id == asset_id)) == asset_id
