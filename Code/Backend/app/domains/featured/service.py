from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.communication import require_communication_allowed
from app.core.contracts import Actor
from app.core.event_safety import (
    discovery_clause,
    event_is_terminal,
    require_mutable_event,
)
from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.featured.models import FeaturedDecision, FeaturedRequest
from app.domains.featured.schemas import (
    FeaturedDecisionInput,
    FeaturedDecisionOut,
    FeaturedRequestOut,
)
from app.domains.organizations.models import Organization
from app.domains.organizations.service import require_manager, require_platform_admin


_FINGERPRINT_FIELDS = (
    "starts_at",
    "ends_at",
    "venue_name",
    "venue_address",
    "banner_key",
    "banner_media_id",
    "capacity",
    "cost_label",
)
_PLACEMENT_LOCK_KEY = 0x4953504F545F4631
_OPEN_STATUSES = ("pending", "paused", "approved")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value.astimezone(timezone.utc)


def material_fingerprint(event: Event) -> str:
    """Hash only the frozen material event fields, in a stable UTC representation."""
    material: dict[str, object] = {}
    for name in _FINGERPRINT_FIELDS:
        value = getattr(event, name)
        if isinstance(value, datetime):
            value = _as_utc(value).isoformat()
        material[name] = value
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fingerprint_matches(request: FeaturedRequest, event: Event) -> bool:
    try:
        return hmac.compare_digest(request.snapshot_hash, material_fingerprint(event))
    except (AttributeError, TypeError, ValueError):
        return False


def _effective_status(
    request: FeaturedRequest,
    event: Event,
    at: datetime,
) -> str:
    status = request.status
    if status == "expired" or status in {"rejected", "revoked"}:
        return status
    try:
        boundary = _as_utc(at)
        if event.starts_at is not None and boundary >= _as_utc(event.starts_at):
            return "expired"
        if status == "approved":
            if request.ends_at is not None and boundary >= _as_utc(request.ends_at):
                return "expired"
        if status in {"pending", "approved"} and not _fingerprint_matches(request, event):
            return "paused"
    except (AttributeError, TypeError, ValueError):
        # Malformed or timezone-naive material must never keep a placement public.
        if status == "approved":
            return "paused"
    return status


def active_featured_event_ids(
    db: Session,
    events: list[Event],
    at: datetime | None = None,
) -> set[str]:
    """Return currently featured ids with one batched query and one time boundary."""
    if not events:
        return set()
    boundary = _as_utc(at or now())
    events_by_id = {event.id: event for event in events}
    event_ids = tuple(events_by_id)
    rows = db.execute(
        select(FeaturedRequest.event_id, FeaturedRequest.snapshot_hash)
        .join(Event, Event.id == FeaturedRequest.event_id)
        .join(Organization, Organization.id == Event.org_id)
        .where(
            FeaturedRequest.event_id.in_(event_ids),
            FeaturedRequest.status == "approved",
            FeaturedRequest.starts_at <= boundary,
            FeaturedRequest.ends_at > boundary,
            Event.status == "published",
            Event.starts_at > boundary,
            Organization.accreditation_status == "approved",
            discovery_clause(at=boundary),
        )
    ).all()
    return {
        event_id
        for event_id, snapshot_hash in rows
        if event_id in events_by_id
        and _matches_hash(snapshot_hash, events_by_id[event_id])
    }


def _matches_hash(snapshot_hash: str, event: Event) -> bool:
    try:
        return hmac.compare_digest(snapshot_hash, material_fingerprint(event))
    except (AttributeError, TypeError, ValueError):
        return False


