from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import current_actor, optional_actor, require_eligible
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.core.communication import require_communication_allowed
from app.db.models import now
from app.db.session import get_db
from app.domains.events.models import Event
from app.domains.events.schemas import EventChangeInput, EventDraftInput, EventPrivate, EventPublic
from app.domains.events.service import (
    create_draft,
    publish,
    update_draft,
    validate_material_change,
)
from app.domains.organizations.models import Organization
from app.domains.organizations.service import active_club_ids, require_manager, require_publishing


router = APIRouter()


def _event_or_404(db: Session, event_id: str) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise DomainError("event_not_found", "Event was not found.", 404)
    return event


def _require_draft_writable(organization: Organization) -> None:
    # Manager authorization is shared with Organizations; rejected organizations
    # retain private read access but cannot mutate event drafts.
    if organization.accreditation_status == "rejected":
        raise DomainError(
            "organization_rejected_read_only",
            "Rejected organizations cannot change event drafts.",
            409,
        )


def _organization_name(db: Session, org_id: str) -> str:
    name = db.scalar(select(Organization.name).where(Organization.id == org_id))
    if name is None:
        raise DomainError("event_not_found", "Event was not found.", 404)
    return name


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Public reads stay read-only. Registration reconciliation runs on write paths or
# a bounded worker, never per-row on GET. Counts aggregate committed confirmed
# and reserved registrations; an unprocessed receipt stays invisible.
def _confirmed_count(db: Session, event_id: str) -> int:
    # Runtime import preserves the existing Events/Registrations module boundary.
    from app.domains.registrations.models import Registration

    return db.scalar(
        select(func.count(Registration.id)).where(
            Registration.event_id == event_id,
            Registration.status == "confirmed",
        )
    ) or 0


def _reserved_count(db: Session, event_id: str) -> int:
    from app.domains.registrations.models import Registration

    return db.scalar(
        select(func.count(Registration.id)).where(
            Registration.event_id == event_id,
            Registration.status.in_(("pending", "reconfirmation_required")),
        )
    ) or 0


def _public_projection(
    db: Session,
    event: Event,
    organization_name: str,
    confirmed: int | None = None,
    reserved: int | None = None,
) -> EventPublic:
    if confirmed is None:
        confirmed = _confirmed_count(db, event.id)
    if reserved is None:
        reserved = _reserved_count(db, event.id)
    capacity = event.capacity or 0
    return EventPublic(
        id=event.id,
        org_id=event.org_id,
        organization_name=organization_name,
        title=event.title,
        summary=event.summary,
        description=event.description,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        venue_name=event.venue_name,
        venue_address=event.venue_address,
        capacity=capacity,
        confirmed_count=confirmed,
        reserved_count=reserved,
        remaining_spots=max(0, capacity - confirmed - reserved),
        interest_count=event.interest_count,
        banner_key=event.banner_key,
        cost_label=event.cost_label,
        registration_mode=event.registration_mode,
        review_window_minutes=event.review_window_minutes,
        material_revision=event.material_revision,
        status="published",
        published_at=event.published_at,
    )


def _private_projection(db: Session, event: Event, organization_name: str) -> EventPrivate:
    if event.status == "published":
        values = _public_projection(db, event, organization_name).model_dump()
    else:
        capacity = event.capacity
        values = {
            "id": event.id,
            "org_id": event.org_id,
            "organization_name": organization_name,
            "title": event.title,
            "summary": event.summary,
            "description": event.description,
            "starts_at": event.starts_at,
            "ends_at": event.ends_at,
            "venue_name": event.venue_name,
            "venue_address": event.venue_address,
            "capacity": capacity,
            "confirmed_count": 0,
            "reserved_count": 0,
            "remaining_spots": capacity,
            "interest_count": event.interest_count,
            "banner_key": event.banner_key,
            "cost_label": event.cost_label,
            "registration_mode": event.registration_mode,
            "review_window_minutes": event.review_window_minutes,
            "material_revision": event.material_revision,
            "status": "draft",
            "published_at": None,
        }
    values["created_by"] = event.created_by
    values["created_at"] = event.created_at
    return EventPrivate.model_validate(values)


