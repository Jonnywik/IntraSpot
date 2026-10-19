import pytest
from sqlalchemy import func, select

from app.domains.announcements.models import Announcement, AnnouncementRevision
from app.domains.announcements.schemas import AnnouncementPatch
from app.domains.announcements.service import update_announcement
from app.domains.identity.models import User
from app.domains.identity.service import actor_for_user
from app.local_announcements import ensure_announcement_fixtures
from app.local_identities import ensure_users, fixture_id
from app.local_organizations import ORGANIZATION_FIXTURE_IDS


def fixtures(db, make_org):
    ensure_users(db)
    db.commit()
    return make_org(owner=db.get(User, fixture_id('Fictional student 4')),
                    id=ORGANIZATION_FIXTURE_IDS['approved'])


def test_additive_announcement_samples_do_not_duplicate_or_overwrite_edits(db, make_org):
    org = fixtures(db, make_org)
    ensure_announcement_fixtures(db)
    db.commit()
    assert db.scalar(select(func.count(Announcement.id))) == 2
    assert db.scalar(select(func.count(AnnouncementRevision.id))) == 2
    post = db.scalar(select(Announcement).where(Announcement.audience == 'public'))
    update_announcement(db, post.id, actor_for_user(db, db.get(User, org.created_by)),
                        AnnouncementPatch(body='Fictional existing edited content.'), '"1"')
    db.commit()
    ensure_announcement_fixtures(db)
    db.commit()
    db.refresh(post)
    assert post.body == 'Fictional existing edited content.' and post.version == 2
    assert db.scalar(select(func.count(Announcement.id))) == 2
    assert db.scalar(select(func.count(AnnouncementRevision.id))) == 3


def test_announcement_sample_collision_is_rejected(db, make_org, make_user):
    org = fixtures(db, make_org)
    other = make_user()
    ensure_announcement_fixtures(db)
    db.commit()
    post = db.scalar(select(Announcement).where(Announcement.org_id == org.id))
    post.created_by = other.id
    db.commit()
    with pytest.raises(RuntimeError, match='collision'):
        ensure_announcement_fixtures(db)


def test_pending_organization_cannot_create_announcement_samples(db, make_org):
    from app.core.errors import DomainError
    org = fixtures(db, make_org)
    org.accreditation_status = 'pending'
    db.commit()
    with pytest.raises(DomainError):
        ensure_announcement_fixtures(db)
    assert db.scalar(select(func.count(Announcement.id))) == 0


def test_announcement_fixture_command_rejects_test_mode():
    from app.local_announcements import main
    with pytest.raises(RuntimeError, match='explicit local mode'):
        main()
