import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.event_safety import event_is_terminal
from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.memberships import policy as membership_policy
from app.domains.organizations.models import Organization
from app.domains.registrations.models import Registration

from .models import AttendanceAudit, AttendanceMark, AttendanceSession
from .schemas import AttendanceMarkInput, AttendanceSessionInput


STAFF_ROLES = ("owner", "admin", "moderator")


def _event_or_404(db: Session, event_id: str) -> Event:
    event = db.scalar(
        select(Event)
        .where(Event.id == str(event_id))
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise DomainError("event_not_found", "The event could not be found.", 404)
    return event


def _read_access(db: Session, actor_id: str, event_id: str) -> tuple[Event, Organization]:
    event = _event_or_404(db, event_id)
    organization, _ = membership_policy.require_staff(
        db, str(actor_id), event.org_id, roles=STAFF_ROLES,
    )
    return event, organization


def _write_access(
    db: Session,
    actor_id: str,
    event_id: str,
    client_key: str,
) -> tuple[Event, Organization]:
    # The unlocked lookup only discovers the organization whose row must be locked first.
    event = _event_or_404(db, event_id)
    org_id = event.org_id
    membership_policy.lock_client_key(db, str(actor_id), client_key)
    membership_policy.require_staff(
        db, str(actor_id), org_id, roles=STAFF_ROLES, lock=True,
    )
    event = db.scalar(
        select(Event)
        .where(Event.id == str(event_id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise DomainError("event_not_found", "The event could not be found.", 404)
    if event.org_id != org_id:
        raise DomainError(
            "attendance_event_changed",
            "The event organization changed while the request was waiting.",
            409,
        )
    organization, _ = membership_policy.require_staff(
        db, str(actor_id), event.org_id, roles=STAFF_ROLES,
    )
    return event, organization


def _require_writable(db: Session, event: Event, organization: Organization) -> None:
    if (event.status != "published" or organization.accreditation_status != "approved"
            or event_is_terminal(db, event)):
        raise DomainError(
            "attendance_event_not_writable",
            "Attendance can be changed only for a published event of an approved organization.",
            409,
        )


def _session(db: Session, event_id: str, *, lock: bool = False) -> AttendanceSession | None:
    query = select(AttendanceSession).where(AttendanceSession.event_id == event_id)
    if lock:
        query = query.with_for_update()
    return db.scalar(query.execution_options(populate_existing=True))


def _request_hash(method: str, path: str, body: dict) -> str:
    canonical = json.dumps(
        {"method": method, "path": path, "body": body},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _replay(
    db: Session,
    actor_id: str,
    client_key: str,
    event_id: str,
    payload_hash: str,
) -> dict | None:
    previous = db.scalar(
        select(AttendanceAudit)
        .where(
            AttendanceAudit.actor_id == actor_id,
            AttendanceAudit.client_key == client_key,
        )
        .execution_options(populate_existing=True)
    )
    if previous is None:
        return None
    if previous.event_id != event_id or previous.payload_hash != payload_hash:
        raise DomainError(
            "attendance_client_key_reused",
            "This client key was already used for a different attendance command.",
            409,
        )
    return dict(previous.result)


def _stale_version() -> DomainError:
    return DomainError(
        "attendance_version_conflict",
        "Attendance changed. Refresh its current state before making a new change.",
        409,
    )


def get_attendance(db: Session, actor_id: str, event_id: str) -> dict:
    event, organization = _read_access(db, actor_id, event_id)
    session = _session(db, event.id)
    rows = db.execute(
        select(Registration, AttendanceMark.attended)
        .outerjoin(AttendanceMark, AttendanceMark.registration_id == Registration.id)
        .where(
            Registration.event_id == event.id,
            Registration.status == "confirmed",
        )
        .order_by(Registration.admission_order, Registration.id)
    ).all()
    attendees = [
        {
            "registration_id": registration.id,
            "participant_label": f"Registration · {registration.id}",
            "attended": bool(attended),
        }
        for registration, attended in rows
    ]
    checked_in_count = sum(attendee["attended"] for attendee in attendees)
    return {
        "event_id": event.id,
        "is_open": session.is_open if session is not None else False,
        "version": session.version if session is not None else 0,
        "writable": (event.status == "published" and organization.accreditation_status == "approved"
                     and not event_is_terminal(db, event)),
        "confirmed_count": len(attendees),
        "checked_in_count": checked_in_count,
        "attendees": attendees,
    }


def list_attendance_history(db: Session, actor_id: str, event_id: str) -> list[dict]:
    event, _ = _read_access(db, actor_id, event_id)
    rows = db.scalars(
        select(AttendanceAudit)
        .where(AttendanceAudit.event_id == event.id)
        .order_by(AttendanceAudit.created_at.desc(), AttendanceAudit.id.desc())
        .limit(100)
    )
    return [
        {
            "id": row.id,
            "event_id": row.event_id,
            "actor_id": row.actor_id,
            "action": row.action,
            "registration_id": row.registration_id,
            "previous_value": row.previous_value,
            "value": row.value,
            "version": row.version,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def set_attendance_session(
    db: Session,
    actor_id: str,
    event_id: str,
    payload: AttendanceSessionInput,
) -> dict:
    actor_id, event_id = str(actor_id), str(event_id)
    client_key = str(payload.client_key)
    path = f"/events/{event_id}/attendance/session"
    payload_hash = _request_hash(
        "POST",
        path,
        {
            "is_open": payload.is_open,
            "version": payload.version,
            "client_key": client_key,
        },
    )
    event, organization = _write_access(db, actor_id, event_id, client_key)
    replay = _replay(db, actor_id, client_key, event.id, payload_hash)
    if replay is not None:
        return replay

    _require_writable(db, event, organization)
    session = _session(db, event.id, lock=True)
    current_version = session.version if session is not None else 0
    current_open = session.is_open if session is not None else False
    if payload.version != current_version:
        raise _stale_version()

    if session is None:
        session = AttendanceSession(event_id=event.id, is_open=False, version=0)
        db.add(session)
    session.is_open = payload.is_open
    session.version = current_version + 1

    recorded_at = now()
    result = {
        "event_id": event.id,
        "registration_id": None,
        "is_open": payload.is_open,
        "attended": None,
        "version": session.version,
        "recorded_at": recorded_at.isoformat(),
    }
    db.add(
        AttendanceAudit(
            id=uid(),
            event_id=event.id,
            actor_id=actor_id,
            client_key=client_key,
            payload_hash=payload_hash,
            action="session",
            registration_id=None,
            previous_value=current_open,
            value=payload.is_open,
            version=session.version,
            result=result,
            created_at=recorded_at,
        )
    )
    db.flush()
    return result


def set_registration_attendance(
    db: Session,
    actor_id: str,
    event_id: str,
    registration_id: str,
    payload: AttendanceMarkInput,
) -> dict:
    actor_id, event_id, registration_id = str(actor_id), str(event_id), str(registration_id)
    client_key = str(payload.client_key)
    path = f"/events/{event_id}/attendance/registrations/{registration_id}"
    payload_hash = _request_hash(
        "PUT",
        path,
        {
            "attended": payload.attended,
            "version": payload.version,
            "client_key": client_key,
        },
    )
    event, organization = _write_access(db, actor_id, event_id, client_key)
    replay = _replay(db, actor_id, client_key, event.id, payload_hash)
    if replay is not None:
        return replay

    _require_writable(db, event, organization)
    session = _session(db, event.id, lock=True)
    current_version = session.version if session is not None else 0
    if payload.version != current_version:
        raise _stale_version()
    if session is None or not session.is_open:
        raise DomainError(
            "attendance_checkin_closed",
            "Open check-in before marking attendance.",
            409,
        )

    registration = db.scalar(
        select(Registration)
        .where(
            Registration.id == registration_id,
            Registration.event_id == event.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if registration is None or registration.status != "confirmed":
        raise DomainError(
            "attendance_registration_unavailable",
            "Only a current confirmed registration for this event can be marked.",
            409,
        )

    mark = db.scalar(
        select(AttendanceMark)
        .where(AttendanceMark.registration_id == registration.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    previous_value = mark.attended if mark is not None else False
    if mark is None:
        mark = AttendanceMark(registration_id=registration.id, attended=False)
        db.add(mark)
    mark.attended = payload.attended
    session.version = current_version + 1

    recorded_at = now()
    result = {
        "event_id": event.id,
        "registration_id": registration.id,
        "is_open": session.is_open,
        "attended": payload.attended,
        "version": session.version,
        "recorded_at": recorded_at.isoformat(),
    }
    db.add(
        AttendanceAudit(
            id=uid(),
            event_id=event.id,
            actor_id=actor_id,
            client_key=client_key,
            payload_hash=payload_hash,
            action="mark",
            registration_id=registration.id,
            previous_value=previous_value,
            value=payload.attended,
            version=session.version,
            result=result,
            created_at=recorded_at,
        )
    )
    db.flush()
    return result
