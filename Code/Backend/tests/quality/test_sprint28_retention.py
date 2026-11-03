from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json
import urllib.request

import pytest
from sqlalchemy import select

from app.db.models import uid
from app.domains.announcements.models import Announcement, AnnouncementRevision
from app.domains.announcements.moderation_models import AnnouncementReport
from app.domains.media.models import MediaAsset
from app.domains.media.storage_models import MediaObject
from app.domains.media import reconciliation, storage
from app.domains.eventsafety.models import SafetyAudit
from app.domains.moderation.models import ContentReport
from app.recovery_models import BackupObjectReference, BackupSnapshot


def _add_media(
    db,
    org,
    *,
    media_id=None,
    status="stored",
    seen_at=None,
    seen_count=0,
    last_seen_at=None,
    backup_protected_until=None,
):
    media_id = media_id or uid()
    db.add(
        MediaAsset(
            id=media_id,
            org_id=org.id,
            kind="logo",
            width=1,
            height=1,
            byte_size=321,
            created_by=org.created_by,
        )
    )
    db.add(
        MediaObject(
            id=media_id,
            org_id=org.id,
            provider="local",
            object_key=f"{media_id}.webp",
            byte_size=321,
            status=status,
            orphan_seen_at=seen_at,
            orphan_seen_count=seen_count,
            last_seen_at=last_seen_at,
            backup_protected_until=backup_protected_until,
        )
    )
    db.commit()
    return media_id


def _eligible_media(db, org, at):
    return _add_media(
        db,
        org,
        seen_at=at - timedelta(days=14),
        seen_count=2,
        last_seen_at=at - timedelta(days=7),
    )


def test_media_dry_run_does_not_record_sightings(db, make_org, monkeypatch):
    org = make_org()
    media_id = _add_media(db, org)
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    monkeypatch.setattr(reconciliation, "object_exists", lambda _media: True)

    manifest = reconciliation.reconcile_media(at=at)

    assert manifest[0]["id"] == media_id
    assert manifest[0]["orphan_candidate"] is False
    db.expire_all()
    media = db.get(MediaObject, media_id)
    assert media.orphan_seen_at is None
    assert media.orphan_seen_count == 0


def test_gc_requires_weekly_sightings_and_explicit_manifest_for_delete(
    db, make_org, monkeypatch
):
    org = make_org()
    media_id = _add_media(db, org)
    first = datetime(2026, 10, 1, tzinfo=timezone.utc)
    second = first + timedelta(days=7)
    eligible_at = first + timedelta(days=14)
    deleted = []
    monkeypatch.setattr(reconciliation, "object_exists", lambda _media: True)
    monkeypatch.setattr(reconciliation, "delete_object", lambda media: deleted.append(media.id))

    reconciliation.reconcile_media(apply=True, at=first)
    reconciliation.reconcile_media(apply=True, at=second)
    manifest = reconciliation.reconcile_media(at=eligible_at)

    assert manifest[0]["orphan_candidate"] is True
    assert deleted == []
    result = reconciliation.apply_media_manifest(manifest, at=eligible_at)
    assert result == [{"id": media_id, "outcome": "deleted"}]
    assert deleted == [media_id]
    db.expire_all()
    assert db.get(MediaObject, media_id) is None
    assert db.get(MediaAsset, media_id) is None

    # Reapplying a stale saved manifest cannot release the accounting rows twice.
    assert reconciliation.apply_media_manifest(manifest, at=eligible_at) == [
        {"id": media_id, "outcome": "stale"}
    ]
    assert deleted == [media_id]


def test_missed_week_restarts_consecutive_orphan_findings(db, make_org, monkeypatch):
    org = make_org()
    media_id = _add_media(db, org)
    first = datetime(2026, 10, 1, tzinfo=timezone.utc)
    missed_week = first + timedelta(days=14)
    next_week = missed_week + timedelta(days=7)
    monkeypatch.setattr(reconciliation, "object_exists", lambda _media: True)

    reconciliation.reconcile_media(apply=True, at=first)
    after_gap = reconciliation.reconcile_media(apply=True, at=missed_week)
    assert after_gap[0]["orphan_seen_count"] == 1
    assert after_gap[0]["orphan_seen_at"] == missed_week.isoformat()

    next_finding = reconciliation.reconcile_media(apply=True, at=next_week)
    assert next_finding[0]["orphan_seen_count"] == 2
    assert next_finding[0]["orphan_candidate"] is False


