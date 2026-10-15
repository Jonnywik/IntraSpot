from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from app.core.communication import (
    author_label,
    is_locally_hidden,
    require_communication_allowed,
)
from app.core.communication_schemas import ContentCreate, ContentItem
from app.core.errors import DomainError
from app.core.membership_access import unrevoked_registration
from app.db.models import now
from app.domains.chat.models import ChatMessage
from app.domains.chat.schemas import ChatInboxItem, ChatThread
from app.domains.events.models import Event
from app.domains.identity.models import User
from app.domains.identity.service import email_is_eligible
from app.domains.organizations.models import Organization
from app.domains.registrations.models import Registration

CHAT_RETENTION = timedelta(hours=72)
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


def _event_for_chat(db: Session, event_id: str, *, lock: bool = False) -> Event:
    statement = select(Event).where(Event.id == event_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    event = db.scalar(statement)
    if event is None or event.status != 'published' or event.ends_at is None:
        raise DomainError('event_not_found', 'Event chat was not found.', 404)
    return event


def _require_retained(event: Event, at: datetime) -> None:
    if at >= event.ends_at + CHAT_RETENTION:
        raise DomainError('chat_expired', 'Event chat is no longer available.', 404)


def _published_event(db: Session, event_id: str, at: datetime) -> Event:
    event = _event_for_chat(db, event_id)
    _require_retained(event, at)
    return event


def _require_chat_user(db: Session, user_id: str) -> None:
    user = db.scalar(select(User).where(User.id == user_id).execution_options(populate_existing=True))
    if user is None or not user.active or not email_is_eligible(user.email, user.email_verified):
        raise DomainError('plm_email_required', 'A verified PLM account is required for event chat.', 403)


def _require_confirmed(db: Session, event_id: str, user_id: str) -> Registration:
    _require_chat_user(db, user_id)
    registration = db.scalar(select(Registration).where(
        Registration.event_id == event_id,
        Registration.user_id == user_id,
        Registration.status == 'confirmed',
        unrevoked_registration(),
    ))
    if registration is None:
        raise DomainError('chat_access_forbidden', 'A confirmed event registration is required.', 403)
    return registration


def _content_item(
    db: Session,
    message: ChatMessage,
    viewer_id: str,
    *,
    event: Event,
    at: datetime,
    author: SimpleNamespace,
    persona_shared: bool = False,
) -> ContentItem:
    label = author_label(
        author,
        viewer_id,
        persona_shared=persona_shared,
        before_end=at < event.ends_at,
    )
    locally_hidden = is_locally_hidden(db, viewer_id, 'message', message.id)
    removed = message.removed_at is not None
    return ContentItem(
        id=message.id,
        event_id=message.event_id,
        author_id=message.author_id,
        author_label=label,
        sequence=message.sequence,
        body=None if removed or locally_hidden else message.body,
        created_at=message.created_at,
        removed=removed,
        locally_hidden=locally_hidden,
        mine=message.author_id == viewer_id,
    )


def list_chat_inbox(db: Session, user_id: str, *, at: datetime | None = None) -> list[ChatInboxItem]:
    _require_chat_user(db, user_id)
    timestamp = at or now()
    latest_at = func.max(ChatMessage.created_at)
    rows = db.execute(
        select(
            Event.id,
            Event.title,
            Organization.name,
            Event.ends_at,
            latest_at,
        )
        .select_from(Event)
        .join(Registration, and_(
            Registration.event_id == Event.id,
            Registration.status == 'confirmed',
            Registration.user_id == user_id,
            unrevoked_registration(),
        ))
        .join(Organization, Organization.id == Event.org_id)
        .outerjoin(ChatMessage, ChatMessage.event_id == Event.id)
        .where(
            Event.status == 'published',
            Event.ends_at > timestamp - CHAT_RETENTION,
        )
        .group_by(Event.id, Event.title, Organization.name, Event.ends_at)
        .order_by(latest_at.desc().nullslast(), Event.ends_at.desc(), Event.id)
    ).all()
    return [
        ChatInboxItem(
            event_id=event_id,
            event_title=event_title,
            organization_name=organization_name,
            ends_at=ends_at,
            deletes_at=ends_at + CHAT_RETENTION,
            status='active' if timestamp < ends_at else 'archived',
            latest_at=last_message_at,
        )
        for event_id, event_title, organization_name, ends_at, last_message_at in rows
    ]


def get_chat_thread(
    db: Session,
    event_id: str,
    user_id: str,
    *,
    after_sequence: int | None = None,
    before_sequence: int | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    communication_restricted: bool = False,
    at: datetime | None = None,
) -> ChatThread:
    if after_sequence is not None and before_sequence is not None:
        raise DomainError('chat_cursor_invalid', 'Use only one chat cursor at a time.', 422)
    if not 1 <= limit <= MAX_PAGE_SIZE:
        raise DomainError('chat_limit_invalid', 'Chat page size must be between 1 and 100.', 422)
    timestamp = at or now()
    event = _published_event(db, event_id, timestamp)
    _require_confirmed(db, event.id, user_id)

    statement = select(
        ChatMessage,
        Registration.persona_shared,
        User.id,
        User.nickname,
        User.persona_visible,
    ).select_from(ChatMessage).join(User, User.id == ChatMessage.author_id).outerjoin(
        Registration,
        and_(
            Registration.event_id == ChatMessage.event_id,
            Registration.user_id == ChatMessage.author_id,
            Registration.status == 'confirmed',
            unrevoked_registration(),
        ),
    ).where(ChatMessage.event_id == event.id)

    if after_sequence is not None:
        statement = statement.where(ChatMessage.sequence > after_sequence).order_by(ChatMessage.sequence)
    else:
        if before_sequence is not None:
            statement = statement.where(ChatMessage.sequence < before_sequence)
        statement = statement.order_by(ChatMessage.sequence.desc())

    rows = db.execute(statement.limit(limit + 1)).all()
    has_more_in_query_direction = len(rows) > limit
    rows = rows[:limit]
    if after_sequence is None:
        rows.reverse()

    items = [
        _content_item(
            db,
            message,
            user_id,
            event=event,
            at=timestamp,
            author=SimpleNamespace(
                id=author_id,
                nickname=nickname,
                persona_visible=persona_visible,
            ),
            persona_shared=bool(persona_shared),
        )
        for message, persona_shared, author_id, nickname, persona_visible in rows
    ]
    next_before = None
    if items:
        if after_sequence is None:
            has_older = has_more_in_query_direction
        else:
            has_older = db.scalar(select(ChatMessage.id).where(
                ChatMessage.event_id == event.id,
                ChatMessage.sequence < items[0].sequence,
            ).limit(1)) is not None
        if has_older:
            next_before = items[0].sequence

    # A sequence cursor cannot discover a later tombstone of an older item.
    # Return every retained tombstone ID so clients can clear cached bodies;
    # do not silently truncate this safety projection.
    # shortcut: IDs can grow during the local 72h window; use bounded invalidation
    # cursors before a cloud pilot with meaningful message traffic.
    removed_ids = db.scalars(select(ChatMessage.id).where(
        ChatMessage.event_id == event.id,
        ChatMessage.removed_at.is_not(None),
    ).order_by(ChatMessage.sequence)).all()

    return ChatThread(
        event_id=event.id,
        event_title=event.title,
        status='active' if timestamp < event.ends_at else 'archived',
        deletes_at=event.ends_at + CHAT_RETENTION,
        can_send=timestamp < event.ends_at and not communication_restricted,
        items=items,
        next_before=next_before,
        removed_ids=removed_ids,
    )


def send_chat_message(
    db: Session,
    event_id: str,
    user_id: str,
    payload: ContentCreate,
    *,
    at: datetime | None = None,
) -> ContentItem:
    # Registration-changing workflows also lock the event first. This keeps
    # admission/revocation and chat sends in one serialized order. Sample the
    # live clock only after a potentially blocking event-row lock is acquired.
    event = _event_for_chat(db, event_id, lock=True)
    timestamp = at if at is not None else now()
    _require_retained(event, timestamp)
    _require_confirmed(db, event.id, user_id)
    if timestamp >= event.ends_at:
        raise DomainError('chat_read_only', 'Event chat is read-only after the scheduled end.', 403)

    body = payload.body.strip()
    body_hash = hashlib.sha256(body.encode('utf-8')).hexdigest()
    client_key = str(payload.client_key)
    existing = db.scalar(select(ChatMessage).where(
        ChatMessage.event_id == event.id,
        ChatMessage.author_id == user_id,
        ChatMessage.client_key == client_key,
    ))
    if existing is not None:
        if existing.body_hash != body_hash:
            raise DomainError('idempotency_key_reused', 'This client key was already used for a different message.', 409)
        return _content_item(
            db,
            existing,
            user_id,
            event=event,
            at=timestamp,
            author=SimpleNamespace(id=user_id, nickname=None, persona_visible=False),
        )

    require_communication_allowed(db, user_id, at=timestamp, lock=True)
    _require_chat_user(db, user_id)

    # The shared user lock may also have waited. Use the actual post-lock time
    # for the stored message and recheck both scheduled-end and retention.
    if at is None:
        timestamp = now()
        _require_retained(event, timestamp)
        if timestamp >= event.ends_at:
            raise DomainError('chat_read_only', 'Event chat is read-only after the scheduled end.', 403)

    message = ChatMessage(
        event_id=event.id,
        author_id=user_id,
        body=body,
        body_hash=body_hash,
        client_key=client_key,
        created_at=timestamp,
    )
    db.add(message)
    db.flush()

    from app.notifications import notify_in_app

    recipients = db.execute(select(User.id, User.email, User.email_verified)
        .select_from(Registration).join(User, User.id == Registration.user_id).where(
        Registration.event_id == event.id,
        Registration.status == 'confirmed',
        Registration.user_id != user_id,
        User.active.is_(True),
        unrevoked_registration(),
    )).all()
    for recipient in recipients:
        if not email_is_eligible(recipient.email, recipient.email_verified):
            continue
        recipient_id = recipient.id
        notify_in_app(
            db,
            user_id=recipient_id,
            event_id=event.id,
            kind='chat_message',
            message='New message in an event chat.',
            dedupe_key=f'chat_message:{message.id}:{recipient_id}',
        )
    return _content_item(
        db,
        message,
        user_id,
        event=event,
        at=timestamp,
        author=SimpleNamespace(id=user_id, nickname=None, persona_visible=False),
    )


def remove_message_locked(
    db: Session,
    message_id: str,
    event_id: str,
    at: datetime | None = None,
) -> ChatMessage | None:
    message = db.scalar(select(ChatMessage).where(
        ChatMessage.id == message_id,
        ChatMessage.event_id == event_id,
    ).with_for_update())
    if message is None:
        return None
    if message.removed_at is None:
        message.body = None
        message.removed_at = at or now()
    return message


def purge_event_chat_locked(db: Session, event: Event, at: datetime | None = None) -> int:
    timestamp = at or now()
    if event.ends_at is None or timestamp < event.ends_at + CHAT_RETENTION:
        return 0

    from app.domains.moderation.models import ContentHide

    db.execute(delete(ContentHide).where(
        ContentHide.event_id == event.id,
        ContentHide.kind == 'message',
    ))
    result = db.execute(delete(ChatMessage).where(ChatMessage.event_id == event.id))
    return int(result.rowcount or 0)
