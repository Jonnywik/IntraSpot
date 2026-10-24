from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.models import now
from app.domains.events.models import Event
from app.domains.events.routes import _public_projection
from app.domains.organizations.models import Organization
from app.domains.planning.models import SavedEvent
from app.domains.planning.schemas import (
    ConflictEvent,
    EventConflictsOut,
    SavedEventOut,
    SavedEventState,
)
from app.domains.registrations.models import Registration


def _visible_public_event(db: Session, event_id: str):
    return db.execute(
        select(Event, Organization.name)
        .join(Organization, Organization.id == Event.org_id)
        .where(
            Event.id == event_id,
            Event.status == "published",
            Organization.accreditation_status == "approved",
        )
    ).first()


def _require_visible_public_event(db: Session, event_id: str):
    row = _visible_public_event(db, event_id)
    if row is None:
        raise DomainError("event_not_found", "Event was not found.", 404)
    return row


def list_saved_events(db: Session, user_id: str) -> list[SavedEventOut]:
    saved_rows = db.execute(
        select(SavedEvent, Event, Organization)
        .outerjoin(Event, Event.id == SavedEvent.event_id)
        .outerjoin(Organization, Organization.id == Event.org_id)
        .where(SavedEvent.user_id == user_id)
        .order_by(SavedEvent.saved_at.desc(), SavedEvent.event_id.asc())
    ).all()
    visible_ids = {event.id for _, event, org in saved_rows
                   if event is not None and org is not None
                   and event.status == 'published' and org.accreditation_status == 'approved'}
    counts = {}
    if visible_ids:
        counts = {event_id: (confirmed, reserved) for event_id, confirmed, reserved in db.execute(
            select(
                Registration.event_id,
                func.count(Registration.id).filter(Registration.status == 'confirmed'),
                func.count(Registration.id).filter(Registration.status.in_(['pending', 'reconfirmation_required'])),
            ).where(Registration.event_id.in_(visible_ids)).group_by(Registration.event_id)
        )}

    result: list[SavedEventOut] = []
    from app.domains.featured.service import active_featured_event_ids
    featured_ids = active_featured_event_ids(db, [event for _, event, _ in saved_rows
                                                if event is not None and event.id in visible_ids])
    for saved, event, organization in saved_rows:
        public_event = None
        if event is not None and event.id in visible_ids:
            confirmed, reserved = counts.get(event.id, (0, 0))
            public_event = _public_projection(db, event, organization.name, confirmed=confirmed, reserved=reserved,
                                              is_featured=event.id in featured_ids)
        result.append(
            SavedEventOut(
                event_id=saved.event_id,
                saved_at=saved.saved_at,
                event=public_event,
            )
        )
    return result


def saved_event_state(db: Session, user_id: str, event_id: str) -> SavedEventState:
    saved = db.get(SavedEvent, (user_id, event_id))
    return SavedEventState(
        event_id=event_id,
        saved=saved is not None,
        saved_at=saved.saved_at if saved is not None else None,
    )


def save_event(db: Session, user_id: str, event_id: str) -> SavedEventState:
    _require_visible_public_event(db, event_id)
    db.execute(
        postgresql_insert(SavedEvent)
        .values(user_id=user_id, event_id=event_id)
        .on_conflict_do_nothing(
            index_elements=[SavedEvent.user_id, SavedEvent.event_id]
        )
    )
    return saved_event_state(db, user_id, event_id)


def remove_saved_event(db: Session, user_id: str, event_id: str) -> SavedEventState:
    db.execute(
        delete(SavedEvent).where(
            SavedEvent.user_id == user_id,
            SavedEvent.event_id == event_id,
        )
    )
    return SavedEventState(event_id=event_id, saved=False, saved_at=None)


def event_conflicts(db: Session, user_id: str, event_id: str) -> EventConflictsOut:
    target, _ = _require_visible_public_event(db, event_id)
    instant = now()
    if (
        target.starts_at is None
        or target.ends_at is None
        or target.ends_at <= instant
    ):
        return EventConflictsOut(event_id=event_id, conflicts=[])

    rows = db.execute(
        select(Event, Organization.name)
        .join(Registration, Registration.event_id == Event.id)
        .join(Organization, Organization.id == Event.org_id)
        .where(
            Registration.user_id == user_id,
            Registration.status == "confirmed",
            Event.id != event_id,
            Event.status == "published",
            Organization.accreditation_status == "approved",
            Event.ends_at > instant,
            Event.starts_at < target.ends_at,
            Event.ends_at > target.starts_at,
        )
        .order_by(Event.starts_at.asc(), Event.id.asc())
    ).all()

    return EventConflictsOut(
        event_id=event_id,
        conflicts=[
            ConflictEvent(
                event_id=event.id,
                title=event.title,
                organization_name=organization_name,
                starts_at=event.starts_at,
                ends_at=event.ends_at,
            )
            for event, organization_name in rows
            if event.starts_at is not None and event.ends_at is not None
        ],
    )
