from datetime import datetime
from types import SimpleNamespace
from typing import Iterable
from uuid import UUID

from sqlalchemy import and_, delete, exists, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.communication import author_label
from app.core.errors import DomainError
from app.core.membership_access import unrevoked_registration
from app.db.models import now
from app.domains.events.models import Event
from app.domains.identity.models import User
from app.domains.identity.service import email_is_eligible
from app.domains.moderation.models import ContentHide
from app.domains.organizations.models import Organization
from app.domains.personas.models import EventPersonaVisibility, UserBlock
from app.domains.personas.schemas import PersonaOut, PersonaVisibilityOut, UserBlockOut
from app.domains.registrations.models import Registration
from app.domains.social.models import EventComment


UNAVAILABLE_CODE = 'persona_unavailable'
UNAVAILABLE_MESSAGE = 'This persona is unavailable in this event.'


def blocked_user_ids(db: Session, viewer_id: str) -> set[str]:
    """Return users hidden from viewer in either block direction."""
    rows = db.execute(select(UserBlock.blocker_id, UserBlock.target_id).where(or_(
        UserBlock.blocker_id == viewer_id,
        UserBlock.target_id == viewer_id,
    ))).all()
    return {
        target_id if blocker_id == viewer_id else blocker_id
        for blocker_id, target_id in rows
    }


def outgoing_blocked_user_ids(db: Session, viewer_id: str) -> set[str]:
    """Return only this user's blocks, for registration-warning projections."""
    return set(db.scalars(select(UserBlock.target_id).where(
        UserBlock.blocker_id == viewer_id,
    )).all())


def is_blocked(db: Session, viewer_id: str, target_id: str) -> bool:
    return db.scalar(select(UserBlock.blocker_id).where(or_(
        and_(UserBlock.blocker_id == viewer_id, UserBlock.target_id == target_id),
        and_(UserBlock.blocker_id == target_id, UserBlock.target_id == viewer_id),
    )).limit(1)) is not None


def _require_actor(db: Session, user_id: str) -> User:
    user = db.get(User, str(user_id))
    if user is None or not user.active:
        raise DomainError('authentication_required', 'Authentication could not be verified.', 401)
    if not email_is_eligible(user.email, user.email_verified):
        raise DomainError('plm_email_required', 'A verified PLM email address is required.', 403)
    return user


def _published_approved_event(db: Session, event_id: str | UUID) -> Event:
    event = db.scalar(
        select(Event)
        .join(Organization, Organization.id == Event.org_id)
        .where(
            Event.id == str(event_id),
            Event.status == 'published',
            Organization.accreditation_status == 'approved',
        )
    )
    if event is None or event.ends_at is None:
        raise DomainError('event_not_found', 'Event was not found.', 404)
    return event


def _confirmed_user_ids(db: Session, event_id: str, user_ids: Iterable[str]) -> set[str]:
    ids = set(user_ids)
    if not ids:
        return set()
    return set(db.scalars(select(Registration.user_id).where(
        Registration.event_id == event_id,
        Registration.user_id.in_(ids),
        Registration.status == 'confirmed',
        unrevoked_registration(),
    )).all())


