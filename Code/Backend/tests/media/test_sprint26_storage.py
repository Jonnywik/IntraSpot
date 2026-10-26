from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import DomainError
from app.db.session import engine
from app.domains.media import reconciliation, storage
from app.domains.media import service as media_service
from app.domains.media.models import MediaAsset
from app.domains.media.storage_models import MediaObject


def _assert_test_database():
    url = make_url(engine().url)
    assert url.database == 'intraspot_mvp_test'
    assert url.host in {'127.0.0.1', 'localhost'} and url.port == 5433


class _Response:
    def __init__(self, body=b''):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


def _supabase_settings():
    return SimpleNamespace(
        environment='hosted',
        media_provider='supabase',
        media_bucket='intraspot-media',
        supabase_storage_secret='sb_secret_test_only_1234567890',
        supabase_url='https://test-project.supabase.co',
    )


def test_private_supabase_upload_and_read_use_apikey_only(monkeypatch):
    _assert_test_database()
    storage._bucket_verified_at.clear()
    monkeypatch.setattr(storage, 'get_settings', _supabase_settings)
    payload = b'webp fixture'
    requests = []

    def mock_open(request):
        requests.append(request)
        if request.full_url.endswith('/storage/v1/bucket/intraspot-media'):
            return _Response(b'{"name":"intraspot-media","public":false}')
        if request.get_method() == 'POST':
            return _Response()
        return _Response(payload)

    monkeypatch.setattr(storage, '_open_http', mock_open)
    org_id = str(uuid4())
    media_id = storage.store_webp(payload, org_id=org_id)
    assert storage.read_webp(media_id) == payload

    assert [request.get_method() for request in requests] == ['GET', 'POST', 'GET']
    assert requests[0].get_header('Apikey') == _supabase_settings().supabase_storage_secret
    assert requests[1].get_header('Apikey') == _supabase_settings().supabase_storage_secret
    assert requests[1].get_header('X-upsert') == 'false'
    assert all(request.get_header('Authorization') is None for request in requests)
    assert requests[1].full_url.endswith(f'/storage/v1/object/intraspot-media/{media_id}.webp')
    storage._bucket_verified_at.clear()


def test_public_bucket_fails_closed_before_object_io_and_hides_secret(monkeypatch):
    _assert_test_database()
    storage._bucket_verified_at.clear()
    settings = _supabase_settings()
    monkeypatch.setattr(storage, 'get_settings', lambda: settings)
    requests = []

    def mock_open(request):
        requests.append(request)
        return _Response(b'{"name":"intraspot-media","public":true}')

    monkeypatch.setattr(storage, '_open_http', mock_open)
    with pytest.raises(storage.MediaStorageError) as caught:
        storage.store_webp(b'webp fixture', org_id=str(uuid4()))

    assert 'sb_secret_' not in str(caught.value)
    assert len(requests) == 1 and requests[0].get_method() == 'GET'
    storage._bucket_verified_at.clear()


def test_concurrent_reservations_serialize_org_quota(monkeypatch, tmp_path):
    _assert_test_database()
    settings = get_settings()
    monkeypatch.setattr(settings, 'media_root', tmp_path)
    monkeypatch.setattr(storage, 'ORG_QUOTA_BYTES', 10)
    monkeypatch.setattr(storage, 'GLOBAL_QUOTA_BYTES', 100)
    barrier = Barrier(2)
    org_id = str(uuid4())

    def upload():
        barrier.wait(timeout=10)
        try:
            return ('stored', storage.store_webp(b'123456', org_id=org_id))
        except storage.MediaQuotaExceeded as error:
            return ('quota', error.status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: upload(), range(2)))

    assert sorted(result[0] for result in outcomes) == ['quota', 'stored']
    assert next(result[1] for result in outcomes if result[0] == 'quota') == 413
    with Session(engine()) as session:
        total = session.scalar(select(MediaObject.byte_size).where(MediaObject.org_id == org_id))
    assert total == 6


