from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import current_actor, optional_actor, require_eligible
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.core.communication import require_communication_allowed
from app.core.event_safety import (discovery_clause, registration_is_available,
                                   require_readable_event, require_publishable_event,
                                   require_mutable_event)
from app.db.models import now
from app.db.session import get_db
from app.domains.events.models import Event
from app.domains.events.recommendations import (
    for_you_statement,
    matched_reason_codes,
    normalized_profile_tags,
)
from app.domains.events.schemas import EventChangeInput, EventDraftInput, EventPrivate, EventPublic, EventReviewSummary
from app.domains.events.service import (
    create_draft,
    draft_version,
    publish,
    require_draft_version,
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
    recommendation_reasons: list[str] | None = None,
    is_featured: bool | None = None,
    registration_available: bool | None = None,
) -> EventPublic:
    if is_featured is None:
        from app.domains.featured.service import active_featured_event_ids
        is_featured = event.id in active_featured_event_ids(db, [event])
    if confirmed is None:
        confirmed = _confirmed_count(db, event.id)
    if reserved is None:
        reserved = _reserved_count(db, event.id)
    capacity = event.capacity or 0
    return EventPublic(
        is_featured=is_featured,
        registration_available=(registration_is_available(db, event)
                                if registration_available is None else registration_available),
        id=event.id,
        org_id=event.org_id,
        organization_name=organization_name,
        title=event.title,
        summary=event.summary,
        tags=event.tags or [],
        coarse_area=event.coarse_area,
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
        banner_url=f'/api/v1/media/{event.banner_media_id}' if event.banner_media_id else None,
        cost_label=event.cost_label,
        registration_mode=event.registration_mode,
        review_window_minutes=event.review_window_minutes,
        event_type=event.event_type or "scheduled",
        material_revision=event.material_revision,
        status="published",
        published_at=event.published_at,
        recommendation_reasons=recommendation_reasons or [],
    )


def _private_projection(db: Session, event: Event, organization_name: str, *, is_featured: bool | None = None) -> EventPrivate:
    if event.status == "published":
        values = _public_projection(db, event, organization_name, is_featured=is_featured).model_dump()
    else:
        capacity = event.capacity
        values = {
            "id": event.id,
            "org_id": event.org_id,
            "organization_name": organization_name,
            "title": event.title,
            "summary": event.summary,
            "tags": event.tags or [],
            "coarse_area": event.coarse_area,
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
            "banner_url": f'/api/v1/media/{event.banner_media_id}' if event.banner_media_id else None,
            "cost_label": event.cost_label,
            "registration_mode": event.registration_mode,
            "review_window_minutes": event.review_window_minutes,
            "event_type": event.event_type or "scheduled",
            "material_revision": event.material_revision,
            "status": "draft",
            "published_at": None,
        }
    values["created_by"] = event.created_by
    values["created_at"] = event.created_at
    values["draft_version"] = draft_version(event)
    return EventPrivate.model_validate(values)


# Pagination contract for GET /events: limit/offset only, no cursor. Defaults keep
# existing client behavior (full small local feed, cap-bounded server-side).
DISCOVERY_DEFAULT_LIMIT = 50
DISCOVERY_MAX_LIMIT = 100


