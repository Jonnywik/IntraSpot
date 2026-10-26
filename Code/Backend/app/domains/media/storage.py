from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import engine
from app.domains.media.models import MediaAsset
from app.domains.media.storage_models import MediaObject

ORG_QUOTA_BYTES = 50 * 1024 * 1024
GLOBAL_QUOTA_BYTES = 500 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 5
MAX_BUCKET_RESPONSE_BYTES = 4096
BUCKET_CACHE_SECONDS = 30
_ADVISORY_LOCK_KEYS = (1296388935, 5066052)
_bucket_lock = threading.Lock()
_bucket_verified_at: dict[tuple[str, str], float] = {}


class MediaStorageError(OSError):
    """A media object could not be safely written, read, or verified."""


class MediaQuotaExceeded(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_http_opener = urllib.request.build_opener(_NoRedirectHandler())


def _open_http(request: urllib.request.Request):
    return _http_opener.open(request, timeout=HTTP_TIMEOUT_SECONDS)


def lock_media_quota(session: Session) -> None:
    session.execute(
        text('SELECT pg_advisory_xact_lock(:key_one, :key_two)'),
        {'key_one': _ADVISORY_LOCK_KEYS[0], 'key_two': _ADVISORY_LOCK_KEYS[1]},
    )


def _settings_value(name: str, default=None):
    return getattr(get_settings(), name, default)


def _provider() -> str:
    value = _settings_value('media_provider', 'local')
    if value not in {'local', 'supabase'}:
        raise MediaStorageError('Media storage configuration is unavailable')
    return value


def _supabase_settings() -> tuple[str, str, str]:
    settings = get_settings()
    root = getattr(settings, 'supabase_url', None)
    bucket = getattr(settings, 'media_bucket', 'intraspot-media')
    secret = getattr(settings, 'supabase_storage_secret', None)
    if not isinstance(root, str) or not isinstance(bucket, str) or not isinstance(secret, str):
        raise MediaStorageError('Private media storage is unavailable')
    parsed = urlsplit(root)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment):
        raise MediaStorageError('Private media storage is unavailable')
    if not re.fullmatch(r'sb_secret_[A-Za-z0-9_-]{10,256}', secret):
        raise MediaStorageError('Private media storage is unavailable')
    return root.rstrip('/'), bucket, secret


def _bucket_url(root: str, bucket: str) -> str:
    return f'{root}/storage/v1/bucket/{quote(bucket, safe="")}'


def _object_url(root: str, bucket: str, object_key: str, *, info: bool = False) -> str:
    endpoint = 'object/info' if info else 'object'
    return f'{root}/storage/v1/{endpoint}/{quote(bucket, safe="")}/{quote(object_key, safe="")}'


def _private_bucket_verified() -> None:
    root, bucket, secret = _supabase_settings()
    cache_key = (root, bucket)
    with _bucket_lock:
        checked_at = _bucket_verified_at.get(cache_key)
        if checked_at is not None and time.monotonic() - checked_at < BUCKET_CACHE_SECONDS:
            return
        request = urllib.request.Request(
            _bucket_url(root, bucket), headers={'apikey': secret, 'Accept': 'application/json'}, method='GET',
        )
        try:
            with _open_http(request) as response:
                body = response.read(MAX_BUCKET_RESPONSE_BYTES + 1)
            if len(body) > MAX_BUCKET_RESPONSE_BYTES:
                raise MediaStorageError('Private media bucket could not be verified')
            bucket_info = json.loads(body)
        except MediaStorageError:
            raise
        except Exception:
            _bucket_verified_at.pop(cache_key, None)
            raise MediaStorageError('Private media bucket could not be verified') from None
        if not isinstance(bucket_info, dict) or bucket_info.get('name') != bucket or bucket_info.get('public') is not False:
            _bucket_verified_at.pop(cache_key, None)
            raise MediaStorageError('Private media bucket could not be verified')
        _bucket_verified_at[cache_key] = time.monotonic()


