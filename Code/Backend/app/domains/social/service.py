"""Transactional event reactions and public event comments."""

from hashlib import sha256
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.communication import (
    author_label,
    is_locally_hidden,
    require_communication_allowed,
)
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.core.communication_schemas import ContentCreate, ContentItem, ContentPage
from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.identity.models import User
from app.domains.moderation.models import ContentHide
from app.domains.personas.service import project_author_labels
from app.domains.social.models import EventComment, EventReaction
from app.domains.social.schemas import REACTION_KINDS, ReactionKind, ReactionSummary


def _published_event(db: Session, event_id: str, *, lock: bool = False) -> Event:
    statement = select(Event).where(Event.id == event_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    event = db.scalar(statement)
    if event is None or event.status != "published":
        raise DomainError("event_not_found", "Event was not found.", 404)
    return event


def _require_prestart(event: Event, at: datetime) -> None:
    if event.starts_at <= at:
        raise DomainError("event_started", "This event no longer accepts changes.", 409)


def _reaction_summary(
    db: Session,
    event: Event,
    viewer_id: str | None,
    can_react: bool,
) -> ReactionSummary:
    rows = db.execute(
        select(EventReaction.kind, func.count(EventReaction.id))
        .where(EventReaction.event_id == event.id)
        .group_by(EventReaction.kind)
    ).all()
    counts: dict[ReactionKind, int] = {kind: 0 for kind in REACTION_KINDS}
    for kind, count in rows:
        counts[kind] = count

    mine = None
    if viewer_id is not None:
        mine = db.scalar(
            select(EventReaction.kind).where(
                EventReaction.event_id == event.id,
                EventReaction.user_id == viewer_id,
            )
        )

    return ReactionSummary(
        counts=counts,
        total=sum(counts.values()),
        mine=mine,
        can_react=can_react,
    )


def get_reaction_summary(
    db: Session,
    event_id: str | UUID,
    actor: Actor | None,
    at: datetime | None = None,
) -> ReactionSummary:
    timestamp = at or now()
    event = _published_event(db, str(event_id))
    viewer_id = actor.user_id if actor is not None else None
    can_react = bool(actor and actor.eligible and event.starts_at > timestamp)
    return _reaction_summary(db, event, viewer_id, can_react)


def set_reaction(
    db: Session,
    event_id: str | UUID,
    user_id: str,
    desired: ReactionKind | None,
    at: datetime | None = None,
) -> ReactionSummary:
    event = _published_event(db, str(event_id), lock=True)
    timestamp = at or now()
    _require_prestart(event, timestamp)

    reaction = db.scalar(
        select(EventReaction)
        .where(EventReaction.event_id == event.id, EventReaction.user_id == user_id)
        .with_for_update()
    )
    previous = reaction.kind if reaction is not None else None
    if previous != desired:
        if reaction is None and desired is not None:
            db.add(
                EventReaction(
                    id=uid(),
                    event_id=event.id,
                    user_id=user_id,
                    kind=desired,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
        elif reaction is not None and desired is None:
            db.delete(reaction)
        elif reaction is not None:
            reaction.kind = desired
            reaction.updated_at = timestamp

        interested_delta = int(desired == "interested") - int(previous == "interested")
        if interested_delta:
            event.interest_count += interested_delta

    db.flush()
    return _reaction_summary(db, event, user_id, can_react=True)


def _comment_projection(
    db: Session,
    event: Event,
    comment: EventComment,
    author: User,
    viewer_id: str | None,
    *,
    show_persona: bool = False,
) -> ContentItem:
    hidden = is_locally_hidden(db, viewer_id, "comment", comment.id)
    removed = comment.removed_at is not None
    return ContentItem(
        id=comment.id,
        event_id=comment.event_id,
        author_id=comment.author_id,
        author_label=author_label(
            author,
            viewer_id,
            show_persona=show_persona and not hidden and not removed,
        ),
        sequence=comment.sequence,
        body=None if removed or hidden else comment.body,
        created_at=comment.created_at,
        removed=removed,
        locally_hidden=hidden,
        mine=viewer_id == comment.author_id,
    )


def list_comments(
    db: Session,
    event_id: str | UUID,
    actor: Actor | None,
    *,
    before_sequence: int | None = None,
    limit: int = 50,
) -> ContentPage:
    if not 1 <= limit <= 100:
        raise DomainError("invalid_limit", "Limit must be between 1 and 100.", 422)
    event = _published_event(db, str(event_id))
    statement = (
        select(EventComment, User)
        .join(User, User.id == EventComment.author_id)
        .where(EventComment.event_id == event.id)
        .order_by(EventComment.sequence.desc())
        .limit(limit + 1)
    )
    if before_sequence is not None:
        if before_sequence < 1:
            raise DomainError("invalid_cursor", "The comment cursor must be positive.", 422)
        statement = statement.where(EventComment.sequence < before_sequence)

    rows = db.execute(statement).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    viewer_id = actor.user_id if actor is not None else None
    author_rows = db.execute(
        select(EventComment.author_id, User.nickname)
        .select_from(EventComment)
        .outerjoin(User, User.id == EventComment.author_id)
        .where(
            EventComment.event_id == event.id,
            EventComment.removed_at.is_(None),
            EventComment.body.is_not(None),
            ~exists(select(ContentHide.id).where(
                ContentHide.user_id == viewer_id,
                ContentHide.kind == 'comment',
                ContentHide.target_id == EventComment.id,
            )),
        )
        .distinct()
    ).all()
    author_labels, visible_personas = project_author_labels(
        db, event, viewer_id, author_rows,
        at=now(),
        allow_broad=True,
    )
    items = [
        _comment_projection(
            db,
            event,
            comment,
            author,
            viewer_id,
            show_persona=author.id in visible_personas,
        )
        for comment, author in rows
    ]
    return ContentPage(
        items=items,
        next_before=items[-1].sequence if has_more and items else None,
        author_labels=author_labels,
    )


def create_comment(
    db: Session,
    event_id: str | UUID,
    author_id: str,
    payload: ContentCreate,
    at: datetime | None = None,
) -> ContentItem:
    event = _published_event(db, str(event_id), lock=True)
    timestamp = at or now()

    key = str(payload.client_key)
    body_hash = sha256(payload.body.encode("utf-8")).hexdigest()
    existing = db.scalar(
        select(EventComment)
        .where(
            EventComment.event_id == event.id,
            EventComment.author_id == author_id,
            EventComment.client_key == key,
        )
        .with_for_update()
    )
    author = db.get(User, author_id)
    if author is None:
        raise DomainError("authentication_required", "Authentication could not be verified.", 401)
    if existing is not None:
        if existing.body_hash != body_hash:
            raise DomainError(
                "idempotency_conflict",
                "This client key was already used for different content.",
                409,
            )
        return _comment_projection(db, event, existing, author, author_id)

    _require_prestart(event, timestamp)
    require_communication_allowed(db, author_id, at=timestamp, lock=True)
    if at is None:
        timestamp = now()
        _require_prestart(event, timestamp)
    comment = EventComment(
        id=uid(),
        event_id=event.id,
        author_id=author_id,
        body=payload.body,
        body_hash=body_hash,
        client_key=key,
        created_at=timestamp,
    )
    db.add(comment)
    db.flush()
    return _comment_projection(db, event, comment, author, author_id)


def remove_comment_locked(
    db: Session,
    comment_id: str | UUID,
    event_id: str | UUID,
    at: datetime | None = None,
) -> EventComment | None:
    """Tombstone a comment while the caller holds the associated event lock."""
    comment = db.scalar(
        select(EventComment)
        .where(
            EventComment.id == str(comment_id),
            EventComment.event_id == str(event_id),
        )
        .with_for_update()
    )
    if comment is None:
        return None
    if comment.removed_at is None:
        comment.body = None
        comment.removed_at = at or now()
        db.flush()
    return comment


def delete_comment(
    db: Session,
    event_id: str | UUID,
    comment_id: str | UUID,
    author_id: str,
    at: datetime | None = None,
) -> ContentItem:
    event = _published_event(db, str(event_id), lock=True)
    timestamp = at or now()
    _require_prestart(event, timestamp)
    comment = db.scalar(
        select(EventComment)
        .where(
            EventComment.id == str(comment_id),
            EventComment.event_id == event.id,
        )
        .with_for_update()
    )
    if comment is None or comment.author_id != author_id:
        raise DomainError("comment_not_found", "Comment was not found.", 404)
    removed = remove_comment_locked(db, comment.id, event.id, timestamp)
    if removed is None:
        raise DomainError("comment_not_found", "Comment was not found.", 404)
    author = db.get(User, author_id)
    if author is None:
        raise DomainError("authentication_required", "Authentication could not be verified.", 401)
    return _comment_projection(db, event, removed, author, author_id)