# Pagination contract for GET /events: limit/offset only, no cursor. Defaults keep
# existing client behavior (full small local feed, cap-bounded server-side).
DISCOVERY_DEFAULT_LIMIT = 50
DISCOVERY_MAX_LIMIT = 100


@router.get("/events", response_model=list[EventPublic])
def list_events(
    db: Session = Depends(get_db, scope="function"),
    actor: Actor | None = Depends(optional_actor),
    q: str | None = Query(default=None, max_length=200),
    sort: Literal["upcoming", "newest"] = "upcoming",
    my_clubs: bool = False,
    limit: int = Query(default=DISCOVERY_DEFAULT_LIMIT, ge=1, le=DISCOVERY_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
):
    club_ids: list[str] | None = None
    if my_clubs:
        if actor is None:
            raise DomainError("authentication_required", "Sign in to view organization events.", 401)
        actor = require_eligible(actor)
        club_ids = active_club_ids(db, actor)
        if not club_ids:
            return []

    # Single clock source: compute the discovery boundary once in Python with the
    # app now() (UTC, tz-aware) instead of DB func.now(). This removes
    # clock skew between the app and DB hosts, matches registration write-path
    # semantics (event.starts_at <= now()), and freezes boundary tests to this
    # module's `now` symbol (previously tests patched `func` from this module).
    boundary = now()
    statement = (
        select(Event, Organization.name)
        .join(Organization, Organization.id == Event.org_id)
        .where(Event.status == "published", Event.ends_at > boundary)
    )
    if club_ids is not None:
        statement = statement.where(Event.org_id.in_(club_ids))
    query_text = q.strip() if q else ""
    if query_text:
        pattern = f"%{_escape_like(query_text)}%"
        statement = statement.where(
            or_(
                Event.title.ilike(pattern, escape="\\"),
                Organization.name.ilike(pattern, escape="\\"),
            )
        )
    if sort == "newest":
        statement = statement.order_by(Event.published_at.desc(), Event.id.asc())
    else:
        # Upcoming is start/id asc; starts_at is non-null for published events and
        # explicit nulls_last() keeps org/me lists and discovery identical if a
        # legacy row ever lacks one.
        statement = statement.order_by(Event.starts_at.asc().nulls_last(), Event.id.asc())

    rows = db.execute(statement.limit(limit).offset(offset)).all()
    if not rows:
        return []
    from app.domains.registrations.models import Registration

    count_rows = db.execute(
        select(Registration.event_id, Registration.status, func.count(Registration.id))
        .where(
            Registration.event_id.in_([event.id for event, _ in rows]),
            Registration.status.in_(("confirmed", "pending", "reconfirmation_required")),
        )
        .group_by(Registration.event_id, Registration.status)
    ).all()
    confirmed_counts: dict[str, int] = {}
    reserved_counts: dict[str, int] = {}
    for counted_event_id, status, count in count_rows:
        if status == "confirmed":
            confirmed_counts[counted_event_id] = count
        else:
            reserved_counts[counted_event_id] = reserved_counts.get(counted_event_id, 0) + count
    return [
        _public_projection(
            db,
            event,
            organization_name,
            confirmed_counts.get(event.id, 0),
            reserved_counts.get(event.id, 0),
        )
        for event, organization_name in rows
    ]


@router.get("/events/{event_id}", response_model=EventPublic)
def get_public_event(
    event_id: UUID,
    db: Session = Depends(get_db, scope="function"),
    _actor: Actor | None = Depends(optional_actor),
):
    event = _event_or_404(db, str(event_id))
    if event.status != "published":
        raise DomainError("event_not_found", "Event was not found.", 404)
    return _public_projection(db, event, _organization_name(db, event.org_id))


@router.get("/organizations/{org_id}/events", response_model=list[EventPrivate])
def list_organization_events(
    org_id: UUID,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor = Depends(current_actor),
):
    organization = require_manager(db, actor, str(org_id))
    rows = db.scalars(
        select(Event)
        .where(Event.org_id == organization.id)
        .order_by(Event.starts_at.asc().nulls_last(), Event.id.asc())
    ).all()
    return [_private_projection(db, event, organization.name) for event in rows]


@router.post("/organizations/{org_id}/events", response_model=EventPrivate, status_code=201)
def create_organization_event(
    org_id: UUID,
    payload: EventDraftInput,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor = Depends(current_actor),
):
    organization = require_manager(db, actor, str(org_id), lock=True)
    _require_draft_writable(organization)
    require_communication_allowed(db, actor.user_id, lock=True)
    fields = payload.model_dump(exclude_unset=True)
    event = create_draft(
        db,
        organization,
        actor.user_id,
        fields,
    )
    return _private_projection(db, event, organization.name)


@router.get("/events/{event_id}/draft", response_model=EventPrivate)
def get_event_draft(
    event_id: UUID,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor = Depends(current_actor),
):
    event = _event_or_404(db, str(event_id))
    organization = require_manager(db, actor, event.org_id)
    return _private_projection(db, event, organization.name)


@router.patch("/events/{event_id}/draft", response_model=EventPrivate)
def patch_event_draft(
    event_id: UUID,
    payload: EventDraftInput,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor = Depends(current_actor),
):
    event = _event_or_404(db, str(event_id))
    organization = require_manager(db, actor, event.org_id, lock=True)
    _require_draft_writable(organization)
    db.refresh(event, with_for_update=True)
    fields = payload.model_dump(exclude_unset=True)
    event = update_draft(db, event, fields)
    return _private_projection(db, event, organization.name)


@router.post("/events/{event_id}/changes", response_model=EventPrivate)
def change_event(
    event_id: UUID,
    payload: EventChangeInput,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor = Depends(current_actor),
):
    event = db.scalar(
        select(Event)
        .where(Event.id == str(event_id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise DomainError("event_not_found", "Event was not found.", 404)
    organization = require_manager(db, actor, event.org_id)
    if event.status != "published":
        raise DomainError(
            "event_change_requires_published",
            "Only published events can use the material change flow.",
            409,
        )

    submitted_fields = payload.model_dump(
        exclude_unset=True,
        exclude={"reconfirm_deadline", "selection_mode", "selected_registration_ids"},
    )
    material_fields = validate_material_change(
        event,
        submitted_fields,
        payload.reconfirm_deadline,
        at=now(),
    )

    # Registrations owns seat reconciliation and notifications; keep the import
    # at the domain boundary and execute it in this event-locked transaction.
    from app.domains.registrations.service import reconcile_material_change

    reconcile_material_change(
        db,
        event,
        material_fields,
        payload.reconfirm_deadline,
        payload.selection_mode,
        [str(registration_id) for registration_id in payload.selected_registration_ids],
    )
    for name, value in material_fields.items():
        setattr(event, name, value)
    event.material_revision += 1
    db.flush()
    return _private_projection(db, event, organization.name)


@router.post("/events/{event_id}/publish", response_model=EventPublic)
def publish_event(
    event_id: UUID,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor = Depends(current_actor),
):
    event = _event_or_404(db, str(event_id))
    organization = require_publishing(db, actor, event.org_id)
    # The organization lock serializes publishers for this organization, but this
    # Event may have been loaded before waiting for that lock. Refresh it under a
    # row lock so a second publisher observes the first transaction's terminal state.
    db.refresh(event, with_for_update=True)
    require_communication_allowed(db, actor.user_id, lock=True)
    event = publish(db, event)
    # Publish is a write path: counts reflect the just-sealed (still empty)
    # registration set; the projection's aggregate query reads it read-only.
    return _public_projection(db, event, organization.name)