def test_global_quota_includes_ledger_rows_from_other_organizations(monkeypatch):
    _assert_test_database()
    monkeypatch.setattr(storage, 'ORG_QUOTA_BYTES', 100)
    monkeypatch.setattr(storage, 'GLOBAL_QUOTA_BYTES', 10)
    other_id = str(uuid4())
    other_org_id = str(uuid4())
    with Session(engine()) as session, session.begin():
        session.add(MediaObject(
            id=other_id,
            org_id=other_org_id,
            provider='local',
            object_key=f'{other_id}.webp',
            byte_size=6,
            status='stored',
        ))

    with pytest.raises(storage.MediaQuotaExceeded) as caught:
        storage.store_webp(b'12345', org_id=str(uuid4()))
    assert caught.value.status_code == 409


def test_failed_object_write_keeps_committed_reservation_charged(monkeypatch, tmp_path):
    _assert_test_database()
    settings = get_settings()
    monkeypatch.setattr(settings, 'media_root', tmp_path)
    media_id = uuid4()
    monkeypatch.setattr(storage, 'uuid4', lambda: media_id)

    def fail_write(*_args):
        raise storage.MediaStorageError('synthetic write failure')

    monkeypatch.setattr(storage, '_write_local_to_id', fail_write)
    with pytest.raises(storage.MediaStorageError):
        storage.store_webp(b'webp fixture', org_id=str(uuid4()))

    with Session(engine()) as session:
        reservation = session.get(MediaObject, str(media_id))
        assert reservation is not None
        assert reservation.status == 'reserved'
        assert reservation.byte_size == len(b'webp fixture')


def test_mark_stored_is_idempotent_after_reconciliation():
    _assert_test_database()
    media_id = str(uuid4())
    with Session(engine()) as session, session.begin():
        session.add(MediaObject(
            id=media_id,
            org_id=str(uuid4()),
            provider='local',
            object_key=f'{media_id}.webp',
            byte_size=12,
            status='stored',
        ))

    storage._mark_stored(media_id)
    with Session(engine()) as session:
        stored = session.get(MediaObject, media_id)
        assert stored is not None and stored.status == 'stored'
        assert stored.last_seen_at is not None


def test_read_webp_uses_the_authorized_request_session(db, monkeypatch, tmp_path):
    _assert_test_database()
    settings = get_settings()
    monkeypatch.setattr(settings, 'media_root', tmp_path)
    media_id = str(uuid4())
    content = b'webp fixture'
    (tmp_path / f'{media_id}.webp').write_bytes(content)
    db.add(MediaObject(
        id=media_id,
        org_id=str(uuid4()),
        provider='local',
        object_key=f'{media_id}.webp',
        byte_size=len(content),
        status='stored',
    ))
    db.flush()
    db.expire_all()

    def unexpected_session(*_args, **_kwargs):
        pytest.fail('read_webp opened a second SQLAlchemy session')

    monkeypatch.setattr(storage, 'Session', unexpected_session)
    assert storage.read_webp(media_id, db=db) == content


def test_ledger_database_failure_is_not_treated_as_legacy_file(monkeypatch, tmp_path):
    _assert_test_database()
    settings = get_settings()
    monkeypatch.setattr(settings, 'media_root', tmp_path)
    media_id = str(uuid4())
    (tmp_path / f'{media_id}.webp').write_bytes(b'legacy bytes')

    class BrokenSession:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            raise RuntimeError('synthetic database outage')

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(storage, 'engine', lambda: object())
    monkeypatch.setattr(storage, 'Session', BrokenSession)
    with pytest.raises(storage.MediaStorageError):
        storage.read_webp(media_id)


def test_authorized_read_maps_ledger_outage_to_503(db, make_user, make_org, monkeypatch):
    _assert_test_database()
    owner = make_user()
    org = make_org(owner=owner, accreditation_status='approved')
    media_id = str(uuid4())
    db.add(MediaAsset(
        id=media_id,
        org_id=org.id,
        kind='logo',
        width=1,
        height=1,
        byte_size=12,
        created_by=owner.id,
    ))
    db.flush()
    org.logo_media_id = media_id
    db.commit()

    def unavailable(_media_id, db=None):
        assert db is not None
        raise storage.MediaStorageError('synthetic database outage')

    monkeypatch.setattr(storage, '_find_media_object', unavailable)
    monkeypatch.setattr(storage, '_read_local', lambda *_args: pytest.fail('legacy fallback ran after DB failure'))
    with pytest.raises(DomainError) as caught:
        media_service.authorize_and_read(db, None, media_id)
    assert caught.value.status == 503