def _reserve_media_object(media_id: str, org_id: str, provider: str, object_key: str, byte_size: int) -> bool:
    try:
        with Session(engine(), expire_on_commit=False) as session:
            with session.begin():
                lock_media_quota(session)
                org_ledger = session.scalar(
                    select(func.coalesce(func.sum(MediaObject.byte_size), 0)).where(MediaObject.org_id == org_id)
                ) or 0
                all_ledger = session.scalar(
                    select(func.coalesce(func.sum(MediaObject.byte_size), 0))
                ) or 0
                legacy_present = (
                    select(MediaObject.id)
                    .where(MediaObject.id == MediaAsset.id)
                    .correlate(MediaAsset)
                    .exists()
                )
                org_legacy = session.scalar(
                    select(func.coalesce(func.sum(MediaAsset.byte_size), 0)).where(
                        MediaAsset.org_id == org_id, ~legacy_present,
                    )
                ) or 0
                all_legacy = session.scalar(
                    select(func.coalesce(func.sum(MediaAsset.byte_size), 0)).where(~legacy_present)
                ) or 0
                if int(org_ledger) + int(org_legacy) + byte_size > ORG_QUOTA_BYTES:
                    raise MediaQuotaExceeded(413)
                if int(all_ledger) + int(all_legacy) + byte_size > GLOBAL_QUOTA_BYTES:
                    raise MediaQuotaExceeded(409)
                session.add(MediaObject(
                    id=media_id,
                    org_id=org_id,
                    provider=provider,
                    object_key=object_key,
                    byte_size=byte_size,
                    created_at=datetime.now(timezone.utc),
                    status='reserved',
                ))
                session.flush()
        return True
    except MediaQuotaExceeded:
        raise
    except IntegrityError:
        return False
    except Exception:
        raise MediaStorageError('Media storage is unavailable') from None


def _mark_stored(media_id: str) -> None:
    try:
        with Session(engine(), expire_on_commit=False) as session:
            with session.begin():
                result = session.execute(
                    update(MediaObject)
                    .where(MediaObject.id == media_id)
                    .values(status='stored', last_seen_at=datetime.now(timezone.utc))
                )
                if result.rowcount != 1:
                    raise MediaStorageError('Media reservation could not be finalized')
    except MediaStorageError:
        raise
    except Exception:
        # The object may already exist. Keep the committed reservation charged.
        raise MediaStorageError('Media reservation could not be finalized') from None


def _write_local_to_id(content: bytes, media_id: str) -> str:
    root = get_settings().media_root
    temporary_path: Path | None = None
    destination = root / f'{media_id}.webp'
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='wb', prefix='.media-', suffix='.tmp', dir=root, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        try:
            os.replace(temporary_path, destination)
            temporary_path = None
        except OSError:
            destination.unlink(missing_ok=True)
            raise
        return media_id
    except FileExistsError:
        raise
    except OSError:
        raise MediaStorageError from None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _store_unreserved_local(content: bytes) -> str:
    for _ in range(3):
        media_id = str(uuid4())
        try:
            return _write_local_to_id(content, media_id)
        except FileExistsError:
            continue
    raise MediaStorageError('Media storage is unavailable')


def _store_supabase(content: bytes, bucket: str, root: str, secret: str, object_key: str) -> None:
    request = urllib.request.Request(
        _object_url(root, bucket, object_key),
        data=content,
        headers={'apikey': secret, 'Content-Type': 'image/webp', 'x-upsert': 'false'},
        method='POST',
    )
    try:
        with _open_http(request) as response:
            response.read(4096)
    except Exception:
        raise MediaStorageError('Media storage is unavailable') from None


