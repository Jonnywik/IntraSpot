import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.eventsafety.models import (
    EventControl,
    EventReport,
    OrganizationSuspension,
    SafetyAudit,
)
from app.domains.memberships import policy as membership_policy
from app.domains.moderation.service import ORG_REVIEW_DAYS, PLATFORM_REVIEW_DAYS
from app.domains.organizations import service as organization_service


REPORT_REASONS = {"safety", "deception"}
ORG_REPORT_ACTIONS = {"dismiss", "hide"}
REPORT_ACTION_STATUS = {
    "dismiss": "dismissed",
    "hide": "hidden",
    "remove": "removed",
    "uphold": "upheld",
}
SUSPENSION_DEFAULT_DAYS = 7
SUSPENSION_SWEEP_LIMIT = 100
REPORT_SWEEP_EVENT_LIMIT = 100
REPORT_SWEEP_PER_EVENT_LIMIT = 100


def _timestamp(at: datetime | None = None) -> datetime:
    value = at if at is not None else now()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _not_found(kind: str) -> DomainError:
    labels = {
        "event": ("event_not_found", "Event was not found."),
        "report": ("event_report_not_found", "Event report was not found."),
        "organization": ("organization_not_found", "Organization was not found."),
    }
    code, message = labels[kind]
    return DomainError(code, message, 404)


def _conflict(code: str, message: str) -> DomainError:
    return DomainError(code, message, 409)


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    return value


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _replay(
    db: Session, actor_id: str, client_key: str, payload_hash: str
) -> dict[str, Any] | None:
    previous = db.scalar(
        select(SafetyAudit).where(
            SafetyAudit.actor_id == actor_id,
            SafetyAudit.client_key == client_key,
        )
    )
    if previous is None:
        return None
    if previous.payload_hash != payload_hash:
        raise _conflict(
            "safety_idempotency_conflict",
            "This request key was already used for a different safety action.",
        )
    return previous.result


def _audit(
    *,
    org_id: str,
    action: str,
    scope: str,
    version: int,
    at: datetime,
    previous: dict[str, Any],
    result: dict[str, Any],
    actor_id: str | None = None,
    event_id: str | None = None,
    report_id: str | None = None,
    client_key: str | None = None,
    payload_hash: str | None = None,
) -> SafetyAudit:
    return SafetyAudit(
        id=uid(),
        org_id=org_id,
        event_id=event_id,
        report_id=report_id,
        actor_id=actor_id,
        client_key=client_key,
        payload_hash=payload_hash,
        scope=scope,
        action=action,
        version=version,
        previous=_json_ready(previous),
        result=_json_ready(result),
        created_at=at,
    )


def _require_current_eligible(db: Session, actor: Actor) -> None:
    if not membership_policy.eligible_user(db, actor.user_id):
        raise DomainError(
            "plm_email_required", "A verified PLM email address is required.", 403
        )


def _is_platform_admin(db: Session, actor: Actor) -> bool:
    try:
        organization_service.require_platform_admin(db, actor)
        return True
    except DomainError as error:
        if error.status == 403:
            return False
        raise


def _require_staff(
    db: Session, actor: Actor, org_id: str, *, roles=("owner", "admin", "moderator")
) -> None:
    membership_policy.require_staff(
        db, actor.user_id, org_id, roles=roles, lock=False
    )


def _require_staff_or_platform(db: Session, actor: Actor, org_id: str) -> bool:
    if _is_platform_admin(db, actor):
        return True
    _require_staff(db, actor, org_id)
    return False


def _event_org_id(db: Session, event_id: str) -> str:
    org_id = db.scalar(select(Event.org_id).where(Event.id == event_id))
    if org_id is None:
        raise _not_found("event")
    return org_id


