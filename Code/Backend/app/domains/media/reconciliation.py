"""Record safe storage observations and return a non-destructive cleanup manifest."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import Text, cast, exists, select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.domains.announcements.moderation_models import AnnouncementReport
from app.domains.events.models import Event
from app.domains.eventsafety.models import EventReport, SafetyAudit
from app.domains.media.storage import MediaStorageError, object_exists
from app.domains.media.storage_models import MediaObject
from app.domains.moderation.models import ContentReport
from app.domains.organizations.models import Organization

ORPHAN_MIN_AGE = timedelta(days=14)
ORPHAN_SCAN_INTERVAL = timedelta(days=7)


def _referenced(session: Session, media_id: str) -> bool:
    if session.scalar(select(exists().where(Organization.logo_media_id == media_id))):
        return True
    if session.scalar(select(exists().where(Event.banner_media_id == media_id))):
        return True
    for report in (ContentReport, EventReport, AnnouncementReport):
        evidence = getattr(report, 'evidence', None)
        if evidence is not None and session.scalar(
            select(exists().where(evidence.contains(media_id)))
        ):
            return True
    for audit in (SafetyAudit,):
        for payload in (audit.previous, audit.result):
            if session.scalar(select(exists().where(cast(payload, Text).contains(media_id)))):
                return True
    return False


def reconcile_media(*, apply: bool = False, at: datetime | None = None) -> list[dict]:
    """Return a dry-run manifest; apply only records verified sightings, never deletes bytes."""
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    at = at.astimezone(timezone.utc)
    manifest: list[dict] = []

    with Session(engine(), expire_on_commit=False) as session:
        with session.begin():
            query = select(MediaObject).order_by(MediaObject.id)
            if apply:
                query = query.with_for_update()
            rows = session.scalars(query).all()
            for media in rows:
                entry = {
                    'id': media.id,
                    'provider': media.provider,
                    'byte_size': media.byte_size,
                    'charged': True,
                    'orphan_candidate': False,
                }
                try:
                    present = object_exists(media)
                except MediaStorageError:
                    entry['observation'] = 'uncertain'
                    manifest.append(entry)
                    continue
                protected = (
                    (media.backup_protected_until is not None and media.backup_protected_until > at)
                    or (media.report_protected_until is not None and media.report_protected_until > at)
                    or _referenced(session, media.id)
                )
                if protected:
                    if apply:
                        media.orphan_seen_at = None
                        media.orphan_seen_count = 0
                        media.last_seen_at = at
                    entry['observation'] = 'protected' if present else 'missing_protected'
                    manifest.append(entry)
                    continue

                if present and apply and media.status == 'reserved':
                    media.status = 'stored'
                seen_at = media.orphan_seen_at
                seen_count = media.orphan_seen_count
                last_seen = media.last_seen_at
                if seen_at is None or seen_count <= 0:
                    seen_at = at
                    seen_count = 1
                    last_seen = at
                elif last_seen is None or at - last_seen >= ORPHAN_SCAN_INTERVAL:
                    seen_count += 1
                    last_seen = at
                if apply:
                    media.orphan_seen_at = seen_at
                    media.orphan_seen_count = seen_count
                    media.last_seen_at = last_seen

                entry['observation'] = 'unreferenced' if present else 'missing_unreferenced'
                entry['orphan_seen_at'] = seen_at.isoformat()
                entry['orphan_seen_count'] = seen_count
                eligible = (
                    seen_count >= 2
                    and at - seen_at >= ORPHAN_MIN_AGE
                )
                entry['orphan_candidate'] = eligible
                manifest.append(entry)
    return manifest