def store_webp(content: bytes, org_id: str | None = None) -> str:
    settings = get_settings()
    provider = _provider()
    if org_id is None:
        if provider != 'local' or settings.environment not in {'local', 'test'}:
            raise MediaStorageError('Organization-scoped media storage is required')
        return _store_unreserved_local(content)
    if not isinstance(org_id, str) or not org_id:
        raise MediaStorageError('Organization-scoped media storage is required')
    if not content:
        raise MediaStorageError('Media storage is unavailable')

    remote: tuple[str, str, str] | None = None
    if provider == 'supabase':
        _private_bucket_verified()
        remote = _supabase_settings()

    for _ in range(3):
        media_id = str(uuid4())
        object_key = f'{media_id}.webp'
        if provider == 'local' and (settings.media_root / object_key).exists():
            continue
        if not _reserve_media_object(media_id, org_id, provider, object_key, len(content)):
            continue
        if remote is None:
            try:
                _write_local_to_id(content, media_id)
            except FileExistsError:
                continue
        else:
            root, bucket, secret = remote
            _store_supabase(content, bucket, root, secret, object_key)
        _mark_stored(media_id)
        return media_id
    raise MediaStorageError('Media storage is unavailable')


def _parse_media_id(media_id: str) -> str | None:
    try:
        parsed = UUID(media_id)
    except (ValueError, AttributeError, TypeError):
        return None
    return str(parsed) if str(parsed) == media_id.lower() else None


def _valid_object_key(media_id: str, object_key: str) -> bool:
    return object_key == f'{media_id}.webp' and len(object_key) <= 128


def _read_local(media_id: str) -> bytes | None:
    try:
        path = get_settings().media_root / f'{media_id}.webp'
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0 or metadata.st_size > ORG_QUOTA_BYTES:
            return None
        with path.open('rb') as content_file:
            content = content_file.read(metadata.st_size + 1)
        return content if len(content) == metadata.st_size else None
    except FileNotFoundError:
        return None
    except OSError:
        raise MediaStorageError('Media storage is unavailable') from None


def _find_media_object(media_id: str, db: Session | None = None) -> MediaObject | None:
    try:
        if db is not None:
            return db.get(MediaObject, media_id)
        with Session(engine(), expire_on_commit=False) as session:
            return session.get(MediaObject, media_id)
    except Exception:
        raise MediaStorageError('Media metadata is unavailable') from None


def _read_supabase(media: MediaObject) -> bytes | None:
    root, bucket, secret = _supabase_settings()
    _private_bucket_verified()
    if media.byte_size <= 0 or media.byte_size > ORG_QUOTA_BYTES:
        return None
    request = urllib.request.Request(
        _object_url(root, bucket, media.object_key),
        headers={'apikey': secret, 'Accept': 'image/webp'},
        method='GET',
    )
    try:
        with _open_http(request) as response:
            content = response.read(media.byte_size + 1)
        if len(content) != media.byte_size:
            return None
        return content
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise MediaStorageError('Media storage is unavailable') from None
    except Exception:
        raise MediaStorageError('Media storage is unavailable') from None


def read_webp(media_id: str, db: Session | None = None) -> bytes | None:
    parsed_id = _parse_media_id(media_id)
    if parsed_id is None:
        return None
    media = _find_media_object(parsed_id, db=db)
    if media is None:
        return _read_local(parsed_id) if _provider() == 'local' else None
    if media.status != 'stored' or not _valid_object_key(parsed_id, media.object_key):
        return None
    if media.provider == 'local':
        content = _read_local(parsed_id)
        return content if content is not None and len(content) == media.byte_size else None
    if media.provider == 'supabase':
        return _read_supabase(media)
    return None


def object_exists(media: MediaObject) -> bool:
    if not _valid_object_key(media.id, media.object_key):
        raise MediaStorageError('Media object metadata is invalid')
    if media.provider == 'local':
        path = get_settings().media_root / media.object_key
        try:
            metadata = path.lstat()
            return stat.S_ISREG(metadata.st_mode) and metadata.st_size == media.byte_size
        except FileNotFoundError:
            return False
        except OSError:
            raise MediaStorageError('Media storage is unavailable') from None
    if media.provider != 'supabase':
        raise MediaStorageError('Media storage configuration is unavailable')
    root, bucket, secret = _supabase_settings()
    _private_bucket_verified()
    request = urllib.request.Request(
        _object_url(root, bucket, media.object_key, info=True),
        headers={'apikey': secret},
        method='HEAD',
    )
    try:
        with _open_http(request):
            return True
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise MediaStorageError('Media storage is unavailable') from None
    except Exception:
        raise MediaStorageError('Media storage is unavailable') from None