def pause_for_material_change(db: Session, event: Event, actor_id: str) -> None:
    """Pause open placements while the caller's event lock is already held."""
    timestamp = now()
    current_hash = material_fingerprint(event)
    requests = list(db.scalars(
        select(FeaturedRequest)
        .where(
            FeaturedRequest.event_id == event.id,
            FeaturedRequest.status.in_(_OPEN_STATUSES),
        )
        .order_by(FeaturedRequest.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))
    for request in requests:
        if _effective_status(request, event, timestamp) == "expired":
            continue
        if hmac.compare_digest(request.snapshot_hash, current_hash):
            continue
        request.status = "paused"
        request.version += 1
        request.snapshot_hash = current_hash
        db.add(FeaturedDecision(
            id=uid(),
            request_id=request.id,
            actor_id=actor_id,
            action="paused",
            created_at=timestamp,
            snapshot_hash=current_hash,
            starts_at=None,
            ends_at=None,
        ))
    db.flush()


def _not_found() -> DomainError:
    return DomainError("featured_request_not_found", "Featured request was not found.", 404)


def _conflict(code: str = "featured_request_conflict") -> DomainError:
    return DomainError(code, "The featured request changed or conflicts with the current schedule.", 409)


def _constraint_name(exc: IntegrityError) -> str | None:
    original = exc.orig
    diagnostic = getattr(original, "diag", None)
    return getattr(diagnostic, "constraint_name", None) or getattr(original, "constraint_name", None)


def _flush_or_conflict(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        name = _constraint_name(exc)
        if name == "ex_featured_requests_window":
            raise _conflict("featured_schedule_conflict") from None
        if name == "uq_featured_requests_open_event":
            raise _conflict() from None
        raise


def create_request(db: Session, actor: Actor, event_id: str) -> FeaturedRequestOut:
    # The initial lookup is deliberately unlocked; all writes acquire org -> event -> request.
    event = db.get(Event, event_id)
    if event is None:
        raise DomainError("event_not_found", "Event was not found.", 404)
    organization = require_manager(db, actor, event.org_id, lock=True)
    event = db.scalar(
        select(Event)
        .where(Event.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise DomainError("event_not_found", "Event was not found.", 404)
    organization = require_manager(db, actor, event.org_id)
    if event_is_terminal(db, event):
        raise _conflict("featured_event_closed")
    require_communication_allowed(db, actor.user_id, lock=True)

    timestamp = now()
    current_hash = material_fingerprint(event)
    existing = list(db.scalars(
        select(FeaturedRequest)
        .where(
            FeaturedRequest.event_id == event.id,
            FeaturedRequest.status.in_(_OPEN_STATUSES),
        )
        .order_by(FeaturedRequest.id)
        .with_for_update()
        .options(selectinload(FeaturedRequest.decisions))
        .execution_options(populate_existing=True)
    ))
    active_existing: list[FeaturedRequest] = []
    for request in existing:
        if _effective_status(request, event, timestamp) == "expired":
            request.status = "expired"
            request.version += 1
        else:
            active_existing.append(request)
    if existing:
        _flush_or_conflict(db)
    if active_existing:
        return _present_requests(db, [(active_existing[0], event, organization.name)], timestamp)[0]

    if organization.accreditation_status != "approved":
        raise DomainError("organization_not_approved", "Organization approval is required.", 403)
    if event.status != "published":
        raise DomainError("event_not_published", "Only a published event can be featured.", 409)
    if event.starts_at is None or _as_utc(event.starts_at) <= _as_utc(timestamp):
        raise DomainError("event_already_started", "The event must not have started.", 409)

    request = FeaturedRequest(
        id=uid(),
        event_id=event.id,
        requested_by=actor.user_id,
        requested_at=timestamp,
        status="pending",
        version=1,
        snapshot_hash=current_hash,
        starts_at=None,
        ends_at=None,
    )
    request.decisions.append(FeaturedDecision(
        id=uid(),
        actor_id=actor.user_id,
        action="requested",
        created_at=timestamp,
        snapshot_hash=current_hash,
        starts_at=None,
        ends_at=None,
    ))
    db.add(request)
    _flush_or_conflict(db)
    return _present_requests(db, [(request, event, organization.name)], timestamp)[0]


def list_organization_requests(
    db: Session,
    actor: Actor,
    org_id: str,
) -> list[FeaturedRequestOut]:
    require_manager(db, actor, org_id)
    entries = list(db.execute(
        select(FeaturedRequest, Event, Organization.name)
        .join(Event, Event.id == FeaturedRequest.event_id)
        .join(Organization, Organization.id == Event.org_id)
        .where(Event.org_id == org_id)
        .options(selectinload(FeaturedRequest.decisions))
        .order_by(FeaturedRequest.requested_at.desc(), FeaturedRequest.id.desc())
    ).tuples())
    return _present_requests(db, entries, now())


def list_platform_requests(
    db: Session,
    actor: Actor,
    limit: int,
) -> list[FeaturedRequestOut]:
    require_platform_admin(db, actor)
    entries = list(db.execute(
        select(FeaturedRequest, Event, Organization.name)
        .join(Event, Event.id == FeaturedRequest.event_id)
        .join(Organization, Organization.id == Event.org_id)
        .options(selectinload(FeaturedRequest.decisions))
        .order_by(FeaturedRequest.requested_at.desc(), FeaturedRequest.id.desc())
        .limit(limit)
    ).tuples())
    return _present_requests(db, entries, now())


def _present_requests(
    db: Session,
    entries: list[tuple[FeaturedRequest, Event, str]],
    boundary: datetime,
) -> list[FeaturedRequestOut]:
    if not entries:
        return []
    from app.domains.events.routes import _public_projection
    from app.domains.registrations.models import Registration

    events = [event for _, event, _ in entries]
    event_ids = {event.id for event in events}
    count_rows = db.execute(
        select(Registration.event_id, Registration.status, func.count(Registration.id))
        .where(
            Registration.event_id.in_(event_ids),
            Registration.status.in_(("confirmed", "pending", "reconfirmation_required")),
        )
        .group_by(Registration.event_id, Registration.status)
    ).all()
    confirmed_counts: dict[str, int] = {}
    reserved_counts: dict[str, int] = {}
    for event_id, status, count in count_rows:
        if status == "confirmed":
            confirmed_counts[event_id] = count
        else:
            reserved_counts[event_id] = reserved_counts.get(event_id, 0) + count

    featured_ids = active_featured_event_ids(db, events, at=boundary)
    results: list[FeaturedRequestOut] = []
    for request, event, organization_name in entries:
        event_public = _public_projection(
            db,
            event,
            organization_name,
            confirmed_counts.get(event.id, 0),
            reserved_counts.get(event.id, 0),
            is_featured=event.id in featured_ids,
        )
        results.append(FeaturedRequestOut(
            id=request.id,
            event_id=request.event_id,
            requested_by=request.requested_by,
            requested_at=request.requested_at,
            status=_effective_status(request, event, boundary),
            version=request.version,
            starts_at=request.starts_at,
            ends_at=request.ends_at,
            event=event_public,
            decisions=[FeaturedDecisionOut(
                id=decision.id,
                actor_id=decision.actor_id,
                action=decision.action,
                created_at=decision.created_at,
                starts_at=decision.starts_at,
                ends_at=decision.ends_at,
            ) for decision in request.decisions],
        ))
    return results


def decide_request(
    db: Session,
    actor: Actor,
    request_id: str,
    payload: FeaturedDecisionInput,
) -> FeaturedRequestOut:
    require_platform_admin(db, actor)
    initial_request = db.get(FeaturedRequest, request_id)
    if initial_request is None:
        raise _not_found()
    initial_event = db.get(Event, initial_request.event_id)
    if initial_event is None:
        raise _not_found()

    organization = db.scalar(
        select(Organization)
        .where(Organization.id == initial_event.org_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if organization is None:
        raise _not_found()
    event = db.scalar(
        select(Event)
        .where(Event.id == initial_event.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None or event.org_id != organization.id:
        raise _not_found()
    request = db.scalar(
        select(FeaturedRequest)
        .where(FeaturedRequest.id == request_id, FeaturedRequest.event_id == event.id)
        .with_for_update()
        .options(selectinload(FeaturedRequest.decisions))
        .execution_options(populate_existing=True)
    )
    if request is None:
        raise _not_found()
    require_platform_admin(db, actor)
    require_mutable_event(db, event)

    if payload.version != request.version:
        raise _conflict("featured_request_stale")
    timestamp = now()
    status = _effective_status(request, event, timestamp)
    if status == "expired" or status in {"rejected", "revoked"}:
        raise _conflict("featured_request_closed")

    current_hash = material_fingerprint(event)
    if payload.action == "approve":
        if status not in {"pending", "paused"}:
            raise _conflict("featured_request_not_reviewable")
        if event.status != "published" or organization.accreditation_status != "approved":
            raise _conflict("featured_event_ineligible")
        db.execute(select(func.pg_advisory_xact_lock(_PLACEMENT_LOCK_KEY)))
        # The global lock can wait behind another scheduler. Re-sample time and
        # review expiry/eligibility only after acquiring it.
        timestamp = now()
        status = _effective_status(request, event, timestamp)
        if status not in {"pending", "paused"}:
            raise _conflict("featured_request_not_reviewable")
        if event.status != "published" or organization.accreditation_status != "approved":
            raise _conflict("featured_event_ineligible")
        if event.starts_at is None or _as_utc(event.starts_at) <= _as_utc(timestamp):
            raise _conflict("featured_event_started")
        starts_at = payload.starts_at if payload.starts_at is not None else timestamp
        ends_at = payload.ends_at
        if ends_at is None:
            # The schema rejects this, retaining a service-level invariant as well.
            raise DomainError("featured_schedule_invalid", "Approval requires an end time.", 422)
        starts_utc, ends_utc = _as_utc(starts_at), _as_utc(ends_at)
        if payload.starts_at is not None and starts_utc < _as_utc(timestamp):
            raise DomainError("featured_start_in_past", "The placement cannot start in the past.", 422)
        if ends_utc <= starts_utc or ends_utc > _as_utc(event.starts_at):
            raise DomainError("featured_schedule_invalid", "Choose a valid placement window before the event starts.", 422)

        overlap = db.scalar(
            select(FeaturedRequest.id)
            .where(
                FeaturedRequest.status == "approved",
                FeaturedRequest.id != request.id,
                FeaturedRequest.starts_at < ends_utc,
                FeaturedRequest.ends_at > starts_utc,
            )
            .limit(1)
        )
        if overlap is not None:
            raise _conflict("featured_schedule_conflict")

        request.status = "approved"
        request.version += 1
        request.snapshot_hash = current_hash
        request.starts_at = starts_utc
        request.ends_at = ends_utc
        decision_action = "approved"
        decision_starts_at, decision_ends_at = starts_utc, ends_utc
    elif payload.action == "reject":
        if status not in {"pending", "paused"}:
            raise _conflict("featured_request_not_reviewable")
        request.status = "rejected"
        request.version += 1
        request.snapshot_hash = current_hash
        decision_action = "rejected"
        decision_starts_at = decision_ends_at = None
    else:
        if request.status != "approved":
            raise _conflict("featured_request_not_revokeable")
        request.status = "revoked"
        request.version += 1
        request.snapshot_hash = current_hash
        decision_action = "revoked"
        decision_starts_at = decision_ends_at = None

    request.decisions.append(FeaturedDecision(
        id=uid(),
        actor_id=actor.user_id,
        action=decision_action,
        created_at=timestamp,
        snapshot_hash=current_hash,
        starts_at=decision_starts_at,
        ends_at=decision_ends_at,
    ))
    _flush_or_conflict(db)
    return _present_requests(db, [(request, event, organization.name)], timestamp)[0]