def visible_persona_user_ids(
    db: Session,
    event: Event,
    viewer_id: str | None,
    author_ids: Iterable[str],
    *,
    at: datetime | None = None,
    allow_broad: bool = False,
) -> set[str]:
    """Batch resolve visible text personas for one event projection."""
    ids = {str(user_id) for user_id in author_ids}
    if not ids or viewer_id is None:
        return set()

    viewer_id = str(viewer_id)
    viewer = db.get(User, viewer_id)
    if viewer is None or not viewer.active or not email_is_eligible(viewer.email, viewer.email_verified):
        return set()
    organization = db.get(Organization, event.org_id)
    if event.status != 'published' or organization is None or organization.accreditation_status != 'approved':
        return set()

    timestamp = at or now()
    people = db.scalars(select(User).where(User.id.in_(ids))).all()
    eligible_ids = {
        person.id for person in people
        if person.active and email_is_eligible(person.email, person.email_verified)
    }
    if not eligible_ids:
        return set()

    blocked = blocked_user_ids(db, viewer_id)
    eligible_ids.difference_update(blocked)
    if not eligible_ids:
        return set()

    pending_ids: set[str] = set()
    if event.registration_mode == 'approval':
        pending_ids = set(db.scalars(select(Registration.user_id).where(
            Registration.event_id == event.id,
            Registration.user_id.in_(eligible_ids),
            Registration.status == 'pending',
        )).all())
        eligible_ids.difference_update(pending_ids)
    if not eligible_ids:
        return set()

    confirmed = set()
    event_shared: set[str] = set()
    if event.ends_at is not None and event.ends_at > timestamp:
        confirmed = _confirmed_user_ids(db, event.id, eligible_ids | {viewer_id})
        if viewer_id in confirmed:
            event_shared = set(db.scalars(select(EventPersonaVisibility.user_id).where(
                EventPersonaVisibility.event_id == event.id,
                EventPersonaVisibility.user_id.in_(eligible_ids),
                EventPersonaVisibility.visible.is_(True),
            )).all()) & confirmed

    broad_ids = {
        person.id for person in people
        if allow_broad and person.id in eligible_ids and person.persona_visible
    }
    return broad_ids | event_shared


def project_author_labels(
    db: Session,
    event: Event,
    viewer_id: str | None,
    author_rows: Iterable[tuple[str, str | None]],
    *,
    at: datetime | None = None,
    allow_broad: bool = False,
) -> tuple[dict[str, str], set[str]]:
    """Project current safe labels for distinct content authors in one batch."""
    authors = {
        str(author_id): SimpleNamespace(id=str(author_id), nickname=nickname)
        for author_id, nickname in author_rows
    }
    if not authors:
        return {}, set()
    visible = visible_persona_user_ids(
        db, event, viewer_id, authors, at=at, allow_broad=allow_broad,
    )
    labels = {
        author_id: author_label(author, viewer_id, show_persona=author_id in visible)
        for author_id, author in authors.items()
    } if viewer_id is not None else {}
    return labels, visible


def _has_visible_comment(db: Session, event_id: str, viewer_id: str, target_id: str) -> bool:
    return db.scalar(select(EventComment.id).where(
        EventComment.event_id == event_id,
        EventComment.author_id == target_id,
        EventComment.removed_at.is_(None),
        EventComment.body.is_not(None),
        ~exists(select(ContentHide.id).where(
            ContentHide.user_id == viewer_id,
            ContentHide.kind == 'comment',
            ContentHide.target_id == EventComment.id,
        )),
    ).limit(1)) is not None


def _has_shared_chat(
    db: Session,
    event: Event,
    viewer_id: str,
    target_id: str,
    at: datetime,
) -> bool:
    from app.domains.chat.service import CHAT_RETENTION

    if event.ends_at is None or at >= event.ends_at + CHAT_RETENTION:
        return False
    return {viewer_id, target_id} <= _confirmed_user_ids(db, event.id, {viewer_id, target_id})


def _unavailable() -> DomainError:
    return DomainError(UNAVAILABLE_CODE, UNAVAILABLE_MESSAGE, 404)


def get_event_persona(
    db: Session,
    event_id: str | UUID,
    target_id: str | UUID,
    viewer_id: str,
    *,
    at: datetime | None = None,
) -> PersonaOut:
    _require_actor(db, viewer_id)
    timestamp = at or now()
    event = _published_approved_event(db, event_id)
    target_id = str(target_id)
    target = db.get(User, target_id)
    if target is None or not target.active or not email_is_eligible(target.email, target.email_verified):
        raise _unavailable()
    has_comment = _has_visible_comment(db, event.id, viewer_id, target_id)
    has_chat = _has_shared_chat(db, event, viewer_id, target_id, timestamp)
    if not has_comment and not has_chat:
        raise _unavailable()

    visible_ids = visible_persona_user_ids(
        db,
        event,
        viewer_id,
        {target_id},
        at=timestamp,
        # This lookup is reached only after proving a visible comment or a
        # retained shared-chat context, so global text sharing applies in
        # either authorized event context.
        allow_broad=has_comment or has_chat,
    )
    if target_id not in visible_ids:
        raise _unavailable()

    tags = target.tags if isinstance(target.tags, list) else []
    return PersonaOut(
        nickname=target.nickname,
        age_bracket=target.age_bracket,
        tags=[tag for tag in tags if isinstance(tag, str)],
        pronouns=target.pronouns,
        icebreaker=target.icebreaker,
    )


