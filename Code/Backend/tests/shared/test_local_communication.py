from app.domains.events.models import Event
from app.local_communication import COMMUNITY_EVENT_ID, ensure_communication_fixture
from app.local_identities import ensure_users
from app.local_organizations import ensure_organizations


def test_community_fixture_preserves_existing_edits(db):
    ensure_users(db); db.commit()
    ensure_organizations(db); db.commit()
    ensure_communication_fixture(db); db.commit()
    event = db.get(Event, COMMUNITY_EVENT_ID)
    assert event.registration_mode == 'instant' and event.status == 'published'
    event.title, event.capacity = 'Preserved local edits', 6
    db.commit()
    ensure_communication_fixture(db); db.commit(); db.refresh(event)
    assert event.title == 'Preserved local edits' and event.capacity == 6
