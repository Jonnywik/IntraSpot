"""Bounded retention for announcement content; audit and report metadata stays intact."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

from sqlalchemy import and_, case, exists, func, select, text, update
from sqlalchemy.orm import Session, aliased

from app.db.session import engine
from app.domains.announcements.models import Announcement, AnnouncementRevision
from app.domains.announcements.moderation_models import AnnouncementReport

CONTENT_RETENTION = timedelta(days=30)
MAX_RETENTION_ROWS = 100
_RETENTION_TIMEOUT_CAPS_MS = {"lock_timeout": 750, "statement_timeout": 3000}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@contextmanager
def _session_scope(db: Session | None) -> Iterator[Session]:
    if db is not None:
        yield db
        return
    with Session(engine(), expire_on_commit=False) as session:
        with session.begin():
            yield session


def _set_bounded_timeout(session: Session, setting: str) -> None:
    cap_ms = _RETENTION_TIMEOUT_CAPS_MS.get(setting)
    if cap_ms is None:
        raise ValueError("unsupported retention timeout setting")
    current_ms = session.scalar(
        text("SELECT setting::integer FROM pg_settings WHERE name = :setting"),
        {"setting": setting},
    )
    value_ms = min(cap_ms, current_ms or cap_ms)
    session.execute(
        text("SELECT set_config(:setting, :value, true)"),
        {"setting": setting, "value": f"{value_ms}ms"},
    )


def purge_announcement_content(
    *,
    at: datetime | None = None,
    limit: int = MAX_RETENTION_ROWS,
    db: Session | None = None,
) -> dict[str, int]:
    """Scrub at most 100 old content rows, using a supplied transaction if given.

    A report whose evidence deadline has not passed protects only the reported
    announcement version. The report and all action metadata remain untouched.
    """
    if not 0 <= limit <= MAX_RETENTION_ROWS:
        raise ValueError(f"limit must be between 0 and {MAX_RETENTION_ROWS}")
    if limit == 0:
        return {"revisions": 0, "announcements": 0, "processed": 0}
    revision_count = 0
    announcement_count = 0

    with _session_scope(db) as session:
        _set_bounded_timeout(session, "lock_timeout")
        _set_bounded_timeout(session, "statement_timeout")
        timestamp = (
            _utc(at) if at is not None else _utc(session.scalar(select(func.clock_timestamp())))
        )
        cutoff = timestamp - CONTENT_RETENTION

        next_revision = aliased(AnnouncementRevision)
        superseded_at = case(
            (
                AnnouncementRevision.version < Announcement.version,
                func.coalesce(
                    next_revision.created_at,
                    Announcement.edited_at,
                    Announcement.updated_at,
                ),
            ),
            (Announcement.removed_at.is_not(None), Announcement.removed_at),
            else_=None,
        )
        revision_report_hold = exists().where(
            AnnouncementReport.announcement_id
            == AnnouncementRevision.announcement_id,
            AnnouncementReport.reported_version == AnnouncementRevision.version,
            AnnouncementReport.deadline > timestamp,
        )
        revision_candidates = session.execute(
            select(
                AnnouncementRevision.id,
                AnnouncementRevision.announcement_id,
            )
            .join(Announcement, Announcement.id == AnnouncementRevision.announcement_id)
            .outerjoin(
                next_revision,
                and_(
                    next_revision.announcement_id
                    == AnnouncementRevision.announcement_id,
                    next_revision.version == AnnouncementRevision.version + 1,
                ),
            )
            .where(
                (AnnouncementRevision.title != "")
                | AnnouncementRevision.body.is_not(None),
                superseded_at <= cutoff,
                ~revision_report_hold,
            )
            .order_by(superseded_at, AnnouncementRevision.id)
            .limit(limit)
        ).all()

        remaining = limit - len(revision_candidates)
        current_report_hold = exists().where(
            AnnouncementReport.announcement_id == Announcement.id,
            AnnouncementReport.reported_version == Announcement.version,
            AnnouncementReport.deadline > timestamp,
        )
        current_candidates = []
        if remaining > 0:
            current_candidates = list(
                session.scalars(
                    select(Announcement.id)
                    .where(
                        Announcement.removed_at.is_not(None),
                        Announcement.removed_at <= cutoff,
                        (Announcement.title != "") | Announcement.body.is_not(None),
                        ~current_report_hold,
                    )
                    .order_by(Announcement.removed_at, Announcement.id)
                    .limit(remaining)
                )
            )

        candidate_parent_ids = {
            row.announcement_id for row in revision_candidates
        } | set(current_candidates)
        # Global retention never takes organization locks; parents are locked in
        # stable order and no organization lock is acquired later in this pass.
        locked_parent_ids = set()
        if candidate_parent_ids:
            locked_parent_ids = set(
                session.scalars(
                    select(Announcement.id)
                    .where(Announcement.id.in_(candidate_parent_ids))
                    .order_by(Announcement.id)
                    .with_for_update(skip_locked=True)
                )
            )

        revision_candidate_ids = [
            row.id
            for row in revision_candidates
            if row.announcement_id in locked_parent_ids
        ]
        revision_ids = []
        if revision_candidate_ids:
            # Re-evaluate age, content presence, and report deadline after the
            # parent lock so a concurrently-created report still protects text.
            revision_ids = list(
                session.scalars(
                    select(AnnouncementRevision.id)
                    .join(
                        Announcement,
                        Announcement.id == AnnouncementRevision.announcement_id,
                    )
                    .outerjoin(
                        next_revision,
                        and_(
                            next_revision.announcement_id
                            == AnnouncementRevision.announcement_id,
                            next_revision.version
                            == AnnouncementRevision.version + 1,
                        ),
                    )
                    .where(
                        AnnouncementRevision.id.in_(revision_candidate_ids),
                        (AnnouncementRevision.title != "")
                        | AnnouncementRevision.body.is_not(None),
                        superseded_at <= cutoff,
                        ~revision_report_hold,
                    )
                    .order_by(AnnouncementRevision.id)
                    .with_for_update(of=AnnouncementRevision, skip_locked=True)
                )
            )
        if revision_ids:
            result = session.execute(
                update(AnnouncementRevision)
                .where(AnnouncementRevision.id.in_(revision_ids))
                .values(title="", body=None)
            )
            revision_count = result.rowcount or 0

        current_ids = []
        if current_candidates:
            current_ids = list(
                session.scalars(
                    select(Announcement.id)
                    .where(
                        Announcement.id.in_(set(current_candidates) & locked_parent_ids),
                        Announcement.removed_at <= cutoff,
                        (Announcement.title != "") | Announcement.body.is_not(None),
                        ~current_report_hold,
                    )
                    .order_by(Announcement.id)
                )
            )
        if current_ids:
            result = session.execute(
                update(Announcement)
                .where(Announcement.id.in_(current_ids))
                .values(title="", body=None)
            )
            announcement_count = result.rowcount or 0

    return {
        "revisions": revision_count,
        "announcements": announcement_count,
        "processed": revision_count + announcement_count,
    }
