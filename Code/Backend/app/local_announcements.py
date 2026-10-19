"""Two additive fictional announcement samples; never overwrite existing posts."""
import sys

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.session import session_factory
from app.domains.announcements.models import Announcement
from app.domains.announcements.schemas import AnnouncementCreate
from app.domains.announcements.service import create_announcement
from app.domains.identity.models import User
from app.domains.identity.service import actor_for_user
from app.local_identities import fixture_id
from app.local_organizations import ORGANIZATION_FIXTURE_IDS

SAMPLES = (
    ('public', 'Fictional community welcome', 'A fictional organization update for the local public demonstration.'),
    ('members', 'Fictional members update', 'A fictional members-only organization update. No real people or private records.'),
)


def ensure_announcement_fixtures(db) -> None:
    org_id = ORGANIZATION_FIXTURE_IDS['approved']
    owner_id = fixture_id('Fictional student 4')
    owner = db.get(User, owner_id)
    if owner is None:
        raise RuntimeError('Initialize the predefined fictional accounts and organizations first.')
    actor = actor_for_user(db, owner)
    for audience, title, body in SAMPLES:
        key = fixture_id('sprint14:announcement:' + audience)
        existing = db.scalar(select(Announcement).where(Announcement.client_key == key))
        if existing is not None:
            if existing.org_id != org_id or existing.created_by != owner_id:
                raise RuntimeError('Fictional announcement collision; nothing was overwritten.')
            continue
        if db.scalar(select(Announcement.id).where(Announcement.org_id == org_id, Announcement.title == title)):
            raise RuntimeError('Fictional announcement title collision; nothing was overwritten.')
        create_announcement(db, org_id, actor, AnnouncementCreate(
            title=title, body=body, audience=audience, client_key=key,
        ))


def main() -> None:
    settings = get_settings()
    target = make_url(settings.database_url)
    if (len(sys.argv) != 1 or settings.environment != 'local' or not settings.fixture_auth
            or target.database != 'intraspot_mvp' or target.host not in {'127.0.0.1', 'localhost'}
            or target.port != 5433):
        raise RuntimeError('Announcement fixtures require explicit local mode and the development MVP database.')
    with session_factory()() as db, db.begin():
        ensure_announcement_fixtures(db)
    print('Fictional announcement fixtures ready; existing posts, history and membership were preserved.')


if __name__ == '__main__':
    main()
