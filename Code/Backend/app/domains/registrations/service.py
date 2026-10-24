from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import and_, case, func, select, text, update
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.event_safety import event_is_terminal, require_new_registration, discovery_clause
from app.db.models import now, uid
from app.db.session import session_factory
from app.domains.events.models import Event
from app.domains.identity.models import User
from app.domains.identity.service import email_is_eligible, profile_is_complete
from app.domains.organizations.models import Organization
from app.domains.organizations.models import OrgMembership
from app.domains.registrations.models import Registration, RegistrationReceipt

WAITLIST_MESSAGE = 'You are on the waitlist. No estimated wait time is available.'
ACTIVE_STATUSES = ('confirmed', 'waitlisted', 'pending', 'reconfirmation_required')
SEAT_STATUSES = ('confirmed', 'pending', 'reconfirmation_required')
REVIEWER_ROLES = ('owner', 'admin', 'moderator')
MATERIAL_FIELDS = ('starts_at', 'ends_at', 'venue_name', 'venue_address', 'capacity', 'cost_label')
REVIEW_STAGE_INITIAL = 0
REVIEW_STAGE_EXTENSION = 1
REVIEW_STAGE_ESCALATED = 2

# Bounded drain: one drain pass locks the event row and finalizes at most this
# many pending receipts in a single short transaction, then re-queues (loops)
# until no pending receipt remains. Bounds lock hold under backlog/crash-restart
# catch-up while preserving strict event_order admission.
DRAIN_BATCH_SIZE = 200

# Admission sequencing is OPAQUE and NON-CONTIGUOUS by design. Intake hands out a
# strictly increasing per-event counter value (event_order) at the durable
# receipt point, and an admitted registration inherits it as admission_order.
# Different-key attempts for an active registration, ineligible attempts, and
# post-start denials consume counter values without creating registrations;
# same-key retries and cross-event key conflicts do not. Gaps are normal.
# Only relative order is meaningful (earliest order wins
# confirmed seats; waitlist rank is computed by counting rows, never by
# arithmetic on the order). Never renumber; never assert contiguity.
#
# Single clock source: every start-time comparison in this module uses the
# application clock via app.db.models.now (never DB func.now()), so intake,
# drain, withdrawal, and listing agree with each other at the start boundary
# and stay injectable in tests. App/DB clock skew cannot split a decision.


@dataclass(frozen=True)
class RegistrationOutcome:
    result: dict[str, Any]
    http_status: int


def _idempotency_lock_id(user_id: str, idempotency_key: str) -> int:
    digest = sha256(f'intraspot:registration:{user_id}:{idempotency_key}'.encode('utf-8')).digest()
    return int.from_bytes(digest[:8], byteorder='big', signed=True)


def _validate_idempotency_key(idempotency_key: str) -> None:
    try:
        valid_ascii = idempotency_key.isascii()
    except AttributeError:
        valid_ascii = False
    if not valid_ascii or not 8 <= len(idempotency_key) <= 128 or any(ord(char) < 32 or ord(char) > 126 for char in idempotency_key):
        raise DomainError('invalid_idempotency_key', 'A valid idempotency key is required.', 400)


