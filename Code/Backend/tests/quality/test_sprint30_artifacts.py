"""Opt-in S28 -> candidate -> S28 artifact rehearsal on the named test DB."""

import hashlib
import io
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from app.core.config import ROOT, get_settings
from app.domains.registrations.models import Registration, RegistrationReceipt
from tests.conftest import assert_test_target


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SPRINT30_ARTIFACTS") != "1",
    reason="Opt-in local artifact promotion and rollback rehearsal",
)

SCHEMA_REVISION = "mvp_0020"
API_BASE = "http://127.0.0.1:8002"
FRONTEND_BASE = "http://127.0.0.1:3000"
HTTP_TIMEOUT_SECONDS = 4
SERVER_START_SECONDS = 45
BUILD_TIMEOUT_SECONDS = 600
BROWSER_TIMEOUT_SECONDS = 45
MAX_LOG_CHARS = 80_000

_EXCLUDED_DIRS = {
    ".cache",
    ".git",
    ".local",
    ".next",
    ".pytest_cache",
    ".turbo",
    ".venv",
    "coverage",
    "__pycache__",
    "node_modules",
    "out",
    "out-hosted",
    "out-real",
    "playwright-report",
    "test-results",
    "venv",
}
_EXCLUDED_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".pyc", ".pyo"}
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+\S+")
_DATABASE_URL_RE = re.compile(
    r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^\s:/@]+:)[^\s@]+(@)"
)
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----.*?-----END (?:RSA |EC )?PRIVATE KEY-----",
    re.DOTALL,
)


def _repo_root() -> Path:
    return ROOT.parents[1].resolve()


def _base_environment() -> dict[str, str]:
    allowed = (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "HOMEDRIVE",
        "HOMEPATH",
    )
    return {name: os.environ[name] for name in allowed if os.environ.get(name)}


def _sanitized_log(output: str) -> str:
    value = _PRIVATE_KEY_RE.sub("[redacted-private-key]", output)
    value = _DATABASE_URL_RE.sub(r"\1[redacted]\2", value)
    value = _JWT_RE.sub("[redacted-token]", value)
    value = _BEARER_RE.sub("Bearer [redacted]", value)
    value = _EMAIL_RE.sub("[redacted-email]", value)
    return value[-MAX_LOG_CHARS:]


def _append_log(path: Path, label: str, return_code: int, output: str) -> None:
    with path.open("a", encoding="utf-8") as log:
        log.write(f"{label}: exit={return_code}\n")
        if output:
            log.write(_sanitized_log(output))
            if not output.endswith("\n"):
                log.write("\n")


