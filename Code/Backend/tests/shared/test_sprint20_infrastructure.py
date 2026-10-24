"""Additive ownership tables, non-destructive rollback and database invariants."""
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import ROOT
from app.db.models import now, uid
from app.db.session import engine


def test_transfer_migration_roundtrip_preserves_creator_and_existing_rows(db, make_org):
    org = make_org()
    org_id, creator_id = org.id, org.created_by
    db.rollback()
    config = Config(str(ROOT / 'alembic.ini'))
    try:
        command.downgrade(config, 'mvp_0014')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT created_by FROM organizations WHERE id=:id'), {'id': org_id}) == creator_id
            assert connection.scalar(text("SELECT to_regclass('ownership_transfers')")) is None
        command.upgrade(config, 'head')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0017'
            assert connection.scalar(text('SELECT count(*) FROM ownership_transfers')) == 0
    finally:
        command.upgrade(config, 'head')


def test_database_refuses_two_active_owners(db, make_org, make_user):
    org = make_org()
    other = make_user()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text('''INSERT INTO org_memberships (id,org_id,user_id,role,active)
                VALUES (:id,:org,:user,'owner',true)'''), {'id': uid(), 'org': org.id, 'user': other.id})
    assert db.scalar(text("SELECT count(*) FROM org_memberships WHERE org_id=:org AND active AND role='owner'"), {'org': org.id}) == 1


def test_transfer_history_cannot_be_silently_downgraded(db, make_org, make_user):
    from datetime import timedelta
    org = make_org()
    nominee = make_user()
    db.execute(text('''INSERT INTO ownership_transfers
        (id,org_id,from_user_id,nominee_id,client_key,status,version,created_at,expires_at)
        VALUES (:id,:org,:owner,:nominee,:key,'pending',1,:at,:expires)'''), {
        'id': uid(), 'org': org.id, 'owner': org.created_by, 'nominee': nominee.id,
        'key': uid(), 'at': now(), 'expires': now() + timedelta(days=7),
    })
    db.commit()
    with pytest.raises(RuntimeError, match='transfer history exists'):
        command.downgrade(Config(str(ROOT / 'alembic.ini')), 'mvp_0014')
    with engine().connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0017'
        assert connection.scalar(text('SELECT count(*) FROM ownership_transfers')) == 1


def test_upgrade_refuses_duplicate_legacy_owners_without_rewriting_them(db, make_org, make_user):
    org = make_org()
    other = make_user()
    org_id, user_id, membership_id = org.id, other.id, uid()
    db.rollback()
    config = Config(str(ROOT / 'alembic.ini'))
    try:
        command.downgrade(config, 'mvp_0014')
        with engine().begin() as connection:
            connection.execute(text('''INSERT INTO org_memberships (id,org_id,user_id,role,active)
                VALUES (:id,:org,:user,'owner',true)'''), {'id': membership_id, 'org': org_id, 'user': user_id})
        with pytest.raises(RuntimeError, match='Multiple active owners exist'):
            command.upgrade(config, 'head')
        with engine().connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'mvp_0014'
            assert connection.scalar(text("SELECT count(*) FROM org_memberships WHERE org_id=:org AND active AND role='owner'"), {'org': org_id}) == 2
    finally:
        # Explicit disposable-test-row cleanup only; never repairs development data.
        with engine().begin() as connection:
            assert connection.scalar(text('SELECT current_database()')) == 'intraspot_mvp_test'
            connection.execute(text('DELETE FROM org_memberships WHERE id=:id'), {'id': membership_id})
        command.upgrade(config, 'head')