def intake_registration(
    user_id: str,
    event_id: str,
    idempotency_key: str,
    *,
    persona_shared: bool = False,
    blocked_attendee_acknowledged: bool = False,
) -> str:
    """Commit one durable admission receipt before any registration result is computed."""
    _validate_idempotency_key(idempotency_key)
    factory = session_factory()
    with factory() as db:
        with db.begin():
            db.execute(
                text('SELECT pg_advisory_xact_lock(:lock_id)'),
                {'lock_id': _idempotency_lock_id(user_id, idempotency_key)},
            )
            from app.domains.eventsafety.service import sweep_expired_suspensions
            org_id = db.scalar(select(Event.org_id).where(Event.id == event_id))
            if org_id is not None:
                sweep_expired_suspensions(db, org_id=org_id)
            existing = db.scalar(
                select(RegistrationReceipt).where(
                    RegistrationReceipt.user_id == user_id,
                    RegistrationReceipt.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.event_id != event_id:
                    raise DomainError('idempotency_key_reused', 'This idempotency key was already used for another event.', 409)
                if existing.persona_shared != persona_shared:
                    raise DomainError('idempotency_key_reused', 'This idempotency key was already used with a different persona-sharing choice.', 409)
                if existing.blocked_attendee_acknowledged != blocked_attendee_acknowledged:
                    raise DomainError('idempotency_key_reused', 'This idempotency key was already used with different registration choices.', 409)
                receipt_id = existing.id
            else:
                event_order = db.execute(
                    update(Event)
                    .where(Event.id == event_id, Event.status == 'published')
                    .values(next_admission=Event.next_admission + 1)
                    .returning(Event.next_admission)
                ).scalar_one_or_none()
                if event_order is None:
                    raise DomainError('event_not_found', 'The event could not be found.', 404)
                event = db.get(Event, event_id, populate_existing=True)
                require_new_registration(db, event)
                if not blocked_attendee_acknowledged:
                    user = db.get(User, user_id)
                    timestamp = now()
                    if (
                        user is not None
                        and user.active
                        and email_is_eligible(user.email, user.email_verified)
                        and profile_is_complete(user)
                        and _is_public_future_event(db, event_id, timestamp)
                        and _has_blocked_confirmed_attendee(db, user_id, event_id)
                    ):
                        raise DomainError(
                            'blocked_attendee_warning',
                            'A blocked attendee is currently registered for this event. Acknowledge the warning to continue.',
                            409,
                        )
                receipt = RegistrationReceipt(
                    id=uid(),
                    user_id=user_id,
                    event_id=event_id,
                    idempotency_key=idempotency_key,
                    event_order=event_order,
                    persona_shared=persona_shared,
                    blocked_attendee_acknowledged=blocked_attendee_acknowledged,
                )
                db.add(receipt)
                db.flush()
                receipt_id = receipt.id
    return receipt_id


def reject_draft_receipts(db: Session, event_id: str) -> None:
    """Seal legacy private-event attempts before publication; caller holds the draft lock.

    New intake cannot create these receipts. Preserve their rejected retry outcome
    in the caller's publication transaction, without inferring state from timestamps.
    """
    db.execute(
        update(RegistrationReceipt)
        .where(
            RegistrationReceipt.event_id == event_id,
            RegistrationReceipt.result.is_(None),
            RegistrationReceipt.http_status.is_(None),
            RegistrationReceipt.processed_at.is_(None),
        )
        .values(
            result={'error': {'code': 'event_not_found', 'message': 'The event could not be found.'}},
            http_status=404,
            processed_at=now(),
        )
    )


def cancel_event_participation_locked(db: Session, event: Event, action_id: str) -> None:
    """Terminal safety action; caller holds organization/event locks and sets flags first."""
    from app.notifications import notify_in_app

    timestamp = now()
    registrations = list(db.scalars(select(Registration).where(
        Registration.event_id == event.id, Registration.status.in_(ACTIVE_STATUSES),
    ).order_by(Registration.id).with_for_update()))
    recipients = {registration.user_id: registration.id for registration in registrations}
    for registration in registrations:
        registration.status = 'cancelled'
        registration.updated_at = timestamp
        _clear_review(registration)
        _clear_reconfirmation(registration)
    db.execute(update(RegistrationReceipt).where(
        RegistrationReceipt.event_id == event.id,
        RegistrationReceipt.result.is_(None), RegistrationReceipt.http_status.is_(None),
        RegistrationReceipt.processed_at.is_(None),
    ).values(result={'error': {'code': 'event_terminal',
                              'message': 'This event has been cancelled or removed.'}},
             http_status=409, processed_at=timestamp))
    members = db.scalars(select(User).join(OrgMembership, OrgMembership.user_id == User.id).where(
        OrgMembership.org_id == event.org_id, OrgMembership.active.is_(True), User.active.is_(True)))
    for member in members:
        if email_is_eligible(member.email, member.email_verified):
            recipients.setdefault(member.id, None)
    for user_id, registration_id in recipients.items():
        notify_in_app(db, user_id=user_id, event_id=event.id, org_id=event.org_id,
                      registration_id=registration_id, kind='event_safety_cancelled',
                      message='This event has been cancelled or removed. Existing registrations have ended.',
                      dedupe_key=f'event_safety_cancelled:{action_id}:{user_id}')
    db.flush()


def submit_registration(
    user_id: str,
    event_id: str,
    idempotency_key: str,
    *,
    persona_shared: bool = False,
    blocked_attendee_acknowledged: bool = False,
) -> RegistrationOutcome:
    receipt_id = intake_registration(
        user_id,
        event_id,
        idempotency_key,
        persona_shared=persona_shared,
        blocked_attendee_acknowledged=blocked_attendee_acknowledged,
    )
    catch_up_event(event_id)
    return registration_outcome(receipt_id)


def registration_outcome(receipt_id: str) -> RegistrationOutcome:
    factory = session_factory()
    with factory() as db:
        receipt = db.get(RegistrationReceipt, receipt_id)
        if receipt is None:
            raise DomainError('registration_receipt_not_found', 'The registration request could not be completed.', 503)
        if receipt.result is None or receipt.http_status is None:
            raise DomainError('registration_processing_pending', 'The registration request is still processing. Retry with the same idempotency key.', 503)
        return RegistrationOutcome(dict(receipt.result), receipt.http_status)


def _is_public_future_event(db: Session, event_id: str, at: datetime) -> bool:
    return db.scalar(
        select(Event.id)
        .join(Organization, Organization.id == Event.org_id)
        .where(
            Event.id == event_id,
            Event.status == 'published',
            Event.starts_at > at,
            Organization.accreditation_status == 'approved',
            discovery_clause(at),
        )
    ) is not None


def _has_blocked_confirmed_attendee(db: Session, user_id: str, event_id: str) -> bool:
    from app.domains.memberships.models import EventAccessRevocation
    from app.domains.personas.models import UserBlock

    revoked = select(EventAccessRevocation.id).where(
        EventAccessRevocation.event_id == Registration.event_id,
        EventAccessRevocation.user_id == Registration.user_id,
        EventAccessRevocation.cutoff_order >= Registration.admission_order,
    ).exists()
    return db.scalar(
        select(1)
        .select_from(UserBlock)
        .join(Registration, Registration.user_id == UserBlock.target_id)
        .where(
            UserBlock.blocker_id == user_id,
            Registration.event_id == event_id,
            Registration.status == 'confirmed',
            ~revoked,
        )
        .limit(1)
    ) is not None


def registration_block_warning(user_id: str, event_id: str) -> bool:
    factory = session_factory()
    with factory() as db:
        user = db.get(User, user_id)
        if user is None or not user.active or not email_is_eligible(user.email, user.email_verified):
            raise DomainError('registration_ineligible', 'An eligible active account is required.', 403)
        timestamp = now()
        if not _is_public_future_event(db, event_id, timestamp):
            raise DomainError('event_not_found', 'The event could not be found.', 404)
        return _has_blocked_confirmed_attendee(db, user_id, event_id)


def _registration_result(db: Session, registration: Registration) -> dict[str, Any]:
    position = None
    message = None
    if registration.status == 'waitlisted':
        ahead = db.scalar(
            select(func.count(Registration.id)).where(
                Registration.event_id == registration.event_id,
                Registration.status == 'waitlisted',
                Registration.admission_order < registration.admission_order,
            )
        ) or 0
        position = int(ahead) + 1
        message = WAITLIST_MESSAGE
    return {
        'id': registration.id,
        'event_id': registration.event_id,
        'status': registration.status,
        'waitlist_position': position,
        'waitlist_message': message,
        'admission_order': registration.admission_order,
        'review_deadline': registration.review_deadline.isoformat() if registration.review_deadline is not None else None,
        'review_stage': registration.review_stage,
        'reviewer_id': registration.reviewer_id,
        'first_reviewer_id': registration.first_reviewer_id,
        'timeout_count': registration.timeout_count,
        'from_waitlist': registration.from_waitlist,
        'persona_shared': registration.persona_shared,
        'reconfirm_deadline': registration.reconfirm_deadline.isoformat() if registration.reconfirm_deadline is not None else None,
        'reconfirm_revision': registration.reconfirm_revision,
    }


def _notify(
    db: Session,
    registration: Registration,
    *,
    kind: str,
    message: str,
    dedupe_key: str,
    user_id: str | None = None,
) -> None:
    from app.notifications import notify_in_app

    notify_in_app(
        db,
        user_id=user_id or registration.user_id,
        event_id=registration.event_id,
        registration_id=registration.id,
        kind=kind,
        message=message,
        dedupe_key=dedupe_key,
    )


def _eligible_reviewers(db: Session, event: Event) -> list[tuple[str, str]]:
    rows = db.execute(
        select(User.id, OrgMembership.role, User.email, User.email_verified)
        .join(OrgMembership, OrgMembership.user_id == User.id)
        .join(Organization, Organization.id == OrgMembership.org_id)
        .where(
            OrgMembership.org_id == event.org_id,
            OrgMembership.active.is_(True),
            OrgMembership.role.in_(REVIEWER_ROLES),
            Organization.accreditation_status == 'approved',
            User.active.is_(True),
        )
        .order_by(
            case(
                (OrgMembership.role == 'owner', 0),
                (OrgMembership.role == 'admin', 1),
                (OrgMembership.role == 'moderator', 2),
                else_=3,
            ),
            User.id,
        )
    ).all()
    return [
        (row.id, row.role)
        for row in rows
        if email_is_eligible(row.email, row.email_verified)
    ]


def _choose_reviewer(db: Session, event: Event, *, exclude: str | None = None) -> str | None:
    return next(
        (reviewer_id for reviewer_id, _ in _eligible_reviewers(db, event) if reviewer_id != exclude),
        None,
    )


def _window(event: Event) -> timedelta:
    minutes = event.review_window_minutes
    if minutes is None or not 15 <= minutes <= 2880:
        raise DomainError('review_settings_invalid', 'The event review window is not configured.', 409)
    return timedelta(minutes=minutes)


def _deadline_for_start(starts_at: datetime | None, anchor: datetime, window: timedelta) -> datetime:
    if starts_at is None:
        return anchor
    latest = starts_at - timedelta(microseconds=1)
    return max(anchor, min(anchor + window, latest))


def _clear_review(registration: Registration) -> None:
    registration.review_deadline = None
    registration.review_stage = None
    registration.reviewer_id = None
    registration.first_reviewer_id = None


def _clear_reconfirmation(registration: Registration) -> None:
    registration.reconfirm_deadline = None
    registration.reconfirm_revision = None


def _start_review(
    db: Session,
    event: Event,
    registration: Registration,
    at: datetime,
    *,
    from_waitlist: bool,
) -> None:
    reviewer_id = _choose_reviewer(db, event)
    registration.status = 'pending'
    registration.review_stage = REVIEW_STAGE_INITIAL
    registration.review_deadline = _deadline_for_start(event.starts_at, at, _window(event))
    registration.reviewer_id = reviewer_id
    registration.first_reviewer_id = reviewer_id
    registration.from_waitlist = from_waitlist
    registration.confirmed_at = None
    registration.updated_at = at
    _clear_reconfirmation(registration)
    cycle = registration.timeout_count
    _notify(
        db,
        registration,
        kind='registration_pending',
        message='Your registration is awaiting event-organizer review.',
        dedupe_key=f'registration_pending:{registration.id}:cycle:{cycle}',
    )
    if reviewer_id is not None:
        _notify(
            db,
            registration,
            user_id=reviewer_id,
            kind='registration_review_requested',
            message='A registration is waiting for your event review.',
            dedupe_key=f'registration_review_requested:{registration.id}:cycle:{cycle}',
        )


def _seat_count(db: Session, event_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(Registration.id)).where(
                Registration.event_id == event_id,
                Registration.status.in_(SEAT_STATUSES),
            )
        )
        or 0
    )


