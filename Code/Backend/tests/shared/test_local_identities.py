from sqlalchemy import func, select

from app.domains.identity.models import User
from app.local_identities import ACCOUNTS, ensure_users, fixture_id


def test_identity_fixtures_are_fixed_idempotent_and_preserve_profiles(db):
    ensure_users(db)
    db.commit()
    assert db.scalar(select(func.count(User.id))) == len(ACCOUNTS) == 15
    student = db.get(User, fixture_id('Fictional student 1'))
    student.nickname = 'Locally edited nickname'
    db.commit()
    ensure_users(db)
    db.commit()
    assert db.scalar(select(func.count(User.id))) == 15
    assert student.nickname == 'Locally edited nickname'
    assert all(not user.persona_visible for user in db.scalars(select(User)))
    assert db.get(User, fixture_id('Fictional incomplete profile')).tags == []
    assert db.get(User, fixture_id('Fictional platform admin')).platform_admin


def test_identity_fixture_collision_never_overwrites_user(db):
    import pytest
    db.add(User(id=fixture_id('Fictional student 1'), email='different@example.invalid'))
    db.commit()
    with pytest.raises(RuntimeError, match='collision'):
        ensure_users(db)
    assert db.get(User, fixture_id('Fictional student 1')).email == 'different@example.invalid'
