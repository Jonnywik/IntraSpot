"""One additive fictional approval event; existing demo work is never reset."""
import sys
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.engine import make_url

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

APPROVAL_EVENT_ID = fixture_id('sprint6:event:approval-workshop')


def ensure_approval_fixture(db) -> None:
    org_id = ORGANIZATION_FIXTURE_IDS['approved']
    owner_id = fixture_id('Fictional student 4')
    existing = db.get(Event, APPROVAL_EVENT_ID)
    if existing is not None:
        if existing.org_id != org_id or existing.created_by != owner_id:
            raise RuntimeError('Fictional approval event ID collision; nothing was changed.')
        return
    title = 'Fictional Approval Workshop'
    if db.scalar(select(Event.id).where(Event.org_id == org_id, Event.title == title)):
        raise RuntimeError('Fictional approval title collision; nothing was changed.')
    owner = db.get(User, owner_id)
    if owner is None:
        raise RuntimeError('Initialize the fixed fictional identities and organizations first.')
    require_publishing(db, actor_for_user(db, owner), org_id)
    start = now() + timedelta(days=14)
    event = Event(id=APPROVAL_EVENT_ID, org_id=org_id, created_by=owner_id,
                  title=title, description='Fictional local-only approval and reconfirmation demonstration.',
                  starts_at=start, ends_at=start + timedelta(hours=2), capacity=3,
                  venue_name='Fictional PLM classroom', venue_address='Fictional local-demo address, Manila',
                  banner_key='design', registration_mode='approval', review_window_minutes=15)
    db.add(event)
    db.flush()
    publish(db, event)


def main() -> None:
    settings = get_settings()
    url = make_url(settings.database_url)
    if (len(sys.argv) != 1 or settings.environment != 'local' or not settings.fixture_auth
            or url.database != 'intraspot_mvp' or url.host not in {'127.0.0.1', 'localhost'} or url.port != 5433):
        raise RuntimeError('Approval fixture setup requires explicit local mode and the separate MVP database.')
    with session_factory()() as db, db.begin():
        ensure_approval_fixture(db)
    print('One fictional approval event is ready; existing events and registrations were preserved.')


if __name__ == '__main__':
    main()