def _require_confirmed_attendee(db: Session, event: Event, user_id: str) -> None:
    if user_id not in _confirmed_user_ids(db, event.id, {user_id}):
        raise DomainError(
            'persona_visibility_forbidden',
            'A confirmed event registration is required.',
            403,
        )


def get_event_visibility(
    db: Session,
    event_id: str | UUID,
    user_id: str,
    *,
    at: datetime | None = None,
) -> PersonaVisibilityOut:
    _require_actor(db, user_id)
    event = _published_approved_event(db, event_id)
    _require_confirmed_attendee(db, event, user_id)
    visibility = db.get(EventPersonaVisibility, (event.id, user_id))
    active = bool(visibility and visibility.visible and event.ends_at > (at or now()))
    return PersonaVisibilityOut(visible=active, expires_at=event.ends_at)


def set_event_visibility(
    db: Session,
    event_id: str | UUID,
    user_id: str,
    visible: bool,
    *,
    at: datetime | None = None,
) -> PersonaVisibilityOut:
    _require_actor(db, user_id)
    event = _published_approved_event(db, event_id)
    _require_confirmed_attendee(db, event, user_id)
    timestamp = at or now()
    if visible and event.ends_at <= timestamp:
        raise DomainError('persona_visibility_expired', 'Event persona sharing has expired.', 409)

    db.execute(pg_insert(EventPersonaVisibility).values(
        event_id=event.id,
        user_id=user_id,
        visible=visible,
    ).on_conflict_do_update(
        index_elements=[EventPersonaVisibility.event_id, EventPersonaVisibility.user_id],
        set_={'visible': visible},
    ))
    db.flush()
    return PersonaVisibilityOut(
        visible=bool(visible and event.ends_at > timestamp),
        expires_at=event.ends_at,
    )


def block_user(
    db: Session,
    event_id: str | UUID,
    viewer_id: str,
    target_id: str | UUID,
    *,
    at: datetime | None = None,
) -> UserBlockOut:
    _require_actor(db, viewer_id)
    target_id = str(target_id)
    if target_id == viewer_id:
        raise DomainError('block_self_forbidden', 'You cannot block your own account.', 422)

    event = _published_approved_event(db, event_id)
    timestamp = at or now()
    has_comment = _has_visible_comment(db, event.id, viewer_id, target_id)
    has_chat = _has_shared_chat(db, event, viewer_id, target_id, timestamp)
    if not has_comment and not has_chat:
        raise _unavailable()

    db.execute(pg_insert(UserBlock).values(
        blocker_id=viewer_id,
        target_id=target_id,
        created_at=timestamp,
    ).on_conflict_do_nothing(
        index_elements=[UserBlock.blocker_id, UserBlock.target_id],
    ))
    db.flush()
    block = db.get(UserBlock, (viewer_id, target_id))
    return UserBlockOut(user_id=target_id, created_at=block.created_at)


def list_blocks(db: Session, user_id: str) -> list[UserBlockOut]:
    _require_actor(db, user_id)
    rows = db.scalars(select(UserBlock).where(
        UserBlock.blocker_id == user_id,
    ).order_by(UserBlock.created_at.desc(), UserBlock.target_id)).all()
    return [UserBlockOut(user_id=row.target_id, created_at=row.created_at) for row in rows]


def unblock_user(db: Session, user_id: str, target_id: str | UUID) -> None:
    _require_actor(db, user_id)
    db.execute(delete(UserBlock).where(
        UserBlock.blocker_id == user_id,
        UserBlock.target_id == str(target_id),
    ))