def test_gc_revalidates_strict_consecutive_finding_gap(db, make_org, monkeypatch):
    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    media_id = _add_media(
        db,
        org,
        seen_at=at - timedelta(days=21),
        seen_count=2,
        last_seen_at=at - timedelta(days=7),
    )
    existence_checks = []
    deleted = []
    monkeypatch.setattr(
        reconciliation,
        "object_exists",
        lambda _media: existence_checks.append(True) or True,
    )
    monkeypatch.setattr(
        reconciliation, "delete_object", lambda media: deleted.append(media.id)
    )

    manifest = reconciliation.reconcile_media(at=at)

    assert manifest[0]["observation"] == "unreferenced"
    assert manifest[0]["orphan_candidate"] is False
    # A saved manifest can be stale or edited; application rechecks DB sightings.
    manifest[0]["orphan_candidate"] = True
    assert reconciliation.apply_media_manifest(manifest, at=at) == [
        {"id": media_id, "outcome": "not_eligible"}
    ]
    assert len(existence_checks) == 1
    assert deleted == []
    db.expire_all()
    assert db.get(MediaObject, media_id) is not None
    assert db.get(MediaAsset, media_id) is not None


def test_uncertain_provider_observation_does_not_advance_orphan_series(
    db, make_org, monkeypatch
):
    org = make_org()
    media_id = _add_media(db, org)
    first = datetime(2026, 10, 1, tzinfo=timezone.utc)
    second = first + timedelta(days=7)
    third = second + timedelta(days=7)
    monkeypatch.setattr(reconciliation, "object_exists", lambda _media: True)
    reconciliation.reconcile_media(apply=True, at=first)

    def uncertain(_media):
        raise storage.MediaStorageError("provider unavailable")

    monkeypatch.setattr(reconciliation, "object_exists", uncertain)
    failed = reconciliation.reconcile_media(apply=True, at=second)
    assert failed[0]["observation"] == "uncertain"
    db.expire_all()
    media = db.get(MediaObject, media_id)
    assert media.orphan_seen_count == 1
    assert media.last_seen_at == first

    monkeypatch.setattr(reconciliation, "object_exists", lambda _media: True)
    recovered = reconciliation.reconcile_media(apply=True, at=third)
    assert recovered[0]["orphan_seen_count"] == 1
    assert recovered[0]["orphan_seen_at"] == third.isoformat()


@pytest.mark.parametrize("status", ["pending", "complete", "failed"])
def test_any_unretired_backup_reference_protects_media_past_pin_ttl(
    db, make_org, monkeypatch, status
):
    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    media_id = _add_media(
        db,
        org,
        seen_at=at - timedelta(days=14),
        seen_count=2,
        last_seen_at=at - timedelta(days=7),
        backup_protected_until=at - timedelta(days=1),
    )
    snapshot_id = uid()
    db.add(
        BackupSnapshot(
            id=snapshot_id,
            purpose="weekly",
            status=status,
            created_at=at - timedelta(days=40),
            retired_at=None,
        )
    )
    db.flush()
    db.add(BackupObjectReference(snapshot_id=snapshot_id, media_id=media_id))
    db.commit()
    monkeypatch.setattr(reconciliation, "object_exists", lambda _media: True)

    manifest = reconciliation.reconcile_media(at=at)

    assert manifest[0]["observation"] == "protected"
    assert manifest[0]["orphan_candidate"] is False


