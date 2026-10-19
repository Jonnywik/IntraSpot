"""Preservation and guarded rollback use only conftest's serial scratch database."""
from datetime import timedelta

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import ROOT
from app.db.models import now
from app.db.session import engine
from app.domains.identity.discovery_models import UserDiscoveryPreferences
from app.domains.identity.preferences_models import UserPreferences


def config():
    return Config(str(ROOT / "alembic.ini"))


def test_flash_expand_and_default_only_rollback_preserve_existing_data(db, make_user, make_event):
    user = make_user()
    event = make_event(tags=["arts"], coarse_area="intramuros")
    recorded_at = now()
    db.add(UserPreferences(user_id=user.id, theme="dark", language="fil", updated_at=recorded_at))
    db.add(UserDiscoveryPreferences(user_id=user.id, coarse_area="manila", availability=[
        {"weekday": 0, "start_minute": 540, "end_minute": 660},
    ], updated_at=recorded_at))
    db.commit()
    event_id, user_id, title = event.id, user.id, event.title
    db.rollback()
    try:
        command.downgrade(config(), "mvp_0008")
        with engine().connect() as connection:
            assert connection.execute(text(
                "SELECT title, event_type, tags, coarse_area FROM events WHERE id=:id"
            ), {"id": event_id}).one() == (title, "scheduled", ["arts"], "intramuros")
            assert connection.execute(text(
                "SELECT language, theme, updated_at FROM user_preferences WHERE user_id=:id"
            ), {"id": user_id}).one() == ("fil", "dark", recorded_at)
        command.upgrade(config(), "head")
        with engine().connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "mvp_0010"
            assert connection.execute(text(
                "SELECT show_flash, language, theme, updated_at FROM user_preferences WHERE user_id=:id"
            ), {"id": user_id}).one() == (True, "fil", "dark", recorded_at)
            assert connection.execute(text(
                "SELECT coarse_area, availability FROM user_discovery_preferences WHERE user_id=:id"
            ), {"id": user_id}).one() == ("manila", [{"weekday": 0, "start_minute": 540, "end_minute": 660}])
    finally:
        db.rollback()
        command.upgrade(config(), "head")


@pytest.mark.parametrize("kind", ["flash_draft", "flash_published", "hidden_preference"])
def test_flash_rollback_refuses_new_state(db, make_user, make_event, kind):
    user = make_user()
    if kind == "hidden_preference":
        db.add(UserPreferences(user_id=user.id, show_flash=False))
        db.commit()
    else:
        at = now()
        make_event(event_type="flash", status="draft" if kind == "flash_draft" else "published",
                   published_at=None if kind == "flash_draft" else at,
                   starts_at=at + timedelta(hours=6), ends_at=at + timedelta(hours=7))
    db.rollback()
    with pytest.raises(RuntimeError, match="Sprint 13 Flash data"):
        command.downgrade(config(), "mvp_0008")
    with engine().connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "mvp_0010"
        if kind == "hidden_preference":
            assert connection.scalar(text("SELECT show_flash FROM user_preferences")) is False
        else:
            assert connection.scalar(text("SELECT count(*) FROM events WHERE event_type='flash'")) == 1


@pytest.mark.parametrize("invalid", ["approval", "review", "at_publication", "beyond_24h"])
def test_database_guards_flash_invariants(db, make_org, make_event, invalid):
    organization = make_org()
    at = now()
    values = dict(org=organization, event_type="flash", published_at=at,
                  starts_at=at + timedelta(hours=6), ends_at=at + timedelta(hours=25))
    if invalid == "approval":
        values.update(registration_mode="approval", review_window_minutes=15)
    elif invalid == "review":
        values.update(review_window_minutes=15)
    elif invalid == "at_publication":
        values.update(starts_at=at)
    else:
        values.update(starts_at=at + timedelta(hours=24, microseconds=1))
    with pytest.raises(IntegrityError):
        make_event(**values)
    db.rollback()


def test_database_accepts_exact_24h_upper_bound(make_event):
    at = now()
    event = make_event(event_type="flash", published_at=at, starts_at=at + timedelta(hours=24),
                       ends_at=at + timedelta(hours=25))
    assert event.event_type == "flash"
