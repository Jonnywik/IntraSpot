"""Pure fault-injection checks plus an opt-in PostgreSQL and media rehearsal."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tarfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import recovery

KEY = b"k" * 32
SNAPSHOT_ID = "11111111-1111-4111-8111-111111111111"
MEDIA_ID = "22222222-2222-4222-8222-222222222222"
USER_ID = "33333333-3333-4333-8333-333333333333"


@pytest.fixture(autouse=True)
def private_permissions(monkeypatch, tmp_path, request):
    integration_run = (
        request.node.name == "test_sprint28_postgres_and_local_object_restore_rehearsal"
        and os.environ.get("RUN_SPRINT28_RECOVERY") == "1"
    )
    if not integration_run:
        monkeypatch.setattr(recovery, "_verify_private_permissions", lambda *args, **kwargs: True)
        synthetic_checkout = tmp_path.parent / ".synthetic-intraspot-checkout"
        monkeypatch.setattr(recovery, "_repo_root", lambda: synthetic_checkout)


def test_external_path_guard_still_rejects_checkout_contents(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    monkeypatch.setattr(recovery, "_repo_root", lambda: checkout)
    with pytest.raises(recovery.RecoveryError, match="outside the IntraSpot checkout"):
        recovery._assert_external_path(checkout / "backup")


def test_official_docker_fallback_does_not_require_pgport_environment(monkeypatch):
    commands = []
    monkeypatch.setattr(recovery.shutil, "which", lambda _tool: "docker")

    def captured(command, **_kwargs):
        commands.append(command)
        if command[1] == "inspect":
            return '/intraspot-mvp-postgres-1|{"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"5433"}]}'
        assert command[-1] == "--version"
        return "PostgreSQL 17.6"

    monkeypatch.setattr(recovery, "_run_captured", captured)
    recovery._validate_docker_postgres()
    assert len(commands) == 3


def test_docker_psql_restore_keeps_standard_input_open(monkeypatch):
    from sqlalchemy.engine import make_url
    monkeypatch.setattr(recovery.shutil, "which", lambda _tool: None)
    monkeypatch.setattr(recovery, "_validate_docker_postgres", lambda: None)
    command, env = recovery._postgres_command(
        'psql', make_url('postgresql+psycopg://fixture@127.0.0.1:5433/intraspot_restore_test'),
        {}, ['--host', '127.0.0.1', '--port', '5433'],
    )
    assert command[:3] == ['docker', 'exec', '--interactive']
    assert command[command.index('--port') + 1] == '5432'
    assert env['PGPORT'] == '5432'


def _encrypt(path, kind, archive_id, payload):
    writer = recovery._EncryptingWriter(path, KEY, kind, archive_id)
    writer.write(payload)
    return writer.finish()


def _tar_object(media_id, content):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        entry = tarfile.TarInfo(f"{media_id}.webp")
        entry.size = len(content)
        archive.addfile(entry, io.BytesIO(content))
    return stream.getvalue()


def test_erasure_ledger_is_detached_fresh_and_authenticated(tmp_path):
    backup_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    exported_at = datetime.now(timezone.utc)
    payload = {
        "format_version": 1,
        "exported_at": exported_at.isoformat(),
        "accounts": [{"user_id": USER_ID, "erased_at": (exported_at - timedelta(minutes=1)).isoformat()}],
    }
    ledger_id = "44444444-4444-4444-8444-444444444444"
    path = tmp_path / "current-erasures.gcm"
    _encrypt(path, "ledger", ledger_id, json.dumps(payload).encode())

    result_id, verified_at, accounts = recovery.verify_erasure_ledger(
        path, KEY, backup_created_at=backup_at.isoformat(),
    )
    assert result_id == ledger_id
    assert verified_at == exported_at.isoformat()
    assert accounts == payload["accounts"]

    encoded = bytearray(path.read_bytes())
    encoded[-1] ^= 1
    path.write_bytes(encoded)
    with pytest.raises(recovery.RecoveryError, match="authentication failed"):
        recovery.verify_erasure_ledger(path, KEY, backup_created_at=backup_at.isoformat())


def test_erasure_ledger_must_be_newer_than_backup(tmp_path):
    backup_at = datetime.now(timezone.utc)
    payload = {"format_version": 1, "exported_at": backup_at.isoformat(), "accounts": []}
    path = tmp_path / "stale-ledger.gcm"
    _encrypt(path, "ledger", "55555555-5555-4555-8555-555555555555", json.dumps(payload).encode())
    with pytest.raises(recovery.RecoveryError, match="newer than the selected backup"):
        recovery.verify_erasure_ledger(path, KEY, backup_created_at=backup_at.isoformat())


def test_restore_rejects_ledger_before_confirmed_cutoff_before_target_sql(tmp_path, monkeypatch):
    backup_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    exported_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    cutoff_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    bundle = tmp_path / SNAPSHOT_ID
    bundle.mkdir()
    ledger_path = tmp_path / "current-ledger.gcm"
    ledger = {
        "format_version": 1,
        "exported_at": exported_at.isoformat(),
        "accounts": [{"user_id": USER_ID, "erased_at": exported_at.isoformat()}],
    }
    _encrypt(
        ledger_path, "ledger", "77777777-7777-4777-8777-777777777777",
        json.dumps(ledger).encode(),
    )
    monkeypatch.setattr(
        recovery, "verify_backup",
        lambda *_args, **_kwargs: {"created_at": backup_at.isoformat()},
    )
    monkeypatch.setattr(
        recovery, "_verify_target_empty",
        lambda *_args, **_kwargs: pytest.fail("Target SQL was reached before ledger cutoff validation"),
    )

    with pytest.raises(recovery.RecoveryError, match="before the confirmed erasure cutoff"):
        recovery.restore_backup(
            bundle,
            KEY,
            "postgresql+psycopg://restore:unused@127.0.0.1:5433/intraspot_restore_test",
            tmp_path / "intraspot_restore_media",
            lambda *_args: None,
            erasure_ledger_file=ledger_path,
            erasure_cutoff_at=cutoff_at.isoformat(),
            confirm_erasure_quiescence=True,
        )


def test_restore_requires_explicit_erasure_quiescence_confirmation():
    with pytest.raises(recovery.RecoveryError, match="explicit confirmation"):
        recovery.restore_backup(
            "unopened-bundle",
            KEY,
            "postgresql+psycopg://restore:unused@127.0.0.1:5433/intraspot_restore_test",
            "intraspot_restore_media",
            erasure_ledger_file="unopened-ledger",
            erasure_cutoff_at=datetime.now(timezone.utc).isoformat(),
        )


def test_backup_verification_checks_authenticated_object_hashes(tmp_path):
    bundle = tmp_path / SNAPSHOT_ID
    bundle.mkdir()
    sql = b"SELECT 1;\n"
    database_entry = _encrypt(bundle / recovery._FILE_NAMES["database"], "database", SNAPSHOT_ID, sql)
    objects_entry = _encrypt(
        bundle / recovery._FILE_NAMES["objects"], "objects", SNAPSHOT_ID,
        _tar_object(MEDIA_ID, b"tampered"),
    )
    manifest = {
        "format_version": 1,
        "snapshot_id": SNAPSHOT_ID,
        "purpose": "weekly",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "archive_status": "verified",
        "database": {"schema": "public", "sha256": hashlib.sha256(sql).hexdigest(), "size": len(sql)},
        "objects": [{
            "id": MEDIA_ID, "status": "stored", "exists": True,
            "size": len(b"original"), "sha256": hashlib.sha256(b"original").hexdigest(),
        }],
        "erasures": {"erased_accounts": [], "completed_requests": []},
    }
    manifest_entry = recovery._write_json_encrypted(
        bundle / recovery._FILE_NAMES["manifest"], KEY, SNAPSHOT_ID, manifest,
    )
    recovery._write_checksums(
        bundle / recovery._FILE_NAMES["checksums"], SNAPSHOT_ID,
        {"database": database_entry, "objects": objects_entry, "manifest": manifest_entry},
    )

    with pytest.raises(recovery.RecoveryError, match="Media object checksum mismatch"):
        recovery.verify_backup(bundle, KEY)


def test_tampered_database_never_starts_psql(tmp_path, monkeypatch):
    bundle = tmp_path / SNAPSHOT_ID
    bundle.mkdir()
    sql = b"SELECT 'restore';\n"
    path = bundle / recovery._FILE_NAMES["database"]
    _encrypt(path, "database", SNAPSHOT_ID, sql)
    encoded = bytearray(path.read_bytes())
    encoded[-1] ^= 1
    path.write_bytes(encoded)
    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setattr(
        recovery, "_postgres_command",
        lambda *args, **kwargs: pytest.fail("psql tooling was reached before GCM authentication"),
    )

    with pytest.raises(recovery.RecoveryError, match="authentication failed"):
        recovery._restore_database(
            bundle,
            KEY,
            "postgresql+psycopg://restore:unused@127.0.0.1:5433/intraspot_restore_test",
            {"database": {"sha256": hashlib.sha256(sql).hexdigest(), "size": len(sql)}},
            {},
            staging,
            timeout=1,
        )
    assert not list(staging.glob(".authenticated-database-*.tmp"))


def test_restore_replays_only_fresh_ledger_accounts_after_database(tmp_path, monkeypatch):
    bundle = tmp_path / SNAPSHOT_ID
    bundle.mkdir()
    parent = tmp_path / "restore-output"
    parent.mkdir()
    media_root = parent / "intraspot_restore_media"
    backup_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    cutoff_at = datetime.now(timezone.utc) - timedelta(seconds=90)
    ledger_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    accounts = [{"user_id": USER_ID, "erased_at": ledger_at.isoformat()}]
    events = []
    manifest = {
        "snapshot_id": SNAPSHOT_ID,
        "created_at": backup_at.isoformat(),
        "erasures": {"must_not_be_replayed": True},
    }

    def verify_archive(*args, **kwargs):
        events.append("archive-authenticated")
        return manifest

    def verify_ledger(path, key, *, backup_created_at, erasure_cutoff_at):
        assert backup_created_at == manifest["created_at"]
        assert erasure_cutoff_at == cutoff_at.isoformat()
        events.append("ledger-authenticated")
        return "66666666-6666-4666-8666-666666666666", ledger_at.isoformat(), accounts

    monkeypatch.setattr(recovery, "verify_backup", verify_archive)
    monkeypatch.setattr(recovery, "verify_erasure_ledger", verify_ledger)
    monkeypatch.setattr(recovery, "_verify_target_empty", lambda _url: events.append("target-checked"))
    monkeypatch.setattr(recovery, "_make_private_directory", lambda path: (path.mkdir() is None))
    monkeypatch.setattr(recovery, "_restore_objects", lambda *args: events.append("objects-staged"))
    monkeypatch.setattr(
        recovery,
        "_restore_database",
        lambda *args, **kwargs: events.append("database-restored"),
    )
    journals = []
    monkeypatch.setattr(
        recovery, "_write_journal", lambda _path, value: journals.append(value.copy()),
    )
    replayed = []

    def replay(records, database_url):
        events.append("erasures-replayed")
        replayed.append((records, database_url))

    result = recovery.restore_backup(
        bundle,
        KEY,
        "postgresql+psycopg://restore:unused@127.0.0.1:5433/intraspot_restore_test",
        media_root,
        replay,
        erasure_ledger_file=parent / "current-ledger.gcm",
        erasure_cutoff_at=cutoff_at.isoformat(),
        confirm_erasure_quiescence=True,
    )

    assert events == [
        "archive-authenticated", "ledger-authenticated", "target-checked",
        "objects-staged", "database-restored", "erasures-replayed",
    ]
    assert replayed == [(
        accounts,
        "postgresql+psycopg://restore:unused@127.0.0.1:5433/intraspot_restore_test",
    )]
    assert journals
    assert all(row["erasure_cutoff_at"] == cutoff_at.isoformat() for row in journals)
    assert all(row["erasure_quiescence_confirmed"] is True for row in journals)
    assert result["media_root"] == str(media_root)


def test_missing_attached_reserved_media_fails_but_unattached_stays_charged(monkeypatch):
    media = SimpleNamespace(status="reserved", provider="local", byte_size=8)
    attached = {recovery.MediaObject: media, recovery.MediaAsset: object()}

    class SessionStub:
        def __init__(self, rows):
            self.rows = rows

        def get(self, model, media_id):
            return self.rows.get(model)

    monkeypatch.setattr(recovery.storage, "read_webp", lambda media_id, db=None: None)
    monkeypatch.setattr(recovery.storage, "object_exists", lambda _media: False)
    with pytest.raises(recovery.RecoveryError, match="attached media reservation has no stored object"):
        recovery._read_retained_object(MEDIA_ID, SessionStub(attached))

    content, status = recovery._read_retained_object(
        MEDIA_ID, SessionStub({recovery.MediaObject: media, recovery.MediaAsset: None}),
    )
    assert content is None
    assert status == "reserved"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://restore:unused@localhost:5433/intraspot_restore_test",
        "postgresql+psycopg://restore:unused@192.0.2.1:5433/intraspot_restore_test",
        "postgresql+psycopg://restore:unused@127.0.0.1:5432/intraspot_restore_test",
        "postgresql+psycopg://restore:unused@127.0.0.1:5433/intraspot_mvp_test",
    ],
)
def test_restore_target_requires_loopback_5433_and_restore_database(url):
    with pytest.raises(recovery.RecoveryError):
        recovery.validate_restore_database_url(url)


@pytest.mark.skipif(
    os.environ.get("RUN_SPRINT28_RECOVERY") != "1",
    reason="Opt in to the local PostgreSQL and media restore rehearsal",
)
def test_sprint28_postgres_and_local_object_restore_rehearsal(
    tmp_path, db, make_user, make_org, make_event, monkeypatch,
):
    from sqlalchemy import create_engine, func, select, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session

    from app.core.config import get_settings
    from app.db.models import now, uid
    from app.domains.events.models import Event
    from app.domains.identity.models import User
    from app.domains.media.models import MediaAsset
    from app.domains.media.storage_models import MediaObject
    from app.domains.media import storage
    from app.domains.organizations.models import Organization
    from app.erasure_models import ErasedAccount

    real_checkout = recovery.ROOT.parents[1].resolve()
    monkeypatch.setattr(recovery, "_repo_root", lambda: real_checkout)
    recovery._assert_external_path(tmp_path.resolve())

    source_url = make_url(get_settings().database_url)
    assert source_url.drivername == "postgresql+psycopg"
    assert source_url.database == "intraspot_mvp_test"
    assert source_url.host in {"127.0.0.1", "localhost"} and source_url.port == 5433
    source_database_url = source_url.render_as_string(hide_password=False)

    suffix = uuid4().hex[:8]
    target_database = f"intraspot_restore_s28_{suffix}"
    target_media_root = tmp_path / f"intraspot_restore_s28_{suffix}_media"
    assert re.fullmatch(r"intraspot_restore_s28_[0-9a-f]{8}", target_database)
    assert target_database not in {
        source_url.database, "intraspot_mvp", "intraspot_real_dev", "intraspot_mvp_test",
    }
    admin_url = source_url.set(host="127.0.0.1", port=5433, database="postgres")
    target_url = source_url.set(
        host="127.0.0.1", port=5433, database=target_database,
    )
    target_database_url = target_url.render_as_string(hide_password=False)
    admin_engine = create_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5},
    )
    target_engine = None
    target_database_created = False
    backup_root = tmp_path / "private-backup"
    source_media_root = tmp_path / "source-local-media"
    snapshot_id = None
    key = os.urandom(32)

    try:
        source_media_root.mkdir()
        assert recovery._make_private_directory(backup_root)

        erased_user = make_user(
            email=f"fictional-sprint28-{suffix}@example.invalid",
            nickname="Recovery fixture profile",
            age_bracket="18-24",
            tags=["synthetic-rehearsal"],
            pronouns="they/them",
            icebreaker="Synthetic recovery check",
            persona_visible=True,
        )
        org = make_org()
        event = make_event(org=org)
        media_id = uid()
        media_content = b"INTRASPOT-S28-LOCAL-MEDIA-FIXTURE"
        (source_media_root / f"{media_id}.webp").write_bytes(media_content)
        db.add_all([
            MediaObject(
                id=media_id, org_id=org.id, provider="local", object_key=f"{media_id}.webp",
                byte_size=len(media_content), status="stored",
            ),
            MediaAsset(
                id=media_id, org_id=org.id, kind="logo", width=1, height=1,
                byte_size=len(media_content), created_by=org.created_by,
            ),
        ])
        db.flush()
        org.logo_media_id = media_id
        db.commit()
        expected_orgs = db.scalar(select(func.count()).select_from(Organization))
        expected_events = db.scalar(select(func.count()).select_from(Event))
        assert expected_orgs == 1 and expected_events == 1

        def read_local_fixture(requested_id):
            path = source_media_root / f"{requested_id}.webp"
            return path.read_bytes() if path.is_file() else None

        monkeypatch.setattr(storage, "_read_local", read_local_fixture)
        monkeypatch.setattr(
            storage, "_read_supabase",
            lambda *_args, **_kwargs: pytest.fail("The rehearsal must not call an external provider"),
        )

        backup = recovery.create_backup(
            source_database_url, backup_root, key, purpose="premigration",
        )
        snapshot_id = backup["snapshot_id"]
        verified = recovery.verify_backup(backup["path"], key)
        media_record = next(item for item in verified["objects"] if item["id"] == media_id)
        assert media_record["sha256"] == hashlib.sha256(media_content).hexdigest()

        user = db.get(User, erased_user.id)
        erased_at = now()
        user.email = f"erased-{user.id}@example.invalid"
        user.email_verified = False
        user.active = False
        user.nickname = None
        user.age_bracket = None
        user.tags = []
        user.pronouns = None
        user.icebreaker = None
        user.persona_visible = False
        db.add(ErasedAccount(user_id=user.id, erased_at=erased_at))
        db.commit()
        cutoff_at = now()
        ledger_path = backup_root / "post-backup-erasures.gcm"
        recovery.export_erasure_ledger(source_database_url, ledger_path, key)

        with admin_engine.connect() as admin:
            assert admin.scalar(text("SELECT current_database()")) == "postgres"
            assert admin.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target_database},
            ) is None
            admin.exec_driver_sql(f'CREATE DATABASE "{target_database}"')
            target_database_created = True

        recovery.restore_backup(
            backup["path"], key, target_database_url, target_media_root,
            erasure_ledger_file=ledger_path,
            erasure_cutoff_at=cutoff_at.isoformat(),
            confirm_erasure_quiescence=True,
        )
        restored_object = target_media_root / f"{media_id}.webp"
        assert restored_object.read_bytes() == media_content
        assert hashlib.sha256(restored_object.read_bytes()).hexdigest() == media_record["sha256"]

        target_engine = create_engine(target_url, connect_args={"connect_timeout": 5})
        with Session(target_engine) as restored:
            restored_user = restored.get(User, erased_user.id)
            assert restored_user is not None and restored_user.active is False
            assert restored_user.email == f"erased-{erased_user.id}@example.invalid"
            assert restored_user.email_verified is False
            assert restored_user.nickname is None and restored_user.age_bracket is None
            assert restored_user.tags == []
            assert restored_user.pronouns is None and restored_user.icebreaker is None
            assert restored_user.persona_visible is False
            assert restored.scalar(select(func.count()).select_from(Organization)) == expected_orgs
            assert restored.scalar(select(func.count()).select_from(Event)) == expected_events
            assert restored.get(MediaObject, media_id).provider == "local"
            assert restored.get(MediaAsset, media_id).org_id == org.id
    finally:
        if target_engine is not None:
            target_engine.dispose()
        assert re.fullmatch(r"intraspot_restore_s28_[0-9a-f]{8}", target_database)
        assert target_database not in {
            source_url.database, "intraspot_mvp", "intraspot_real_dev", "intraspot_mvp_test",
        }
        if target_database_created:
            with admin_engine.connect() as admin:
                exists = admin.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": target_database},
                )
                if exists:
                    admin.exec_driver_sql(f'DROP DATABASE "{target_database}"')
        admin_engine.dispose()
        if snapshot_id is not None:
            try:
                recovery.retire_snapshot(
                    source_database_url, backup_root, snapshot_id, apply=True,
                )
            except recovery.RecoveryError:
                pass
        shutil.rmtree(tmp_path, ignore_errors=True)