def test_retired_backup_reference_with_expired_pin_does_not_hold_media(
    db, make_org, monkeypatch
):
    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    media_id = _add_media(
        db,
        org,
        seen_at=at - timedelta(days=14),
        seen_count=2,
        last_seen_at=at - timedelta(days=7),
        backup_protected_until=at - timedelta(days=1),
    )
    snapshot_id = uid()
    db.add(
        BackupSnapshot(
            id=snapshot_id,
            purpose="weekly",
            status="complete",
            created_at=at - timedelta(days=40),
            retired_at=at - timedelta(days=2),
        )
    )
    db.flush()
    db.add(BackupObjectReference(snapshot_id=snapshot_id, media_id=media_id))
    db.commit()
    monkeypatch.setattr(reconciliation, "object_exists", lambda _media: True)

    manifest = reconciliation.reconcile_media(at=at)

    assert manifest[0]["observation"] == "unreferenced"
    assert manifest[0]["orphan_candidate"] is True


def test_report_evidence_and_safety_audit_protect_media(db, make_org, make_event, monkeypatch):
    org = make_org()
    event = make_event(org=org)
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    media_id = _eligible_media(db, org, at)
    db.add(
        ContentReport(
            id=uid(),
            event_id=event.id,
            org_id=org.id,
            reporter_id=org.created_by,
            subject_user_id=org.created_by,
            kind="comment",
            target_id=uid(),
            reason="other",
            status="dismissed",
            stage="organization",
            evidence=f"reported media {media_id}",
            deadline=at + timedelta(days=1),
        )
    )
    db.add(
        SafetyAudit(
            id=uid(),
            org_id=org.id,
            actor_id=org.created_by,
            scope="organization",
            action="suspend",
            version=1,
            previous={"logo_media_id": media_id},
            result={},
        )
    )
    db.commit()
    monkeypatch.setattr(reconciliation, "object_exists", lambda _media: True)

    manifest = reconciliation.reconcile_media(at=at)

    assert manifest[0]["observation"] == "protected"
    assert manifest[0]["orphan_candidate"] is False


def test_apply_rechecks_attachment_under_locks(db, make_org, monkeypatch):
    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    media_id = _eligible_media(db, org, at)
    monkeypatch.setattr(reconciliation, "object_exists", lambda _media: True)
    manifest = reconciliation.reconcile_media(at=at)
    deleted = []
    monkeypatch.setattr(reconciliation, "delete_object", lambda media: deleted.append(media.id))

    org.logo_media_id = media_id
    db.commit()
    result = reconciliation.apply_media_manifest(manifest, at=at)

    assert result == [{"id": media_id, "outcome": "protected"}]
    assert deleted == []
    db.expire_all()
    assert db.get(MediaObject, media_id) is not None
    assert db.get(MediaAsset, media_id) is not None


def test_uncertain_provider_delete_keeps_media_charged(db, make_org, monkeypatch):
    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    media_id = _eligible_media(db, org, at)
    monkeypatch.setattr(reconciliation, "object_exists", lambda _media: True)
    manifest = reconciliation.reconcile_media(at=at)

    def fail_delete(_media):
        raise storage.MediaStorageError("uncertain")

    monkeypatch.setattr(reconciliation, "delete_object", fail_delete)
    assert reconciliation.apply_media_manifest(manifest, at=at) == [
        {"id": media_id, "outcome": "provider_uncertain"}
    ]
    db.expire_all()
    assert db.get(MediaObject, media_id) is not None
    assert db.get(MediaAsset, media_id) is not None


def test_reserved_media_is_never_a_gc_candidate(db, make_org, monkeypatch):
    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    media_id = _add_media(
        db,
        org,
        status="reserved",
        seen_at=at - timedelta(days=30),
        seen_count=4,
        last_seen_at=at - timedelta(days=7),
    )
    monkeypatch.setattr(reconciliation, "object_exists", lambda _media: True)

    manifest = reconciliation.reconcile_media(at=at)

    assert manifest[0]["id"] == media_id
    assert manifest[0]["observation"] == "inflight"
    assert manifest[0]["orphan_candidate"] is False


def test_manifest_and_scan_are_hard_bounded():
    with pytest.raises(ValueError):
        reconciliation.reconcile_media(limit=101)
    with pytest.raises(ValueError):
        reconciliation.apply_media_manifest([{}] * 101)