def _promote_open_seats_locked(
    db: Session,
    event: Event,
    at: datetime,
    *,
    capacity: int | None = None,
    starts_at: datetime | None = None,
) -> list[Registration]:
    if event_is_terminal(db, event):
        return []
    proposed_capacity = event.capacity if capacity is None else capacity
    proposed_start = event.starts_at if starts_at is None else starts_at
    if proposed_capacity is None or proposed_start is None or proposed_start <= at:
        return []
    open_seats = proposed_capacity - _seat_count(db, event.id)
    if open_seats <= 0:
        return []
    queued = list(
        db.scalars(
            select(Registration)
            .where(Registration.event_id == event.id, Registration.status == 'waitlisted')
            .order_by(Registration.admission_order, Registration.id)
            .limit(open_seats)
            .with_for_update()
        )
    )
    promoted: list[Registration] = []
    for registration in queued:
        if event.registration_mode == 'approval':
            reviewer_id = _choose_reviewer(db, event)
            registration.status = 'pending'
            registration.review_stage = REVIEW_STAGE_INITIAL
            registration.review_deadline = _deadline_for_start(proposed_start, at, _window(event))
            registration.reviewer_id = reviewer_id
            registration.first_reviewer_id = reviewer_id
            registration.from_waitlist = True
            registration.confirmed_at = None
            registration.updated_at = at
            _clear_reconfirmation(registration)
            cycle = registration.timeout_count
            _notify(
                db,
                registration,
                kind='registration_pending',
                message='A spot opened. Your registration is awaiting event-organizer review.',
                dedupe_key=f'registration_pending:{registration.id}:cycle:{cycle}',
            )
            if reviewer_id is not None:
                _notify(
                    db,
                    registration,
                    user_id=reviewer_id,
                    kind='registration_review_requested',
                    message='A registration is waiting for your event review.',
                    dedupe_key=f'registration_review_requested:{registration.id}:cycle:{cycle}',
                )
        else:
            registration.status = 'confirmed'
            registration.confirmed_at = at
            registration.updated_at = at
            registration.from_waitlist = False
            _clear_review(registration)
            _clear_reconfirmation(registration)
            from app.notifications import notify_promotion

            notify_promotion(db, registration)
        promoted.append(registration)
    return promoted


