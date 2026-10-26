"""Additive media upgrade preserves legacy rows and refuses data-loss rollback."""
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from app.core.config import ROOT
from app.db.models import uid
from app.db.session import engine
from app.domains.media.models import MediaAsset
from app.domains.media.storage_models import MediaObject


def test_legacy_media_is_accounted_without_rewriting_metadata(db, make_org):
    org = make_org()
    asset = MediaAsset(id=uid(), org_id=org.id, kind='logo', width=24, height=24,
                       byte_size=1234, created_by=org.created_by)
    db.add(asset)
    db.commit()
    asset_id, org_id = asset.id, org.id
    config = Config(str(ROOT / 'alembic.ini'))
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT current_database()')) == 'intraspot_mvp_test'
        original = connection.scalar(text('SELECT to_jsonb(t)::text FROM media_assets t WHERE id=:id'), {'id': asset_id})
    command.downgrade(config, 'mvp_0017')
    command.upgrade(config, 'head')
    db.expire_all()
    ledger = db.get(MediaObject, asset_id)
    assert (ledger.org_id, ledger.provider, ledger.object_key, ledger.byte_size, ledger.status) == (
        org_id, 'local', asset_id + '.webp', 1234, 'stored')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT to_jsonb(t)::text FROM media_assets t WHERE id=:id'), {'id': asset_id}) == original
    db.rollback()
    with pytest.raises(RuntimeError, match='Media accounting exists'):
        command.downgrade(config, 'mvp_0017')
    assert db.scalar(select(MediaObject.id).where(MediaObject.id == asset_id)) == asset_id
