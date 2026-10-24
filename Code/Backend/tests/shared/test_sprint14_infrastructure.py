"""Additive announcement migration and rollback preservation proof."""
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text

from app.core.config import ROOT
from app.db.models import now, uid
from app.db.session import engine
from app.domains.identity.preferences_models import UserPreferences


def test_announcement_expand_and_empty_rollback_preserve_flash_and_preferences(db, make_event, make_user):
    boundary = now()
    event = make_event(event_type='flash', starts_at=boundary + timedelta(hours=6),
                       ends_at=boundary + timedelta(hours=7), published_at=boundary)
    user = make_user()
    db.add(UserPreferences(user_id=user.id, language='fil', theme='dark', show_flash=False))
    db.commit()
    event_id, user_id, title = event.id, user.id, event.title
    config = Config(str(ROOT / 'alembic.ini'))
    db.rollback()
    try:
        command.downgrade(config, 'mvp_0009')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT event_type FROM events WHERE id=:id'), {'id': event_id}) == 'flash'
            assert connection.scalar(text('SELECT title FROM events WHERE id=:id'), {'id': event_id}) == title
            assert connection.scalar(text('SELECT show_flash FROM user_preferences WHERE user_id=:id'), {'id': user_id}) is False
            assert 'announcements' not in inspect(connection).get_table_names()
        command.upgrade(config, 'head')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0016'
            assert set(('announcements', 'announcement_revisions', 'announcement_reactions',
                        'announcement_reports', 'announcement_report_decisions')) <= set(inspect(connection).get_table_names())
            assert connection.scalar(text('SELECT show_flash FROM user_preferences WHERE user_id=:id'), {'id': user_id}) is False
    finally:
        db.rollback()
        command.upgrade(config, 'head')


def test_announcement_rollback_refuses_data_and_preserves_it(db, make_org):
    from app.domains.announcements.models import Announcement
    organization = make_org()
    post = Announcement(id=uid(), org_id=organization.id, created_by=organization.created_by,
                        title='Fictional rollback proof', body='Preserve this local content.',
                        audience='members', version=1, client_key=uid(), create_hash='a' * 64,
                        created_at=now(), updated_at=now())
    db.add(post)
    db.commit()
    post_id = post.id
    db.rollback()
    with pytest.raises(RuntimeError, match='Sprint 14 announcement data exists'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0009')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0016'
        assert connection.scalar(select(Announcement.body).where(Announcement.id == post_id)) == 'Preserve this local content.'