def test_supabase_delete_uses_private_storage_api_without_redirects(monkeypatch):
    media_id = uid()
    media = SimpleNamespace(
        id=media_id,
        object_key=f"{media_id}.webp",
        provider="supabase",
    )
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b"[]"

    def fake_open(request, timeout):
        captured.update(request=request, timeout=timeout)
        return Response()

    monkeypatch.setattr(storage, "_supabase_settings", lambda: ("https://db.example", "media", "sb_secret_private"))
    monkeypatch.setattr(storage, "_private_bucket_verified", lambda: None)
    monkeypatch.setattr(storage._http_opener, "open", fake_open)

    storage.delete_object(media)

    request = captured["request"]
    assert request.get_method() == "DELETE"
    assert request.full_url == "https://db.example/storage/v1/object/media"
    assert request.get_header("Apikey") == "sb_secret_private"
    assert json.loads(request.data) == {"prefixes": [media.object_key]}
    assert captured["timeout"] == storage.HTTP_TIMEOUT_SECONDS
    handler = storage._NoRedirectHandler()
    assert handler.redirect_request(
        urllib.request.Request("https://db.example"), None, 302, "Found", {}, "https://other.example"
    ) is None


def test_local_delete_requires_valid_immutable_key(tmp_path, monkeypatch):
    media_id = uid()
    settings = SimpleNamespace(media_root=tmp_path)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    media = SimpleNamespace(id=media_id, object_key=f"{media_id}.webp", provider="local")
    target = tmp_path / media.object_key
    target.write_bytes(b"immutable media")

    storage.delete_object(media)
    storage.delete_object(media)  # Confirmed missing is idempotent.
    assert not target.exists()
    media.object_key = "../outside.webp"
    with pytest.raises(storage.MediaStorageError):
        storage.delete_object(media)


def _announcement(org, actor_id, *, at, version, removed_at=None, title="old title", body="old body"):
    announcement_id = uid()
    return Announcement(
        id=announcement_id,
        org_id=org.id,
        created_by=actor_id,
        title=title,
        body=body,
        audience="members",
        version=version,
        client_key=uid(),
        create_hash="a" * 64,
        created_at=at - timedelta(days=60),
        updated_at=at - timedelta(days=31),
        removed_at=removed_at,
    )


def _revision(
    announcement, actor_id, *, at, version, action="publish", created_at=None
):
    return AnnouncementRevision(
        id=uid(),
        announcement_id=announcement.id,
        version=version,
        actor_id=actor_id,
        action=action,
        title=f"revision {version}",
        body=f"private copy {version}",
        audience="members",
        created_at=created_at or at - timedelta(days=60),
    )


def _report(announcement, org, reporter_id, *, at, version, deadline):
    return AnnouncementReport(
        id=uid(),
        announcement_id=announcement.id,
        org_id=org.id,
        reporter_id=reporter_id,
        subject_user_id=announcement.created_by,
        reason="other",
        status="dismissed",
        reported_version=version,
        evidence="retained report evidence",
        created_at=at - timedelta(days=45),
        deadline=deadline,
    )


