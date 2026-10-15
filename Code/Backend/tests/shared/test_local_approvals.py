from app.domains.events.models import Event
from app.local_approvals import APPROVAL_EVENT_ID, ensure_approval_fixture
from app.local_identities import ensure_users
from app.local_organizations import ensure_organizations


def test_approval_fixture_is_additive_and_preserves_user_edits(db):
    ensure_users(db)
    db.flush()
    ensure_organizations(db)
    ensure_approval_fixture(db)
    db.commit()
    event = db.get(Event, APPROVAL_EVENT_ID)
    assert event.registration_mode == 'approval' and event.review_window_minutes == 15
    event.title = 'Fictional edited approval workshop'
    event.capacity = 9
    db.commit()
    ensure_approval_fixture(db)
    db.commit()
    db.expire_all()
    assert db.get(Event, APPROVAL_EVENT_ID).title == 'Fictional edited approval workshop'
    assert db.get(Event, APPROVAL_EVENT_ID).capacity == 9
