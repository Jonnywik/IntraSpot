import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.announcements.models import Announcement
from app.domains.announcements.moderation_models import (
    AnnouncementReport,
    AnnouncementReportDecision,
)
from app.domains.moderation.service import PLATFORM_REVIEW_DAYS
from app.domains.organizations.service import get_organization, require_platform_admin


REPORT_REASONS = {'harassment', 'spam', 'deception', 'impersonation', 'other'}
DECISION_ACTIONS = {'dismiss', 'hide', 'restore', 'remove'}


def _not_found() -> DomainError:
    return DomainError('announcement_not_found', 'Announcement was not found.', 404)


def _receipt(report: AnnouncementReport) -> dict:
    return {
        'id': report.id,
        'announcement_id': report.announcement_id,
        'org_id': report.org_id,
        'status': report.status,
        'deadline': report.deadline,
    }


def _lock_announcement(db: Session, org_id: str, announcement_id: str) -> Announcement:
    get_organization(db, org_id, lock=True)
    announcement = db.scalar(
        select(Announcement)
        .where(Announcement.id == announcement_id, Announcement.org_id == org_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if announcement is None:
        raise _not_found()
    return announcement


def _announcement_org_id(db: Session, announcement_id: str) -> str:
    org_id = db.scalar(select(Announcement.org_id).where(Announcement.id == announcement_id))
    if org_id is None:
        raise _not_found()
    return org_id


def _active_report(
    db: Session,
    reporter_id: str,
    announcement_id: str,
    *,
    lock: bool,
) -> AnnouncementReport | None:
    statement = select(AnnouncementReport).where(
        AnnouncementReport.reporter_id == reporter_id,
        AnnouncementReport.announcement_id == announcement_id,
        AnnouncementReport.status == 'open',
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return db.scalar(statement.order_by(AnnouncementReport.created_at, AnnouncementReport.id))


def _notify_transition(db: Session, report: AnnouncementReport, transition: str) -> None:
    from app.domains.moderation.service import _eligible_platform_reviewer_ids
    from app.notifications import notify_in_app

    messages = {
        'received': (
            'Your announcement safety report was received.',
            'An announcement you authored is under platform safety review.',
            'An announcement safety report requires platform review.',
        ),
        'dismissed': (
            'Your announcement safety report was resolved.',
            'A safety review of an announcement you authored was closed.',
            'An announcement safety review was completed.',
        ),
        'hidden': (
            'Your announcement safety report was resolved.',
            'An announcement you authored was hidden after review.',
            'An announcement safety review was completed.',
        ),
        'restored': (
            'Your announcement safety report was resolved.',
            'An announcement you authored was restored after review.',
            'An announcement safety review was completed.',
        ),
        'removed': (
            'Your announcement safety report was resolved.',
            'An announcement you authored was removed after review.',
            'An announcement safety review was completed.',
        ),
        'expired': (
            'Your announcement safety report review window ended.',
            'A safety review involving an announcement you authored has ended.',
            'An announcement safety review window ended.',
        ),
    }
    reporter_message, subject_message, reviewer_message = messages[transition]
    recipients = {
        report.reporter_id: reporter_message,
        report.subject_user_id: subject_message,
    }
    for reviewer_id in _eligible_platform_reviewer_ids(db):
        recipients.setdefault(reviewer_id, reviewer_message)

    for user_id, message in recipients.items():
        notify_in_app(
            db,
            user_id=user_id,
            org_id=report.org_id,
            kind='safety_report',
            message=message,
            dedupe_key=f'announcement_report:{report.id}:{transition}:{user_id}',
        )


def create_announcement_report(
    db: Session,
    actor: Actor,
    announcement_id: str,
    reason: str,
    *,
    at: datetime | None = None,
) -> dict:
    if reason not in REPORT_REASONS:
        raise DomainError('report_reason_invalid', 'Choose an available report reason.', 422)

    org_id = _announcement_org_id(db, announcement_id)
    announcement = _lock_announcement(db, org_id, announcement_id)

    # Receipt recovery is private to the reporter and remains available after
    # membership loss, hiding, or removal. It never returns evidence.
    existing = _active_report(db, actor.user_id, announcement_id, lock=True)
    if existing is not None:
        return _receipt(existing)

    if not actor.eligible:
        raise DomainError('plm_email_required', 'A verified PLM email address is required.', 403)

    from app.domains.announcements.service import get_readable_announcement

    announcement = get_readable_announcement(db, announcement_id, actor, lock=True)
    if announcement.created_by == actor.user_id:
        raise DomainError('self_report_forbidden', 'You cannot report your own announcement.', 403)

    timestamp = at if at is not None else now()
    evidence = json.dumps(
        {'title': announcement.title, 'body': announcement.body},
        ensure_ascii=False,
        separators=(',', ':'),
    )
    report = AnnouncementReport(
        id=uid(),
        announcement_id=announcement.id,
        org_id=announcement.org_id,
        reporter_id=actor.user_id,
        subject_user_id=announcement.created_by,
        reason=reason,
        status='open',
        reported_version=announcement.version,
        evidence=evidence,
        created_at=timestamp,
        deadline=timestamp + timedelta(days=PLATFORM_REVIEW_DAYS),
    )
    try:
        with db.begin_nested():
            db.add(report)
            db.flush()
    except IntegrityError:
        existing = _active_report(db, actor.user_id, announcement_id, lock=True)
        if existing is not None:
            return _receipt(existing)
        raise DomainError('report_conflict', 'The announcement report could not be created.', 409)

    _notify_transition(db, report, 'received')
    db.flush()
    return _receipt(report)


def list_my_announcement_reports(db: Session, user_id: str) -> list[dict]:
    reports = db.scalars(
        select(AnnouncementReport)
        .where(AnnouncementReport.reporter_id == user_id)
        .order_by(AnnouncementReport.created_at.desc(), AnnouncementReport.id)
    )
    return [_receipt(report) for report in reports]


def _post_state(announcement: Announcement) -> str:
    if announcement.removed_at is not None:
        return 'removed'
    if announcement.hidden_at is not None:
        return 'hidden'
    return 'visible'


def _review_payloads(db: Session, reports: list[AnnouncementReport], at: datetime) -> list[dict]:
    if not reports:
        return []

    report_ids = [report.id for report in reports]
    announcement_ids = {report.announcement_id for report in reports}
    announcements = db.scalars(
        select(Announcement)
        .where(Announcement.id.in_(announcement_ids))
        .execution_options(populate_existing=True)
    )
    announcements_by_id = {announcement.id: announcement for announcement in announcements}

    decisions_by_report: dict[str, list[dict]] = {report_id: [] for report_id in report_ids}
    decisions = db.scalars(
        select(AnnouncementReportDecision)
        .where(AnnouncementReportDecision.report_id.in_(report_ids))
        .order_by(AnnouncementReportDecision.created_at, AnnouncementReportDecision.id)
    )
    for decision in decisions:
        decisions_by_report[decision.report_id].append({
            'id': decision.id,
            'reviewer_id': decision.reviewer_id,
            'action': decision.action,
            'created_at': decision.created_at,
        })

    results = []
    for report in reports:
        announcement = announcements_by_id.get(report.announcement_id)
        if announcement is None:
            continue
        result = _receipt(report)
        result.update({
            'reason': report.reason,
            'reporter_id': report.reporter_id,
            'subject_user_id': report.subject_user_id,
            'reported_version': report.reported_version,
            'evidence': (
                report.evidence
                if report.status == 'open' and report.deadline > at
                else None
            ),
            'decisions': decisions_by_report[report.id],
            'post_state': _post_state(announcement),
            'post_version': announcement.version,
        })
        results.append(result)
    return results


def list_announcement_moderation_reports(
    db: Session,
    actor: Actor,
    *,
    at: datetime | None = None,
) -> list[dict]:
    require_platform_admin(db, actor)
    reports = list(db.scalars(
        select(AnnouncementReport).order_by(
            AnnouncementReport.deadline,
            AnnouncementReport.created_at,
            AnnouncementReport.id,
        )
    ))
    return _review_payloads(db, reports, at if at is not None else now())


def get_announcement_moderation_report(
    db: Session,
    actor: Actor,
    report_id: str,
    *,
    at: datetime | None = None,
) -> dict:
    require_platform_admin(db, actor)
    report = db.get(AnnouncementReport, report_id)
    if report is None:
        raise DomainError('report_not_found', 'Announcement report was not found.', 404)
    return _review_payloads(db, [report], at if at is not None else now())[0]


def _lock_report_context(
    db: Session,
    report_id: str,
) -> tuple[Announcement, AnnouncementReport]:
    stub = db.execute(
        select(AnnouncementReport.announcement_id, AnnouncementReport.org_id)
        .where(AnnouncementReport.id == report_id)
    ).first()
    if stub is None:
        raise DomainError('report_not_found', 'Announcement report was not found.', 404)

    announcement = _lock_announcement(db, stub.org_id, stub.announcement_id)
    report = db.scalar(
        select(AnnouncementReport)
        .where(AnnouncementReport.id == report_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if report is None:
        raise DomainError('report_not_found', 'Announcement report was not found.', 404)
    return announcement, report


def decide_announcement_report(
    db: Session,
    actor: Actor,
    report_id: str,
    action: str,
    *,
    expected_version: int | None = None,
    at: datetime | None = None,
) -> dict:
    require_platform_admin(db, actor)
    if action not in DECISION_ACTIONS:
        raise DomainError('report_decision_invalid', 'Choose an available announcement report decision.', 422)
    if action in {'hide', 'restore', 'remove'} and (expected_version is None or expected_version < 1):
        raise DomainError('announcement_version_required', 'A current announcement version is required.', 409)

    announcement, report = _lock_report_context(db, report_id)
    timestamp = at if at is not None else now()
    action_status = {
        'dismiss': 'dismissed',
        'hide': 'hidden',
        'restore': 'restored',
        'remove': 'removed',
    }[action]

    if report.status == action_status:
        return _review_payloads(db, [report], timestamp)[0]

    if report.status == 'open':
        if report.deadline <= timestamp:
            raise DomainError('report_deadline_expired', 'This announcement report deadline has passed.', 409)
        if action == 'restore':
            raise DomainError('report_decision_conflict', 'Only the case that hid an announcement can restore it.', 409)
    elif report.status == 'hidden':
        if action not in {'restore', 'remove'}:
            raise DomainError('report_decision_conflict', 'This announcement report already has a different final decision.', 409)
        if action == 'restore' and (announcement.hidden_at is None or announcement.removed_at is not None):
            raise DomainError('report_decision_conflict', 'This hidden announcement can no longer be restored.', 409)
    else:
        raise DomainError('report_decision_conflict', 'This announcement report already has a different final decision.', 409)

    if action in {'hide', 'restore', 'remove'} and announcement.version != expected_version:
        raise DomainError('announcement_version_conflict', 'The announcement changed while you were reviewing it.', 409)

    if action == 'hide':
        if announcement.removed_at is not None:
            raise DomainError('report_decision_conflict', 'A removed announcement cannot be hidden.', 409)
        if announcement.hidden_at is not None:
            raise DomainError('report_decision_conflict', 'This announcement is already hidden by another review.', 409)
        announcement.hidden_at = timestamp
        announcement.version += 1
        announcement.updated_at = timestamp
        from app.domains.announcements.service import record_revision

        record_revision(db, announcement, actor.user_id, 'hide', timestamp)
    elif action == 'restore':
        announcement.hidden_at = None
        announcement.version += 1
        announcement.updated_at = timestamp
        from app.domains.announcements.service import record_revision

        record_revision(db, announcement, actor.user_id, 'restore', timestamp)
    elif action == 'remove':
        if announcement.removed_at is None:
            announcement.body = None
            announcement.removed_at = timestamp
            announcement.version += 1
            announcement.updated_at = timestamp
            from app.domains.announcements.service import record_revision

            record_revision(db, announcement, actor.user_id, 'remove', timestamp)

    report.status = action_status
    report.resolved_at = timestamp
    report.evidence = None
    db.add(AnnouncementReportDecision(
        id=uid(),
        report_id=report.id,
        reviewer_id=actor.user_id,
        action=action,
        created_at=timestamp,
    ))
    _notify_transition(db, report, action_status)
    db.flush()
    return _review_payloads(db, [report], timestamp)[0]


def catch_up_announcement_reports_locked(db: Session, org_id: str, at: datetime) -> int:
    """Expire due open cases while the caller holds the organization lock."""
    due_announcement_ids = list(db.scalars(
        select(AnnouncementReport.announcement_id)
        .where(
            AnnouncementReport.org_id == org_id,
            AnnouncementReport.status == 'open',
            AnnouncementReport.deadline <= at,
        )
        .distinct()
        .order_by(AnnouncementReport.announcement_id)
    ))
    if not due_announcement_ids:
        return 0

    # Lock every post in a stable order before locking any case row.
    list(db.scalars(
        select(Announcement)
        .where(
            Announcement.org_id == org_id,
            Announcement.id.in_(due_announcement_ids),
        )
        .order_by(Announcement.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))
    reports = list(db.scalars(
        select(AnnouncementReport)
        .where(
            AnnouncementReport.org_id == org_id,
            AnnouncementReport.status == 'open',
            AnnouncementReport.deadline <= at,
        )
        .order_by(AnnouncementReport.announcement_id, AnnouncementReport.deadline, AnnouncementReport.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))

    transitions = 0
    for report in reports:
        report.status = 'expired'
        report.resolved_at = at
        report.evidence = None
        db.add(AnnouncementReportDecision(
            id=uid(),
            report_id=report.id,
            reviewer_id=None,
            action='expire',
            created_at=at,
        ))
        _notify_transition(db, report, 'expired')
        transitions += 1
    db.flush()
    return transitions
