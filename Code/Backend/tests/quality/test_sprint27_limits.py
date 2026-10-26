"""Shared rate-limit, proxy-header, and failure-boundary coverage."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import rate_limits
from app.core.config import ROOT, get_settings
from app.core.errors import DomainError
from app.db.session import engine
from app.operations_models import RateLimitBucket


SECRET = "sprint27-test-secret-0123456789abcdef"
CLIENT_IP = "203.0.113.17"
ACTOR_ID = "fictional-account-7d615676"

_LIMIT_CHILD = r"""
import sys
from fastapi import Request
from app import rate_limits
from app.core.errors import DomainError

rate_limits.IP_REQUESTS_PER_MINUTE = 1
ip = sys.argv[1]
path = "/api/v1/events"
request = Request({
    "type": "http", "http_version": "1.1", "method": "GET",
    "scheme": "http", "path": path, "raw_path": path.encode(),
    "query_string": b"", "headers": [(b"host", b"testserver")],
    "client": (ip, 12345), "server": ("testserver", 80),
})
try:
    rate_limits.check_ip(request)
except DomainError as error:
    if error.code == "rate_limited":
        print(f"limited:{error.retry_after}:{type(error.retry_after).__name__}")
    else:
        print(error.code)
else:
    print("allowed")
"""


def _request(
    path="/api/v1/events",
    method="GET",
    *,
    client_ip=CLIENT_IP,
    headers=(),
):
    raw_headers = [(b"host", b"testserver"), *headers]
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_ip, 12345),
        "server": ("testserver", 80),
    })


def _enable_test_limits(monkeypatch, *, trusted_proxy="none"):
    monkeypatch.setattr(
        rate_limits,
        "get_settings",
        lambda: SimpleNamespace(
            rate_limit_enabled=True,
            rate_limit_secret=SECRET,
            trusted_proxy=trusted_proxy,
        ),
    )


@pytest.fixture
def process_rate_settings(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_SECRET", SECRET)
    monkeypatch.setenv("TRUSTED_PROXY", "none")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _run_limiter_process(client_ip):
    return subprocess.run(
        [sys.executable, "-c", _LIMIT_CHILD, client_ip],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_koyeb_uses_the_last_address_across_duplicate_forwarded_headers(monkeypatch):
    _enable_test_limits(monkeypatch, trusted_proxy="koyeb")
    captured = []
    monkeypatch.setattr(rate_limits, "_apply_limits", lambda buckets: captured.extend(buckets))

    rate_limits.check_ip(_request(headers=[
        (b"x-forwarded-for", b"192.0.2.80"),
        (b"x-forwarded-for", b"198.51.100.41, 203.0.113.91"),
    ]))

    assert captured == [
        (rate_limits._bucket_key(SECRET, "ip", "203.0.113.91"), 600),
    ]
    assert "192.0.2.80" not in captured[0][0]
    assert "203.0.113.91" not in captured[0][0]

    with pytest.raises(DomainError) as malformed:
        rate_limits.check_ip(_request(headers=[
            (b"x-forwarded-for", b"not-an-ip"),
            (b"x-forwarded-for", b"203.0.113.91"),
        ]))
    assert (malformed.value.code, malformed.value.status) == ("rate_limit_unavailable", 503)

    with pytest.raises(DomainError) as missing:
        rate_limits.check_ip(_request())
    assert (missing.value.code, missing.value.status) == ("rate_limit_unavailable", 503)


def test_untrusted_forwarding_headers_are_ignored(monkeypatch):
    _enable_test_limits(monkeypatch, trusted_proxy="none")
    captured = []
    monkeypatch.setattr(rate_limits, "_apply_limits", lambda buckets: captured.extend(buckets))

    rate_limits.check_ip(_request(headers=[
        (b"x-forwarded-for", b"malformed, 198.51.100.41"),
        (b"x-forwarded-for", b"192.0.2.80"),
    ]))

    assert captured == [(rate_limits._bucket_key(SECRET, "ip", CLIENT_IP), 600)]


def test_account_limits_and_sensitive_write_bucket_are_scoped_and_deduplicated(monkeypatch):
    _enable_test_limits(monkeypatch)
    captured = []
    monkeypatch.setattr(rate_limits, "_apply_limits", lambda buckets: captured.append(tuple(buckets)))
    actor = SimpleNamespace(user_id=ACTOR_ID)

    read_request = _request()
    rate_limits.check_account(read_request, actor)
    rate_limits.check_account(read_request, actor)
    report_request = _request("/api/v1/events/event-1/event-reports", "POST")
    media_request = _request("/api/v1/organizations/org-1/logo", "DELETE")
    rate_limits.check_account(report_request, actor)
    rate_limits.check_account(media_request, actor)

    assert captured[0] == ((rate_limits._bucket_key(SECRET, "account-read", ACTOR_ID), 120),)
    assert captured[1][0] == (rate_limits._bucket_key(SECRET, "account-write", ACTOR_ID), 60)
    assert captured[1][1] == (rate_limits._bucket_key(SECRET, "sensitive-write", ACTOR_ID), 10)
    assert captured[2][1] == captured[1][1]
    assert all(len(key) <= 80 and ACTOR_ID not in key for call in captured for key, _ in call)
    assert len(captured) == 3


def test_options_health_and_ready_paths_skip_limit_checks(monkeypatch):
    _enable_test_limits(monkeypatch)
    monkeypatch.setattr(
        rate_limits,
        "_apply_limits",
        lambda _buckets: pytest.fail("excluded request reached the database limiter"),
    )
    actor = SimpleNamespace(user_id=ACTOR_ID)

    for request in (
        _request("/api/v1/events", "OPTIONS"),
        _request("/health"),
        _request("/ready"),
        _request("/docs"),
    ):
        assert rate_limits.check_ip(request) is None
        assert rate_limits.check_account(request, actor) is None


def test_database_outage_fails_closed_and_does_not_cache_account_failure(monkeypatch):
    _enable_test_limits(monkeypatch)
    attempts = 0

    def unavailable_database():
        nonlocal attempts
        attempts += 1
        raise OSError("database unavailable")

    monkeypatch.setattr(rate_limits, "session_factory", unavailable_database)
    with pytest.raises(DomainError) as ip_error:
        rate_limits.check_ip(_request())
    assert (ip_error.value.code, ip_error.value.status) == ("rate_limit_unavailable", 503)

    request = _request("/api/v1/events", "POST")
    actor = SimpleNamespace(user_id=ACTOR_ID)
    for _ in range(2):
        with pytest.raises(DomainError) as account_error:
            rate_limits.check_account(request, actor)
        assert (account_error.value.code, account_error.value.status) == ("rate_limit_unavailable", 503)
    assert attempts == 3


def test_limit_state_survives_a_process_restart(monkeypatch, process_rate_settings):
    monkeypatch.setattr(rate_limits, "IP_REQUESTS_PER_MINUTE", 1)
    rate_limits.check_ip(_request())

    restarted = _run_limiter_process(CLIENT_IP)

    assert restarted.returncode == 0, restarted.stderr
    outcome, retry_after, retry_type = restarted.stdout.strip().split(":")
    assert outcome == "limited"
    assert retry_type == "int"
    assert int(retry_after) >= 1


def test_two_processes_cannot_spend_the_same_last_token(db, monkeypatch, process_rate_settings):
    monkeypatch.setattr(rate_limits, "IP_REQUESTS_PER_MINUTE", 1)
    key = rate_limits._bucket_key(SECRET, "ip", CLIENT_IP)
    current = db.scalar(select(func.now())).astimezone(timezone.utc)
    db.add(RateLimitBucket(
        key=key,
        tokens=1.0,
        updated_at=current,
        expires_at=current + timedelta(hours=24),
    ))
    db.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: _run_limiter_process(CLIENT_IP), range(2)))

    assert all(result.returncode == 0 for result in results)
    outcomes = [result.stdout.strip() for result in results]
    assert outcomes.count("allowed") == 1
    limited = next(outcome for outcome in outcomes if outcome.startswith("limited:"))
    _, retry_after, retry_type = limited.split(":")
    assert retry_type == "int"
    assert int(retry_after) >= 1


def test_expiry_cleanup_removes_no_more_than_one_hundred_rows(db, monkeypatch, process_rate_settings):
    current = db.scalar(select(func.now())).astimezone(timezone.utc)
    expired_at = current - timedelta(seconds=1)
    db.add_all([
        RateLimitBucket(
            key=f"expired:{index:03d}",
            tokens=0.0,
            updated_at=expired_at,
            expires_at=expired_at,
        )
        for index in range(150)
    ])
    db.commit()

    rate_limits.check_ip(_request())

    remaining = db.scalar(
        select(func.count()).select_from(RateLimitBucket).where(RateLimitBucket.expires_at <= current)
    )
    assert remaining == 50


def test_account_limiter_reuses_the_request_session_without_a_new_checkout(
    db, monkeypatch, process_rate_settings
):
    db.scalar(select(func.now()))
    factory_calls = 0

    def unexpected_checkout():
        nonlocal factory_calls
        factory_calls += 1
        raise AssertionError("the supplied request session should be reused")

    monkeypatch.setattr(rate_limits, "session_factory", unexpected_checkout)

    assert rate_limits.check_account(_request(), SimpleNamespace(user_id=ACTOR_ID), db=db) is None
    assert factory_calls == 0
    assert not db.in_transaction()
    assert db.scalar(select(func.now())) is not None


def test_account_limiter_rejects_pending_request_session_changes_without_committing(
    db, process_rate_settings
):
    now = db.scalar(select(func.clock_timestamp())).astimezone(timezone.utc)
    pending = RateLimitBucket(
        key="uncommitted-auth-change",
        tokens=1.0,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(pending)

    with pytest.raises(DomainError) as error:
        rate_limits.check_account(
            _request("/api/v1/events", "POST"),
            SimpleNamespace(user_id=ACTOR_ID),
            db=db,
        )

    assert (error.value.code, error.value.status) == ("rate_limit_unavailable", 503)
    assert pending in db.new
    db.rollback()
    with Session(engine(), expire_on_commit=False) as verify_db:
        assert verify_db.get(RateLimitBucket, pending.key) is None


def test_account_429_commits_limiter_state_and_leaves_request_session_reusable(
    db, process_rate_settings
):
    key = rate_limits._bucket_key(SECRET, "account-write", ACTOR_ID)
    now = db.scalar(select(func.clock_timestamp())).astimezone(timezone.utc)
    future = now + timedelta(hours=1)
    db.add(RateLimitBucket(
        key=key,
        tokens=0.0,
        updated_at=future,
        expires_at=now + timedelta(hours=24),
    ))
    db.commit()
    db.scalar(select(func.now()))

    with pytest.raises(DomainError) as error:
        rate_limits.check_account(
            _request("/api/v1/events", "POST"),
            SimpleNamespace(user_id=ACTOR_ID),
            db=db,
        )

    assert (error.value.code, error.value.status) == ("rate_limited", 429)
    assert isinstance(error.value.retry_after, int) and error.value.retry_after >= 1
    assert not db.in_transaction()
    with Session(engine(), expire_on_commit=False) as verify_db:
        stored = verify_db.get(RateLimitBucket, key)
        assert stored is not None
        assert stored.tokens == 0.0
        assert stored.updated_at < future
    assert db.scalar(select(func.clock_timestamp())) is not None


def test_active_bucket_keeps_its_original_expiry(db, process_rate_settings):
    client_ip = "198.51.100.29"
    key = rate_limits._bucket_key(SECRET, "ip", client_ip)

    rate_limits.check_ip(_request(client_ip=client_ip))
    original_expiry = db.scalar(
        select(RateLimitBucket.expires_at).where(RateLimitBucket.key == key)
    )
    rate_limits.check_ip(_request(client_ip=client_ip))
    db.expire_all()
    after_activity = db.scalar(
        select(RateLimitBucket.expires_at).where(RateLimitBucket.key == key)
    )

    assert after_activity == original_expiry
