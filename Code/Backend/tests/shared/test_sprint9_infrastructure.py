"""Coordinator-owned preference migration and readiness regression checks."""
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import text

from app.core.config import ROOT
from app.db.session import engine


def test_preferences_downgrade_refuses_saved_choices(client, token_for, make_user):
    user = make_user()
    response = client.patch('/api/v1/me/preferences',
                            headers={'Authorization': f'Bearer {token_for(user)}'},
                            json={'language': 'fil', 'theme': 'dark'})
    assert response.status_code == 200
    with pytest.raises(RuntimeError, match='Sprint 9 preferences exist'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0006')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0016'
        assert connection.execute(text('SELECT language, theme FROM user_preferences')).one() == ('fil', 'dark')


def test_empty_preferences_migration_preserves_existing_users(db, make_user):
    user = make_user(nickname='Fictional preserved account')
    user_id = user.id
    db.rollback()
    config = Config(str(ROOT / 'alembic.ini'))
    try:
        command.downgrade(config, 'mvp_0006')
        command.upgrade(config, 'head')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT nickname FROM users WHERE id=:id'), {'id': user_id}) == 'Fictional preserved account'
            assert connection.scalar(text('SELECT COUNT(*) FROM user_preferences')) == 0
    finally:
        db.rollback()
        command.upgrade(config, 'head')


def test_readiness_requires_current_reviewed_migration(client):
    config = Config(str(ROOT / 'alembic.ini'))
    try:
        command.downgrade(config, 'mvp_0006')
        response = client.get('/ready')
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'database_not_ready'
        assert client.get('/health').status_code == 200
        command.upgrade(config, 'head')
        assert client.get('/ready').json() == {'status': 'ready', 'migration': 'mvp_0016'}
    finally:
        command.upgrade(config, 'head')
