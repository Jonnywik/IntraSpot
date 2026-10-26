"""Shared PostgreSQL-backed request rate limits."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta, timezone

from fastapi import Request
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import DomainError
from app.db.session import session_factory
from app.operations_models import RateLimitBucket


IP_REQUESTS_PER_MINUTE = 600
ACCOUNT_READS_PER_MINUTE = 120
ACCOUNT_WRITES_PER_MINUTE = 60
SENSITIVE_WRITES_PER_MINUTE = 10

_BUCKET_TTL = timedelta(hours=24)
_EXPIRY_DELETE_BATCH = 100
_ACCOUNT_STATE_KEY = "intraspot.rate_limit.account_buckets"


def _unavailable() -> DomainError:
    return DomainError(
        "rate_limit_unavailable",
        "The service is temporarily unavailable. Please retry shortly.",
        503,
    )


def _enabled_settings():
    try:
        settings = get_settings()
    except Exception as exc:
        raise _unavailable() from exc
    if not settings.rate_limit_enabled:
        return None
    secret = settings.rate_limit_secret
    if not secret or len(secret) < 32:
        raise _unavailable()
    return settings, secret


def _eligible(request: Request) -> bool:
    method = request.method.upper()
    path = request.url.path
    return (
        method != "OPTIONS"
        and path not in {"/health", "/ready"}
        and (path == "/api/v1" or path.startswith("/api/v1/"))
    )


def _normalize_ip(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip() or "%" in value:
        raise ValueError("invalid IP address")
    address = ipaddress.ip_address(value.strip())
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return str(address)


def _client_ip(request: Request, trusted_proxy: str) -> str:
    client = request.client
    peer_ip = _normalize_ip(client.host if client is not None else None)
    if trusted_proxy == "none":
        return peer_ip
    if trusted_proxy != "koyeb":
        raise ValueError("invalid trusted proxy")

    forwarded_fields = []
    for name, value in request.scope.get("headers", ()):
        if not isinstance(name, bytes) or not isinstance(value, bytes):
            raise ValueError("invalid raw header")
        if name.lower() == b"x-forwarded-for":
            forwarded_fields.append(value.decode("ascii"))
    if not forwarded_fields:
        raise ValueError("Koyeb forwarding header is missing")

    # Koyeb appends the connecting client after any client-supplied X-Forwarded-For values.
    chain = ",".join(forwarded_fields).split(",")
    addresses = [_normalize_ip(item) for item in chain]
    return addresses[-1]


def _bucket_key(secret: str, category: str, identity: str) -> str:
    message = f"{category}\0{identity}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"{category}:{digest}"


def _database_time(db):
    current = db.scalar(select(func.clock_timestamp()))
    if current is None or current.tzinfo is None:
        raise RuntimeError("database clock is unavailable")
    return current.astimezone(timezone.utc)


@contextmanager
def _limiter_transaction(db: Session | None = None) -> Iterator[Session]:
    if db is None:
        with session_factory()() as owned_db:
            with owned_db.begin():
                yield owned_db
        return

    if db.new or db.dirty or db.deleted:
        raise RuntimeError("request session has pending changes")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _apply_limits(buckets: list[tuple[str, int]], db: Session | None = None) -> None:
    limits = dict(buckets)
    if not limits:
        return
    if len(limits) != len(buckets) or any(capacity < 1 for capacity in limits.values()):
        raise _unavailable()

    keys = sorted(limits)
    try:
        with _limiter_transaction(db) as session:
            session.execute(text("SET LOCAL lock_timeout = '500ms'"))
            session.execute(text("SET LOCAL statement_timeout = '2000ms'"))
            cleanup_time = _database_time(session)
            cleanup_expiry = cleanup_time + _BUCKET_TTL

            expired = (
                select(RateLimitBucket.key)
                .where(RateLimitBucket.expires_at <= cleanup_time)
                .order_by(RateLimitBucket.expires_at, RateLimitBucket.key)
                .limit(_EXPIRY_DELETE_BATCH)
                .with_for_update(skip_locked=True)
            )
            session.execute(delete(RateLimitBucket).where(RateLimitBucket.key.in_(expired)))

            session.execute(
                insert(RateLimitBucket)
                .values([
                    {
                        "key": key,
                        "tokens": limits[key],
                        "updated_at": cleanup_time,
                        "expires_at": cleanup_expiry,
                    }
                    for key in keys
                ])
                .on_conflict_do_nothing(index_elements=[RateLimitBucket.key])
            )

            rows = session.scalars(
                select(RateLimitBucket)
                .where(RateLimitBucket.key.in_(keys))
                .order_by(RateLimitBucket.key)
                .with_for_update()
            ).all()
            if len(rows) != len(keys):
                raise RuntimeError("rate limit buckets are unavailable")

            now = _database_time(session)
            expires_at = now + _BUCKET_TTL
            available_by_key = {}
            expired_by_key = {}
            retry_after = 0
            for row in rows:
                capacity = limits[row.key]
                expired = row.expires_at <= now
                expired_by_key[row.key] = expired
                if expired:
                    available = float(capacity)
                else:
                    elapsed = max(0.0, (now - row.updated_at).total_seconds())
                    available = min(
                        float(capacity),
                        max(0.0, float(row.tokens) + elapsed * capacity / 60.0),
                    )
                available_by_key[row.key] = available
                if available < 1.0:
                    retry_after = max(
                        retry_after,
                        math.ceil((1.0 - available) * 60.0 / capacity),
                    )

            consume = retry_after == 0
            for row in rows:
                available = available_by_key[row.key]
                row.tokens = available - 1.0 if consume else available
                row.updated_at = now
                if expired_by_key[row.key]:
                    row.expires_at = expires_at
    except Exception as exc:
        raise _unavailable() from exc

    if retry_after:
        error = DomainError(
            "rate_limited",
            "Too many requests. Please retry later.",
            429,
        )
        error.retry_after = max(1, retry_after)
        raise error


def check_ip(request: Request) -> None:
    if not _eligible(request):
        return None
    configured = _enabled_settings()
    if configured is None:
        return None
    settings, secret = configured
    try:
        client_ip = _client_ip(request, settings.trusted_proxy)
    except (AttributeError, TypeError, UnicodeError, ValueError) as exc:
        raise _unavailable() from exc
    _apply_limits([
        (_bucket_key(secret, "ip", client_ip), IP_REQUESTS_PER_MINUTE),
    ])
    return None


def _is_sensitive_write(path: str) -> bool:
    segments = path.lower().rstrip("/").split("/")
    return any(
        segment == "media"
        or segment in {"banner", "logo"}
        or segment == "reports"
        or segment.endswith("-reports")
        for segment in segments
    )


def check_account(request: Request, actor, db: Session | None = None) -> None:
    if not _eligible(request):
        return None
    configured = _enabled_settings()
    if configured is None:
        return None
    _, secret = configured

    actor_id = getattr(actor, "user_id", None)
    if actor_id is None or not str(actor_id):
        raise _unavailable()

    is_read = request.method.upper() in {"GET", "HEAD"}
    category = "account-read" if is_read else "account-write"
    capacity = ACCOUNT_READS_PER_MINUTE if is_read else ACCOUNT_WRITES_PER_MINUTE
    account_identity = str(actor_id)
    account_key = _bucket_key(secret, category, account_identity)
    buckets = [(account_key, capacity)]
    if not is_read and _is_sensitive_write(request.url.path):
        buckets.append((
            _bucket_key(secret, "sensitive-write", account_identity),
            SENSITIVE_WRITES_PER_MINUTE,
        ))

    try:
        state = request.scope.setdefault("state", {})
        checked = state.setdefault(_ACCOUNT_STATE_KEY, set())
        if account_key in checked:
            return None
        checked.add(account_key)
    except Exception as exc:
        raise _unavailable() from exc

    try:
        if db is None:
            _apply_limits(buckets)
        else:
            _apply_limits(buckets, db=db)
    except Exception:
        checked.discard(account_key)
        raise
    return None
