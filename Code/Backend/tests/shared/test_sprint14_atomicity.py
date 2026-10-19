"""Independent PostgreSQL race checks for announcement authoring."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select

from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.models import uid
from app.db.session import session_factory
from app.domains.announcements.models import Announcement, AnnouncementRevision
from app.domains.announcements.schemas import AnnouncementCreate, AnnouncementPatch
from app.domains.announcements.service import create_announcement, update_announcement


def actor(user):
    return Actor(user_id=user.id, nickname=user.nickname, eligible=True,
                 profile_complete=True, platform_admin=False)


def test_concurrent_create_retries_publish_one_post_and_one_revision(db, make_user, make_org):
    owner = make_user()
    organization = make_org(owner=owner)
    verified = actor(owner)
    org_id = organization.id
    payload = AnnouncementCreate(title='Fictional concurrent publication', body='One durable publication.',
                                 audience='public', client_key=uid())
    workers = 6
    ready = Barrier(workers)

    def publish():
        with session_factory()() as connection, connection.begin():
            ready.wait(timeout=15)
            return create_announcement(connection, org_id, verified, payload).id

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda _: publish(), range(workers)))
    assert len(set(results)) == 1
    assert db.scalar(select(func.count(Announcement.id))) == 1
    assert db.scalar(select(func.count(AnnouncementRevision.id))) == 1


def test_competing_versioned_edits_cannot_silently_overwrite(db, make_user, make_org):
    owner = make_user()
    organization = make_org(owner=owner)
    verified = actor(owner)
    created = create_announcement(db, organization.id, verified, AnnouncementCreate(
        title='Fictional version race', body='Original body.', audience='public', client_key=uid(),
    ))
    db.commit()
    ready = Barrier(2)

    def edit(body):
        try:
            with session_factory()() as connection, connection.begin():
                ready.wait(timeout=15)
                result = update_announcement(connection, created.id, verified,
                                             AnnouncementPatch(body=body), '"1"')
                return ('saved', result.body)
        except DomainError as error:
            return ('conflict', error.status)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ['First contender.', 'Second contender.']))
    assert sorted(item[0] for item in results) == ['conflict', 'saved']
    assert next(item[1] for item in results if item[0] == 'conflict') == 409
    db.expire_all()
    post = db.get(Announcement, created.id)
    assert post.version == 2
    assert post.body == next(item[1] for item in results if item[0] == 'saved')
    assert db.scalar(select(func.count(AnnouncementRevision.id)).where(
        AnnouncementRevision.announcement_id == created.id)) == 2
