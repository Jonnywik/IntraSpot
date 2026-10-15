from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.communication_schemas import ContentCreate
from app.db.session import engine
from app.domains.events.models import Event
from app.domains.organizations.models import Organization  # noqa: F401 - register event foreign-key targets before fixture cleanup
from app.domains.social import service
from app.domains.social.models import EventComment, EventReaction


def _run_concurrently(worker, count=3):
    barrier = Barrier(count)

    def start(index):
        barrier.wait(timeout=10)
        return worker(index)

    with ThreadPoolExecutor(max_workers=count) as executor:
        return list(executor.map(start, range(count)))


def test_concurrent_desired_reaction_is_one_row_and_one_interest_delta(
    db, make_user, make_event
):
    user = make_user()
    event = make_event()

    def set_same_reaction(_index):
        with Session(engine(), expire_on_commit=False) as session:
            summary = service.set_reaction(session, event.id, user.id, "interested")
            session.commit()
            return summary

    summaries = _run_concurrently(set_same_reaction)
    assert all(summary.total == 1 for summary in summaries)
    assert db.scalar(
        select(func.count(EventReaction.id)).where(
            EventReaction.event_id == event.id,
            EventReaction.user_id == user.id,
        )
    ) == 1
    assert db.scalar(select(EventReaction.kind).where(EventReaction.event_id == event.id)) == "interested"
    assert db.scalar(select(Event.interest_count).where(Event.id == event.id)) == 1


def test_concurrent_same_comment_key_returns_one_comment(db, make_user, make_event):
    author = make_user()
    event = make_event()
    payload = ContentCreate(body="Exactly once", client_key=uuid4())

    def create_same_comment(_index):
        with Session(engine(), expire_on_commit=False) as session:
            item = service.create_comment(session, event.id, author.id, payload)
            session.commit()
            return item

    items = _run_concurrently(create_same_comment)
    assert len({item.id for item in items}) == 1
    assert len({item.sequence for item in items}) == 1
    assert db.scalar(select(func.count(EventComment.id)).where(EventComment.event_id == event.id)) == 1
