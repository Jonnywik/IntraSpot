"""Migration proof runs only against conftest's isolated test target."""
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import ROOT
from app.core.discovery import AvailabilityWindow, normalized_label, weekly_intervals
from app.db.models import now
from app.db.session import engine
from app.domains.identity.discovery_models import UserDiscoveryPreferences


def test_labels_and_weekly_union_are_deterministic():
    assert normalized_label("  ＡＲＴＳ  Society  ") == "arts society"
    assert normalized_label("Straße") == "strasse"
    assert weekly_intervals([
        {"weekday": 0, "start_minute": 60, "end_minute": 120},
        {"weekday": 0, "start_minute": 90, "end_minute": 150},
        {"weekday": 0, "start_minute": 150, "end_minute": 180},
    ]) == [(60, 180)]
    with pytest.raises(ValueError):
        AvailabilityWindow(weekday=True, start_minute=60, end_minute=120)
    with pytest.raises(ValueError):
        AvailabilityWindow(weekday=0, start_minute=120, end_minute=60)


def test_discovery_expand_and_empty_rollback_preserve_existing_event(db, make_event):
    event = make_event()
    event_id, title, revision = event.id, event.title, event.material_revision
    db.rollback()
    config = Config(str(ROOT / "alembic.ini"))
    try:
        command.downgrade(config, "mvp_0007")
        with engine().connect() as connection:
            row = connection.execute(text("SELECT title, material_revision FROM events WHERE id=:id"), {"id": event_id}).one()
            assert tuple(row) == (title, revision)
        command.upgrade(config, "head")
        with engine().connect() as connection:
            row = connection.execute(text("SELECT title, material_revision, tags, coarse_area FROM events WHERE id=:id"), {"id": event_id}).one()
            assert tuple(row) == (title, revision, [], None)
    finally:
        db.rollback()
        command.upgrade(config, "head")


@pytest.mark.parametrize("metadata", ["tags", "coarse_area", "private_preferences"])
def test_discovery_rollback_refuses_new_data(db, make_event, metadata):
    event = make_event()
    if metadata == "tags":
        event.tags = ["arts"]
    elif metadata == "coarse_area":
        event.coarse_area = "intramuros"
    else:
        db.add(UserDiscoveryPreferences(user_id=event.created_by, coarse_area="intramuros", availability=[], updated_at=now()))
    db.commit()
    with pytest.raises(RuntimeError, match="Sprint 12 discovery data exists"):
        command.downgrade(Config(str(ROOT / "alembic.ini")), "mvp_0007")
    with engine().connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini'))).get_current_head()
        if metadata == "private_preferences":
            assert connection.scalar(text("SELECT coarse_area FROM user_discovery_preferences")) == "intramuros"
        else:
            row = connection.execute(text("SELECT tags, coarse_area FROM events WHERE id=:id"), {"id": event.id}).one()
            assert row.tags == (["arts"] if metadata == "tags" else [])
            assert row.coarse_area == ("intramuros" if metadata == "coarse_area" else None)
