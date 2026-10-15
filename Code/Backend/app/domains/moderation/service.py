"""Transactional report review, evidence retention, and per-user content hides."""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.contracts import Actor
from app.core.errors import DomainError
from app.core.membership_access import unrevoked_registration
from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.moderation.models import ContentHide, ContentReport, ReportDecision
from app.domains.organizations.models import OrgMembership


ACTIVE_REPORT_STATUSES = ('open', 'escalated')
ORG_REVIEW_DAYS = 7
PLATFORM_REVIEW_DAYS = 14
CHAT_RETENTION_HOURS = 72
ORG_STAFF_ROLES = ('owner', 'admin', 'moderator')


def _require_eligible(actor: Actor) -> None:
    if not actor.eligible:
        raise DomainError('plm_email_required', 'A verified PLM email address is required.', 403)


def _lock_event(db: Session, event_id: str) -> Event:
    event = db.scalar(
        select(Event)
        .where(Event.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise DomainError('event_not_found', 'Event was not found.', 404)
    return event


def _lock_user(db: Session, user_id: str):
    from app.domains.identity.models import User

    user = db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise DomainError('report_subject_not_found', 'The reported person could not be verified.', 404)
    return user


def _require_org_staff(db: Session, actor: Actor, org_id: str) -> None:
    _require_eligible(actor)
    membership = db.scalar(select(OrgMembership.id).where(
        OrgMembership.org_id == org_id,
        OrgMembership.user_id == actor.user_id,
        OrgMembership.active.is_(True),
        OrgMembership.role.in_(ORG_STAFF_ROLES),
    ))
    if membership is None:
        raise DomainError('moderation_forbidden', 'Organization moderation access is required.', 403)


def _require_platform_admin(db: Session, actor: Actor) -> None:
    from app.domains.organizations.service import require_platform_admin

    require_platform_admin(db, actor)


def _require_stage_access(db: Session, actor: Actor, report: ContentReport) -> None:
    if report.stage == 'platform':
        _require_platform_admin(db, actor)
    else:
        _require_org_staff(db, actor, report.org_id)


def _active_report(
    db: Session,
    reporter_id: str,
    kind: str,
    target_id: str,
    *,
    lock: bool,
) -> ContentReport | None:
    statement = select(ContentReport).where(
        ContentReport.reporter_id == reporter_id,
        ContentReport.kind == kind,
        ContentReport.target_id == target_id,
        ContentReport.status.in_(ACTIVE_REPORT_STATUSES),
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return db.scalar(statement.order_by(ContentReport.created_at, ContentReport.id))


def _hidden_for(db: Session, user_id: str, kind: str, target_id: str) -> bool:
    from app.core.communication import is_locally_hidden

    return is_locally_hidden(db, user_id, kind, target_id)


def _visible_comment(db: Session, event_id: str, target_id: str, viewer_id: str):
    from app.domains.social.models import EventComment

    comment = db.scalar(select(EventComment).where(
        EventComment.id == target_id,
        EventComment.event_id == event_id,
        EventComment.body.is_not(None),
        EventComment.removed_at.is_(None),
    ))
    if comment is None or _hidden_for(db, viewer_id, 'comment', target_id):
        return None
    return comment


def _visible_message(db: Session, event_id: str, target_id: str, viewer_id: str):
    from app.domains.chat.models import ChatMessage

    message = db.scalar(select(ChatMessage).where(
        ChatMessage.id == target_id,
        ChatMessage.event_id == event_id,
        ChatMessage.body.is_not(None),
        ChatMessage.removed_at.is_(None),
    ))
    if message is None or _hidden_for(db, viewer_id, 'message', target_id):
        return None
    return message


def _confirmed_chat_access(db: Session, event: Event, user_id: str, at: datetime) -> bool:
    if event.status != 'published' or event.ends_at is None:
        return False
    if at >= event.ends_at + timedelta(hours=CHAT_RETENTION_HOURS):
        return False

    from app.domains.registrations.models import Registration

    return db.scalar(select(Registration.id).where(
        Registration.event_id == event.id,
        Registration.user_id == user_id,
        Registration.status == 'confirmed',
        unrevoked_registration(),
    )) is not None


def _visible_person_evidence(
    db: Session,
    event: Event,
    author_id: str,
    viewer_id: str,
    at: datetime,
) -> str | None:
    # A person target is discoverable only through content visible in this event.
    from app.domains.social.models import EventComment

    comments = db.scalars(select(EventComment).where(
        EventComment.event_id == event.id,
        EventComment.author_id == author_id,
        EventComment.body.is_not(None),
        EventComment.removed_at.is_(None),
    ).order_by(EventComment.sequence, EventComment.id))
    for comment in comments:
        if not _hidden_for(db, viewer_id, 'comment', comment.id):
            return comment.body

    if not _confirmed_chat_access(db, event, viewer_id, at):
        return None
    from app.domains.chat.models import ChatMessage

    messages = db.scalars(select(ChatMessage).where(
        ChatMessage.event_id == event.id,
        ChatMessage.author_id == author_id,
        ChatMessage.body.is_not(None),
        ChatMessage.removed_at.is_(None),
    ).order_by(ChatMessage.sequence, ChatMessage.id))
    for message in messages:
        if not _hidden_for(db, viewer_id, 'message', message.id):
            return message.body
    return None


def _receipt(report: ContentReport) -> dict:
    return {
        'id': report.id,
        'event_id': report.event_id,
        'kind': report.kind,
        'target_id': report.target_id,
        'status': report.status,
        'stage': report.stage,
        'deadline': report.deadline,
    }


def _eligible_platform_reviewer_ids(db: Session) -> list[str]:
    from app.domains.identity.models import User
    from app.domains.identity.service import email_is_eligible

    rows = db.execute(select(User.id, User.email, User.email_verified).where(
        User.active.is_(True), User.platform_admin.is_(True),
    )).all()
    return [row.id for row in rows if email_is_eligible(row.email, row.email_verified)]


def _eligible_org_reviewer_ids(db: Session, org_id: str) -> list[str]:
    from app.domains.identity.models import User
    from app.domains.identity.service import email_is_eligible

    rows = db.execute(
        select(User.id, User.email, User.email_verified)
        .join(OrgMembership, OrgMembership.user_id == User.id)
        .where(
            OrgMembership.org_id == org_id,
            OrgMembership.active.is_(True),
            OrgMembership.role.in_(ORG_STAFF_ROLES),
            User.active.is_(True),
        )
    ).all()
    return [row.id for row in rows if email_is_eligible(row.email, row.email_verified)]


def _notify_transition(
    db: Session,
    report: ContentReport,
    *,
    transition: str,
    reviewer_stage: str,
    reporter_message: str,
    subject_message: str,
    reviewer_message: str,
) -> None:
    from app.notifications import notify_in_app

    recipients = {
        report.reporter_id: reporter_message,
        report.subject_user_id: subject_message,
    }
    reviewer_ids = (
        _eligible_platform_reviewer_ids(db)
        if reviewer_stage == 'platform'
        else _eligible_org_reviewer_ids(db, report.org_id)
    )
    for reviewer_id in reviewer_ids:
        recipients.setdefault(reviewer_id, reviewer_message)

    for user_id, message in recipients.items():
        notify_in_app(
            db,
            user_id=user_id,
            event_id=report.event_id,
            kind='safety_report',
            message=message,
            dedupe_key=f'content_report:{report.id}:{transition}:{user_id}',
        )


def create_report(
    db: Session,
    actor: Actor,
    event_id: str,
    kind: str,
    target_id: str,
    reason: str,
    *,
    at: datetime | None = None,
) -> dict:
    _require_eligible(actor)
    if kind not in {'comment', 'message', 'person'}:
        raise DomainError('report_kind_invalid', 'Choose a comment, message, or person report.', 422)
    if reason not in {'harassment', 'spam', 'deception', 'impersonation', 'other'}:
        raise DomainError('report_reason_invalid', 'Choose an available report reason.', 422)

    event = _lock_event(db, event_id)
    if event.status != 'published':
        raise DomainError('event_not_found', 'Event was not found.', 404)

    # Recovery reads the caller's existing receipt; hiding/removing its evidence
    # must not make an already-admitted report look like a failed submission.
    validation_time = at if at is not None else now()
    if kind == 'message' and not _confirmed_chat_access(db, event, actor.user_id, validation_time):
        raise DomainError('chat_access_forbidden', 'Confirmed event chat access is required to report a message.', 403)
    existing = _active_report(db, actor.user_id, kind, target_id, lock=True)
    if existing is not None:
        return _receipt(existing)

    if kind == 'person':
        validation_time = at if at is not None else now()
        evidence = _visible_person_evidence(db, event, target_id, actor.user_id, validation_time)
        if evidence is None:
            raise DomainError('report_target_not_visible', 'The reported person must appear in visible event content.', 404)
        if target_id == actor.user_id:
            raise DomainError('self_report_forbidden', 'You cannot report your own account.', 403)
        _lock_user(db, target_id)
        existing = _active_report(db, actor.user_id, kind, target_id, lock=True)
        timestamp = at if at is not None else now()
        evidence = _visible_person_evidence(db, event, target_id, actor.user_id, timestamp)
        if evidence is None:
            raise DomainError('report_target_not_visible', 'The reported person must appear in visible event content.', 404)
        if existing is not None:
            return _receipt(existing)
        stage = 'platform'
        deadline = timestamp + timedelta(days=PLATFORM_REVIEW_DAYS)
        subject_user_id = target_id
    else:
        validation_time = at if at is not None else now()
        if kind == 'message' and not _confirmed_chat_access(db, event, actor.user_id, validation_time):
            raise DomainError('chat_access_forbidden', 'Confirmed event chat access is required to report a message.', 403)
        item = (
            _visible_comment(db, event.id, target_id, actor.user_id)
            if kind == 'comment'
            else _visible_message(db, event.id, target_id, actor.user_id)
        )
        if item is None:
            raise DomainError('report_target_not_visible', 'The reported content was not found or is unavailable.', 404)
        if item.author_id == actor.user_id:
            raise DomainError('self_report_forbidden', 'You cannot report your own content.', 403)
        evidence = item.body
        subject_user_id = item.author_id
        existing = _active_report(db, actor.user_id, kind, target_id, lock=True)
        timestamp = at if at is not None else now()
        if kind == 'message' and not _confirmed_chat_access(db, event, actor.user_id, timestamp):
            raise DomainError('chat_access_forbidden', 'Confirmed event chat access is required to report a message.', 403)
        if existing is not None:
            return _receipt(existing)
        stage = 'organization'
        deadline = timestamp + timedelta(days=ORG_REVIEW_DAYS)

    report = ContentReport(
        id=uid(),
        event_id=event.id,
        org_id=event.org_id,
        reporter_id=actor.user_id,
        subject_user_id=subject_user_id,
        kind=kind,
        target_id=target_id,
        reason=reason,
        status='open',
        stage=stage,
        evidence=evidence,
        created_at=timestamp,
        deadline=deadline,
    )
    try:
        with db.begin_nested():
            db.add(report)
            db.flush()
    except IntegrityError:
        # The partial unique index is the final guard for retries racing across events.
        existing = _active_report(db, actor.user_id, kind, target_id, lock=True)
        if existing is not None:
            return _receipt(existing)
        raise DomainError('report_conflict', 'A report for this target could not be created.', 409)

    _notify_transition(
        db,
        report,
        transition='received',
        reviewer_stage=stage,
        reporter_message='Your safety report was received.',
        subject_message='A safety report involving you or content you authored is under review.',
        reviewer_message='A safety report requires review.',
    )
    db.flush()
    return _receipt(report)


def list_my_reports(db: Session, user_id: str) -> list[dict]:
    reports = db.scalars(select(ContentReport).where(
        ContentReport.reporter_id == user_id,
    ).order_by(ContentReport.created_at.desc(), ContentReport.id))
    return [_receipt(report) for report in reports]


def set_content_hide(
    db: Session,
    actor: Actor,
    event_id: str,
    kind: str,
    target_id: str,
    hidden: bool,
    *,
    at: datetime | None = None,
) -> dict:
    event = _lock_event(db, event_id)
    if event.status != 'published':
        raise DomainError('event_not_found', 'Event was not found.', 404)
    if kind not in {'comment', 'message'}:
        raise DomainError('hide_kind_invalid', 'Only comments and messages can be hidden.', 422)

    validation_time = at if at is not None else now()
    if kind == 'comment':
        from app.domains.social.models import EventComment

        target = db.scalar(select(EventComment.id).where(
            EventComment.id == target_id,
            EventComment.event_id == event.id,
        ))
    else:
        if not _confirmed_chat_access(db, event, actor.user_id, validation_time):
            raise DomainError('chat_access_forbidden', 'Confirmed event chat access is required.', 403)
        from app.domains.chat.models import ChatMessage

        target = db.scalar(select(ChatMessage.id).where(
            ChatMessage.id == target_id,
            ChatMessage.event_id == event.id,
        ))
    if target is None:
        raise DomainError('content_not_found', 'Content was not found or is unavailable.', 404)

    hide = db.scalar(select(ContentHide).where(
        ContentHide.user_id == actor.user_id,
        ContentHide.kind == kind,
        ContentHide.target_id == target_id,
    ).with_for_update())
    timestamp = at if at is not None else now()
    if kind == 'message' and not _confirmed_chat_access(db, event, actor.user_id, timestamp):
        raise DomainError('chat_access_forbidden', 'Confirmed event chat access is required.', 403)
    if hidden:
        if hide is None:
            db.add(ContentHide(
                id=uid(),
                user_id=actor.user_id,
                event_id=event.id,
                kind=kind,
                target_id=target_id,
                created_at=timestamp,
            ))
    elif hide is not None:
        if hide.event_id != event.id:
            raise DomainError('content_not_found', 'Content was not found or is unavailable.', 404)
        db.delete(hide)
    db.flush()
    return {'hidden': hidden}


def _reviewer_stage_for_list(db: Session, actor: Actor, org_id: str | None) -> tuple[str, str | None]:
    if org_id is not None and actor.eligible:
        membership = db.scalar(select(OrgMembership.id).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == actor.user_id,
            OrgMembership.active.is_(True),
            OrgMembership.role.in_(ORG_STAFF_ROLES),
        ))
        if membership is not None:
            return 'organization', org_id
    _require_platform_admin(db, actor)
    return 'platform', org_id


def _review_payloads(db: Session, reports: list[ContentReport], at: datetime) -> list[dict]:
    if not reports:
        return []
    report_ids = [report.id for report in reports]
    decisions_by_report: dict[str, list[dict]] = {report_id: [] for report_id in report_ids}
    decisions = db.scalars(select(ReportDecision).where(
        ReportDecision.report_id.in_(report_ids),
    ).order_by(ReportDecision.created_at, ReportDecision.id))
    for decision in decisions:
        decisions_by_report[decision.report_id].append({
            'id': decision.id,
            'reviewer_id': decision.reviewer_id,
            'action': decision.action,
            'created_at': decision.created_at,
        })

    results = []
    for report in reports:
        result = _receipt(report)
        result.update({
            'org_id': report.org_id,
            'reason': report.reason,
            'reporter_id': report.reporter_id,
            'subject_user_id': report.subject_user_id,
            'evidence': (
                report.evidence
                if report.status in ACTIVE_REPORT_STATUSES and report.deadline > at
                else None
            ),
            'decisions': decisions_by_report[report.id],
        })
        results.append(result)
    return results


def list_moderation_reports(db: Session, actor: Actor, org_id: str | None = None) -> list[dict]:
    stage, scoped_org_id = _reviewer_stage_for_list(db, actor, org_id)
    statement = select(ContentReport).where(ContentReport.stage == stage)
    if scoped_org_id is not None:
        statement = statement.where(ContentReport.org_id == scoped_org_id)
    reports = list(db.scalars(statement.order_by(
        ContentReport.deadline, ContentReport.created_at, ContentReport.id,
    )))
    return _review_payloads(db, reports, now())


def get_moderation_report(db: Session, actor: Actor, report_id: str, *, at: datetime | None = None) -> dict:
    report = db.get(ContentReport, report_id)
    if report is None:
        raise DomainError('report_not_found', 'Report was not found.', 404)
    _require_stage_access(db, actor, report)
    return _review_payloads(db, [report], at or now())[0]


def decide_report(
    db: Session,
    actor: Actor,
    report_id: str,
    action: str,
    *,
    at: datetime | None = None,
) -> dict:
    stub = db.execute(select(
        ContentReport.event_id,
        ContentReport.kind,
        ContentReport.subject_user_id,
    ).where(ContentReport.id == report_id)).first()
    if stub is None:
        raise DomainError('report_not_found', 'Report was not found.', 404)

    # Mutations always lock event, then the affected person if this is a personal
    # report, then report and content rows.
    _lock_event(db, stub.event_id)
    if stub.kind == 'person':
        _lock_user(db, stub.subject_user_id)
    report = db.scalar(select(ContentReport).where(
        ContentReport.id == report_id,
    ).with_for_update().execution_options(populate_existing=True))
    if report is None:
        raise DomainError('report_not_found', 'Report was not found.', 404)
    timestamp = at if at is not None else now()
    _require_stage_access(db, actor, report)

    terminal_status = {
        'dismiss': 'dismissed',
        'remove': 'removed',
        'warn': 'warned',
    }
    if report.status in {'dismissed', 'removed', 'warned', 'expired'}:
        if terminal_status.get(action) == report.status:
            return _review_payloads(db, [report], timestamp)[0]
        raise DomainError('report_decision_conflict', 'This report already has a different final decision.', 409)
    if action not in {'dismiss', 'remove', 'escalate', 'warn'}:
        raise DomainError('report_decision_invalid', 'Choose an available report decision.', 422)
    if report.deadline <= timestamp:
        raise DomainError('report_deadline_expired', 'This report review deadline has passed.', 409)

    is_person = report.kind == 'person'
    if is_person and action not in {'dismiss', 'warn'}:
        raise DomainError('report_decision_invalid', 'Personal reports may only be dismissed or warned.', 422)
    if not is_person and action == 'warn':
        raise DomainError('report_decision_invalid', 'Content reports may only be dismissed, removed, or escalated.', 422)
    if action == 'escalate' and report.stage != 'organization':
        raise DomainError('report_decision_conflict', 'Only organization-stage content reports can be escalated.', 409)

    if action == 'escalate':
        report.stage = 'platform'
        report.status = 'escalated'
        report.deadline = timestamp + timedelta(days=PLATFORM_REVIEW_DAYS)
        transition = 'escalated'
        reviewer_stage = 'platform'
        reporter_message = 'A safety report was escalated for platform review.'
        subject_message = 'A safety report involving you or content you authored is under platform review.'
        reviewer_message = 'A safety report requires platform review.'
    else:
        if action == 'remove':
            if report.kind == 'comment':
                from app.domains.social.service import remove_comment_locked

                remove_comment_locked(db, report.target_id, report.event_id, timestamp)
            elif report.kind == 'message':
                from app.domains.chat.service import remove_message_locked

                remove_message_locked(db, report.target_id, report.event_id, timestamp)
        report.status = terminal_status[action]
        report.resolved_at = timestamp
        report.evidence = None
        transition = report.status
        reviewer_stage = report.stage
        if action == 'warn':
            reporter_message = 'A safety report was resolved.'
            subject_message = 'A safety warning was issued after review.'
        else:
            reporter_message = 'A safety report was resolved.'
            subject_message = 'A safety review involving you or your content was closed.'
        reviewer_message = 'A safety report review was completed.'

    db.add(ReportDecision(
        id=uid(),
        report_id=report.id,
        reviewer_id=actor.user_id,
        action=action,
        created_at=timestamp,
    ))
    _notify_transition(
        db,
        report,
        transition=transition,
        reviewer_stage=reviewer_stage,
        reporter_message=reporter_message,
        subject_message=subject_message,
        reviewer_message=reviewer_message,
    )
    db.flush()
    return _review_payloads(db, [report], timestamp)[0]


def has_pending_person_report(db: Session, user_id: str, at: datetime | None = None) -> bool:
    """Read-only restriction hook; expired cases stop restricting at their deadline."""
    timestamp = at or now()
    return db.scalar(select(ContentReport.id).where(
        ContentReport.subject_user_id == user_id,
        ContentReport.kind == 'person',
        ContentReport.stage == 'platform',
        ContentReport.status.in_(ACTIVE_REPORT_STATUSES),
        ContentReport.deadline > timestamp,
    ).limit(1)) is not None


def catch_up_reports_locked(db: Session, event: Event, at: datetime | None = None) -> int:
    """Apply durable report deadlines while the caller holds the event row lock."""
    reports = list(db.scalars(select(ContentReport).where(
        ContentReport.event_id == event.id,
        ContentReport.status.in_(ACTIVE_REPORT_STATUSES),
    ).order_by(ContentReport.deadline, ContentReport.id).with_for_update()))
    timestamp = at if at is not None else now()
    reports = [report for report in reports if report.deadline <= timestamp]
    transitions = 0

    for report in reports:
        if report.stage == 'organization':
            report.stage = 'platform'
            report.status = 'escalated'
            report.deadline = report.deadline + timedelta(days=PLATFORM_REVIEW_DAYS)
            db.add(ReportDecision(
                id=uid(), report_id=report.id, reviewer_id=None,
                action='escalate', created_at=timestamp,
            ))
            _notify_transition(
                db,
                report,
                transition='escalated',
                reviewer_stage='platform',
                reporter_message='A safety report was escalated for platform review.',
                subject_message='A safety report involving you or content you authored is under platform review.',
                reviewer_message='A safety report requires platform review.',
            )
            transitions += 1

        if report.stage == 'platform' and report.status in ACTIVE_REPORT_STATUSES and report.deadline <= timestamp:
            report.status = 'expired'
            report.resolved_at = timestamp
            report.evidence = None
            db.add(ReportDecision(
                id=uid(), report_id=report.id, reviewer_id=None,
                action='expire', created_at=timestamp,
            ))
            _notify_transition(
                db,
                report,
                transition='expired',
                reviewer_stage='platform',
                reporter_message='A safety report was closed after its review window.',
                subject_message='A safety review involving you or your content was closed after its review window.',
                reviewer_message='A safety report reached its review deadline.',
            )
            transitions += 1

    if transitions:
        db.flush()
    return transitions