def _process_receipt(db: Session, event: Event, receipt: RegistrationReceipt) -> tuple[dict[str, Any], int]:
    user = db.scalar(select(User).where(User.id == receipt.user_id).with_for_update(key_share=True))
    if user is None or not user.active or not email_is_eligible(user.email, user.email_verified):
        raise DomainError('registration_ineligible', 'An eligible active account is required to register.', 403)
    if not profile_is_complete(user):
        raise DomainError('profile_incomplete', 'Complete your nickname, age range, and at least one interest before registering.', 403)
    if event.status != 'published' or event.starts_at is None:
        raise DomainError('event_not_found', 'The event could not be found.', 404)
    if event.starts_at <= now():
        raise DomainError('event_started', 'Registration is closed because the event has started.', 409)
    if event.capacity is None or event.capacity <= 0:
        raise DomainError('event_capacity_invalid', 'The event is not accepting registrations.', 409)

    from app.domains.memberships.models import EventAccessRevocation
    cutoff = db.scalar(select(EventAccessRevocation.cutoff_order).where(
        EventAccessRevocation.event_id == event.id, EventAccessRevocation.user_id == user.id,
    ))
    if cutoff is not None and receipt.event_order <= cutoff:
        raise DomainError('membership_ended', 'This earlier registration attempt ended with your organization membership. Submit a new request to register again.', 409)

    current = db.scalar(
        select(Registration)
        .where(
            Registration.user_id == user.id,
            Registration.event_id == event.id,
            Registration.status.in_(ACTIVE_STATUSES),
        )
        .with_for_update()
    )
    if current is not None:
        return _registration_result(db, current), 200

    require_new_registration(db, event)
    timestamp = now()
    has_seat = _seat_count(db, event.id) < event.capacity
    if event.registration_mode == 'approval':
        status = 'pending' if has_seat else 'waitlisted'
    else:
        status = 'confirmed' if has_seat else 'waitlisted'
    registration = Registration(
        id=uid(),
        user_id=user.id,
        event_id=event.id,
        status=status,
        admission_order=receipt.event_order,
        created_at=timestamp,
        confirmed_at=timestamp if status == 'confirmed' else None,
        updated_at=timestamp,
        persona_shared=receipt.persona_shared,
    )
    db.add(registration)
    db.flush()
    if status == 'pending':
        _start_review(db, event, registration, timestamp, from_waitlist=False)
    return _registration_result(db, registration), 201


def _drain_event_locked(db: Session, event: Event, limit: int | None = None) -> int:
    """Finalize pending receipts in platform-assigned order; caller holds the event lock.

    `limit=None` drains the whole backlog in one pass; every caller in this
    module passes the batch bound so a single transaction never holds the
    event lock across an unbounded backlog. Returns receipts finalized.
    """
    query = (
        select(RegistrationReceipt)
        .where(
            RegistrationReceipt.event_id == event.id,
            RegistrationReceipt.result.is_(None),
            RegistrationReceipt.http_status.is_(None),
            RegistrationReceipt.processed_at.is_(None),
        )
        .order_by(RegistrationReceipt.event_order)
    )
    if limit is not None:
        query = query.limit(limit)
    pending = list(db.scalars(query.with_for_update()))
    if pending:
        # Different events may share attendees in opposite receipt orders. Lock
        # their users in one global order, but still decide seats in receipt order.
        list(db.scalars(
            select(User)
            .where(User.id.in_({receipt.user_id for receipt in pending}))
            .order_by(User.id)
            .with_for_update(key_share=True)
        ))
    for receipt in pending:
        try:
            result, http_status = _process_receipt(db, event, receipt)
        except DomainError as exc:
            result = {'error': {'code': exc.code, 'message': exc.message}}
            http_status = exc.status
        receipt.result = result
        receipt.http_status = http_status
        receipt.processed_at = now()
    return len(pending)


def _next_admission_order(db: Session, event: Event) -> int:
    order = db.execute(
        update(Event)
        .where(Event.id == event.id)
        .values(next_admission=Event.next_admission + 1)
        .returning(Event.next_admission)
    ).scalar_one()
    event.next_admission = order
    return int(order)


def _finish_review_timeout(db: Session, event: Event, registration: Registration, at: datetime) -> None:
    timeout_count = registration.timeout_count + 1
    registration.timeout_count = timeout_count
    if registration.from_waitlist:
        if timeout_count == 1:
            registration.status = 'waitlisted'
            registration.admission_order = _next_admission_order(db, event)
            registration.updated_at = at
            _clear_review(registration)
            message = 'Your review window expired. You were returned to the waitlist once.'
        else:
            registration.status = 'cancelled'
            registration.updated_at = at
            _clear_review(registration)
            message = 'Your registration was removed after its second expired waitlist review.'
        _notify(
            db,
            registration,
            kind='registration_waitlist_timeout',
            message=message,
            dedupe_key=f'registration_waitlist_timeout:{registration.id}:timeout:{timeout_count}',
        )
        return

    registration.status = 'cancelled'
    registration.updated_at = at
    _clear_review(registration)
    _notify(
        db,
        registration,
        kind='registration_review_timeout',
        message='Your registration was removed because its review window expired.',
        dedupe_key=f'registration_review_timeout:{registration.id}:timeout:{timeout_count}',
    )


