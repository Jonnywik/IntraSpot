"""Bounded Render UAT configuration, startup, and edge IP handling."""

import pytest
from fastapi import Request
from pydantic import ValidationError

from app import rate_limits
from app.core.config import Settings
from app.core.errors import DomainError
from app import hosted_entrypoint
from tests.shared.test_sprint25_configuration import hosted_settings


SECRET = "render-hosting-test-secret-0123456789"
PEER_IP = "192.0.2.17"
CLIENT_IP = "203.0.113.91"


def _render_environment(**changes):
    return {
        "RENDER": "true",
        "RENDER_SERVICE_TYPE": "web",
        "RENDER_SERVICE_ID": "srv-" + "a" * 20,
        "RENDER_INSTANCE_ID": "instance-uat-1",
        "RENDER_EXTERNAL_HOSTNAME": "intraspot-uat.onrender.com",
        "RENDER_EXTERNAL_URL": "https://intraspot-uat.onrender.com",
        "PUBLIC_API_URL": "https://intraspot-uat.onrender.com",
        "TRUSTED_PROXY": "render",
        "PORT": "10000",
    } | changes


def _set_process_environment(monkeypatch, values):
    keys = {
        "RENDER", "RENDER_SERVICE_TYPE", "RENDER_SERVICE_ID", "RENDER_INSTANCE_ID",
        "RENDER_EXTERNAL_HOSTNAME", "RENDER_EXTERNAL_URL", "PUBLIC_API_URL",
        "TRUSTED_PROXY", "KOYEB_SERVICE_ID", "KOYEB_INSTANCE_ID", "PORT",
    }
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _request(headers=(), *, client_ip=PEER_IP):
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/events",
        "raw_path": b"/api/v1/events",
        "query_string": b"",
        "headers": [(b"host", b"testserver"), *headers],
        "client": (client_ip, 12345),
        "server": ("testserver", 80),
    })


def _enable_render_limiter(monkeypatch, trusted_proxy="render"):
    monkeypatch.setattr(
        rate_limits,
        "get_settings",
        lambda: type("TestSettings", (), {
            "rate_limit_enabled": True,
            "rate_limit_secret": SECRET,
            "trusted_proxy": trusted_proxy,
        })(),
    )


def test_render_hosted_configuration_keeps_existing_security_requirements(tmp_path):
    configured = hosted_settings(
        tmp_path,
        trusted_proxy="render",
        public_api_url="https://intraspot-uat.onrender.com",
    )
    assert configured.trusted_proxy == "render"
    assert configured.maintenance_enabled and configured.rate_limit_enabled
    assert configured.auth_provider == "supabase" and not configured.fixture_auth
    assert configured.media_provider == "supabase"

    for changes in (
        {"maintenance_enabled": False},
        {"rate_limit_enabled": False},
        {"rate_limit_secret": "short"},
        {"media_provider": "local"},
        {"public_api_url": "https://api.intraspot.example"},
    ):
        with pytest.raises(ValidationError):
            hosted_settings(tmp_path, **({
                "trusted_proxy": "render",
                "public_api_url": "https://intraspot-uat.onrender.com",
            } | changes))


def test_koyeb_hosted_configuration_remains_accepted(tmp_path):
    assert hosted_settings(tmp_path).trusted_proxy == "koyeb"


def test_local_profile_still_rejects_render_proxy(tmp_path):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="test",
            fixture_auth=True,
            database_url="postgresql+psycopg://unit:unit@127.0.0.1:5433/intraspot_mvp_test",
            trusted_proxy="render",
            jwt_public_key_file=tmp_path / "missing-key.pem",
        )


def test_render_entrypoint_uses_single_worker_without_proxy_headers(monkeypatch):
    calls = []
    _set_process_environment(monkeypatch, _render_environment())
    monkeypatch.setattr(hosted_entrypoint, "prepare_ca", lambda: calls.append("prepare_ca"))
    monkeypatch.setattr(hosted_entrypoint.os, "execvp", lambda program, args: calls.append((program, args)))

    hosted_entrypoint.main()

    assert calls == [
        "prepare_ca",
        ("uvicorn", [
            "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000",
            "--workers", "1", "--no-access-log", "--no-proxy-headers",
        ]),
    ]


@pytest.mark.parametrize(("key", "value"), [
    ("RENDER", "false"),
    ("TRUSTED_PROXY", "none"),
    ("TRUSTED_PROXY", "koyeb"),
    ("RENDER_SERVICE_TYPE", "worker"),
    ("RENDER_SERVICE_ID", "srv-" + "a" * 19),
    ("RENDER_SERVICE_ID", "srv-" + "A" * 20),
    ("RENDER_SERVICE_ID", "srv-" + "a" * 41),
    ("RENDER_INSTANCE_ID", "  \t"),
    ("RENDER_INSTANCE_ID", "i" * 129),
    ("RENDER_INSTANCE_ID", "instance\nforged"),
    ("RENDER_EXTERNAL_HOSTNAME", "api.example.com"),
    ("RENDER_EXTERNAL_HOSTNAME", "https://intraspot-uat.onrender.com"),
    ("RENDER_EXTERNAL_URL", "http://intraspot-uat.onrender.com"),
    ("RENDER_EXTERNAL_URL", "https://other.onrender.com"),
    ("RENDER_EXTERNAL_URL", "https://intraspot-uat.onrender.com/"),
    ("PUBLIC_API_URL", "https://other.onrender.com"),
    ("PUBLIC_API_URL", "https://intraspot-uat.onrender.com/"),
])
def test_render_entrypoint_rejects_invalid_provider_metadata(monkeypatch, key, value):
    environment = _render_environment(**{key: value})
    _set_process_environment(monkeypatch, environment)
    monkeypatch.setattr(hosted_entrypoint, "prepare_ca", lambda: pytest.fail("invalid identity reached CA setup"))
    monkeypatch.setattr(hosted_entrypoint.os, "execvp", lambda *_args: pytest.fail("invalid identity started Uvicorn"))

    with pytest.raises(SystemExit, match="Hosted startup configuration is invalid"):
        hosted_entrypoint.main()


