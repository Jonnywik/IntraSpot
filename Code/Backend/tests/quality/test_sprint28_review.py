from concurrent.futures import ThreadPoolExecutor
from threading import Event as Signal
import json
from sqlalchemy import select, func
from app.core.errors import DomainError
from app.db.session import session_factory
from app.domains.identity.models import User
from app.domains.identity.service import actor_for_user
from app.domains.identity.service import update_profile
from app.domains.organizations.models import Organization
from app.domains.organizations.service import create_organization
from app.domains.eventsafety.service import _event_evidence


def test_stale_actor_cannot_create_an_organization_after_erasure_starts(db, make_user):
    user = make_user()
    actor = actor_for_user(db, user)
    db.commit()
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    started = Signal()

    def create():
        with session_factory().begin() as other:
            started.set()
            try:
                create_organization(other, actor, name='Fictional race', description='test')
            except DomainError as error:
                return error.code
            return 'created'

    with ThreadPoolExecutor(max_workers=1) as pool:
        attempt = pool.submit(create)
        assert started.wait(3)
        user.active = False
        db.commit()
        assert attempt.result(10) == 'organization_forbidden'
    assert db.scalar(select(func.count()).select_from(Organization)) == 0


def test_report_snapshot_keeps_banner_id_within_its_existing_size_bound(make_event):
    event = make_event(description='界' * 2200)
    event.banner_media_id = '11111111-1111-4111-8111-111111111111'
    evidence = _event_evidence(event)
    assert len(evidence.encode()) <= 4096
    assert json.loads(evidence)['banner_media_id'] == event.banner_media_id


def test_loaded_profile_cannot_repopulate_fields_after_erasure(db, make_user):
    user = make_user()
    db.commit()
    with session_factory().begin() as other:
        erased = other.get(User, user.id)
        erased.active = False
        erased.nickname = None
        erased.tags = []
    assert user.active is True  # This request loaded the actor before erasure.
    assert update_profile(db, user.id, {'nickname': 'Restored private data'}) is None
    db.commit()
    db.expire_all()
    assert db.get(User, user.id).nickname is None