def _catch_up_deadlines_locked(db: Session, event: Event, at: datetime) -> int:
    changed = 0
    due_reviews = list(
        db.scalars(
            select(Registration)
            .where(
                Registration.event_id == event.id,
                Registration.status == 'pending',
                Registration.review_deadline.is_not(None),
                Registration.review_deadline <= at,
            )
            .order_by(Registration.review_deadline, Registration.admission_order, Registration.id)
            .with_for_update()
        )
    )
    for registration in due_reviews:
        while (
            registration.status == 'pending'
            and registration.review_deadline is not None
            and registration.review_deadline <= at
        ):
            prior_deadline = registration.review_deadline
            stage = registration.review_stage if registration.review_stage is not None else REVIEW_STAGE_INITIAL
            window = _window(event)
            if stage == REVIEW_STAGE_INITIAL:
                registration.review_stage = REVIEW_STAGE_EXTENSION
                registration.review_deadline = _deadline_for_start(
                    event.starts_at,
                    prior_deadline,
                    window,
                )
                registration.updated_at = at
                _notify(
                    db,
                    registration,
                    kind='registration_review_warning',
                    message='Your registration is still awaiting review. The review window was extended once.',
                    dedupe_key=f'registration_review_warning:{registration.id}:timeout:{registration.timeout_count}',
                )
                if registration.reviewer_id is not None:
                    _notify(
                        db,
                        registration,
                        user_id=registration.reviewer_id,
                        kind='registration_review_warning',
                        message='A registration assigned to you still awaits review during its extension window.',
                        dedupe_key=f'registration_review_warning:{registration.id}:timeout:{registration.timeout_count}:reviewer:{registration.reviewer_id}',
                    )
                changed += 1
                continue

            if stage == REVIEW_STAGE_EXTENSION:
                final_reviewer = _choose_reviewer(
                    db,
                    event,
                    exclude=registration.first_reviewer_id,
                )
                registration.review_stage = REVIEW_STAGE_ESCALATED
                registration.review_deadline = _deadline_for_start(
                    event.starts_at,
                    prior_deadline,
                    window,
                )
                registration.reviewer_id = final_reviewer
                registration.updated_at = at
                _notify(
                    db,
                    registration,
                    kind='registration_review_escalated',
                    message='Your registration has reached the final review stage.',
                    dedupe_key=f'registration_review_escalated:{registration.id}:timeout:{registration.timeout_count}',
                )
                if final_reviewer is not None:
                    _notify(
                        db,
                        registration,
                        user_id=final_reviewer,
                        kind='registration_review_requested',
                        message='A registration is waiting for final event review.',
                        dedupe_key=f'registration_review_escalated:{registration.id}:timeout:{registration.timeout_count}:reviewer:{final_reviewer}',
                    )
                changed += 1
                continue

            _finish_review_timeout(db, event, registration, at)
            changed += 1
            break

    due_reconfirmations = list(
        db.scalars(
            select(Registration)
            .where(
                Registration.event_id == event.id,
                Registration.status == 'reconfirmation_required',
                Registration.reconfirm_deadline.is_not(None),
                Registration.reconfirm_deadline <= at,
            )
            .order_by(Registration.reconfirm_deadline, Registration.admission_order, Registration.id)
            .with_for_update()
        )
    )
    for registration in due_reconfirmations:
        revision = registration.reconfirm_revision
        registration.status = 'cancelled'
        registration.updated_at = at
        _clear_reconfirmation(registration)
        _notify(
            db,
            registration,
            kind='registration_reconfirmation_expired',
            message='Your registration was removed because reconfirmation was not received in time.',
            dedupe_key=f'registration_reconfirmation_expired:{registration.id}:revision:{revision}',
        )
        changed += 1

    if changed:
        _promote_open_seats_locked(db, event, at)
    return changed


def catch_up_locked(db: Session, event: Event, at: datetime | None = None) -> int:
    """Apply due review and reconfirmation transitions while caller holds event lock."""
    return _catch_up_deadlines_locked(db, event, at or now())


def catch_up_event(event_id: str) -> None:
    """Drain durable receipts in bounded FIFO passes, then catch up deadlines."""
    factory = session_factory()
    while True:
        with factory() as db:
            with db.begin():
                event = db.scalar(select(Event).where(Event.id == event_id).with_for_update())
                if event is None:
                    return
                timestamp = now()
                processed = _drain_event_locked(db, event, limit=DRAIN_BATCH_SIZE)
                if processed < DRAIN_BATCH_SIZE:
                    catch_up_locked(db, event, timestamp)
                    return


def drain_event(event_id: str) -> None:
    """Backward-compatible name for the app's event catch-up entry point."""
    catch_up_event(event_id)


def _lock_event(db: Session, event_id: str) -> Event:
    event = db.scalar(select(Event).where(Event.id == event_id).with_for_update())
    if event is None:
        raise DomainError('event_not_found', 'The event could not be found.', 404)
    return event


