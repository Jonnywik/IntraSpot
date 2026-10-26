"""Explicit reversible Sprint 18 migration and preservation safeguards."""
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import ROOT
from app.db.models import now
from app.db.session import engine


def test_sprint18_roundtrip_preserves_old_profile_and_feature_tables(db, make_user):
    user = make_user(pronouns='they/them', icebreaker='Fictional welcome', persona_visible=True)
    user_id = user.id
    db.rollback()
    config = Config(str(ROOT / 'alembic.ini'))
    try:
        command.downgrade(config, 'mvp_0013')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT pronouns FROM users WHERE id=:id'), {'id': user_id}) == 'they/them'
            assert connection.scalar(text("SELECT to_regclass('featured_requests')")) is not None
            assert connection.scalar(text("SELECT to_regclass('user_blocks')")) is None
        command.upgrade(config, 'head')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini'))).get_current_head()
            assert connection.scalar(text('SELECT count(*) FROM user_blocks')) == 0
    finally:
        command.upgrade(config, 'head')


def test_sprint18_downgrade_refuses_to_erase_privacy_choices(db, make_user):
    first, second = make_user(), make_user()
    db.execute(text('INSERT INTO user_blocks (blocker_id,target_id,created_at) VALUES (:a,:b,:at)'),
               {'a': first.id, 'b': second.id, 'at': now()})
    db.commit()
    with pytest.raises(RuntimeError, match='privacy choices exist'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0013')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini'))).get_current_head()
        assert connection.scalar(text('SELECT count(*) FROM user_blocks')) == 1