def _lock_event_context(db: Session, event_id: str) -> tuple[Event, str]:
    org_id = _event_org_id(db, event_id)
    organization_service.get_organization(db, org_id, lock=True)
    event = db.scalar(
        select(Event)
        .where(Event.id == event_id, Event.org_id == org_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise _not_found("event")
    return event, org_id


def _event_control(db: Session, event_id: str) -> EventControl | None:
    return db.scalar(
        select(EventControl)
        .where(EventControl.event_id == event_id)
        .execution_options(populate_existing=True)
    )


def _ensure_event_control(db: Session, event_id: str) -> EventControl:
    control = _event_control(db, event_id)
    if control is None:
        control = EventControl(event_id=event_id)
        db.add(control)
        db.flush()
    return control


def _control_values(control: EventControl | None) -> dict[str, Any]:
    return {
        "org_hidden": bool(control.org_hidden) if control else False,
        "platform_hidden": bool(control.platform_hidden) if control else False,
        "removed": bool(control.removed) if control else False,
        "cancelled": bool(control.cancelled) if control else False,
        "version": int(control.version) if control else 0,
        "org_reviewed_at": control.org_reviewed_at if control else None,
    }


def _terminal(db: Session, event: Event) -> bool:
    from app.core.event_safety import event_is_terminal

    return event_is_terminal(db, event)


def _event_evidence(event: Event) -> str:
    limits = {
        "title": 200,
        "summary": 400,
        "description": 2200,
        "venue_name": 200,
        "venue_address": 500,
    }
    snapshot = {
        name: (getattr(event, name) or "")[:limit]
        for name, limit in limits.items()
    }
    encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    encoded_size = len(encoded.encode("utf-8"))
    while encoded_size > 4096:
        largest = max(snapshot, key=lambda name: len(snapshot[name].encode("utf-8")))
        trim = max(1, (encoded_size - 4096 + 1) // 2)
        snapshot[largest] = snapshot[largest][:-trim]
        encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
        encoded_size = len(encoded.encode("utf-8"))
    return encoded


def _receipt(report: EventReport) -> dict[str, Any]:
    return {
        "id": report.id,
        "event_id": report.event_id,
        "org_id": report.org_id,
        "status": report.status,
        "stage": report.stage,
        "version": report.version,
        "deadline": report.deadline,
    }


def _captured_material_revision(db: Session, report: EventReport) -> int:
    result = db.scalar(
        select(SafetyAudit.result)
        .where(SafetyAudit.report_id == report.id, SafetyAudit.action == "report")
        .order_by(SafetyAudit.created_at, SafetyAudit.id)
        .limit(1)
    )
    return int((result or {}).get("captured_material_revision", 0))


def _current_event_version(db: Session, event: Event) -> int:
    control = _event_control(db, event.id)
    return int(event.material_revision) + (int(control.version) if control else 0)


def _report_review(db: Session, report: EventReport, at: datetime) -> dict[str, Any]:
    event = db.scalar(
        select(Event)
        .where(Event.id == report.event_id)
        .execution_options(populate_existing=True)
    )
    audit_rows = list(
        db.scalars(
            select(SafetyAudit)
            .where(
                SafetyAudit.report_id == report.id,
                SafetyAudit.action != "report",
            )
            .order_by(SafetyAudit.created_at, SafetyAudit.id)
        )
    )
    result = _receipt(report)
    result.update(
        {
            "reason": report.reason,
            "evidence": (
                report.evidence
                if report.status in {"open", "escalated"} and report.deadline > at
                else None
            ),
            "reporter_id": report.reporter_id,
            "created_at": report.created_at,
            "event_version": _current_event_version(db, event) if event else 0,
            "decisions": [
                {
                    "id": row.id,
                    "org_id": row.org_id,
                    "event_id": row.event_id,
                    "report_id": row.report_id,
                    "actor_id": row.actor_id,
                    "scope": row.scope,
                    "action": row.action,
                    "version": row.version,
                    "created_at": row.created_at,
                }
                for row in audit_rows
            ],
        }
    )
    return result


def _notify_report_reviewers(db: Session, report: EventReport) -> None:
    from app.domains.moderation.service import (
        _eligible_org_reviewer_ids,
        _eligible_platform_reviewer_ids,
    )
    from app.notifications import notify_in_app

    reviewers = (
        _eligible_org_reviewer_ids(db, report.org_id)
        if report.stage == "organization"
        else _eligible_platform_reviewer_ids(db)
    )
    stage_label = "organization" if report.stage == "organization" else "platform"
    for reviewer_id in reviewers:
        notify_in_app(
            db,
            user_id=reviewer_id,
            event_id=report.event_id,
            org_id=report.org_id,
            kind="event_safety_report",
            message=f"An event safety report requires {stage_label} review.",
            dedupe_key=f"event_safety:report:{report.id}:review:{reviewer_id}",
        )


def _notify_reporter_resolution(db: Session, report: EventReport) -> None:
    from app.notifications import notify_in_app

    notify_in_app(
        db,
        user_id=report.reporter_id,
        event_id=report.event_id,
        org_id=report.org_id,
        kind="event_safety_report",
        message="Your event safety report was resolved.",
        dedupe_key=f"event_safety:report:{report.id}:resolved:{report.version}",
    )


def _notify_org_safety(
    db: Session, org_id: str, version: int, message: str
) -> None:
    from app.domains.moderation.service import _eligible_org_reviewer_ids
    from app.notifications import notify_in_app

    for user_id in _eligible_org_reviewer_ids(db, org_id):
        notify_in_app(
            db,
            user_id=user_id,
            org_id=org_id,
            kind="organization_safety",
            message=message,
            dedupe_key=f"event_safety:organization:{org_id}:version:{version}:{user_id}",
        )


def sweep_expired_suspensions(
    db: Session, org_id: str | None = None, at: datetime | None = None
) -> int:
    """Seal due suspensions under organization locks, before callers lock events."""
    timestamp = _timestamp(at)
    query = select(OrganizationSuspension.org_id).where(
        OrganizationSuspension.suspended_until.is_not(None),
        OrganizationSuspension.suspended_until <= timestamp,
    )
    if org_id is not None:
        query = query.where(OrganizationSuspension.org_id == org_id)
    org_ids = list(
        db.scalars(query.order_by(OrganizationSuspension.org_id).limit(SUSPENSION_SWEEP_LIMIT))
    )
    expired = 0
    for current_org_id in org_ids:
        organization_service.get_organization(db, current_org_id, lock=True)
        suspension = db.scalar(
            select(OrganizationSuspension)
            .where(OrganizationSuspension.org_id == current_org_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            suspension is None
            or suspension.suspended_until is None
            or suspension.suspended_until > timestamp
        ):
            continue
        expiry = suspension.suspended_until
        previous = {
            "version": suspension.version,
            "suspended_until": expiry,
        }
        suspension.suspended_until = None
        suspension.version += 1
        db.add(
            _audit(
                org_id=current_org_id,
                scope="organization",
                action="expire",
                version=suspension.version,
                at=expiry,
                previous=previous,
                result={"version": suspension.version, "suspended_until": None},
            )
        )
        _notify_org_safety(
            db,
            current_org_id,
            suspension.version,
            "The organization safety suspension has ended.",
        )
        expired += 1
    if expired:
        db.flush()
    return expired


def sweep_expired_reports(
    db: Session,
    *,
    org_id: str | None = None,
    event_id: str | None = None,
    at: datetime | None = None,
) -> int:
    """Purge due snapshots after locking organization, event, then report rows."""
    timestamp = _timestamp(at)
    query = (
        select(EventReport.org_id, EventReport.event_id)
        .where(
            EventReport.status.in_(("open", "escalated")),
            EventReport.deadline <= timestamp,
        )
        .distinct()
    )
    if org_id is not None:
        query = query.where(EventReport.org_id == org_id)
    if event_id is not None:
        query = query.where(EventReport.event_id == event_id)
    contexts = list(
        db.execute(
            query.order_by(EventReport.org_id, EventReport.event_id).limit(
                REPORT_SWEEP_EVENT_LIMIT
            )
        ).tuples()
    )
    expired = 0
    for current_org_id, current_event_id in contexts:
        organization_service.get_organization(db, current_org_id, lock=True)
        event = db.scalar(
            select(Event)
            .where(Event.id == current_event_id, Event.org_id == current_org_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if event is None:
            continue
        reports = list(
            db.scalars(
                select(EventReport)
                .where(
                    EventReport.org_id == current_org_id,
                    EventReport.event_id == current_event_id,
                    EventReport.status.in_(("open", "escalated")),
                    EventReport.deadline <= timestamp,
                )
                .order_by(EventReport.deadline, EventReport.id)
                .limit(REPORT_SWEEP_PER_EVENT_LIMIT)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        for report in reports:
            deadline = report.deadline
            previous = {
                "status": report.status,
                "version": report.version,
                "deadline": deadline,
            }
            report.status = "expired"
            report.version += 1
            report.resolved_at = deadline
            report.evidence = None
            db.add(
                _audit(
                    org_id=report.org_id,
                    event_id=report.event_id,
                    report_id=report.id,
                    scope="report",
                    action="expire",
                    version=report.version,
                    at=deadline,
                    previous=previous,
                    result={
                        "status": "expired",
                        "version": report.version,
                        "deadline": deadline,
                    },
                )
            )
            expired += 1
    if expired:
        db.flush()
    return expired


def create_event_report(
    db: Session,
    actor: Actor,
    event_id: str,
    reason: str,
    client_key: str,
    *,
    at: datetime | None = None,
) -> dict[str, Any]:
    if reason not in REPORT_REASONS:
        raise DomainError("event_report_reason_invalid", "Choose an available report reason.", 422)
    _require_current_eligible(db, actor)
    timestamp = _timestamp(at)
    key = str(client_key)
    payload_hash = _payload_hash(
        {"action": "report", "event_id": event_id, "reason": reason}
    )
    membership_policy.lock_client_key(db, actor.user_id, key)
    org_id = _event_org_id(db, event_id)
    sweep_expired_suspensions(db, org_id, timestamp)
    sweep_expired_reports(db, org_id=org_id, event_id=event_id, at=timestamp)
    event, org_id = _lock_event_context(db, event_id)

    replay = _replay(db, actor.user_id, key, payload_hash)
    if replay is not None:
        return replay["receipt"]

    active = db.scalar(
        select(EventReport)
        .where(
            EventReport.reporter_id == actor.user_id,
            EventReport.event_id == event_id,
            EventReport.status.in_(("open", "escalated")),
        )
        .order_by(EventReport.created_at, EventReport.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if active is not None:
        captured_material_revision = _captured_material_revision(db, active)
        receipt = _receipt(active)
        db.add(
            _audit(
                org_id=org_id,
                event_id=event_id,
                report_id=active.id,
                actor_id=actor.user_id,
                client_key=key,
                payload_hash=payload_hash,
                scope="report",
                action="report",
                version=active.version,
                at=timestamp,
                previous={},
                result={
                    "receipt": receipt,
                    "captured_material_revision": captured_material_revision,
                },
            )
        )
        db.flush()
        return receipt

    from app.core.event_safety import require_readable_event

    require_readable_event(db, event, actor.user_id, timestamp)
    control = _event_control(db, event.id)
    stage = "organization"
    status = "open"
    if control is not None and control.org_reviewed_at is not None:
        reporters = set(
            db.scalars(
                select(EventReport.reporter_id)
                .where(
                    EventReport.event_id == event.id,
                    EventReport.created_at > control.org_reviewed_at,
                    EventReport.created_at >= timestamp - timedelta(days=ORG_REVIEW_DAYS),
                    EventReport.created_at <= timestamp,
                )
                .distinct()
            )
        )
        if len(reporters | {actor.user_id}) >= 3:
            stage, status = "platform", "escalated"

    report = EventReport(
        id=uid(),
        event_id=event.id,
        org_id=org_id,
        reporter_id=actor.user_id,
        reason=reason,
        stage=stage,
        status=status,
        version=1,
        evidence=_event_evidence(event),
        created_at=timestamp,
        deadline=timestamp
        + timedelta(days=PLATFORM_REVIEW_DAYS if stage == "platform" else ORG_REVIEW_DAYS),
    )
    db.add(report)
    db.flush()
    receipt = _receipt(report)
    db.add(
        _audit(
            org_id=org_id,
            event_id=event.id,
            report_id=report.id,
            actor_id=actor.user_id,
            client_key=key,
            payload_hash=payload_hash,
            scope="report",
            action="report",
            version=report.version,
            at=timestamp,
            previous={},
            result={
                "receipt": receipt,
                "captured_material_revision": event.material_revision,
            },
        )
    )
    _notify_report_reviewers(db, report)
    db.flush()
    return receipt


def list_my_event_reports(
    db: Session, actor: Actor, *, at: datetime | None = None
) -> list[dict[str, Any]]:
    timestamp = _timestamp(at)
    due_orgs = list(
        db.scalars(
            select(EventReport.org_id)
            .where(
                EventReport.reporter_id == actor.user_id,
                EventReport.status.in_(("open", "escalated")),
                EventReport.deadline <= timestamp,
            )
            .distinct()
            .order_by(EventReport.org_id)
            .limit(50)
        )
    )
    for current_org_id in due_orgs:
        sweep_expired_reports(db, org_id=current_org_id, at=timestamp)
    reports = db.scalars(
        select(EventReport)
        .where(EventReport.reporter_id == actor.user_id)
        .order_by(EventReport.created_at.desc(), EventReport.id.desc())
        .limit(100)
    )
    return [_receipt(report) for report in reports]


def list_event_moderation_reports(
    db: Session,
    actor: Actor,
    *,
    org_id: str | None = None,
    at: datetime | None = None,
) -> list[dict[str, Any]]:
    timestamp = _timestamp(at)
    if org_id is None:
        organization_service.require_platform_admin(db, actor)
        stage = "platform"
        sweep_expired_reports(db, at=timestamp)
        query = select(EventReport).where(EventReport.stage == stage)
    else:
        if _is_platform_admin(db, actor):
            organization_service.get_organization(db, org_id, lock=True)
            stage = "platform"
        else:
            membership_policy.require_staff(db, actor.user_id, org_id, lock=True)
            stage = "organization"
        sweep_expired_reports(db, org_id=org_id, at=timestamp)
        query = select(EventReport).where(
            EventReport.org_id == org_id,
            EventReport.stage == stage,
        )
    reports = list(
        db.scalars(
            query.order_by(EventReport.created_at.desc(), EventReport.id.desc()).limit(100)
        )
    )
    return [_report_review(db, report, timestamp) for report in reports]


def decide_event_report(
    db: Session,
    actor: Actor,
    report_id: str,
    action: str,
    version: int,
    event_version: int,
    client_key: str,
    *,
    at: datetime | None = None,
) -> dict[str, Any]:
    if action not in REPORT_ACTION_STATUS:
        raise DomainError("event_report_action_invalid", "Choose an available report decision.", 422)
    timestamp = _timestamp(at)
    key = str(client_key)
    payload_hash = _payload_hash(
        {
            "action": action,
            "event_version": event_version,
            "report_id": report_id,
            "version": version,
        }
    )
    membership_policy.lock_client_key(db, actor.user_id, key)
    stub = db.execute(
        select(EventReport.event_id, EventReport.org_id).where(EventReport.id == report_id)
    ).first()
    if stub is None:
        raise _not_found("report")
    org_id, event_id = stub.org_id, stub.event_id
    sweep_expired_suspensions(db, org_id, timestamp)
    sweep_expired_reports(db, org_id=org_id, event_id=event_id, at=timestamp)
    event, _ = _lock_event_context(db, event_id)
    report = db.scalar(
        select(EventReport)
        .where(EventReport.id == report_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if report is None:
        raise _not_found("report")

    if report.stage == "organization":
        _require_staff(db, actor, report.org_id)
        if action not in ORG_REPORT_ACTIONS:
            raise DomainError(
                "event_report_action_forbidden",
                "Organization reviewers may dismiss or hide an event report.",
                403,
            )
    else:
        organization_service.require_platform_admin(db, actor)

    replay = _replay(db, actor.user_id, key, payload_hash)
    if replay is not None:
        return replay
    if report.status == "expired":
        return _report_review(db, report, timestamp)
    if report.status not in {"open", "escalated"} or report.deadline <= timestamp:
        raise _conflict("event_report_closed", "This event report is already closed.")
    if report.version != version:
        raise _conflict("event_report_version_conflict", "This event report has changed.")
    if _current_event_version(db, event) != event_version:
        raise _conflict(
            "event_report_event_version_conflict",
            "The event safety state changed while you were reviewing it.",
        )

    policy = __import__("app.core.event_safety", fromlist=["event_is_terminal"])
    control = _ensure_event_control(db, event.id)
    if action in {"hide", "remove"} and policy.event_is_terminal(db, event):
        raise _conflict("event_terminal", "This event has already been cancelled or removed.")
    previous = {
        "report_status": report.status,
        "report_version": report.version,
        "control": _control_values(control),
    }
    control_changed = False
    if report.stage == "organization" and control.org_reviewed_at is None:
        control.org_reviewed_at = timestamp
        control_changed = True
    if action == "hide":
        field = "org_hidden" if report.stage == "organization" else "platform_hidden"
        if not getattr(control, field):
            setattr(control, field, True)
            control_changed = True
    if action == "remove":
        control.removed = True
        control_changed = True
    if control_changed:
        control.version += 1

    report.status = REPORT_ACTION_STATUS[action]
    report.version += 1
    report.resolved_at = timestamp
    report.evidence = None
    audit = _audit(
        org_id=report.org_id,
        event_id=event.id,
        report_id=report.id,
        actor_id=actor.user_id,
        client_key=key,
        payload_hash=payload_hash,
        scope="report",
        action=action,
        version=report.version,
        at=timestamp,
        previous=previous,
        result={},
    )
    db.add(audit)
    db.flush()
    if action == "remove":
        from app.domains.registrations.service import cancel_event_participation_locked

        cancel_event_participation_locked(db, event, action_id=audit.id)
    _notify_reporter_resolution(db, report)
    result = _report_review(db, report, timestamp)
    audit.result = _json_ready(result)
    db.flush()
    return result


def _event_safety_out(
    db: Session,
    actor: Actor,
    event: Event,
    control: EventControl | None,
    *,
    at: datetime,
    platform_admin: bool | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    from app.core.event_safety import registration_is_available

    is_platform_admin = (
        _is_platform_admin(db, actor) if platform_admin is None else platform_admin
    )
    if role is None:
        membership = membership_policy.membership_for(db, event.org_id, actor.user_id)
        role = membership.role if membership is not None and membership.active else None
    channel = "platform_hidden" if is_platform_admin else "org_hidden"
    terminal = _terminal(db, event)
    return {
        "event_id": event.id,
        "org_id": event.org_id,
        "org_hidden": bool(control.org_hidden) if control else False,
        "platform_hidden": bool(control.platform_hidden) if control else False,
        "removed": bool(control.removed) if control else False,
        "cancelled": bool(control.cancelled) if control else False,
        "version": int(control.version) if control else 0,
        "registration_available": registration_is_available(db, event, at),
        "can_hide": bool(
            not terminal
            and event.status == "published"
            and not (getattr(control, channel) if control else False)
            and (is_platform_admin or role in {"owner", "admin", "moderator"})
        ),
        "can_restore": bool(
            not terminal
            and (getattr(control, channel) if control else False)
            and (is_platform_admin or role in {"owner", "admin", "moderator"})
        ),
        "can_remove": bool(is_platform_admin and not terminal),
        "can_cancel": bool(
            not terminal and event.status == "published" and role in {"owner", "admin"}
        ),
    }


def get_event_safety(
    db: Session, actor: Actor, event_id: str, *, at: datetime | None = None
) -> dict[str, Any]:
    timestamp = _timestamp(at)
    org_id = _event_org_id(db, event_id)
    sweep_expired_suspensions(db, org_id, timestamp)
    sweep_expired_reports(db, org_id=org_id, event_id=event_id, at=timestamp)
    event, _ = _lock_event_context(db, event_id)
    platform_admin = _require_staff_or_platform(db, actor, org_id)
    control = _event_control(db, event.id)
    return _event_safety_out(
        db, actor, event, control, at=timestamp, platform_admin=platform_admin
    )


def _cancel_event_participation(db: Session, event: Event, action_id: str) -> None:
    """The shared hook owns registration changes and cancellation notices."""
    from app.domains.registrations.service import cancel_event_participation_locked

    cancel_event_participation_locked(db, event, action_id=action_id)


def change_event_safety(
    db: Session,
    actor: Actor,
    event_id: str,
    action: str,
    version: int,
    client_key: str,
    *,
    at: datetime | None = None,
) -> dict[str, Any]:
    if action not in {"hide", "restore", "remove", "cancel"}:
        raise DomainError("event_safety_action_invalid", "Choose an available event action.", 422)
    timestamp = _timestamp(at)
    key = str(client_key)
    payload_hash = _payload_hash(
        {"action": action, "event_id": event_id, "version": version}
    )
    membership_policy.lock_client_key(db, actor.user_id, key)
    org_id = _event_org_id(db, event_id)
    sweep_expired_suspensions(db, org_id, timestamp)
    sweep_expired_reports(db, org_id=org_id, event_id=event_id, at=timestamp)
    event, org_id = _lock_event_context(db, event_id)

    platform_admin = False
    role = None
    if action in {"hide", "restore"}:
        platform_admin = _is_platform_admin(db, actor)
        if platform_admin:
            organization_service.get_organization(db, org_id)
        else:
            _, membership = membership_policy.require_staff(
                db, actor.user_id, org_id, lock=False
            )
            role = membership.role
    elif action == "remove":
        organization_service.require_platform_admin(db, actor)
        platform_admin = True
    else:
        _, membership = membership_policy.require_staff(
            db, actor.user_id, org_id, roles=("owner", "admin"), lock=False
        )
        role = membership.role

    replay = _replay(db, actor.user_id, key, payload_hash)
    if replay is not None:
        return replay
    control = _ensure_event_control(db, event.id)
    if control.version != version:
        raise _conflict("event_safety_version_conflict", "Event safety state has changed.")
    if _terminal(db, event):
        raise _conflict("event_terminal", "This event has already been cancelled or removed.")
    if action == "cancel" and event.status != "published":
        raise _conflict("event_cancel_unavailable", "Only a published event can be cancelled.")

    previous = _control_values(control)
    if action in {"hide", "restore"}:
        field = "platform_hidden" if platform_admin else "org_hidden"
        hidden = bool(getattr(control, field))
        if action == "hide" and hidden:
            raise _conflict("event_already_hidden", "This event is already hidden in your review channel.")
        if action == "restore" and not hidden:
            raise _conflict("event_not_hidden", "This event is not hidden in your review channel.")
        setattr(control, field, action == "hide")
    elif action == "remove":
        control.removed = True
    else:
        control.cancelled = True
    control.version += 1
    audit = _audit(
        org_id=org_id,
        event_id=event.id,
        actor_id=actor.user_id,
        client_key=key,
        payload_hash=payload_hash,
        scope="event",
        action=action,
        version=control.version,
        at=timestamp,
        previous=previous,
        result={},
    )
    db.add(audit)
    db.flush()
    if action in {"remove", "cancel"}:
        _cancel_event_participation(db, event, audit.id)
    result = _event_safety_out(
        db,
        actor,
        event,
        control,
        at=timestamp,
        platform_admin=platform_admin,
        role=role,
    )
    audit.result = _json_ready(result)
    db.flush()
    return result


def _suspension_out(
    org_id: str,
    suspension: OrganizationSuspension | None,
    at: datetime,
    *,
    can_manage: bool,
) -> dict[str, Any]:
    until = suspension.suspended_until if suspension else None
    return {
        "org_id": org_id,
        "version": int(suspension.version) if suspension else 0,
        "suspended_until": until,
        "is_suspended": until is not None and until > at,
        "can_manage": can_manage,
    }


def get_organization_suspension(
    db: Session, actor: Actor, org_id: str, *, at: datetime | None = None
) -> dict[str, Any]:
    timestamp = _timestamp(at)
    sweep_expired_suspensions(db, org_id, timestamp)
    organization_service.get_organization(db, org_id, lock=True)
    can_manage = _require_staff_or_platform(db, actor, org_id)
    suspension = db.scalar(
        select(OrganizationSuspension)
        .where(OrganizationSuspension.org_id == org_id)
        .execution_options(populate_existing=True)
    )
    return _suspension_out(org_id, suspension, timestamp, can_manage=can_manage)


def change_organization_suspension(
    db: Session,
    actor: Actor,
    org_id: str,
    action: str,
    version: int,
    days: int | None,
    client_key: str,
    *,
    at: datetime | None = None,
) -> dict[str, Any]:
    if action not in {"suspend", "resume"}:
        raise DomainError("organization_suspension_action_invalid", "Choose suspend or resume.", 422)
    if action == "resume" and days is not None:
        raise DomainError(
            "organization_suspension_days_invalid",
            "A resume request cannot include a suspension duration.",
            422,
        )
    organization_service.require_platform_admin(db, actor)
    timestamp = _timestamp(at)
    key = str(client_key)
    payload_hash = _payload_hash(
        {"action": action, "days": days, "org_id": org_id, "version": version}
    )
    membership_policy.lock_client_key(db, actor.user_id, key)
    sweep_expired_suspensions(db, org_id, timestamp)
    organization_service.get_organization(db, org_id, lock=True)
    organization_service.require_platform_admin(db, actor)
    suspension = db.scalar(
        select(OrganizationSuspension)
        .where(OrganizationSuspension.org_id == org_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    replay = _replay(db, actor.user_id, key, payload_hash)
    if replay is not None:
        return replay
    if (
        action == "resume"
        and suspension is not None
        and suspension.suspended_until is None
        and version == suspension.version - 1
    ):
        expiry = db.scalar(
            select(SafetyAudit)
            .where(
                SafetyAudit.org_id == org_id,
                SafetyAudit.scope == "organization",
                SafetyAudit.action == "expire",
                SafetyAudit.version == suspension.version,
            )
            .order_by(SafetyAudit.created_at.desc(), SafetyAudit.id.desc())
        )
        if expiry is not None:
            result = _suspension_out(org_id, suspension, timestamp, can_manage=True)
            db.add(
                _audit(
                    org_id=org_id,
                    actor_id=actor.user_id,
                    client_key=key,
                    payload_hash=payload_hash,
                    scope="organization",
                    action="resume",
                    version=suspension.version,
                    at=timestamp,
                    previous={
                        "version": version,
                        "suspended_until": expiry.previous.get("suspended_until"),
                    },
                    result=result,
                )
            )
            db.flush()
            return result
    if suspension is None:
        if action == "resume":
            raise _conflict("organization_not_suspended", "This organization is not suspended.")
        suspension = OrganizationSuspension(org_id=org_id)
        db.add(suspension)
        db.flush()
    if suspension.version != version:
        raise _conflict("organization_suspension_version_conflict", "Suspension state has changed.")

    previous = {
        "version": suspension.version,
        "suspended_until": suspension.suspended_until,
    }
    if action == "suspend":
        days = SUSPENSION_DEFAULT_DAYS if days is None else days
        if not 1 <= days <= 30:
            raise DomainError("organization_suspension_days_invalid", "Choose a duration from 1 to 30 days.", 422)
        suspension.suspended_until = timestamp + timedelta(days=days)
        message = "Your organization has been temporarily suspended from publishing new events."
    else:
        if suspension.suspended_until is None or suspension.suspended_until <= timestamp:
            raise _conflict("organization_not_suspended", "This organization is not suspended.")
        suspension.suspended_until = None
        message = "The organization safety suspension has ended."
    suspension.version += 1
    result = _suspension_out(org_id, suspension, timestamp, can_manage=True)
    audit = _audit(
        org_id=org_id,
        actor_id=actor.user_id,
        client_key=key,
        payload_hash=payload_hash,
        scope="organization",
        action=action,
        version=suspension.version,
        at=timestamp,
        previous=previous,
        result=result,
    )
    db.add(audit)
    _notify_org_safety(db, org_id, suspension.version, message)
    db.flush()
    return result


def get_safety_history(
    db: Session, actor: Actor, org_id: str
) -> list[dict[str, Any]]:
    organization_service.get_organization(db, org_id, lock=True)
    _require_staff_or_platform(db, actor, org_id)
    audits = db.scalars(
        select(SafetyAudit)
        .where(SafetyAudit.org_id == org_id)
        .order_by(SafetyAudit.created_at.desc(), SafetyAudit.id.desc())
        .limit(100)
    )
    return [
        {
            "id": audit.id,
            "org_id": audit.org_id,
            "event_id": audit.event_id,
            "report_id": audit.report_id,
            "actor_id": audit.actor_id,
            "scope": audit.scope,
            "action": audit.action,
            "version": audit.version,
            "created_at": audit.created_at,
        }
        for audit in audits
    ]