def _run_event_operation(event_id: str, operation, authorize=None):
    """Serialize an operation after bounded receipt and durable-deadline catch-up."""
    factory = session_factory()
    while True:
        retry = False
        deferred_error = None
        result = None
        with factory() as db:
            with db.begin():
                event = _lock_event(db, event_id)
                timestamp = now()
                if authorize is not None:
                    # Rejected staff calls must not drain receipts or apply due
                    # transitions as a side effect of an unauthorized read/write.
                    authorize(db, event)
                processed = _drain_event_locked(db, event, limit=DRAIN_BATCH_SIZE)
                if processed >= DRAIN_BATCH_SIZE:
                    retry = True
                else:
                    catch_up_locked(db, event, timestamp)
                    try:
                        result = operation(db, event, timestamp)
                    except DomainError as exc:
                        # Commit deadline catch-up even if the requested action is stale.
                        deferred_error = exc
        if retry:
            continue
        if deferred_error is not None:
            raise deferred_error
        return result


def _require_reviewer(db: Session, event: Event, user_id: str) -> None:
    if not any(reviewer_id == user_id for reviewer_id, _ in _eligible_reviewers(db, event)):
        raise DomainError('registration_reviewer_forbidden', 'An authorized event reviewer is required.', 403)


def list_registration_reviews(reviewer_id: str, event_id: str) -> list[dict[str, Any]]:
    def read_queue(db: Session, event: Event, timestamp: datetime) -> list[dict[str, Any]]:
        registrations = list(
            db.scalars(
                select(Registration)
                .where(
                    Registration.event_id == event.id,
                    Registration.status.in_(ACTIVE_STATUSES),
                )
                .order_by(Registration.admission_order, Registration.id)
            )
        )
        opted_in_ids = {
            row.user_id
            for row in registrations
            if row.persona_shared and event.ends_at is not None and timestamp < event.ends_at
        }
        blocked_ids = set()
        if opted_in_ids:
            from app.domains.personas.service import blocked_user_ids

            blocked_ids = set(blocked_user_ids(db, reviewer_id))
        visible_persona_ids = opted_in_ids - blocked_ids
        personas = {}
        if visible_persona_ids:
            rows = db.execute(
                select(
                    User.id,
                    User.nickname,
                    User.age_bracket,
                    User.tags,
                    User.pronouns,
                    User.icebreaker,
                ).where(User.id.in_(visible_persona_ids))
            ).all()
            personas = {
                row.id: {
                    'nickname': row.nickname,
                    'age_bracket': row.age_bracket,
                    'tags': list(row.tags or []),
                    'pronouns': row.pronouns,
                    'icebreaker': row.icebreaker,
                }
                for row in rows
            }
        return [
            {
                'registration': _registration_result(db, registration),
                'user_id': registration.user_id,
                'persona': personas.get(registration.user_id),
            }
            for registration in registrations
        ]

    return _run_event_operation(
        event_id,
        read_queue,
        authorize=lambda db, event: _require_reviewer(db, event, reviewer_id),
    )


def decide_registration(
    reviewer_id: str,
    event_id: str,
    registration_id: str,
    decision: str,
) -> dict[str, Any]:
    def decide(db: Session, event: Event, timestamp: datetime) -> dict[str, Any]:
        registration = db.scalar(
            select(Registration)
            .where(Registration.id == registration_id, Registration.event_id == event.id)
            .with_for_update()
        )
        if registration is None:
            raise DomainError('registration_not_found', 'The registration could not be found for this event.', 404)
        if (decision == 'approve' and registration.status == 'confirmed') or (
            decision == 'reject' and registration.status == 'rejected'
        ):
            return _registration_result(db, registration)
        if registration.status != 'pending':
            raise DomainError('registration_decision_stale', 'This registration is no longer awaiting review.', 409)
        if (
            event.starts_at is None
            or event.starts_at <= timestamp
            or registration.review_deadline is None
            or registration.review_deadline <= timestamp
        ):
            raise DomainError('registration_decision_expired', 'The review deadline has passed.', 409)
        if (
            registration.review_stage == REVIEW_STAGE_ESCALATED
            and registration.first_reviewer_id == reviewer_id
        ):
            raise DomainError('registration_reviewer_unassigned', 'An escalated review requires a different reviewer.', 403)

        if decision == 'approve':
            registration.status = 'confirmed'
            registration.confirmed_at = timestamp
            registration.updated_at = timestamp
            _clear_review(registration)
            _notify(
                db,
                registration,
                kind='registration_approved',
                message='Your event registration was approved.',
                dedupe_key=f'registration_approved:{registration.id}',
            )
        elif decision == 'reject':
            registration.status = 'rejected'
            registration.updated_at = timestamp
            _clear_review(registration)
            _notify(
                db,
                registration,
                kind='registration_rejected',
                message='Your event registration was not approved.',
                dedupe_key=f'registration_rejected:{registration.id}',
            )
            _promote_open_seats_locked(db, event, timestamp)
        else:
            raise DomainError('registration_decision_invalid', 'Choose approve or reject.', 422)
        return _registration_result(db, registration)

    return _run_event_operation(
        event_id,
        decide,
        authorize=lambda db, event: _require_reviewer(db, event, reviewer_id),
    )