def test_koyeb_entrypoint_keeps_uuid_checks_and_launch_flags(monkeypatch):
    calls = []
    _set_process_environment(monkeypatch, {
        "KOYEB_SERVICE_ID": "00000000-0000-4000-8000-000000000001",
        "KOYEB_INSTANCE_ID": "00000000-0000-4000-8000-000000000002",
        "TRUSTED_PROXY": "koyeb",
        "PORT": "8000",
    })
    monkeypatch.setattr(hosted_entrypoint, "prepare_ca", lambda: calls.append("prepare_ca"))
    monkeypatch.setattr(hosted_entrypoint.os, "execvp", lambda program, args: calls.append((program, args)))

    hosted_entrypoint.main()

    assert calls[0] == "prepare_ca"
    assert calls[1][1][-4:] == ["--workers", "1", "--no-access-log", "--no-proxy-headers"]


@pytest.mark.parametrize("key", ["KOYEB_SERVICE_ID", "KOYEB_INSTANCE_ID"])
def test_koyeb_entrypoint_still_rejects_non_uuid_identity(monkeypatch, key):
    environment = {
        "KOYEB_SERVICE_ID": "00000000-0000-4000-8000-000000000001",
        "KOYEB_INSTANCE_ID": "00000000-0000-4000-8000-000000000002",
        "TRUSTED_PROXY": "koyeb",
        "PORT": "8000",
    }
    environment[key] = "not-a-uuid"
    _set_process_environment(monkeypatch, environment)
    monkeypatch.setattr(hosted_entrypoint, "prepare_ca", lambda: pytest.fail("invalid identity reached CA setup"))
    monkeypatch.setattr(hosted_entrypoint.os, "execvp", lambda *_args: pytest.fail("invalid identity started Uvicorn"))

    with pytest.raises(SystemExit, match="Hosted startup configuration is invalid"):
        hosted_entrypoint.main()


def test_render_rate_limit_uses_only_single_cloudflare_ip_header(monkeypatch):
    _enable_render_limiter(monkeypatch)
    captured = []
    monkeypatch.setattr(rate_limits, "_apply_limits", lambda buckets: captured.extend(buckets))

    rate_limits.check_ip(_request([
        (b"x-forwarded-for", b"198.51.100.24, 198.51.100.25"),
        (b"cf-connecting-ip", CLIENT_IP.encode("ascii")),
        (b"x-forwarded-for", b"192.0.2.80"),
    ]))

    assert captured == [(rate_limits._bucket_key(SECRET, "ip", CLIENT_IP), 600)]
    assert "198.51.100.24" not in captured[0][0]
    assert "198.51.100.25" not in captured[0][0]


@pytest.mark.parametrize("headers", [
    [],
    [(b"cf-connecting-ip", b"not-an-ip")],
    [(b"cf-connecting-ip", b"203.0.113.91, 198.51.100.24")],
    [(b"cf-connecting-ip", b"203.0.113.91"), (b"cf-connecting-ip", b"198.51.100.24")],
    [(b"cf-connecting-ip", b"\xff")],
])
def test_render_rate_limit_fails_closed_for_missing_duplicate_or_malformed_header(monkeypatch, headers):
    _enable_render_limiter(monkeypatch)
    monkeypatch.setattr(rate_limits, "_apply_limits", lambda _buckets: pytest.fail("invalid IP reached limiter"))

    with pytest.raises(DomainError) as error:
        rate_limits.check_ip(_request(headers))

    assert (error.value.code, error.value.status) == ("rate_limit_unavailable", 503)


def test_local_and_koyeb_proxy_source_behavior_is_unchanged(monkeypatch):
    captured = []
    monkeypatch.setattr(rate_limits, "_apply_limits", lambda buckets: captured.extend(buckets))

    _enable_render_limiter(monkeypatch, trusted_proxy="none")
    rate_limits.check_ip(_request([(b"cf-connecting-ip", b"198.51.100.24")]))
    assert captured.pop() == (rate_limits._bucket_key(SECRET, "ip", PEER_IP), 600)

    _enable_render_limiter(monkeypatch, trusted_proxy="koyeb")
    rate_limits.check_ip(_request([
        (b"cf-connecting-ip", b"198.51.100.24"),
        (b"x-forwarded-for", b"192.0.2.80, 203.0.113.91"),
    ]))
    assert captured == [(rate_limits._bucket_key(SECRET, "ip", CLIENT_IP), 600)]