@router.get("/events", response_model=list[EventPublic])
def list_events(
    response: Response,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor | None = Depends(optional_actor),
    q: str | None = Query(default=None, max_length=200),
    sort: Literal["upcoming", "newest", "for_you"] = "upcoming",
    my_clubs: bool = False,
    include_flash: bool = True,
    limit: int = Query(default=DISCOVERY_DEFAULT_LIMIT, ge=1, le=DISCOVERY_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
):
    personalized = sort == "for_you" and actor is not None
    effective_sort = "upcoming" if sort == "for_you" and actor is None else sort
    if sort == "for_you":
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Authorization"

    club_ids: list[str] | None = None
    ranking_club_ids: list[str] = []
    if my_clubs:
        if actor is None:
            raise DomainError("authentication_required", "Sign in to view organization events.", 401)
        actor = require_eligible(actor)
        ranking_club_ids = active_club_ids(db, actor)
        club_ids = ranking_club_ids
        if not club_ids:
            return []
    elif personalized and actor is not None and actor.eligible:
        ranking_club_ids = active_club_ids(db, actor)

    profile_tags: set[str] = set()
    preferred_area: str | None = None
    availability: list[dict] = []
    if personalized and actor is not None:
        from app.domains.identity.discovery_models import UserDiscoveryPreferences
        from app.domains.identity.models import User

        profile_tags = normalized_profile_tags(
            db.scalar(select(User.tags).where(User.id == actor.user_id)) or []
        )
        preferences = db.get(UserDiscoveryPreferences, actor.user_id)
        if preferences is not None:
            preferred_area = preferences.coarse_area
            availability = preferences.availability or []

    # Single clock source: compute the discovery boundary once in Python with the
    # app now() (UTC, tz-aware) instead of DB func.now(). This removes
    # clock skew between the app and DB hosts, matches registration write-path
    # semantics (event.starts_at <= now()), and freezes boundary tests to this
    # module's `now` symbol (previously tests patched `func` from this module).
    boundary = now()
    from app.domains.eventsafety.service import sweep_expired_suspensions
    sweep_expired_suspensions(db, at=boundary)
    statement = (
        select(Event, Organization.name)
        .join(Organization, Organization.id == Event.org_id)
        .where(Event.status == "published", Event.ends_at > boundary,
               Organization.accreditation_status == "approved", discovery_clause(boundary))
    )
    if not include_flash:
        statement = statement.where(Event.event_type == "scheduled")
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
    reason_codes_by_event: dict[str, list[str]] = {}
    if effective_sort == "newest":
        statement = statement.order_by(Event.published_at.desc(), Event.id.asc())
        rows = db.execute(statement.limit(limit).offset(offset)).all()
    elif effective_sort == "for_you" and personalized:
        ranked_rows = db.execute(
            for_you_statement(
                statement,
                active_clubs=ranking_club_ids,
                profile_tags=profile_tags,
                coarse_area=preferred_area,
                availability=availability,
                request_now=boundary,
            ).limit(limit).offset(offset)
        ).all()
        rows = [(row[0], row[1]) for row in ranked_rows]
        reason_codes_by_event = {
            row[0].id: matched_reason_codes(row[2], row[3], row[4], row[5], row[6])
            for row in ranked_rows
        }
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
    from app.domains.featured.service import active_featured_event_ids
    featured_ids = active_featured_event_ids(db, [event for event, _ in rows], at=boundary)
    return [
        _public_projection(
            db,
            event,
            organization_name,
            confirmed_counts.get(event.id, 0),
            reserved_counts.get(event.id, 0),
            reason_codes_by_event.get(event.id, []),
            is_featured=event.id in featured_ids,
            registration_available=True,
        )
        for event, organization_name in rows
    ]


@router.get("/events/{event_id}", response_model=EventPublic)
def get_public_event(
    event_id: UUID,
    response: Response,
    db: Session = Depends(get_db, scope="function"),
    _actor: Actor | None = Depends(optional_actor),
):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"
    event = _event_or_404(db, str(event_id))
    from app.domains.eventsafety.service import sweep_expired_suspensions
    sweep_expired_suspensions(db, org_id=event.org_id)
    require_readable_event(db, event, _actor.user_id if _actor else None)
    organization = db.get(Organization, event.org_id)
    if event.status != "published" or organization is None or organization.accreditation_status != "approved":
        raise DomainError("event_not_found", "Event was not found.", 404)
    return _public_projection(db, event, organization.name)


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
    from app.domains.featured.service import active_featured_event_ids
    featured_ids = active_featured_event_ids(db, rows)
    return [_private_projection(db, event, organization.name, is_featured=event.id in featured_ids) for event in rows]


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


@router.get("/organizations/{org_id}/review-events", response_model=list[EventReviewSummary])
def list_review_events(
    org_id: UUID,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor = Depends(current_actor),
):
    from app.domains.memberships.policy import require_staff
    from app.domains.registrations.models import Registration

    organization, _ = require_staff(db, actor.user_id, str(org_id))
    events = list(db.scalars(select(Event).where(
        Event.org_id == organization.id, Event.status == "published",
    ).order_by(Event.starts_at, Event.id)))
    if not events:
        return []
    counts = {event.id: {"confirmed": 0, "reserved": 0, "pending": 0, "deadline": None}
              for event in events}
    rows = db.execute(select(Registration.event_id, Registration.status,
                             func.count(Registration.id), func.min(Registration.review_deadline))
                      .where(Registration.event_id.in_(counts),
                             Registration.status.in_(("confirmed", "pending", "reconfirmation_required")))
                      .group_by(Registration.event_id, Registration.status)).all()
    for event_id, status, count, deadline in rows:
        summary = counts[event_id]
        if status == "confirmed":
            summary["confirmed"] = count
        else:
            summary["reserved"] += count
        if status == "pending":
            summary.update(pending=count, deadline=deadline)
    from app.domains.featured.service import active_featured_event_ids
    featured_ids = active_featured_event_ids(db, events)
    return [EventReviewSummary(
        **_public_projection(db, event, organization.name, counts[event.id]["confirmed"],
                             counts[event.id]["reserved"], is_featured=event.id in featured_ids).model_dump(),
        pending_registration_count=counts[event.id]["pending"],
        next_review_deadline=counts[event.id]["deadline"],
    ) for event in events]


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
    if_match: str | None = Header(default=None, max_length=128),
):
    event = _event_or_404(db, str(event_id))
    organization = require_manager(db, actor, event.org_id, lock=True)
    _require_draft_writable(organization)
    db.refresh(event, with_for_update=True)
    require_mutable_event(db, event)
    require_draft_version(event, if_match)
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
    require_mutable_event(db, event)
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
    from app.domains.featured.service import pause_for_material_change
    pause_for_material_change(db, event, actor.user_id)
    db.flush()
    return _private_projection(db, event, organization.name)


@router.post("/events/{event_id}/publish", response_model=EventPublic)
def publish_event(
    event_id: UUID,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor = Depends(current_actor),
    if_match: str | None = Header(default=None, max_length=128),
):
    event = _event_or_404(db, str(event_id))
    from app.domains.eventsafety.service import sweep_expired_suspensions
    sweep_expired_suspensions(db, org_id=event.org_id)
    organization = require_publishing(db, actor, event.org_id)
    # The organization lock serializes publishers for this organization, but this
    # Event may have been loaded before waiting for that lock. Refresh it under a
    # row lock so a second publisher observes the first transaction's terminal state.
    db.refresh(event, with_for_update=True)
    require_publishable_event(db, event)
    require_draft_version(event, if_match)
    require_communication_allowed(db, actor.user_id, lock=True)
    publication_time = now()
    event = publish(db, event, at=publication_time)
    # Publish is a write path: counts reflect the just-sealed (still empty)
    # registration set; the projection's aggregate query reads it read-only.
    return _public_projection(db, event, organization.name)