def reconfirm_registration(
    user_id: str,
    event_id: str,
    accept: bool,
    revision: int,
) -> dict[str, Any]:
    def reconfirm(db: Session, event: Event, timestamp: datetime) -> dict[str, Any]:
        registration = db.scalar(
            select(Registration)
            .where(
                Registration.user_id == user_id,
                Registration.event_id == event.id,
                Registration.status == 'reconfirmation_required',
            )
            .with_for_update()
        )
        if registration is None:
            raise DomainError('registration_reconfirmation_stale', 'There is no outstanding reconfirmation for this registration.', 409)
        if (
            revision != event.material_revision
            or revision != registration.reconfirm_revision
        ):
            raise DomainError('registration_reconfirmation_stale', 'This reconfirmation revision is no longer current.', 409)
        if (
            registration.reconfirm_deadline is None
            or registration.reconfirm_deadline <= timestamp
            or event.starts_at is None
            or event.starts_at <= timestamp
        ):
            raise DomainError('registration_reconfirmation_expired', 'The reconfirmation deadline has passed.', 409)

        if accept:
            registration.status = 'confirmed'
            registration.updated_at = timestamp
            _clear_reconfirmation(registration)
            _notify(
                db,
                registration,
                kind='registration_reconfirmed',
                message='Your event registration is confirmed for the updated event details.',
                dedupe_key=f'registration_reconfirmed:{registration.id}:revision:{revision}',
            )
        else:
            registration.status = 'cancelled'
            registration.updated_at = timestamp
            _clear_reconfirmation(registration)
            _notify(
                db,
                registration,
                kind='registration_reconfirmation_declined',
                message='Your registration was cancelled as requested.',
                dedupe_key=f'registration_reconfirmation_declined:{registration.id}:revision:{revision}',
            )
            _promote_open_seats_locked(db, event, timestamp)
        return _registration_result(db, registration)

    return _run_event_operation(event_id, reconfirm)


def withdraw_registration(user_id: str, event_id: str) -> dict[str, Any]:
    def withdraw(db: Session, event: Event, timestamp: datetime) -> dict[str, Any]:
        registration = db.scalar(
            select(Registration)
            .where(
                Registration.user_id == user_id,
                Registration.event_id == event.id,
                Registration.status.in_(ACTIVE_STATUSES),
            )
            .with_for_update()
        )
        if registration is None:
            registration = db.scalar(
                select(Registration)
                .where(
                    Registration.user_id == user_id,
                    Registration.event_id == event.id,
                    Registration.status == 'cancelled',
                )
                .order_by(Registration.admission_order.desc())
                .limit(1)
            )
            if registration is None:
                raise DomainError('registration_not_found', 'No registration was found for this account and event.', 404)
            return _registration_result(db, registration)

        if event.starts_at is None or event.starts_at <= timestamp:
            raise DomainError('event_started', 'A registration cannot be withdrawn after the event starts.', 409)
        released_seat = registration.status in SEAT_STATUSES
        registration.status = 'cancelled'
        registration.updated_at = timestamp
        _clear_review(registration)
        _clear_reconfirmation(registration)
        if released_seat:
            _promote_open_seats_locked(db, event, timestamp)
        return _registration_result(db, registration)

    return _run_event_operation(event_id, withdraw)


def list_my_registrations(user_id: str) -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        event_ids = set(
            db.scalars(select(Registration.event_id).where(Registration.user_id == user_id))
        )
        event_ids.update(
            db.scalars(
                select(RegistrationReceipt.event_id).where(
                    RegistrationReceipt.user_id == user_id,
                    RegistrationReceipt.result.is_(None),
                )
            )
        )
    for event_id in sorted(event_ids):
        drain_event(event_id)

    factory = session_factory()
    with factory() as db:
        latest = (
            select(
                Registration.event_id.label('event_id'),
                func.max(Registration.admission_order).label('admission_order'),
            )
            .where(Registration.user_id == user_id)
            .group_by(Registration.event_id)
            .subquery()
        )
        rows = db.execute(
            select(Registration, Event, Organization)
            .join(
                latest,
                and_(
                    Registration.event_id == latest.c.event_id,
                    Registration.admission_order == latest.c.admission_order,
                ),
            )
            .join(Event, Event.id == Registration.event_id)
            .join(Organization, Organization.id == Event.org_id)
            .where(Registration.user_id == user_id)
            .order_by(Event.starts_at.asc().nulls_last(), Event.id.asc())
        ).all()
        timestamp = now()
        from app.domains.featured.service import active_featured_event_ids
        featured_ids = active_featured_event_ids(db, [event for _, event, _ in rows], at=timestamp)
        results = []
        for registration, event, organization in rows:
            result = _registration_result(db, registration)
            result.update({
                'event_title': event.title,
                'is_featured': event.id in featured_ids,
                'starts_at': event.starts_at,
                'ends_at': event.ends_at,
                'organization_name': organization.name,
                'is_past': event.ends_at is not None and event.ends_at <= timestamp,
            })
            results.append(result)
        return results


def end_membership_attendance(db: Session, org_id: str, user_id: str) -> tuple[int, int]:
    """End current participation atomically; caller holds org lock and deactivated grant."""
    from app.domains.memberships.models import EventAccessRevocation

    # All events before any attendance rows: registration intake cannot race the
    # durable per-event cutoffs, and multi-event departures keep one lock order.
    events = list(db.scalars(select(Event).where(
        Event.org_id == org_id, Event.status == 'published',
    ).order_by(Event.id).with_for_update().execution_options(populate_existing=True)))
    timestamp = now()
    cancelled = revoked = 0
    for event in events:
        marker = db.scalar(select(EventAccessRevocation).where(
            EventAccessRevocation.event_id == event.id, EventAccessRevocation.user_id == user_id,
        ).with_for_update())
        previous_cutoff = marker.cutoff_order if marker is not None else -1
        # Older local drafts can contain attendance without intake receipts.
        # Advance only; never renumber their history or let a new order reuse it.
        stored_order = max(
            db.scalar(select(func.max(Registration.admission_order)).where(Registration.event_id == event.id)) or 0,
            db.scalar(select(func.max(RegistrationReceipt.event_order)).where(RegistrationReceipt.event_id == event.id)) or 0,
        )
        cutoff = max(previous_cutoff, event.next_admission, stored_order)
        event.next_admission = cutoff
        rows = list(db.scalars(select(Registration).where(
            Registration.event_id == event.id, Registration.user_id == user_id,
            Registration.status.in_(ACTIVE_STATUSES),
        ).order_by(Registration.id).with_for_update()))
        for registration in rows:
            if (registration.status == 'confirmed' and registration.admission_order > previous_cutoff
                    and event.ends_at is not None and event.ends_at + timedelta(hours=72) > timestamp):
                revoked += 1
            if event.ends_at is not None and event.ends_at <= timestamp:
                continue  # Preserve actual ended attendance; marker revokes retained chat.
            registration.status = 'cancelled'
            registration.updated_at = timestamp
            _clear_review(registration)
            _clear_reconfirmation(registration)
            cancelled += 1
            _notify(db, registration, kind='membership_attendance_ended',
                    message='An event registration ended because your organization membership ended.',
                    dedupe_key=f'membership_departure:{registration.id}:{cutoff}')
        if marker is None:
            db.add(EventAccessRevocation(event_id=event.id, user_id=user_id,
                   cutoff_order=cutoff, created_at=timestamp, updated_at=timestamp))
        else:
            marker.cutoff_order = cutoff
            marker.updated_at = timestamp
        db.flush()
        decision_time = now()
        catch_up_locked(db, event, decision_time)
        _promote_open_seats_locked(db, event, decision_time)
    return cancelled, revoked


