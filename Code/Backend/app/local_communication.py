"""Add one fictional community event; no reports, identities or seats are fabricated."""
import sys
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.communication import require_communication_allowed
from app.core.config import get_settings
from app.db.models import now
from app.db.session import session_factory
from app.domains.events.models import Event
from app.domains.events.service import publish
from app.domains.identity.models import User
from app.domains.identity.service import actor_for_user
from app.domains.organizations.service import require_publishing
from app.local_identities import fixture_id
from app.local_organizations import ORGANIZATION_FIXTURE_IDS

COMMUNITY_EVENT_ID = fixture_id('sprint7:event:community-meetup')


def ensure_communication_fixture(db) -> None:
    org_id, owner_id = ORGANIZATION_FIXTURE_IDS['approved'], fixture_id('Fictional student 4')
    existing = db.get(Event, COMMUNITY_EVENT_ID)
    if existing is not None:
        if existing.org_id != org_id or existing.created_by != owner_id:
            raise RuntimeError('Fictional community event collision; nothing was changed.')
        return
    title = 'Fictional Community Meetup'
    if db.scalar(select(Event.id).where(Event.org_id == org_id, Event.title == title)):
        raise RuntimeError('Fictional community title collision; nothing was changed.')
    owner = db.get(User, owner_id)
    if owner is None:
        raise RuntimeError('Initialize the fixed fictional accounts and organizations first.')
    require_publishing(db, actor_for_user(db, owner), org_id)
    require_communication_allowed(db, owner_id, lock=True)
    start = now() + timedelta(days=14)
    event = Event(id=COMMUNITY_EVENT_ID, org_id=org_id, created_by=owner_id,
                  title=title, description='A fictional local-only event for comments, reactions, confirmed chat and safety review.',
                  starts_at=start, ends_at=start + timedelta(hours=2), capacity=8,
                  venue_name='Fictional PLM courtyard', venue_address='Fictional local-demo address, Manila',
                  banner_key='garden', registration_mode='instant')
    db.add(event); db.flush(); publish(db, event)


def main() -> None:
    settings = get_settings()
    target = make_url(settings.database_url)
    if (len(sys.argv) != 1 or settings.environment != 'local' or not settings.fixture_auth
            or target.database != 'intraspot_mvp' or target.host not in {'127.0.0.1', 'localhost'} or target.port != 5433):
        raise RuntimeError('Community fixture setup requires the separate local MVP development database.')
    with session_factory()() as db, db.begin():
        ensure_communication_fixture(db)
    print('One fictional community event ready; existing data preserved. Register sample attendees to open its chat.')


if __name__ == '__main__':
    main()