def test_announcement_retention_scrubs_old_content_and_honors_report_deadlines(
    db, make_org
):
    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    superseded_with_report = _announcement(org, org.created_by, at=at, version=2)
    removed_without_report = _announcement(
        org,
        org.created_by,
        at=at,
        version=1,
        removed_at=at - timedelta(days=31),
    )
    removed_with_report = _announcement(
        org,
        org.created_by,
        at=at,
        version=1,
        removed_at=at - timedelta(days=31),
    )
    revisions = [
        _revision(superseded_with_report, org.created_by, at=at, version=1),
        _revision(removed_without_report, org.created_by, at=at, version=1, action="remove"),
        _revision(removed_with_report, org.created_by, at=at, version=1, action="remove"),
    ]
    db.add_all(
        [
            superseded_with_report,
            removed_without_report,
            removed_with_report,
            *revisions,
            _report(
                superseded_with_report,
                org,
                org.created_by,
                at=at,
                version=1,
                deadline=at + timedelta(days=2),
            ),
            _report(
                removed_with_report,
                org,
                org.created_by,
                at=at,
                version=1,
                deadline=at + timedelta(days=2),
            ),
        ]
    )
    db.commit()

    from app.retention import purge_announcement_content

    result = purge_announcement_content(at=at, limit=100, db=db)

    assert result == {"revisions": 1, "announcements": 1, "processed": 2}
    db.expire_all()
    scrubbed_post = db.get(Announcement, removed_without_report.id)
    scrubbed_revision = db.scalar(
        select(AnnouncementRevision).where(
            AnnouncementRevision.announcement_id == removed_without_report.id
        )
    )
    assert (scrubbed_post.title, scrubbed_post.body, scrubbed_post.removed_at) == (
        "",
        None,
        removed_without_report.removed_at,
    )
    assert (scrubbed_revision.title, scrubbed_revision.body, scrubbed_revision.action) == (
        "",
        None,
        "remove",
    )
    db.expire_all()
    held_revision = db.scalar(
        select(AnnouncementRevision).where(
            AnnouncementRevision.announcement_id == superseded_with_report.id
        )
    )
    held_post = db.get(Announcement, removed_with_report.id)
    assert held_revision.body == "private copy 1"
    assert held_post.body == "old body"
    assert db.scalar(
        select(AnnouncementReport.evidence).where(
            AnnouncementReport.announcement_id == removed_with_report.id
        )
    ) == "retained report evidence"


def test_announcement_retention_caps_each_pass_at_100_rows(db, make_org):
    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    announcement = _announcement(org, org.created_by, at=at, version=106)
    db.add(announcement)
    db.add_all(
        [
            _revision(announcement, org.created_by, at=at, version=version)
            for version in range(1, 106)
        ]
    )
    db.commit()

    from app.retention import purge_announcement_content

    first = purge_announcement_content(at=at, limit=100, db=db)
    second = purge_announcement_content(at=at, limit=100, db=db)

    assert first["processed"] == 100
    assert second["processed"] == 5


def test_retention_zero_remaining_rows_is_a_noop(db):
    from app.retention import purge_announcement_content

    assert purge_announcement_content(limit=0, db=db) == {
        "revisions": 0,
        "announcements": 0,
        "processed": 0,
    }


def test_standalone_retention_commits_its_own_session(db, make_org):
    from app.retention import purge_announcement_content

    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    removed = _announcement(
        org,
        org.created_by,
        at=at,
        version=1,
        removed_at=at - timedelta(days=31),
    )
    db.add(removed)
    db.commit()

    result = purge_announcement_content(at=at)

    assert result["announcements"] == 1
    db.expire_all()
    assert db.get(Announcement, removed.id).body is None


def test_retention_uses_supplied_session_without_checkout_or_commit(
    db, make_org, monkeypatch
):
    from app import retention

    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    removed = _announcement(
        org,
        org.created_by,
        at=at,
        version=1,
        removed_at=at - timedelta(days=31),
    )
    db.add(removed)
    db.commit()

    def no_new_session(*_args, **_kwargs):
        raise AssertionError("caller-owned session should be reused")

    monkeypatch.setattr(retention, "Session", no_new_session)
    result = retention.purge_announcement_content(at=at, db=db)

    assert result["announcements"] == 1
    assert db.in_transaction()
    db.expire_all()
    assert db.get(Announcement, removed.id).body is None


def test_superseded_revision_retention_starts_at_supersession(db, make_org):
    from app.retention import purge_announcement_content

    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    announcement = _announcement(org, org.created_by, at=at, version=2)
    old_revision = _revision(
        announcement,
        org.created_by,
        at=at,
        version=1,
        created_at=at - timedelta(days=40),
    )
    _current_revision = _revision(
        announcement,
        org.created_by,
        at=at,
        version=2,
        created_at=at - timedelta(days=1),
        action="edit",
    )
    announcement.edited_at = at - timedelta(days=1)
    announcement.updated_at = at - timedelta(days=1)
    db.add_all([announcement, old_revision, _current_revision])
    db.commit()

    result = purge_announcement_content(at=at, db=db)

    assert result["revisions"] == 0
    db.expire_all()
    assert db.get(AnnouncementRevision, old_revision.id).body == "private copy 1"