def _git(repo_root: Path, *args: str, binary: bool = False):
    safe_path = repo_root.as_posix()
    result = subprocess.run(
        ["git", "-c", f"safe.directory={safe_path}", *args],
        cwd=repo_root,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError("Required local Git object or source revision is unavailable")
    return result.stdout if binary else result.stdout.decode("utf-8", errors="replace").strip()


def _safe_revision(repo_root: Path) -> str:
    revision = os.environ.get("SPRINT30_ROLLBACK_REVISION", "")
    assert re.fullmatch(r"[0-9a-fA-F]{40}", revision), (
        "SPRINT30_ROLLBACK_REVISION must be the full 40-character S28 commit SHA"
    )
    revision = revision.lower()
    assert revision.startswith("54735aa"), "Rollback revision is not the supplied Sprint 28 checkpoint"
    assert _git(repo_root, "cat-file", "-t", revision) == "commit", (
        "SPRINT30_ROLLBACK_REVISION must resolve to a commit object"
    )
    assert _git(repo_root, "rev-parse", "--verify", f"{revision}^{{commit}}") == revision
    return revision


def _excluded(relative: Path) -> bool:
    parts = tuple(part.casefold() for part in relative.parts)
    name = relative.name.casefold()
    return (
        any(part in _EXCLUDED_DIRS or part.startswith(".env") for part in parts)
        or name.startswith(".env")
        or name in {"credentials.json", "secrets.json"}
        or relative.suffix.casefold() in _EXCLUDED_SUFFIXES
    )


def _copy_source(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    destination.mkdir(parents=True, exist_ok=False)
    for current, directory_names, file_names in os.walk(source, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(source)
        target_dir = destination / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        directory_names[:] = [
            name
            for name in directory_names
            if not _excluded(relative_dir / name)
            and not (current_path / name).is_symlink()
        ]
        for name in file_names:
            relative_file = relative_dir / name
            file_path = current_path / name
            if _excluded(relative_file) or file_path.is_symlink() or not file_path.is_file():
                continue
            target = destination / relative_file
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, target)


def _archive_s28(repo_root: Path, revision: str, target: Path) -> None:
    archive_bytes = _git(
        repo_root,
        "archive",
        "--format=tar",
        revision,
        "Code/Backend/app",
        "Code/Backend/migrations",
        "Code/Backend/alembic.ini",
        "Code/Frontend",
        binary=True,
    )
    target.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        safe_members = []
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                raise AssertionError("S28 archive contains an unsafe path")
            if member.issym() or member.islnk():
                raise AssertionError("S28 source archive contains an unexpected link")
            if not (member.isfile() or member.isdir()):
                raise AssertionError("S28 archive contains an unsupported entry")
            if any(_excluded(Path(part)) for part in path.parts):
                continue
            allowed = (
                member.name == "Code/Backend/alembic.ini"
                or member.name.startswith("Code/Backend/app/")
                or member.name == "Code/Backend/app"
                or member.name.startswith("Code/Backend/migrations/")
                or member.name == "Code/Backend/migrations"
                or member.name.startswith("Code/Frontend/")
                or member.name == "Code/Frontend"
            )
            if allowed:
                safe_members.append(member)
        if not hasattr(tarfile, "data_filter"):
            raise AssertionError("Python tarfile data-filter support is required")
        archive.extractall(path=target, members=safe_members, filter="data")


def _adjust_turbopack_root(frontend: Path, repo_root: Path) -> None:
    config_path = frontend / "next.config.ts"
    config = config_path.read_text(encoding="utf-8")
    marker = "const nextConfig: NextConfig = {"
    assert config.count(marker) == 1 and "turbopack:" not in config, (
        "Expected the isolated frontend config to have one unconfigured Turbopack root"
    )
    root_literal = json.dumps(str(repo_root))
    config = config.replace(
        marker,
        f"{marker}\n  turbopack: {{ root: {root_literal} }},",
        1,
    )
    config_path.write_text(config, encoding="utf-8")


def _link_dependencies(node: str, frontend: Path, dependency_root: Path) -> None:
    link = frontend / "node_modules"
    assert not link.exists() and not link.is_symlink()
    assert dependency_root.is_dir(), "Repository frontend dependencies are unavailable"
    if os.name == "nt":
        result = subprocess.run(
            [
                node,
                "-e",
                "require('node:fs').symlinkSync(process.argv[1], process.argv[2], 'junction')",
                str(dependency_root.resolve()),
                str(link),
            ],
            cwd=frontend,
            env=_base_environment(),
            capture_output=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 0, "Could not create the isolated frontend dependency junction"
    else:
        link.symlink_to(dependency_root.resolve(), target_is_directory=True)
    assert link.is_dir() and link.resolve() == dependency_root.resolve()


def _is_directory_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _tree_sha256(root: Path, *, source_only: bool = False) -> str:
    assert root.is_dir() and not _is_directory_link(root), (
        "Expected source or static export directory is missing or linked"
    )
    root = root.resolve(strict=True)
    excluded_dirs = _EXCLUDED_DIRS if source_only else set()
    digest = hashlib.sha256()
    files = []
    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_directories = []
        for name in sorted(directory_names):
            child = current_path / name
            excluded = name.casefold() in excluded_dirs or (
                source_only and name.casefold().startswith(".env")
            )
            if excluded:
                continue
            if _is_directory_link(child):
                raise AssertionError("Source or artifact tree contains an unexpected directory link")
            kept_directories.append(name)
        directory_names[:] = kept_directories
        for name in sorted(file_names):
            path = current_path / name
            if source_only and (
                name.casefold().startswith(".env")
                or name.casefold() in {"credentials.json", "secrets.json"}
                or path.suffix.casefold() in _EXCLUDED_SUFFIXES
            ):
                continue
            if path.is_symlink():
                raise AssertionError("Source or artifact tree contains an unexpected file link")
            if path.is_file():
                files.append(path)
    files.sort(key=lambda path: path.relative_to(root).as_posix())
    assert files, "Expected source or static export directory is empty"
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _run_owned(args, *, cwd: Path, env: dict[str, str], timeout: int, input_text=None):
    creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
        start_new_session=os.name != "nt",
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_owned(process)
        process.communicate()
        return 124, ""
    return process.returncode or 0, f"{stdout or ''}{stderr or ''}"


def _terminate_owned(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", os.environ.get("SYSTEMROOT", "C:\\Windows"))
        taskkill = str(Path(system_root) / "System32" / "taskkill.exe")
        subprocess.run(
            [taskkill, "/PID", str(process.pid), "/T", "/F"],
            env=_base_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _assert_ports_free() -> None:
    for port in (8002, 3000):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError:
                raise AssertionError(f"Required loopback port {port} is already in use") from None


def _wait_for_http(process: subprocess.Popen, url: str, expected_status: int) -> None:
    deadline = time.monotonic() + SERVER_START_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError("An owned rehearsal server exited before becoming ready")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == expected_status:
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.2)
    raise AssertionError("An owned rehearsal server did not become ready in time")


def _http_json(url: str, *, method="GET", headers=None, body=None):
    encoded = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=encoded, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            status, payload = response.status, response.read()
    except HTTPError as error:
        status, payload = error.code, error.read()
    except (OSError, URLError):
        return 0, None
    try:
        return status, json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, None


def _db_schema_version(db) -> str:
    return db.scalar(text("SELECT version_num FROM alembic_version"))


def _registration_counts(db, event_id: str) -> tuple[int, int]:
    registration_count = db.scalar(
        select(func.count()).select_from(Registration).where(Registration.event_id == event_id)
    )
    receipt_count = db.scalar(
        select(func.count()).select_from(RegistrationReceipt).where(
            RegistrationReceipt.event_id == event_id
        )
    )
    return registration_count, receipt_count


def _backend_environment(settings, media_root: Path, public_key: Path) -> dict[str, str]:
    env = _base_environment()
    env.update(
        {
            "ENVIRONMENT": "test",
            "FIXTURE_AUTH": "true",
            "AUTH_PROVIDER": "fixture",
            "DATABASE_URL": settings.database_url,
            "JWT_PUBLIC_KEY_FILE": str(public_key),
            "JWT_ISSUER": settings.jwt_issuer,
            "JWT_AUDIENCE": settings.jwt_audience,
            "MEDIA_PROVIDER": "local",
            "MEDIA_ROOT": str(media_root),
            "MAINTENANCE_ENABLED": "false",
            "RATE_LIMIT_ENABLED": "false",
        }
    )
    return env


def _frontend_environment() -> dict[str, str]:
    env = _base_environment()
    env.update(
        {
            "CI": "1",
            "NO_COLOR": "1",
            "NEXT_TELEMETRY_DISABLED": "1",
            "NEXT_PUBLIC_DEPLOYMENT": "local",
            "NEXT_PUBLIC_AUTH_MODE": "fixture",
            "NEXT_PUBLIC_LOCAL_DEMO": "false",
            "NEXT_PUBLIC_API_URL": API_BASE,
        }
    )
    return env


def _build_static(node: str, frontend: Path, log_path: Path) -> None:
    commands = (
        ("public-assets-before", [node, "scripts/check-public-assets.mjs"]),
        ("next-build", [node, "node_modules/next/dist/bin/next", "build"]),
        ("public-assets-after", [node, "scripts/check-public-assets.mjs", "out"]),
    )
    env = _frontend_environment()
    for label, command in commands:
        code, output = _run_owned(
            command,
            cwd=frontend,
            env=env,
            timeout=BUILD_TIMEOUT_SECONDS,
        )
        _append_log(log_path, label, code, output)
        assert code == 0, f"Static artifact build failed at {label}; see the sanitized run log"


def _start_api(python: str, backend: Path, env: dict[str, str]) -> subprocess.Popen:
    child_env = dict(env)
    child_env["PYTHONPATH"] = str(backend)
    creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8002", "--no-access-log", "--log-level", "warning"],
        cwd=backend,
        env=child_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
        start_new_session=os.name != "nt",
    )
    try:
        _wait_for_http(process, f"{API_BASE}/health", 200)
    except BaseException:
        _terminate_owned(process)
        raise
    return process


def _start_static(node: str, frontend: Path) -> subprocess.Popen:
    creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        [node, "scripts/serve-static.mjs"],
        cwd=frontend,
        env=_frontend_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
        start_new_session=os.name != "nt",
    )
    try:
        _wait_for_http(process, f"{FRONTEND_BASE}/", 200)
    except BaseException:
        _terminate_owned(process)
        raise
    return process


def _stop_servers(processes: list[subprocess.Popen]) -> None:
    if not processes:
        return
    for process in reversed(processes):
        _terminate_owned(process)
    processes.clear()
    _assert_ports_free()


def _browser_smoke(
    *, node: str, script: Path, frontend_dependencies: Path, title: str,
    private_markers: list[str], run_root: Path, phase: str,
) -> dict[str, int]:
    env = _base_environment()
    driver = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'
    assert driver.is_dir(), 'Bundled browser driver is required for the opt-in rehearsal'
    env["SPRINT30_PLAYWRIGHT"] = str(driver)
    payload = json.dumps({"title": title, "privateMarkers": private_markers})
    code, output = _run_owned(
        [node, str(script)],
        cwd=script.parents[2],
        env=env,
        timeout=BROWSER_TIMEOUT_SECONDS,
        input_text=payload,
    )
    _append_log(run_root / f"{phase}-browser.log", "browser-smoke", code, output)
    try:
        report = json.loads(output.splitlines()[0])
    except (IndexError, json.JSONDecodeError):
        raise AssertionError("Rendered guest smoke did not return counts-only JSON") from None
    required = {
        "discoveryResponseCount": 1,
        "discoverySuccessCount": 1,
        "visibleTitleCount": 1,
        "privateMarkerMatchCount": 0,
        "authenticatedDiscoveryRequestCount": 0,
        "fixtureAccountPickerCount": 0,
        "profileRequestCount": 0,
        "browserErrorCount": 0,
        "failureCount": 0,
    }
    assert all(report.get(key) == value for key, value in required.items()), (
        "Rendered guest discovery did not meet the artifact smoke checks"
    )
    return report


def _phase_checks(
    *, db, api_process: subprocess.Popen, frontend_process: subprocess.Popen,
    title: str, private_markers: list[str], node: str, smoke_script: Path,
    frontend_dependencies: Path, run_root: Path, phase: str, user_token: str,
    event_id: str, idempotency_key: str, expected_registration,
):
    _wait_for_http(api_process, f"{API_BASE}/health", 200)
    _wait_for_http(frontend_process, f"{FRONTEND_BASE}/", 200)
    health_status, health_body = _http_json(f"{API_BASE}/health")
    ready_status, ready_body = _http_json(f"{API_BASE}/ready")
    assert health_status == 200 and health_body == {"status": "ok"}
    assert ready_status == 200 and ready_body == {"status": "ready"}
    assert _db_schema_version(db) == SCHEMA_REVISION

    discovery_status, discovery = _http_json(
        f"{API_BASE}/api/v1/events?sort=upcoming&limit=50"
    )
    assert discovery_status == 200 and isinstance(discovery, list)
    title_matches = sum(item.get("title") == title for item in discovery if isinstance(item, dict))
    serialized_discovery = json.dumps(discovery, ensure_ascii=False).casefold()
    private_leaks = sum(marker.casefold() in serialized_discovery for marker in private_markers)
    assert title_matches == 1 and private_leaks == 0

    profile_status, profile_body = _http_json(f"{API_BASE}/api/v1/me/profile")
    serialized_profile = json.dumps(profile_body, ensure_ascii=False).casefold()
    profile_leaks = sum(marker.casefold() in serialized_profile for marker in private_markers)
    assert profile_status == 401 and profile_leaks == 0

    browser = _browser_smoke(
        node=node,
        script=smoke_script,
        frontend_dependencies=frontend_dependencies,
        title=title,
        private_markers=private_markers,
        run_root=run_root,
        phase=phase,
    )
    registration_status, registration_body = _http_json(
        f"{API_BASE}/api/v1/events/{event_id}/registrations",
        method="POST",
        headers={
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        },
        body={},
    )
    assert registration_status == 201 and isinstance(registration_body, dict)
    if expected_registration is None:
        expected_registration = (registration_status, registration_body)
        retry_status, retry_body = _http_json(
            f"{API_BASE}/api/v1/events/{event_id}/registrations",
            method="POST",
            headers={
                "Authorization": f"Bearer {user_token}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
            body={},
        )
        assert (retry_status, retry_body) == expected_registration
        retry_count = 1
        registration_posts = 2
    else:
        assert (registration_status, registration_body) == expected_registration
        retry_count = 1
        registration_posts = 1

    registration_count, receipt_count = _registration_counts(db, event_id)
    assert registration_count == 1 and receipt_count == 1
    assert _db_schema_version(db) == SCHEMA_REVISION
    return expected_registration, {
        "healthOk": 1,
        "readyOk": 1,
        "guestDiscoveryTitles": title_matches,
        "guestPrivateProfileLeaks": private_leaks + profile_leaks,
        "anonymousProfileDenials": 1,
        "browserDiscoveryResponses": browser["discoverySuccessCount"],
        "browserTitleMatches": browser["visibleTitleCount"],
        "browserPrivateProfileLeaks": browser["privateMarkerMatchCount"],
        "fixtureAccountPickers": browser["fixtureAccountPickerCount"],
        "authenticatedGuestRequests": browser["authenticatedDiscoveryRequestCount"],
        "registrationPosts": registration_posts,
        "unchangedRetries": retry_count,
        "registrationRows": registration_count,
        "registrationReceipts": receipt_count,
    }


def test_sprint30_artifact_promotion_and_rollback(
    db, make_user, make_org, make_event, token_for
):
    assert_test_target()
    settings = get_settings()
    target = make_url(settings.database_url)
    assert (
        settings.environment == "test"
        and settings.fixture_auth
        and settings.auth_provider == "fixture"
        and settings.media_provider == "local"
        and target.drivername == "postgresql+psycopg"
        and target.database == "intraspot_mvp_test"
        and target.host in {"127.0.0.1", "localhost"}
        and target.port == 5433
    )

    repo_root = _repo_root()
    revision = _safe_revision(repo_root)
    current_head = _git(repo_root, "rev-parse", "--verify", "HEAD^{commit}")
    assert re.fullmatch(r"[0-9a-f]{40}", current_head)
    assert ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_current_head() == SCHEMA_REVISION
    assert _db_schema_version(db) == SCHEMA_REVISION
    public_key = (ROOT / ".local" / "public.pem").resolve(strict=True)
    node = shutil.which("node")
    assert node, "Node.js is required for the static artifact rehearsal"

    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:10]}"
    run_root = ROOT / ".cache" / "s30artifact" / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    revision_root = run_root / "revision"
    candidate_root = run_root / "candidate"
    evidence_path = run_root / "evidence.json"
    media_root = run_root / "private-media"
    media_root.mkdir(mode=0o700)

    evidence = {
        "sourceShas": {"rollbackCommit": revision, "candidateBaseCommit": current_head},
        "sourceTreeSha256": {},
        "artifactSha256": {},
        "phases": {},
        "failureCount": 0,
    }
    servers: list[subprocess.Popen] = []
    expected_registration = None
    try:
        _assert_ports_free()
        _archive_s28(repo_root, revision, revision_root)
        old_backend = revision_root / "Code" / "Backend"
        old_frontend = revision_root / "Code" / "Frontend"
        assert (old_backend / "migrations" / "env.py").is_file()
        assert (old_backend / "alembic.ini").is_file()
        assert (old_frontend / "scripts" / "serve-static.mjs").is_file()
        assert ScriptDirectory.from_config(Config(str(old_backend / "alembic.ini"))).get_current_head() == SCHEMA_REVISION

        candidate_backend = candidate_root / "Code" / "Backend"
        candidate_frontend = candidate_root / "Code" / "Frontend"
        candidate_backend.parent.mkdir(parents=True, exist_ok=True)
        _copy_source(ROOT / "app", candidate_backend / "app")
        _copy_source(ROOT / "migrations", candidate_backend / "migrations")
        shutil.copy2(ROOT / "alembic.ini", candidate_backend / "alembic.ini")
        _copy_source(repo_root / "Code" / "Frontend", candidate_frontend)
        assert ScriptDirectory.from_config(Config(str(candidate_backend / "alembic.ini"))).get_current_head() == SCHEMA_REVISION
        evidence["sourceTreeSha256"] = {
            "rollbackArchive": _tree_sha256(revision_root, source_only=True),
            "candidateWorkingTree": _tree_sha256(candidate_root, source_only=True),
        }

        dependency_root = repo_root / "Code" / "Frontend" / "node_modules"
        _link_dependencies(node, old_frontend, dependency_root)
        _link_dependencies(node, candidate_frontend, dependency_root)
        _adjust_turbopack_root(old_frontend, repo_root)
        _adjust_turbopack_root(candidate_frontend, repo_root)

        _build_static(node, old_frontend, run_root / "old-s28-build.log")
        _build_static(node, candidate_frontend, run_root / "candidate-build.log")
        old_artifact_hash = _tree_sha256(old_frontend / "out")
        candidate_artifact_hash = _tree_sha256(candidate_frontend / "out")
        evidence["artifactSha256"] = {
            "oldS28Static": old_artifact_hash,
            "candidateStatic": candidate_artifact_hash,
        }

        owner_nickname = f"S30 private owner {uuid4().hex[:10]}"
        attendee_nickname = f"S30 private attendee {uuid4().hex[:10]}"
        owner = make_user(nickname=owner_nickname)
        attendee = make_user(nickname=attendee_nickname)
        organization = make_org(owner=owner, name=f"S30 rehearsal society {uuid4().hex[:8]}")
        title = f"S30 artifact rehearsal {uuid4().hex[:10]}"
        event = make_event(org=organization, title=title)
        private_markers = [owner.email, owner.nickname, attendee.email, attendee.nickname]
        user_token = token_for(attendee)
        idempotency_key = f"s30-artifact-{uuid4().hex}"
        backend_env = _backend_environment(settings, media_root, public_key)
        smoke_script = repo_root / "docs" / "validation" / "sprint30-artifact-smoke.mjs"
        frontend_dependencies = dependency_root

        phases = (
            ("oldS28Promotion", old_backend, old_frontend),
            ("currentCandidate", candidate_backend, candidate_frontend),
            ("oldS28Rollback", old_backend, old_frontend),
        )
        for phase, backend, frontend in phases:
            _assert_ports_free()
            api_process = _start_api(sys.executable, backend, backend_env)
            servers.append(api_process)
            frontend_process = _start_static(node, frontend)
            servers.append(frontend_process)
            expected_registration, phase_evidence = _phase_checks(
                db=db,
                api_process=api_process,
                frontend_process=frontend_process,
                title=title,
                private_markers=private_markers,
                node=node,
                smoke_script=smoke_script,
                frontend_dependencies=frontend_dependencies,
                run_root=run_root,
                phase=phase,
                user_token=user_token,
                event_id=event.id,
                idempotency_key=idempotency_key,
                expected_registration=expected_registration,
            )
            evidence["phases"][phase] = phase_evidence
            _stop_servers(servers)

        phase_rows = list(evidence["phases"].values())
        evidence["counts"] = {
            "phaseCount": len(phase_rows),
            "healthOk": sum(row["healthOk"] for row in phase_rows),
            "readyOk": sum(row["readyOk"] for row in phase_rows),
            "guestDiscoveryTitles": sum(row["guestDiscoveryTitles"] for row in phase_rows),
            "privateProfileLeaks": sum(
                row["guestPrivateProfileLeaks"] + row["browserPrivateProfileLeaks"]
                for row in phase_rows
            ),
            "anonymousProfileDenials": sum(row["anonymousProfileDenials"] for row in phase_rows),
            "registrationPosts": sum(row["registrationPosts"] for row in phase_rows),
            "unchangedRetries": sum(row["unchangedRetries"] for row in phase_rows),
            "registrationRowsPerPhase": sum(row["registrationRows"] for row in phase_rows),
            "registrationReceiptsPerPhase": sum(row["registrationReceipts"] for row in phase_rows),
        }
        assert evidence["counts"] == {
            "phaseCount": 3,
            "healthOk": 3,
            "readyOk": 3,
            "guestDiscoveryTitles": 3,
            "privateProfileLeaks": 0,
            "anonymousProfileDenials": 3,
            "registrationPosts": 4,
            "unchangedRetries": 3,
            "registrationRowsPerPhase": 3,
            "registrationReceiptsPerPhase": 3,
        }
    except BaseException:
        evidence["failureCount"] = 1
        raise
    finally:
        try:
            _stop_servers(servers)
        finally:
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    print(json.dumps({"evidence": str(evidence_path), "phaseCount": 3, "failureCount": 0}))
