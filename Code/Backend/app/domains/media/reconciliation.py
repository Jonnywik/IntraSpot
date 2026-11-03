"""Bounded, explicit-manifest media reconciliation and garbage collection."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import Text, cast, exists, func, or_, select, text
from sqlalchemy.orm import Session

from app.db.session import engine
from app.domains.announcements.moderation_models import AnnouncementReport
from app.domains.events.models import Event
from app.domains.eventsafety.models import EventReport, SafetyAudit
from app.domains.media.models import MediaAsset
from app.domains.media.storage import (
    MediaStorageError,
    delete_object,
    lock_media_quota,
    object_exists,
)
from app.domains.media.storage_models import MediaObject
from app.domains.moderation.models import ContentReport
from app.domains.organizations.models import Organization
from app.recovery_models import BackupObjectReference, BackupSnapshot

ORPHAN_MIN_AGE = timedelta(days=14)
ORPHAN_SCAN_INTERVAL = timedelta(days=7)
MAX_MANIFEST_TARGETS = 100
GC_LOCK_TIMEOUT = "750ms"
GC_STATEMENT_TIMEOUT = "8000ms"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _database_time(session: Session) -> datetime:
    return _utc(session.scalar(select(func.clock_timestamp())))


def _set_timeouts(session: Session) -> None:
    session.execute(
        text("SELECT set_config('lock_timeout', :value, true)"),
        {"value": GC_LOCK_TIMEOUT},
    )
    session.execute(
        text("SELECT set_config('statement_timeout', :value, true)"),
        {"value": GC_STATEMENT_TIMEOUT},
    )


def _is_protected(session: Session, media: MediaObject, at: datetime) -> bool:
    if media.status != "stored":
        return True
    if (
        media.backup_protected_until is not None
        and _utc(media.backup_protected_until) > at
    ):
        return True
    if (
        media.report_protected_until is not None
        and _utc(media.report_protected_until) > at
    ):
        return True
    references = [
        exists().where(Organization.logo_media_id == media.id),
        exists().where(Event.banner_media_id == media.id),
        exists().where(
            BackupObjectReference.media_id == media.id,
            BackupObjectReference.snapshot_id == BackupSnapshot.id,
            BackupSnapshot.retired_at.is_(None),
        ),
        *(
            exists().where(getattr(report, "evidence").contains(media.id))
            for report in (ContentReport, EventReport, AnnouncementReport)
            if getattr(report, "evidence", None) is not None
        ),
        exists().where(cast(SafetyAudit.previous, Text).contains(media.id)),
        exists().where(cast(SafetyAudit.result, Text).contains(media.id)),
    ]
    return bool(session.scalar(select(or_(*references))))


def _weekly_sightings_ready(media: MediaObject, at: datetime) -> bool:
    if media.orphan_seen_at is None or media.last_seen_at is None:
        return False
    first = _utc(media.orphan_seen_at)
    last = _utc(media.last_seen_at)
    intervals = media.orphan_seen_count - 1
    elapsed = last - first
    return (
        intervals >= 1
        and elapsed >= ORPHAN_SCAN_INTERVAL * intervals
        and elapsed < ORPHAN_SCAN_INTERVAL * (2 * intervals)
        and at - first >= ORPHAN_MIN_AGE
    )


def _entry(media: MediaObject, at: datetime, observation: str) -> dict:
    return {
        "id": media.id,
        "provider": media.provider,
        "object_key": media.object_key,
        "byte_size": media.byte_size,
        "status": media.status,
        "charged": True,
        "observation": observation,
        "orphan_seen_at": (
            _utc(media.orphan_seen_at).isoformat() if media.orphan_seen_at else None
        ),
        "orphan_seen_count": media.orphan_seen_count,
        "last_seen_at": (
            _utc(media.last_seen_at).isoformat() if media.last_seen_at else None
        ),
        "orphan_candidate": (
            observation in {"unreferenced", "missing_unreferenced"}
            and _weekly_sightings_ready(media, at)
        ),
    }


def _record_observation(
    expected: MediaObject, *, present: bool, at: datetime | None
) -> tuple[str, dict | None]:
    with Session(engine(), expire_on_commit=False) as session:
        with session.begin():
            _set_timeouts(session)
            org_id = session.scalar(
                select(MediaObject.org_id).where(MediaObject.id == expected.id)
            )
            if org_id is None:
                return "stale", None
            locked_org = session.scalar(
                select(Organization.id)
                .where(Organization.id == org_id)
                .with_for_update()
            )
            if locked_org is None:
                return "organization_missing", None
            lock_media_quota(session)
            media = session.scalar(
                select(MediaObject)
                .where(MediaObject.id == expected.id)
                .with_for_update()
            )
            if media is None or (
                media.provider,
                media.object_key,
                media.byte_size,
            ) != (expected.provider, expected.object_key, expected.byte_size):
                return "stale", None
            timestamp = _utc(at) if at is not None else _database_time(session)
            if _is_protected(session, media, timestamp):
                media.orphan_seen_at = None
                media.orphan_seen_count = 0
                if present:
                    media.last_seen_at = timestamp
                session.flush()
                observation = "protected" if present else "missing_protected"
                return observation, _entry(media, timestamp, observation)

            if media.orphan_seen_at is None or media.orphan_seen_count <= 0:
                media.orphan_seen_at = timestamp
                media.orphan_seen_count = 1
                media.last_seen_at = timestamp
            elif media.last_seen_at is None:
                media.orphan_seen_count += 1
                media.last_seen_at = timestamp
            else:
                gap = timestamp - _utc(media.last_seen_at)
                if gap >= ORPHAN_SCAN_INTERVAL * 2:
                    # A missing weekly finding breaks the consecutive series.
                    media.orphan_seen_at = timestamp
                    media.orphan_seen_count = 1
                    media.last_seen_at = timestamp
                elif gap >= ORPHAN_SCAN_INTERVAL:
                    media.orphan_seen_count += 1
                    media.last_seen_at = timestamp
            session.flush()
            observation = "unreferenced" if present else "missing_unreferenced"
            return observation, _entry(media, timestamp, observation)


def reconcile_media(
    *,
    apply: bool = False,
    at: datetime | None = None,
    after_id: str | None = None,
    limit: int = MAX_MANIFEST_TARGETS,
) -> list[dict]:
    """Inspect one bounded page; apply only records sightings, never deletes bytes."""
    if not 1 <= limit <= MAX_MANIFEST_TARGETS:
        raise ValueError(f"limit must be between 1 and {MAX_MANIFEST_TARGETS}")
    timestamp = _utc(at) if at is not None else None
    with Session(engine(), expire_on_commit=False) as session:
        if timestamp is None:
            timestamp = _database_time(session)
        query = select(MediaObject).order_by(MediaObject.id).limit(limit)
        if after_id is not None:
            query = query.where(MediaObject.id > after_id)
        rows = list(session.scalars(query))

    manifest: list[dict] = []
    for media in rows:
        if media.status != "stored":
            manifest.append(_entry(media, timestamp, "inflight"))
            continue
        try:
            present = object_exists(media)
        except MediaStorageError:
            manifest.append(_entry(media, timestamp, "uncertain"))
            continue
        if apply:
            observation, entry = _record_observation(
                media, present=present, at=timestamp if at is not None else None
            )
            if entry is None:
                manifest.append(_entry(media, timestamp, observation))
            else:
                manifest.append(entry)
            continue

        with Session(engine(), expire_on_commit=False) as session:
            current = session.get(MediaObject, media.id)
            protected = current is None or _is_protected(session, current, timestamp)
            if current is not None:
                media = current
        observation = (
            ("protected" if present else "missing_protected")
            if protected
            else "unreferenced" if present else "missing_unreferenced"
        )
        manifest.append(_entry(media, timestamp, observation))
    return manifest


def _validated_manifest_entries(manifest) -> list[dict]:
    if isinstance(manifest, dict):
        manifest = manifest.get("objects")
    if not isinstance(manifest, list) or len(manifest) > MAX_MANIFEST_TARGETS:
        raise ValueError("manifest must contain at most 100 object entries")
    entries: list[dict] = []
    seen: set[str] = set()
    for entry in manifest:
        if not isinstance(entry, dict):
            raise ValueError("invalid manifest entry")
        media_id = entry.get("id")
        try:
            valid_id = isinstance(media_id, str) and str(UUID(media_id)) == media_id.lower()
        except (ValueError, TypeError, AttributeError):
            valid_id = False
        if (
            not valid_id
            or media_id in seen
            or entry.get("provider") not in {"local", "supabase"}
            or entry.get("object_key") != f"{media_id}.webp"
            or not isinstance(entry.get("byte_size"), int)
            or isinstance(entry.get("byte_size"), bool)
            or entry["byte_size"] <= 0
            or entry.get("orphan_candidate") is not True
            or entry.get("observation") not in {"unreferenced", "missing_unreferenced"}
        ):
            raise ValueError("manifest contains an invalid or ineligible target")
        seen.add(media_id)
        entries.append(entry)
    return entries


def _apply_one(entry: dict, at: datetime | None) -> str:
    with Session(engine(), expire_on_commit=False) as session:
        with session.begin():
            _set_timeouts(session)
            org_id = session.scalar(
                select(MediaObject.org_id).where(MediaObject.id == entry["id"])
            )
            if org_id is None:
                return "stale"
            if session.scalar(
                select(Organization.id)
                .where(Organization.id == org_id)
                .with_for_update()
            ) is None:
                return "organization_missing"
            lock_media_quota(session)
            media = session.scalar(
                select(MediaObject)
                .where(MediaObject.id == entry["id"])
                .with_for_update()
            )
            if media is None:
                return "stale"
            if (
                media.provider != entry["provider"]
                or media.object_key != entry["object_key"]
                or media.byte_size != entry["byte_size"]
                or media.status != "stored"
            ):
                return "stale"
            timestamp = _utc(at) if at is not None else _database_time(session)
            if _is_protected(session, media, timestamp):
                media.orphan_seen_at = None
                media.orphan_seen_count = 0
                return "protected"
            if not _weekly_sightings_ready(media, timestamp):
                return "not_eligible"

            # Keep the org, quota, and media locks until provider deletion and the
            # corresponding accounting rows commit. A failed commit remains charged.
            present = object_exists(media)
            if present:
                delete_object(media)
            asset = session.get(MediaAsset, media.id)
            if asset is not None:
                session.delete(asset)
            session.delete(media)
            session.flush()
            return "deleted" if present else "missing"


def apply_media_manifest(manifest, *, at: datetime | None = None) -> list[dict]:
    """Revalidate and delete only explicitly listed, still-eligible media targets."""
    entries = _validated_manifest_entries(manifest)
    results = []
    for entry in entries:
        try:
            outcome = _apply_one(entry, at)
        except MediaStorageError:
            outcome = "provider_uncertain"
        except Exception:
            # Any DB or timeout failure keeps the charged row for a later retry.
            outcome = "revalidation_failed"
        results.append({"id": entry["id"], "outcome": outcome})
    return results
