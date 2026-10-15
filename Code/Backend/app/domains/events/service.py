from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.events.schemas import SUMMARY_MAX_LENGTH
from app.domains.organizations.models import Organization

EVENT_VALIDATION_FIELDS = (
    "title",
    "summary",
    "description",
    "starts_at",
    "ends_at",
    "venue_name",
    "venue_address",
    "capacity",
    "banner_key",
    "cost_label",
    "registration_mode",
    "review_window_minutes",
    "event_type",
)
MATERIAL_EVENT_FIELDS = (
    "starts_at",
    "ends_at",
    "venue_name",
    "venue_address",
    "capacity",
    "cost_label",
)


def create_draft(db: Session, organization: Organization, created_by: str, fields: dict) -> Event:
    event = Event(id=uid(), org_id=organization.id, created_by=created_by, **fields)
    db.add(event)
    db.flush()
    return event


def update_draft(db: Session, event: Event, fields: dict) -> Event:
    if event.status != "draft":
        raise DomainError("published_event_immutable", "Published events cannot be edited.", 409)
    for name, value in fields.items():
        setattr(event, name, value)
    db.flush()
    return event


def validate_publishable(event: Event, at: datetime | None = None) -> None:
    _validate_event_values(
        {name: getattr(event, name) for name in EVENT_VALIDATION_FIELDS},
        at=at,
    )


def _validate_event_values(fields: dict, at: datetime | None = None) -> None:
    if len(fields["summary"] or "") > SUMMARY_MAX_LENGTH:
        raise DomainError("event_summary_too_long", "The event summary is too long.", 422)
    required = (
        fields["title"],
        fields["description"],
        fields["venue_name"],
        fields["venue_address"],
        fields["banner_key"],
    )
    if any(not isinstance(value, str) or not value.strip() for value in required):
        raise DomainError(
            "event_fields_required",
            "Complete the title, description, venue, and banner before publishing.",
            422,
        )
    if fields["cost_label"] is None:
        raise DomainError("event_fields_required", "Add a cost label before publishing.", 422)
    starts_at = fields["starts_at"]
    ends_at = fields["ends_at"]
    capacity = fields["capacity"]
    if starts_at is None or ends_at is None or capacity is None:
        raise DomainError(
            "event_fields_required",
            "Add a start time, end time, and positive capacity before publishing.",
            422,
        )
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise DomainError("event_datetime_timezone_required", "Event times must include a timezone.", 422)
    if ends_at.tzinfo is None or ends_at.utcoffset() is None:
        raise DomainError("event_datetime_timezone_required", "Event times must include a timezone.", 422)
    starts_at_utc = starts_at.astimezone(timezone.utc)
    ends_at_utc = ends_at.astimezone(timezone.utc)
    if starts_at_utc <= (at or now()):
        raise DomainError("event_start_must_be_future", "The event must start in the future.", 422)
    if ends_at_utc <= starts_at_utc:
        raise DomainError("event_end_must_follow_start", "The event end must follow its start.", 422)
    if capacity <= 0:
        raise DomainError("event_capacity_invalid", "Event capacity must be positive.", 422)
    if fields["banner_key"] not in {"heritage", "design", "garden", "music"}:
        raise DomainError("event_banner_invalid", "Choose an available event banner.", 422)
    registration_mode = fields["registration_mode"]
    review_window_minutes = fields["review_window_minutes"]
    if registration_mode not in {"instant", "approval"} or fields["event_type"] != "scheduled":
        raise DomainError(
            "event_mode_invalid",
            "Only scheduled events with instant or approval registration are available.",
            422,
        )
    if registration_mode == "instant" and review_window_minutes is not None:
        raise DomainError(
            "event_review_window_invalid",
            "Instant registration events cannot have a review window.",
            422,
        )
    if registration_mode == "approval" and (
        not isinstance(review_window_minutes, int)
        or isinstance(review_window_minutes, bool)
        or not 15 <= review_window_minutes <= 2880
    ):
        raise DomainError(
            "event_review_window_invalid",
            "Approval events require a review window from 15 to 2880 minutes.",
            422,
        )


def validate_material_change(
    event: Event,
    fields: dict,
    reconfirm_deadline: datetime,
    at: datetime | None = None,
) -> dict:
    validation_time = at or now()
    proposed = {name: getattr(event, name) for name in EVENT_VALIDATION_FIELDS}
    changes = {name: value for name, value in fields.items() if value != proposed[name]}
    if not changes:
        raise DomainError(
            "event_material_change_required",
            "At least one event detail must materially change.",
            422,
        )
    proposed.update(changes)
    _validate_event_values(proposed, at=validation_time)

    if reconfirm_deadline.tzinfo is None or reconfirm_deadline.utcoffset() is None:
        raise DomainError(
            "event_datetime_timezone_required",
            "The reconfirmation deadline must include a timezone.",
            422,
        )
    deadline_utc = reconfirm_deadline.astimezone(timezone.utc)
    start_utc = proposed["starts_at"].astimezone(timezone.utc)
    if deadline_utc <= validation_time.astimezone(timezone.utc) or deadline_utc >= start_utc:
        raise DomainError(
            "event_reconfirmation_deadline_invalid",
            "The reconfirmation deadline must be in the future and before the event starts.",
            422,
        )
    return {name: proposed[name] for name in MATERIAL_EVENT_FIELDS}


def publish(db: Session, event: Event) -> Event:
    if event.status != "draft":
        raise DomainError("published_event_immutable", "Published events cannot be changed.", 409)
    validate_publishable(event)
    # Seal interrupted attempts made while private, atomically with publication.
    # Runtime import preserves the existing Events/Registrations module boundary.
    from app.domains.registrations.service import reject_draft_receipts

    reject_draft_receipts(db, event.id)
    event.status = "published"
    event.published_at = now()
    db.flush()
    return event