def test_active_report_versions_do_not_consume_retention_page_limit(db, make_org):
    from app.retention import purge_announcement_content

    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    held_announcement = _announcement(org, org.created_by, at=at, version=6)
    held_revisions = [
        _revision(
            held_announcement,
            org.created_by,
            at=at,
            version=version,
            created_at=at - timedelta(days=70),
        )
        for version in range(1, 7)
    ]
    eligible_announcement = _announcement(org, org.created_by, at=at, version=2)
    eligible_revision = _revision(
        eligible_announcement,
        org.created_by,
        at=at,
        version=1,
        created_at=at - timedelta(days=70),
    )
    eligible_next = _revision(
        eligible_announcement,
        org.created_by,
        at=at,
        version=2,
        action="edit",
        created_at=at - timedelta(days=31),
    )
    reports = [
        _report(
            held_announcement,
            org,
            org.created_by,
            at=at,
            version=version,
            deadline=at + timedelta(days=2),
        )
        for version in range(1, 6)
    ]
    db.add_all(
        [
            held_announcement,
            *held_revisions,
            eligible_announcement,
            eligible_revision,
            eligible_next,
            *reports,
        ]
    )
    db.commit()

    result = purge_announcement_content(at=at, limit=1, db=db)

    assert result == {"revisions": 1, "announcements": 0, "processed": 1}
    db.expire_all()
    assert db.get(AnnouncementRevision, eligible_revision.id).body is None
    assert db.get(AnnouncementRevision, held_revisions[0].id).body == "private copy 1"


def test_report_hold_recheck_follows_parent_lock(db, make_org, monkeypatch):
    from app import retention

    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    announcement = _announcement(org, org.created_by, at=at, version=2)
    revision = _revision(announcement, org.created_by, at=at, version=1)
    next_revision = _revision(
        announcement,
        org.created_by,
        at=at,
        version=2,
        action="edit",
        created_at=at - timedelta(days=31),
    )
    db.add_all([announcement, revision, next_revision])
    db.commit()

    original_scalars = db.scalars
    report_inserted = False

    def scalars_with_racing_report(statement, *args, **kwargs):
        nonlocal report_inserted
        result = original_scalars(statement, *args, **kwargs)
        sql = str(statement.compile(dialect=db.get_bind().dialect)).upper()
        if (
            not report_inserted
            and "FROM ANNOUNCEMENTS" in sql
            and "FOR UPDATE SKIP LOCKED" in sql
        ):
            # Insert only after Session.scalars has executed the parent lock query.
            db.add(
                _report(
                    announcement,
                    org,
                    org.created_by,
                    at=at,
                    version=1,
                    deadline=at + timedelta(days=2),
                )
            )
            db.flush()
            report_inserted = True
        return result

    monkeypatch.setattr(db, "scalars", scalars_with_racing_report)
    result = retention.purge_announcement_content(at=at, db=db)

    assert report_inserted is True
    assert result["revisions"] == 0
    db.expire_all()
    assert db.get(AnnouncementRevision, revision.id).body == "private copy 1"


def test_retention_does_not_scrub_a_parent_skipped_by_the_lock(db, make_org, monkeypatch):
    from app import retention

    org = make_org()
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    announcement = _announcement(
        org, org.created_by, at=at, version=1, removed_at=at - timedelta(days=31),
    )
    db.add(announcement)
    db.commit()
    original_scalars = db.scalars

    def skip_busy_parent(statement, *args, **kwargs):
        sql = str(statement.compile(dialect=db.get_bind().dialect)).upper()
        if "FROM ANNOUNCEMENTS" in sql and "FOR UPDATE SKIP LOCKED" in sql:
            return []
        return original_scalars(statement, *args, **kwargs)

    monkeypatch.setattr(db, "scalars", skip_busy_parent)
    assert retention.purge_announcement_content(at=at, db=db)["processed"] == 0
    db.expire_all()
    assert db.get(Announcement, announcement.id).body == "old body"
