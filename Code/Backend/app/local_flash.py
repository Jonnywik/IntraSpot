"""One additive fictional Flash event; never renew or overwrite an existing event."""
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

FLASH_EVENT_ID = fixture_id("sprint13:event:flash-campus-meetup")
FLASH_TITLE = "Fictional Flash Campus Meetup"


def ensure_flash_fixture(db) -> None:
    org_id = ORGANIZATION_FIXTURE_IDS["approved"]
    owner_id = fixture_id("Fictional student 4")
    existing = db.get(Event, FLASH_EVENT_ID)
    if existing is not None:
        if existing.org_id != org_id or existing.created_by != owner_id:
            raise RuntimeError("Fictional Flash event collision; nothing was changed.")
        return
    if db.scalar(select(Event.id).where(Event.org_id == org_id, Event.title == FLASH_TITLE)):
        raise RuntimeError("Fictional Flash title collision; nothing was changed.")
    owner = db.get(User, owner_id)
    if owner is None:
        raise RuntimeError("Initialize the predefined fictional accounts and organizations first.")
    require_publishing(db, actor_for_user(db, owner), org_id)
    require_communication_allowed(db, owner_id, lock=True)
    starts = now() + timedelta(hours=6)
    event = Event(
        id=FLASH_EVENT_ID, org_id=org_id, created_by=owner_id,
        title=FLASH_TITLE, summary="A fictional, short-notice PLM community gathering.",
        description="Local fictional Flash-event demonstration; no real participants or data.",
        starts_at=starts, ends_at=starts + timedelta(hours=1), capacity=8,
        venue_name="Fictional PLM courtyard", venue_address="Fictional local-demo address, Manila",
        banner_key="garden", registration_mode="instant", event_type="flash",
        tags=["community"], coarse_area="intramuros",
    )
    db.add(event)
    db.flush()
    publish(db, event)


def main() -> None:
    settings = get_settings()
    target = make_url(settings.database_url)
    if (len(sys.argv) != 1 or settings.environment != "local" or not settings.fixture_auth
            or target.database != "intraspot_mvp" or target.host not in {"127.0.0.1", "localhost"}
            or target.port != 5433):
        raise RuntimeError("Flash fixture setup requires explicit local mode and the separate MVP development database.")
    with session_factory()() as db, db.begin():
        ensure_flash_fixture(db)
    print("Fictional Flash fixture ready; existing data preserved. Existing publication times are never renewed.")


if __name__ == "__main__":
    main()