def test_store_and_read_work_while_parent_holds_organization_lock(make_org, monkeypatch, tmp_path):
    _assert_test_database()
    settings = get_settings()
    monkeypatch.setattr(settings, 'media_root', tmp_path)
    org = make_org()
    content = b'webp fixture'

    with Session(engine()) as parent, parent.begin():
        from app.domains.organizations.models import Organization

        locked = parent.scalar(
            select(Organization).where(Organization.id == org.id).with_for_update()
        )
        assert locked is not None
        media_id = storage.store_webp(content, org_id=org.id)
        assert storage.read_webp(media_id, db=parent) == content


def test_reconciliation_dry_run_does_not_change_ledger_or_delete_object(monkeypatch, tmp_path):
    _assert_test_database()
    settings = get_settings()
    monkeypatch.setattr(settings, 'media_root', tmp_path)
    media_id = str(uuid4())
    org_id = str(uuid4())
    object_path = tmp_path / f'{media_id}.webp'
    object_path.write_bytes(b'webp fixture')
    with Session(engine()) as session, session.begin():
        session.add(MediaObject(
            id=media_id,
            org_id=org_id,
            provider='local',
            object_key=f'{media_id}.webp',
            byte_size=12,
            status='stored',
        ))
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    dry_run = reconciliation.reconcile_media(at=start)
    assert dry_run[0]['orphan_seen_count'] == 1
    assert dry_run[0]['orphan_candidate'] is False
    with Session(engine()) as session:
        unchanged = session.get(MediaObject, media_id)
        assert unchanged.orphan_seen_at is None and unchanged.orphan_seen_count == 0

    reconciliation.reconcile_media(apply=True, at=start)
    reconciliation.reconcile_media(apply=True, at=start + timedelta(days=7))
    candidate = reconciliation.reconcile_media(at=start + timedelta(days=14))[0]
    assert candidate['orphan_candidate'] is True
    with Session(engine()) as session:
        retained = session.get(MediaObject, media_id)
        assert retained is not None and retained.orphan_seen_count == 2
    assert object_path.read_bytes() == b'webp fixture'


def test_missing_objects_age_only_when_unreferenced_and_remain_charged(
    db, make_user, make_org, monkeypatch, tmp_path,
):
    _assert_test_database()
    settings = get_settings()
    monkeypatch.setattr(settings, 'media_root', tmp_path)
    owner = make_user()
    org = make_org(owner=owner)
    protected_id = str(uuid4())
    db.add(MediaAsset(
        id=protected_id,
        org_id=org.id,
        kind='logo',
        width=1,
        height=1,
        byte_size=12,
        created_by=owner.id,
    ))
    db.flush()
    org.logo_media_id = protected_id
    db.commit()

    unreferenced_id = str(uuid4())
    with Session(engine()) as session, session.begin():
        for media_id in (protected_id, unreferenced_id):
            session.add(MediaObject(
                id=media_id,
                org_id=org.id,
                provider='local',
                object_key=f'{media_id}.webp',
                byte_size=12,
                status='stored',
            ))

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    manifest = []
    for day in (0, 7, 14):
        manifest = reconciliation.reconcile_media(
            apply=True,
            at=start + timedelta(days=day),
        )
    by_id = {entry['id']: entry for entry in manifest}
    assert by_id[unreferenced_id]['observation'] == 'missing_unreferenced'
    assert by_id[unreferenced_id]['orphan_candidate'] is True
    assert by_id[unreferenced_id]['charged'] is True
    assert by_id[protected_id]['observation'] == 'missing_protected'
    assert by_id[protected_id]['orphan_candidate'] is False
    assert by_id[protected_id]['charged'] is True
    with Session(engine()) as session:
        assert session.get(MediaObject, unreferenced_id) is not None
        assert session.get(MediaObject, protected_id) is not None