def reconcile_material_change(
    db: Session,
    event: Event,
    fields: dict[str, Any],
    reconfirm_deadline: datetime,
    selection_mode: str,
    selected_registration_ids: list[str],
) -> int:
    """Apply registration consequences under the caller's event lock and transaction."""
    timestamp = now()
    catch_up_locked(db, event, timestamp)
    proposed = dict(fields)
    changed_fields = {
        name
        for name in MATERIAL_FIELDS
        if name in proposed and proposed[name] != getattr(event, name)
    }
    if not changed_fields:
        return event.material_revision

    proposed_start = proposed.get('starts_at', event.starts_at)
    proposed_capacity = proposed.get('capacity', event.capacity)
    if proposed_start is None or proposed_capacity is None or proposed_capacity <= 0:
        raise DomainError('event_change_invalid', 'The proposed event must have a future start and positive capacity.', 422)
    if (
        reconfirm_deadline.tzinfo is None
        or reconfirm_deadline.utcoffset() is None
        or reconfirm_deadline <= timestamp
        or reconfirm_deadline >= proposed_start
    ):
        raise DomainError('event_reconfirmation_deadline_invalid', 'The reconfirmation deadline must be in the future and before the proposed event start.', 422)
    selected_ids = list(selected_registration_ids)
    if len(selected_ids) != len(set(selected_ids)):
        raise DomainError('event_selection_duplicate', 'A registration may only be selected once.', 422)

    holders = list(
        db.scalars(
            select(Registration)
            .where(
                Registration.event_id == event.id,
                Registration.status.in_(SEAT_STATUSES),
            )
            .order_by(Registration.id)
            .with_for_update()
        )
    )
    by_id = {registration.id: registration for registration in holders}
    selected_set = set(selected_ids)
    if selected_set - by_id.keys():
        raise DomainError('event_selection_invalid', 'Selections must be current seat holders in this event.', 422)
    deficit = max(0, len(holders) - proposed_capacity)
    if selection_mode == 'exact':
        if len(selected_ids) != deficit:
            raise DomainError('event_selection_count_invalid', 'Select exactly the number of seats removed by the capacity change.', 422)
        to_cancel = [by_id[registration_id] for registration_id in selected_ids]
    elif selection_mode == 'newest_in_pool':
        if deficit == 0 and selected_ids:
            raise DomainError('event_selection_unnecessary', 'Do not submit selections when no seats need to be removed.', 422)
        if len(selected_ids) < deficit:
            raise DomainError('event_selection_pool_too_small', 'The selected pool must contain enough current seat holders.', 422)
        candidates = [by_id[registration_id] for registration_id in selected_ids]
        candidates.sort(
            key=lambda registration: (
                registration.confirmed_at or registration.created_at,
                registration.admission_order,
                registration.id,
            ),
            reverse=True,
        )
        to_cancel = candidates[:deficit]
    else:
        raise DomainError('event_selection_mode_invalid', 'Choose exact or newest_in_pool selection.', 422)

    next_revision = event.material_revision + 1
    active = list(
        db.scalars(
            select(Registration)
            .where(
                Registration.event_id == event.id,
                Registration.status.in_(ACTIVE_STATUSES),
            )
            .order_by(Registration.admission_order, Registration.id)
            .with_for_update()
        )
    )
    active_user_ids = {registration.user_id for registration in active}
    # Notice every currently active registrant, including anyone selected for
    # removal. Revision-scoped keys keep a later material edit independently visible.
    for registration in active:
        _notify(
            db,
            registration,
            kind='event_material_change',
            message='Event details changed. Review your registration status and any reconfirmation request.',
            dedupe_key=f'registration_material_change:{event.id}:revision:{next_revision}:{registration.id}',
        )
    from app.notifications import notify_event_change_members

    notify_event_change_members(
        db,
        event,
        next_revision,
        excluded_user_ids=active_user_ids,
    )

    cancel_ids = {registration.id for registration in to_cancel}
    for registration in holders:
        registration.updated_at = timestamp
        if registration.id in cancel_ids:
            registration.status = 'cancelled'
            _clear_review(registration)
            _clear_reconfirmation(registration)
        elif registration.status in {'confirmed', 'reconfirmation_required'}:
            registration.status = 'reconfirmation_required'
            registration.reconfirm_deadline = reconfirm_deadline
            registration.reconfirm_revision = next_revision
            _clear_review(registration)
        elif registration.status == 'pending':
            registration.reconfirm_deadline = None
            registration.reconfirm_revision = None
            if registration.review_deadline is not None:
                before_start = proposed_start - timedelta(microseconds=1)
                registration.review_deadline = min(registration.review_deadline, before_start)

    _promote_open_seats_locked(
        db,
        event,
        timestamp,
        capacity=proposed_capacity,
        starts_at=proposed_start,
    )
    return next_revision
