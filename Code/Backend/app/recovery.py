"""Encrypted PostgreSQL and media backups with isolated restore safeguards."""
from __future__ import annotations

import base64
import hashlib
import io
import ipaddress
import json
import os
import queue
import re
import shutil
import stat
import subprocess
import tarfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Callable, Iterable
from uuid import UUID, uuid4

import psycopg
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import ROOT, get_settings
from app.db.session import engine as configured_engine
from app.domains.media import storage
from app.domains.media.models import MediaAsset
from app.domains.media.storage_models import MediaObject
from app.erasure_models import ErasedAccount, ErasureRequest
from app.recovery_models import BackupObjectReference, BackupSnapshot

CHUNK_SIZE = 1024 * 1024
MAX_OBJECT_BYTES = 50 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
TAG_SIZE = 16
MAGIC = b"INTRASPOT"
FORMAT_VERSION = 1
DOCKER_POSTGRES_CONTAINER = "intraspot-mvp-postgres-1"
MEDIA_LOCK_KEYS = (1296388935, 5066052)
SNAPSHOT_PURPOSES = {"weekly", "premigration"}
WEEKLY_RETENTION = 4
_FILE_NAMES = {
    "database": "database.sql.gcm",
    "objects": "objects.tar.gcm",
    "manifest": "manifest.json.gcm",
    "checksums": "checksums.json",
}
_SNAPSHOT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_RESTORE_DATABASE = re.compile(r"^intraspot_restore_[a-z0-9_]+$")
_OBJECT_NAME = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.webp$")
_KIND_CODES = {"database": b"D", "objects": b"O", "manifest": b"M", "ledger": b"L"}


class RecoveryError(RuntimeError):
    """A backup or restore could not safely complete."""


def load_backup_key(key_file: str | Path | None = None) -> bytes:
    """Load a 32-byte key from INTRASPOT_BACKUP_KEY or a protected external file."""
    env_value = os.environ.get("INTRASPOT_BACKUP_KEY")
    if key_file is not None and env_value:
        raise RecoveryError("Set either INTRASPOT_BACKUP_KEY or --key-file, not both")
    if key_file is None:
        if not env_value:
            raise RecoveryError("Set INTRASPOT_BACKUP_KEY or provide --key-file")
        try:
            encoded = env_value.encode("ascii", errors="strict")
        except UnicodeEncodeError:
            raise RecoveryError("The backup key must be 32-byte hex or URL-safe base64") from None
    else:
        candidate = Path(key_file).expanduser()
        if candidate.is_symlink():
            raise RecoveryError("The backup key file must be a regular file")
        path = candidate.resolve(strict=True)
        _assert_external_path(path)
        if not path.is_file():
            raise RecoveryError("The backup key file must be a regular file")
        _verify_private_permissions(path, require_private=True)
        encoded = path.read_bytes().strip()
    try:
        if re.fullmatch(rb"[0-9a-fA-F]{64}", encoded):
            key = bytes.fromhex(encoded.decode("ascii"))
        else:
            key = base64.b64decode(
                encoded + b"=" * (-len(encoded) % 4), altchars=b"-_", validate=True,
            )
    except (ValueError, UnicodeError):
        raise RecoveryError("The backup key must be 32-byte hex or URL-safe base64") from None
    if len(key) != 32:
        raise RecoveryError("The backup key must decode to exactly 32 bytes")
    return key


def validate_restore_database_url(database_url: str):
    """Accept only a new, isolated loopback PostgreSQL restore database."""
    try:
        url = make_url(database_url)
        address = ipaddress.ip_address(url.host or "")
    except (TypeError, ValueError):
        raise RecoveryError("Restore target must use a loopback IP address") from None
    if (url.drivername != "postgresql+psycopg" or not address.is_loopback
            or url.port != 5433 or not _RESTORE_DATABASE.fullmatch(url.database or "")):
        raise RecoveryError(
            "Restore target must be a fresh intraspot_restore_* database on loopback port 5433"
        )
    return url


def _snapshot_directory(root: Path, snapshot_id: str) -> Path:
    if not _SNAPSHOT_ID.fullmatch(snapshot_id):
        raise RecoveryError("Snapshot ID is invalid")
    return root / snapshot_id


def _bundle_paths(bundle: Path) -> dict[str, Path]:
    return {key: bundle / name for key, name in _FILE_NAMES.items()}


def _repo_root() -> Path:
    return ROOT.parents[1].resolve()


def _assert_external_path(path: Path) -> Path:
    repo = _repo_root()
    if path == repo or _is_relative_to(path, repo):
        raise RecoveryError("Backup artifacts and keys must be outside the IntraSpot checkout")
    try:
        media_root = get_settings().media_root.resolve()
    except Exception:
        raise RecoveryError("Configured media storage could not be validated") from None
    if (_is_relative_to(path, media_root) or _is_relative_to(media_root, path)):
        raise RecoveryError("Backup artifacts and keys must be separate from configured media storage")
    return path


def _assert_external_root(root: str | Path) -> Path:
    candidate = Path(root).expanduser()
    if candidate.is_symlink():
        raise RecoveryError("Backup output root must not be a symbolic link")
    path = candidate.resolve()
    _assert_external_path(path)
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise RecoveryError("Backup output root must be a real directory")
    if path.exists():
        _verify_private_permissions(path, require_private=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        _make_private_directory(path)
    return path


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _verify_private_permissions(path: Path, *, require_private: bool = False) -> bool:
    """Set and inspect restrictive permissions where the platform exposes them."""
    if os.name == "nt":
        icacls = shutil.which("icacls")
        username = os.environ.get("USERDOMAIN", "")
        account = os.environ.get("USERNAME")
        if not icacls or not account:
            if require_private:
                raise RecoveryError("Could not verify Windows permissions for the backup key")
            return False
        principal = f"{username}\\{account}" if username else account
        try:
            result = subprocess.run(
                [icacls, str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, timeout=5, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            if require_private:
                raise RecoveryError("Could not verify Windows permissions for the backup key") from None
            return False
        if result.returncode != 0:
            if require_private:
                raise RecoveryError("Could not verify Windows permissions for the backup key")
            return False
        acl = result.stdout.casefold()
        if any(group in acl for group in (
            "everyone", "builtin\\users", "authenticated users", "nt authority\\authenticated users",
        )):
            if require_private:
                raise RecoveryError("The backup key has permissions broader than its owner")
            return False
        return principal.casefold() in acl or "nt authority\\system" in acl
    try:
        if not path.exists():
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            if require_private:
                raise RecoveryError("The backup key must not be readable by group or other users")
            return False
        return True
    except OSError:
        if require_private:
            raise RecoveryError("Could not verify private permissions for the backup key") from None
        return False


def _make_private_directory(path: Path) -> bool:
    path.mkdir(mode=0o700)
    if os.name == "nt":
        icacls = shutil.which("icacls")
        username = os.environ.get("USERNAME")
        domain = os.environ.get("USERDOMAIN", "")
        principal = f"{domain}\\{username}" if domain else username
        if icacls and principal:
            try:
                result = subprocess.run(
                    [icacls, str(path), "/inheritance:r", "/grant:r",
                     f"{principal}:(OI)(CI)F", "NT AUTHORITY\\SYSTEM:(OI)(CI)F"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=5, check=False,
                )
                if result.returncode == 0:
                    if _verify_private_permissions(path):
                        return True
            except (OSError, subprocess.TimeoutExpired):
                pass
        raise RecoveryError("Could not set and verify private permissions on the backup directory")
    os.chmod(path, 0o700)
    return _verify_private_permissions(path)


def _open_private_file(path: Path) -> BinaryIO:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    stream = os.fdopen(descriptor, "wb")
    if os.name != "nt":
        os.fchmod(descriptor, 0o600)
    return stream


def _header(kind: str, snapshot_id: str, nonce: bytes) -> bytes:
    if kind not in _KIND_CODES or not _SNAPSHOT_ID.fullmatch(snapshot_id):
        raise RecoveryError("Encrypted archive metadata is invalid")
    kind_code = _KIND_CODES[kind]
    return MAGIC + bytes([FORMAT_VERSION]) + kind_code + nonce + snapshot_id.encode("ascii")


class _EncryptingWriter:
    def __init__(self, path: Path, key: bytes, kind: str, snapshot_id: str):
        self.path = path
        self.stream = _open_private_file(path)
        self.nonce = os.urandom(12)
        self.header = _header(kind, snapshot_id, self.nonce)
        self.encryptor = Cipher(algorithms.AES(key), modes.GCM(self.nonce)).encryptor()
        self.encryptor.authenticate_additional_data(self.header)
        self.cipher_hash = hashlib.sha256()
        self.plain_hash = hashlib.sha256()
        self.plain_size = 0
        self.cipher_size = 0
        self._write_ciphertext(self.header)

    def _write_ciphertext(self, data: bytes) -> None:
        if data:
            self.stream.write(data)
            self.cipher_hash.update(data)
            self.cipher_size += len(data)

    def write(self, data: bytes) -> int:
        if not data:
            return 0
        self.plain_hash.update(data)
        self.plain_size += len(data)
        self._write_ciphertext(self.encryptor.update(data))
        return len(data)

    def flush(self) -> None:
        self.stream.flush()

    def finish(self) -> dict:
        self._write_ciphertext(self.encryptor.finalize())
        self._write_ciphertext(self.encryptor.tag)
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.stream.close()
        _verify_private_permissions(self.path, require_private=True)
        return {
            "name": self.path.name,
            "size": self.cipher_size,
            "sha256": self.cipher_hash.hexdigest(),
            "plaintext_size": self.plain_size,
            "plaintext_sha256": self.plain_hash.hexdigest(),
        }

    def abort(self) -> None:
        try:
            self.stream.close()
        finally:
            self.path.unlink(missing_ok=True)


def _read_header(stream: BinaryIO, kind: str, snapshot_id: str) -> tuple[bytes, bytes]:
    length = len(MAGIC) + 1 + 1 + 12 + 36
    header = stream.read(length)
    if len(header) != length or header[:len(MAGIC)] != MAGIC:
        raise RecoveryError("Encrypted archive header is invalid")
    version = header[len(MAGIC)]
    expected_kind = _KIND_CODES[kind]
    nonce_start = len(MAGIC) + 2
    nonce = header[nonce_start:nonce_start + 12]
    encoded_id = header[nonce_start + 12:]
    if (version != FORMAT_VERSION or header[len(MAGIC) + 1:len(MAGIC) + 2] != expected_kind
            or encoded_id != snapshot_id.encode("ascii")):
        raise RecoveryError("Encrypted archive does not match its snapshot")
    return header, nonce


def _decrypt_chunks(path: Path, key: bytes, kind: str, snapshot_id: str):
    with path.open("rb") as stream:
        header, nonce = _read_header(stream, kind, snapshot_id)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).decryptor()
        decryptor.authenticate_additional_data(header)
        tail = b""
        while True:
            chunk = stream.read(CHUNK_SIZE)
            if not chunk:
                break
            tail += chunk
            if len(tail) > TAG_SIZE:
                ciphertext, tail = tail[:-TAG_SIZE], tail[-TAG_SIZE:]
                plaintext = decryptor.update(ciphertext)
                if plaintext:
                    yield plaintext
        if len(tail) != TAG_SIZE:
            raise RecoveryError("Encrypted archive authentication tag is missing")
        try:
            final = decryptor.finalize_with_tag(tail)
        except Exception:
            raise RecoveryError("Encrypted archive authentication failed") from None
        if final:
            yield final


class _ChunkReader:
    """Bounded-memory file-like adapter for a decrypted chunk iterator."""
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.buffer = bytearray()
        self.finished = False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise RecoveryError("Unbounded archive reads are not supported")
        while len(self.buffer) < size and not self.finished:
            try:
                self.buffer.extend(next(self.chunks))
            except StopIteration:
                self.finished = True
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def drain(self) -> None:
        self.buffer.clear()
        for _ in self.chunks:
            pass
        self.finished = True


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _read_json(path: Path, max_bytes: int) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise RecoveryError("Backup manifest is missing or too large")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise RecoveryError("Backup manifest is invalid") from None
    if not isinstance(value, dict):
        raise RecoveryError("Backup manifest is invalid")
    return value


def _validate_internal_manifest(manifest: dict, snapshot_id: str) -> dict:
    if (manifest.get("format_version") != FORMAT_VERSION
            or manifest.get("snapshot_id") != snapshot_id
            or manifest.get("archive_status") != "verified"
            or manifest.get("purpose") not in SNAPSHOT_PURPOSES):
        raise RecoveryError("Encrypted backup manifest is invalid")
    _parse_aware_timestamp(manifest.get("created_at"), "Backup created_at")
    database = manifest.get("database")
    objects = manifest.get("objects")
    erasures = manifest.get("erasures")
    if (not isinstance(database, dict) or not isinstance(database.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", database["sha256"])
            or not isinstance(database.get("size"), int) or database["size"] < 0
            or not isinstance(objects, list) or len(objects) > 5000
            or not isinstance(erasures, dict)):
        raise RecoveryError("Encrypted backup manifest is invalid")
    seen = set()
    for item in objects:
        if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                or not _OBJECT_NAME.fullmatch(item["id"] + ".webp")
                or item["id"] in seen or not isinstance(item.get("exists"), bool)):
            raise RecoveryError("Encrypted backup object manifest is invalid")
        seen.add(item["id"])
        if item["exists"]:
            if (not isinstance(item.get("size"), int) or not 0 < item["size"] <= MAX_OBJECT_BYTES
                    or not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", ""))):
                raise RecoveryError("Encrypted backup object manifest is invalid")
        elif item.get("size") != 0 or item.get("sha256") is not None:
            raise RecoveryError("Encrypted backup object manifest is invalid")
    for group in ("erased_accounts", "completed_requests"):
        if not isinstance(erasures.get(group), list) or len(erasures[group]) > 10_000:
            raise RecoveryError("Encrypted erasure manifest is invalid")
    return manifest


def _load_encrypted_manifest(bundle: Path, key: bytes, snapshot_id: str) -> dict:
    path = _bundle_paths(bundle)["manifest"]
    chunks = _decrypt_chunks(path, key, "manifest", snapshot_id)
    data = bytearray()
    try:
        for chunk in chunks:
            data.extend(chunk)
            if len(data) > MAX_MANIFEST_BYTES:
                raise RecoveryError("Encrypted backup manifest is too large")
    except Exception:
        raise
    try:
        manifest = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise RecoveryError("Encrypted backup manifest is invalid") from None
    if not isinstance(manifest, dict):
        raise RecoveryError("Encrypted backup manifest is invalid")
    return _validate_internal_manifest(manifest, snapshot_id)


def _verify_ciphertext_checksums(bundle: Path, snapshot_id: str) -> dict:
    checksums = _read_json(_bundle_paths(bundle)["checksums"], 64 * 1024)
    if (checksums.get("format_version") != FORMAT_VERSION
            or checksums.get("snapshot_id") != snapshot_id):
        raise RecoveryError("Backup checksum manifest does not match its directory")
    files = checksums.get("files")
    if not isinstance(files, dict) or set(files) != {"database", "objects", "manifest"}:
        raise RecoveryError("Backup checksum manifest is invalid")
    paths = _bundle_paths(bundle)
    for kind, entry in files.items():
        if (not isinstance(entry, dict) or entry.get("name") != _FILE_NAMES[kind]
                or not isinstance(entry.get("size"), int) or entry["size"] <= 0
                or not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", ""))):
            raise RecoveryError("Backup checksum manifest is invalid")
        path = paths[kind]
        if path.is_symlink() or not path.is_file():
            raise RecoveryError("An encrypted backup component is missing")
        digest, size = _hash_file(path)
        if digest != entry["sha256"] or size != entry["size"]:
            raise RecoveryError("Encrypted backup checksum mismatch")
    allowed = set(_FILE_NAMES.values())
    if any(path.name not in allowed for path in bundle.iterdir()):
        raise RecoveryError("Backup directory contains unexpected files")
    return checksums


def _verify_database_payload(path: Path, key: bytes, snapshot_id: str, expected: dict) -> None:
    digest = hashlib.sha256()
    size = 0
    for chunk in _decrypt_chunks(path, key, "database", snapshot_id):
        digest.update(chunk)
        size += len(chunk)
    if digest.hexdigest() != expected["sha256"] or size != expected["size"]:
        raise RecoveryError("Decrypted database checksum mismatch")


def _verify_objects_payload(path: Path, key: bytes, snapshot_id: str, manifest: dict) -> None:
    expected = {item["id"]: item for item in manifest["objects"] if item["exists"]}
    reader = _ChunkReader(_decrypt_chunks(path, key, "objects", snapshot_id))
    seen = set()
    try:
        with tarfile.open(fileobj=reader, mode="r|") as archive:
            for member in archive:
                if not member.isfile() or not _OBJECT_NAME.fullmatch(member.name):
                    raise RecoveryError("Media archive contains an unsafe entry")
                media_id = member.name[:-5]
                item = expected.get(media_id)
                if item is None or media_id in seen or member.size != item["size"]:
                    raise RecoveryError("Media archive does not match its encrypted manifest")
                source = archive.extractfile(member)
                if source is None:
                    raise RecoveryError("Media archive entry could not be read")
                digest = hashlib.sha256()
                size = 0
                while chunk := source.read(CHUNK_SIZE):
                    digest.update(chunk)
                    size += len(chunk)
                if digest.hexdigest() != item["sha256"] or size != item["size"]:
                    raise RecoveryError("Media object checksum mismatch")
                seen.add(media_id)
        reader.drain()
    except (tarfile.TarError, OSError):
        raise RecoveryError("Media archive is invalid") from None
    if seen != set(expected):
        raise RecoveryError("Media archive is missing retained objects")


def verify_backup(
    bundle_dir: str | Path, key: bytes, *, snapshot_id: str | None = None,
) -> dict:
    """Verify outer checksums, every GCM tag, and all decrypted payload hashes."""
    candidate = Path(bundle_dir).expanduser()
    if candidate.is_symlink():
        raise RecoveryError("Backup directory must not be a symbolic link")
    bundle = candidate.resolve(strict=True)
    snapshot_id = snapshot_id or bundle.name
    if (not bundle.is_dir() or not _SNAPSHOT_ID.fullmatch(snapshot_id)
            or (bundle.name != snapshot_id and bundle.name != f".{snapshot_id}.partial")):
        raise RecoveryError("Backup directory must be named with its snapshot UUID")
    _verify_ciphertext_checksums(bundle, snapshot_id)
    manifest = _load_encrypted_manifest(bundle, key, snapshot_id)
    paths = _bundle_paths(bundle)
    _verify_database_payload(paths["database"], key, snapshot_id, manifest["database"])
    _verify_objects_payload(paths["objects"], key, snapshot_id, manifest)
    return manifest


def _database_url_parts(database_url: str) -> tuple[object, dict[str, str]]:
    try:
        url = make_url(database_url)
    except (TypeError, ValueError):
        raise RecoveryError("PostgreSQL connection configuration is invalid") from None
    if url.drivername != "postgresql+psycopg" or not url.host or not url.port or not url.database:
        raise RecoveryError("PostgreSQL connection configuration is incomplete")
    env = {
        "PGHOST": url.host,
        "PGPORT": str(url.port),
        "PGDATABASE": url.database,
        "PGCONNECT_TIMEOUT": "5",
    }
    if url.username is not None:
        env["PGUSER"] = url.username
    if url.password is not None:
        env["PGPASSWORD"] = url.password
    for query_key, env_key in (
        ("sslmode", "PGSSLMODE"),
        ("sslrootcert", "PGSSLROOTCERT"),
        ("sslcert", "PGSSLCERT"),
        ("sslkey", "PGSSLKEY"),
    ):
        value = url.query.get(query_key)
        if isinstance(value, str):
            env[env_key] = value
    return url, env


def _run_captured(command: list[str], *, timeout: int = 10) -> str:
    try:
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RecoveryError("Required PostgreSQL or Docker tooling is unavailable") from None
    if result.returncode != 0:
        raise RecoveryError("PostgreSQL or Docker tooling validation failed")
    return result.stdout.strip()


def _validate_docker_postgres() -> None:
    docker = shutil.which("docker")
    if not docker:
        raise RecoveryError("Install PostgreSQL 17 client tools or start the approved local PostgreSQL 17 container")
    identity = _run_captured([
        docker, "inspect", "--format", "{{.Name}}|{{json .NetworkSettings.Ports}}",
        DOCKER_POSTGRES_CONTAINER,
    ])
    try:
        name, encoded_ports = identity.split("|", 1)
        ports = json.loads(encoded_ports)
        bindings = ports.get("5432/tcp") or []
        mapped = any(
            ipaddress.ip_address(binding["HostIp"]).is_loopback
            and binding["HostPort"] == "5433"
            for binding in bindings
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        mapped = False
        name = ""
    if name != f"/{DOCKER_POSTGRES_CONTAINER}" or not mapped:
        raise RecoveryError("Docker fallback requires the dedicated IntraSpot container mapped to loopback port 5433")
    # The official image need not set PGPORT. The inspected binding and explicit
    # client port below select 5432 without trusting a container environment default.
    for tool in ("pg_dump", "psql"):
        version = _run_captured([docker, "exec", DOCKER_POSTGRES_CONTAINER, tool, "--version"])
        if not re.search(r"\b17(?:\.\d+)?\b", version):
            raise RecoveryError("Docker fallback requires PostgreSQL 17 client tools in the IntraSpot container")


def _postgres_command(tool: str, url, env: dict[str, str], args: list[str]) -> tuple[list[str], dict[str, str]]:
    program = shutil.which(tool)
    if program:
        version = _run_captured([program, "--version"])
        match = re.search(r"PostgreSQL\)\s+(\d+)", version)
        if not match or int(match.group(1)) < 17:
            raise RecoveryError(f"{tool} version 17 or newer is required")
        return [program, *args], env
    try:
        address = ipaddress.ip_address(url.host or "")
    except ValueError:
        address = None
    if address is None or not address.is_loopback or url.port != 5433:
        raise RecoveryError(f"{tool} is required for this database; Docker fallback is limited to isolated loopback PostgreSQL")
    _validate_docker_postgres()
    args = list(args)
    for option, value in (("--host", "127.0.0.1"), ("--port", "5432")):
        try:
            position = args.index(option)
        except ValueError:
            args.extend([option, value])
        else:
            args[position + 1] = value
    docker_env = env.copy()
    docker_env["PGHOST"] = "127.0.0.1"
    docker_env["PGPORT"] = "5432"
    command = ["docker", "exec"]
    if tool == "psql":
        command.append("--interactive")
    for name in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE"):
        if name in docker_env:
            command.extend(["--env", name])
    command.extend([DOCKER_POSTGRES_CONTAINER, tool, *args])
    return command, docker_env


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _stream_process(command: list[str], env: dict[str, str], writer: _EncryptingWriter, timeout: int) -> None:
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env, bufsize=0,
        )
    except OSError:
        raise RecoveryError("Could not start pg_dump") from None
    chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=2)
    stop = threading.Event()
    def read_output():
        try:
            while not stop.is_set():
                data = process.stdout.read(CHUNK_SIZE)
                if not data:
                    break
                while not stop.is_set():
                    try:
                        chunks.put(data, timeout=0.1)
                        break
                    except queue.Full:
                        continue
        finally:
            while not stop.is_set():
                try:
                    chunks.put(None, timeout=0.1)
                    break
                except queue.Full:
                    continue
    reader = threading.Thread(target=read_output, name="intraspot-pgdump-reader", daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RecoveryError("pg_dump exceeded its configured timeout")
            try:
                chunk = chunks.get(timeout=min(0.25, remaining))
            except queue.Empty:
                if process.poll() is not None and not reader.is_alive():
                    break
                continue
            if chunk is None:
                break
            writer.write(chunk)
        try:
            code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise RecoveryError("pg_dump exceeded its configured timeout") from None
        if code != 0:
            raise RecoveryError(f"pg_dump failed with exit code {code}")
    except Exception:
        stop.set()
        _terminate_process(process)
        raise
    finally:
        stop.set()
        if process.stdout:
            process.stdout.close()
        reader.join(timeout=5)


def _engine_for(database_url: str):
    try:
        configured_url = get_settings().database_url
    except Exception:
        configured_url = None
    if database_url == configured_url:
        return configured_engine(), False
    from sqlalchemy import create_engine
    return create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5}), True


def _create_pending_snapshot(database_url: str, snapshot_id: str, purpose: str) -> None:
    engine, dispose = _engine_for(database_url)
    try:
        with Session(engine, expire_on_commit=False) as session, session.begin():
            storage.lock_media_quota(session)
            snapshot = BackupSnapshot(id=snapshot_id, purpose=purpose, status="pending")
            session.add(snapshot)
            session.flush()
            media_ids = set(session.scalars(select(MediaObject.id)).all())
            media_ids.update(session.scalars(select(MediaAsset.id)).all())
            session.add_all(
                BackupObjectReference(snapshot_id=snapshot_id, media_id=media_id)
                for media_id in sorted(media_ids)
            )
    except Exception:
        raise RecoveryError("Could not pin retained media for the backup") from None
    finally:
        if dispose:
            engine.dispose()


@contextmanager
def _consistent_snapshot(database_url: str, snapshot_id: str):
    """Fence media reservations, revalidate pins, then export a repeatable PG snapshot."""
    url, _ = _database_url_parts(database_url)
    engine, dispose = _engine_for(database_url)
    connection = engine.connect()
    snapshot_session = None
    transaction = None
    try:
        connection.execute(
            text("SELECT pg_advisory_lock(:key_one, :key_two)"),
            {"key_one": MEDIA_LOCK_KEYS[0], "key_two": MEDIA_LOCK_KEYS[1]},
        )
        connection.commit()
        with connection.begin():
            current_ids = set(connection.scalars(select(MediaObject.id)).all())
            current_ids.update(connection.scalars(select(MediaAsset.id)).all())
            pinned_ids = set(connection.scalars(
                select(BackupObjectReference.media_id)
                .where(BackupObjectReference.snapshot_id == snapshot_id)
            ).all())
            missing = current_ids - pinned_ids
            if missing:
                connection.execute(
                    BackupObjectReference.__table__.insert(),
                    [{"snapshot_id": snapshot_id, "media_id": media_id} for media_id in sorted(missing)],
                )
        connection = connection.execution_options(isolation_level="REPEATABLE READ")
        transaction = connection.begin()
        exported = connection.scalar(text("SELECT pg_export_snapshot()"))
        snapshot_session = Session(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint",
        )
        snapshot = snapshot_session.get(BackupSnapshot, snapshot_id)
        if snapshot is None or snapshot.status != "pending" or snapshot.retired_at is not None:
            raise RecoveryError("Backup snapshot is no longer pending")
        # The exported PG snapshot and committed references now fence this backup;
        # release the upload lock before slow provider reads or pg_dump.
        connection.execute(
            text("SELECT pg_advisory_unlock(:key_one, :key_two)"),
            {"key_one": MEDIA_LOCK_KEYS[0], "key_two": MEDIA_LOCK_KEYS[1]},
        )
        yield connection, snapshot_session, exported, url
        snapshot_session.close()
        snapshot_session = None
        transaction.commit()
    finally:
        if snapshot_session is not None:
            snapshot_session.close()
        if connection.in_transaction():
            connection.rollback()
        try:
            connection.execute(
                text("SELECT pg_advisory_unlock(:key_one, :key_two)"),
                {"key_one": MEDIA_LOCK_KEYS[0], "key_two": MEDIA_LOCK_KEYS[1]},
            )
            connection.commit()
        except Exception:
            connection.invalidate()
        connection.close()
        if dispose:
            engine.dispose()


def _erasure_records(session: Session) -> dict:
    accounts = session.execute(
        select(ErasedAccount.user_id, ErasedAccount.erased_at).order_by(ErasedAccount.user_id)
    ).all()
    requests = session.execute(
        select(ErasureRequest.id, ErasureRequest.user_id, ErasureRequest.completed_at)
        .where(ErasureRequest.status == "completed")
        .order_by(ErasureRequest.id)
    ).all()
    return {
        "erased_accounts": [
            {"user_id": row.user_id, "erased_at": row.erased_at.isoformat()} for row in accounts
        ],
        "completed_requests": [
            {"id": row.id, "user_id": row.user_id,
             "completed_at": row.completed_at.isoformat() if row.completed_at else None}
            for row in requests
        ],
    }


def _validate_erasure_records(records: dict) -> dict:
    if not isinstance(records, dict):
        raise RecoveryError("Erasure ledger is invalid")
    accounts = records.get("erased_accounts")
    requests = records.get("completed_requests")
    if (not isinstance(accounts, list) or not isinstance(requests, list)
            or len(accounts) > 10_000 or len(requests) > 10_000):
        raise RecoveryError("Erasure ledger is invalid")
    for row in accounts:
        if (not isinstance(row, dict) or not isinstance(row.get("user_id"), str)
                or not _SNAPSHOT_ID.fullmatch(row["user_id"])
                or not isinstance(row.get("erased_at"), str)):
            raise RecoveryError("Erasure ledger is invalid")
        _parse_aware_timestamp(row["erased_at"], "Archived erasure timestamp")
    for row in requests:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or not _SNAPSHOT_ID.fullmatch(row["id"])
                or row.get("user_id") is not None
                and (not isinstance(row["user_id"], str) or not _SNAPSHOT_ID.fullmatch(row["user_id"]))
                or row.get("completed_at") is not None and not isinstance(row["completed_at"], str)):
            raise RecoveryError("Erasure ledger is invalid")
        if row.get("completed_at") is not None:
            _parse_aware_timestamp(row["completed_at"], "Archived completion timestamp")
    return {"erased_accounts": accounts, "completed_requests": requests}


def _parse_aware_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise RecoveryError(f"{label} must be an ISO timestamp with a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise RecoveryError(f"{label} must be an ISO timestamp with a timezone") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecoveryError(f"{label} must be an ISO timestamp with a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_current_erasure_ledger(value: object) -> tuple[str, list[dict[str, str]]]:
    if (not isinstance(value, dict) or set(value) != {"format_version", "exported_at", "accounts"}
            or type(value.get("format_version")) is not int
            or value["format_version"] != FORMAT_VERSION
            or not isinstance(value.get("accounts"), list)
            or len(value["accounts"]) > 10_000):
        raise RecoveryError("Current erasure ledger is invalid")
    exported_at = _parse_aware_timestamp(value.get("exported_at"), "Erasure ledger exported_at")
    accounts = []
    seen = set()
    for row in value["accounts"]:
        if (not isinstance(row, dict) or set(row) != {"user_id", "erased_at"}
                or not isinstance(row.get("user_id"), str)):
            raise RecoveryError("Current erasure ledger is invalid")
        try:
            user_id = str(UUID(row["user_id"]))
        except ValueError:
            raise RecoveryError("Current erasure ledger is invalid") from None
        if user_id != row["user_id"].casefold() or user_id in seen:
            raise RecoveryError("Current erasure ledger is invalid")
        erased_at = _parse_aware_timestamp(row.get("erased_at"), "Erasure ledger erased_at")
        if erased_at > exported_at:
            raise RecoveryError("Current erasure ledger contains a future erasure timestamp")
        seen.add(user_id)
        accounts.append({"user_id": user_id, "erased_at": erased_at.isoformat()})
    return exported_at.isoformat(), accounts


def export_erasure_ledger(database_url: str, output_file: str | Path, key: bytes) -> dict:
    """Create a separate authenticated current erasure export for later restore."""
    candidate = Path(output_file).expanduser()
    if candidate.exists() or candidate.is_symlink() or not candidate.parent.is_dir():
        raise RecoveryError("Erasure ledger output must be a new file in an existing directory")
    parent = candidate.parent.resolve(strict=True)
    _assert_external_path(parent)
    _verify_private_permissions(parent, require_private=True)
    path = parent / candidate.name
    if len(key) != 32:
        raise RecoveryError("Backup key must be 32 bytes")
    engine, dispose = _engine_for(database_url)
    try:
        with Session(engine) as session:
            accounts = [
                {"user_id": row.user_id, "erased_at": row.erased_at.isoformat()}
                for row in session.execute(
                    select(ErasedAccount.user_id, ErasedAccount.erased_at)
                    .order_by(ErasedAccount.user_id)
                ).all()
            ]
        ledger_id = str(uuid4())
        exported_at = datetime.now(timezone.utc).isoformat()
        payload = {"format_version": FORMAT_VERSION, "exported_at": exported_at, "accounts": accounts}
        exported_at, accounts = _validate_current_erasure_ledger(payload)
        payload["exported_at"] = exported_at
        payload["accounts"] = accounts
        writer = _EncryptingWriter(path, key, "ledger", ledger_id)
        try:
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(encoded) > MAX_MANIFEST_BYTES:
                raise RecoveryError("Erasure ledger exceeds the size limit")
            writer.write(encoded)
            entry = writer.finish()
        except Exception:
            writer.abort()
            raise
        return {"ledger_id": ledger_id, "exported_at": exported_at, "path": str(path), "size": entry["size"]}
    except RecoveryError:
        raise
    except Exception:
        raise RecoveryError("Could not export the current erasure ledger") from None
    finally:
        if dispose:
            engine.dispose()


def _read_encrypted_id(path: Path, kind: str) -> str:
    with path.open("rb") as stream:
        length = len(MAGIC) + 1 + 1 + 12 + 36
        header = stream.read(length)
    if len(header) != length or header[:len(MAGIC)] != MAGIC:
        raise RecoveryError("Encrypted archive header is invalid")
    if header[len(MAGIC)] != FORMAT_VERSION or header[len(MAGIC) + 1:len(MAGIC) + 2] != _KIND_CODES[kind]:
        raise RecoveryError("Encrypted archive kind is invalid")
    try:
        archive_id = header[-36:].decode("ascii")
    except UnicodeDecodeError:
        raise RecoveryError("Encrypted archive ID is invalid") from None
    if not _SNAPSHOT_ID.fullmatch(archive_id):
        raise RecoveryError("Encrypted archive ID is invalid")
    return archive_id


def verify_erasure_ledger(
    ledger_file: str | Path,
    key: bytes,
    *,
    backup_created_at: str,
    erasure_cutoff_at: str | None = None,
) -> tuple[str, str, list[dict[str, str]]]:
    candidate = Path(ledger_file).expanduser()
    if candidate.is_symlink() or not candidate.is_file():
        raise RecoveryError("A separately encrypted current erasure ledger is required")
    path = candidate.resolve(strict=True)
    _assert_external_path(path)
    _verify_private_permissions(path, require_private=True)
    if path.stat().st_size > MAX_MANIFEST_BYTES + 128:
        raise RecoveryError("Erasure ledger exceeds the size limit")
    ledger_id = _read_encrypted_id(path, "ledger")
    chunks = _decrypt_chunks(path, key, "ledger", ledger_id)
    data = bytearray()
    for chunk in chunks:
        data.extend(chunk)
        if len(data) > MAX_MANIFEST_BYTES:
            raise RecoveryError("Erasure ledger exceeds the size limit")
    try:
        ledger = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise RecoveryError("Erasure ledger metadata is invalid") from None
    exported_at, accounts = _validate_current_erasure_ledger(ledger)
    exported_time = _parse_aware_timestamp(exported_at, "Erasure ledger exported_at")
    backup_time = _parse_aware_timestamp(backup_created_at, "Backup created_at")
    if erasure_cutoff_at is None:
        if exported_time <= backup_time:
            raise RecoveryError("Erasure ledger must be current and newer than the selected backup")
    else:
        cutoff_time = _parse_aware_timestamp(erasure_cutoff_at, "Erasure cutoff")
        if cutoff_time < backup_time or cutoff_time > datetime.now(timezone.utc):
            raise RecoveryError("Erasure cutoff must be between the selected backup and the current time")
        if exported_time < cutoff_time:
            raise RecoveryError("Current erasure ledger was exported before the confirmed erasure cutoff")
    return ledger_id, exported_at, accounts


def merge_erasure_records(archived: dict, current: dict) -> dict:
    """Union authenticated tombstones by their stable primary IDs."""
    merged_accounts = {}
    for row in [*_validate_erasure_records(archived)["erased_accounts"],
                *_validate_erasure_records(current)["erased_accounts"]]:
        existing = merged_accounts.get(row["user_id"])
        if existing is None or row["erased_at"] > existing["erased_at"]:
            merged_accounts[row["user_id"]] = row
    merged_requests = {}
    for row in [*_validate_erasure_records(archived)["completed_requests"],
                *_validate_erasure_records(current)["completed_requests"]]:
        existing = merged_requests.get(row["id"])
        if existing is None or (row["completed_at"] or "") > (existing["completed_at"] or ""):
            merged_requests[row["id"]] = row
    return {
        "erased_accounts": [merged_accounts[key] for key in sorted(merged_accounts)],
        "completed_requests": [merged_requests[key] for key in sorted(merged_requests)],
    }


def _read_retained_object(media_id: str, session: Session) -> tuple[bytes | None, str]:
    media = session.get(MediaObject, media_id)
    content = storage.read_webp(media_id, db=session)
    if content is not None:
        if len(content) > MAX_OBJECT_BYTES:
            raise RecoveryError("A retained media object exceeds the backup size limit")
        return content, media.status if media is not None else "legacy"
    if media is None:
        raise RecoveryError("A retained legacy media object could not be read")
    if media.status != "reserved":
        raise RecoveryError("A retained stored media object is missing or unreadable")
    try:
        present = storage.object_exists(media)
    except Exception:
        raise RecoveryError("A retained media reservation could not be checked") from None
    if not present:
        # An in-flight reservation may legitimately have no object yet, but a
        # snapshot-attached asset may never be silently restored without bytes.
        if session.get(MediaAsset, media_id) is not None:
            raise RecoveryError("An attached media reservation has no stored object")
        return None, "reserved"
    try:
        if media.provider == "local":
            content = storage._read_local(media_id)
        elif media.provider == "supabase":
            content = storage._read_supabase(media)
        else:
            content = None
    except Exception:
        raise RecoveryError("A retained media reservation exists but could not be read") from None
    if content is None or len(content) != media.byte_size or len(content) > MAX_OBJECT_BYTES:
        raise RecoveryError("A retained media reservation exists but could not be verified")
    return content, "reserved"


def _write_tar_objects(writer: _EncryptingWriter, session: Session, snapshot_id: str) -> list[dict]:
    references = session.scalars(
        select(BackupObjectReference.media_id)
        .where(BackupObjectReference.snapshot_id == snapshot_id)
        .order_by(BackupObjectReference.media_id)
    ).all()
    items = []
    with tarfile.open(fileobj=writer, mode="w|", format=tarfile.PAX_FORMAT) as archive:
        for media_id in references:
            if not _OBJECT_NAME.fullmatch(f"{media_id}.webp"):
                raise RecoveryError("A retained media ID is invalid")
            content, status = _read_retained_object(media_id, session)
            if content is None:
                items.append({
                    "id": media_id, "status": status, "exists": False,
                    "size": 0, "sha256": None,
                })
                continue
            item = {
                "id": media_id, "status": status, "exists": True,
                "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
            }
            info = tarfile.TarInfo(f"{media_id}.webp")
            info.size = len(content)
            info.mode = 0o600
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            archive.addfile(info, io.BytesIO(content))
            items.append(item)
    return items


def _write_json_encrypted(path: Path, key: bytes, snapshot_id: str, value: dict) -> dict:
    writer = _EncryptingWriter(path, key, "manifest", snapshot_id)
    try:
        writer.write(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return writer.finish()
    except Exception:
        writer.abort()
        raise


def _write_checksums(path: Path, snapshot_id: str, file_entries: dict[str, dict]) -> None:
    payload = {
        "format_version": FORMAT_VERSION,
        "snapshot_id": snapshot_id,
        "files": {
            name: {key: file_entries[name][key] for key in ("name", "size", "sha256")}
            for name in ("database", "objects", "manifest")
        },
    }
    with _open_private_file(path) as stream:
        stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    _verify_private_permissions(path, require_private=True)


def _set_snapshot_status(database_url: str, snapshot_id: str, status: str) -> None:
    engine, dispose = _engine_for(database_url)
    try:
        with Session(engine, expire_on_commit=False) as session, session.begin():
            snapshot = session.get(BackupSnapshot, snapshot_id)
            if snapshot is None or snapshot.retired_at is not None:
                raise RecoveryError("Backup snapshot is missing or already retired")
            if status == "complete" and snapshot.status != "pending":
                raise RecoveryError("Only a pending backup can be completed")
            snapshot.status = status
    except RecoveryError:
        raise
    except Exception:
        raise RecoveryError("Could not update backup snapshot status") from None
    finally:
        if dispose:
            engine.dispose()


def _cleanup_stage(stage: Path, root: Path) -> None:
    if not stage.exists():
        return
    resolved_root = root.resolve()
    resolved = stage.resolve()
    if resolved.parent != resolved_root or stage.is_symlink() or not stage.is_dir():
        raise RecoveryError("Refusing to remove an unexpected backup path")
    for child in stage.iterdir():
        if child.is_symlink() or not child.is_file() or child.name not in set(_FILE_NAMES.values()):
            raise RecoveryError("Refusing to remove unexpected backup staging content")
        child.unlink()
    stage.rmdir()


def _mark_failed(database_url: str, snapshot_id: str) -> None:
    try:
        _set_snapshot_status(database_url, snapshot_id, "failed")
    except Exception:
        # Pending references remain protective if the database cannot record failure.
        pass


def _list_weekly(database_url: str) -> list[BackupSnapshot]:
    engine, dispose = _engine_for(database_url)
    try:
        with Session(engine) as session:
            return list(session.scalars(
                select(BackupSnapshot)
                .where(BackupSnapshot.retired_at.is_(None),
                       BackupSnapshot.status == "complete",
                       BackupSnapshot.purpose == "weekly")
                .order_by(BackupSnapshot.created_at.desc(), BackupSnapshot.id.desc())
            ).all())
    except Exception:
        raise RecoveryError("Could not read weekly backup retention state") from None
    finally:
        if dispose:
            engine.dispose()


def _delete_archive(root: Path, snapshot_id: str, *, allow_partial: bool = False) -> None:
    bundle = _snapshot_directory(root, snapshot_id)
    partial = root / f".{snapshot_id}.partial"
    target = bundle if bundle.exists() else (partial if allow_partial and partial.exists() else None)
    if target is None:
        raise RecoveryError("Archive directory is missing; use --confirm-no-archive only after checking all copies")
    if target.is_symlink() or not target.is_dir() or target.resolve().parent != root.resolve():
        raise RecoveryError("Refusing to remove an unexpected archive path")
    allowed = set(_FILE_NAMES.values())
    names = {child.name for child in target.iterdir()}
    if not names.issubset(allowed):
        raise RecoveryError("Archive directory contains unexpected files")
    if target == bundle and "checksums.json" in names:
        checksum = _read_json(target / "checksums.json", 64 * 1024)
        if checksum.get("snapshot_id") != snapshot_id:
            raise RecoveryError("Archive checksum manifest belongs to another snapshot")
    for name in _FILE_NAMES.values():
        file = target / name
        if file.exists():
            if file.is_symlink() or not file.is_file():
                raise RecoveryError("Refusing to remove an unexpected archive component")
            file.unlink()
    target.rmdir()


def retire_snapshot(
    database_url: str,
    output_root: str | Path,
    snapshot_id: str,
    *,
    apply: bool = False,
    confirm_no_archive: bool = False,
) -> dict:
    """Dry-run by default. Delete archive bytes first, then release GC protection."""
    candidate = Path(output_root).expanduser()
    if candidate.is_symlink():
        raise RecoveryError("Backup output root must not be a symbolic link")
    root = candidate.resolve(strict=True)
    if not root.is_dir():
        raise RecoveryError("Backup output root must be a real directory")
    engine, dispose = _engine_for(database_url)
    try:
        with Session(engine) as session:
            snapshot = session.get(BackupSnapshot, snapshot_id)
            if snapshot is None:
                raise RecoveryError("Backup snapshot was not found")
            if snapshot.retired_at is not None:
                return {"snapshot_id": snapshot_id, "status": "retired", "changed": False}
            bundle = _snapshot_directory(root, snapshot_id)
            partial = root / f".{snapshot_id}.partial"
            archive_exists = bundle.exists() or partial.exists()
            if not archive_exists and not confirm_no_archive:
                raise RecoveryError("Archive is missing; confirm all copies are absent before retirement")
            plan = {
                "snapshot_id": snapshot_id,
                "purpose": snapshot.purpose,
                "status": snapshot.status,
                "archive": str(bundle if bundle.exists() else partial),
                "archive_exists": archive_exists,
                "will_retire": apply,
                "changed": False,
            }
        if not apply:
            return plan
        if archive_exists:
            _delete_archive(root, snapshot_id, allow_partial=True)
        with Session(engine, expire_on_commit=False) as session, session.begin():
            snapshot = session.get(BackupSnapshot, snapshot_id)
            if snapshot is None:
                raise RecoveryError("Backup snapshot disappeared before retirement")
            if snapshot.retired_at is None:
                snapshot.retired_at = datetime.now(timezone.utc)
        plan["changed"] = True
        plan["status"] = "retired"
        return plan
    except RecoveryError:
        raise
    except Exception:
        raise RecoveryError("Snapshot retirement could not be completed") from None
    finally:
        if dispose:
            engine.dispose()


def _retain_four_weeklies(database_url: str, root: Path) -> list[str]:
    warnings = []
    for snapshot in _list_weekly(database_url)[WEEKLY_RETENTION:]:
        try:
            retire_snapshot(database_url, root, snapshot.id, apply=True)
        except RecoveryError:
            warnings.append(snapshot.id)
    return warnings


def create_backup(
    database_url: str,
    output_root: str | Path,
    key: bytes,
    *,
    purpose: str = "weekly",
    timeout: int = 1800,
) -> dict:
    """Create a pending snapshot, stream two encrypted payloads, verify, then complete it."""
    if purpose not in SNAPSHOT_PURPOSES:
        raise RecoveryError("Backup purpose must be weekly or premigration")
    if len(key) != 32:
        raise RecoveryError("Backup key must be 32 bytes")
    root = _assert_external_root(output_root)
    snapshot_id = str(uuid4())
    final = _snapshot_directory(root, snapshot_id)
    stage = root / f".{snapshot_id}.partial"
    if final.exists() or stage.exists():
        raise RecoveryError("Backup output collision; choose another output directory")
    pinned = False
    installed = False
    try:
        _create_pending_snapshot(database_url, snapshot_id, purpose)
        pinned = True
        permissions_verified = _make_private_directory(stage)
        url, pg_env = _database_url_parts(database_url)
        process_env = os.environ.copy() | pg_env
        with _consistent_snapshot(database_url, snapshot_id) as (
            connection, snapshot_session, exported_snapshot, _,
        ):
            snapshot = snapshot_session.get(BackupSnapshot, snapshot_id)
            if snapshot is None:
                raise RecoveryError("Pinned backup snapshot is unavailable")
            database_args = [
                "--schema=public", "--no-owner", "--no-acl", "--format=plain",
                "--clean", "--if-exists", f"--snapshot={exported_snapshot}",
                "--host", url.host, "--port", str(url.port),
                "--username", url.username or "", "--dbname", url.database,
            ]
            dump_command, dump_env = _postgres_command("pg_dump", url, process_env, database_args)
            database_writer = _EncryptingWriter(
                stage / _FILE_NAMES["database"], key, "database", snapshot_id,
            )
            try:
                _stream_process(dump_command, dump_env, database_writer, timeout)
                database_entry = database_writer.finish()
            except Exception:
                database_writer.abort()
                raise

            objects_writer = _EncryptingWriter(
                stage / _FILE_NAMES["objects"], key, "objects", snapshot_id,
            )
            try:
                object_items = _write_tar_objects(objects_writer, snapshot_session, snapshot_id)
                objects_entry = objects_writer.finish()
            except Exception:
                objects_writer.abort()
                raise
            erasures = _erasure_records(snapshot_session)
            manifest = {
                "format_version": FORMAT_VERSION,
                "snapshot_id": snapshot_id,
                "purpose": purpose,
                "created_at": snapshot.created_at.isoformat(),
                "archive_status": "verified",
                "database": {
                    "schema": "public",
                    "sha256": database_entry["plaintext_sha256"],
                    "size": database_entry["plaintext_size"],
                },
                "objects": object_items,
                "erasures": erasures,
            }
            manifest_entry = _write_json_encrypted(
                stage / _FILE_NAMES["manifest"], key, snapshot_id, manifest,
            )
        _write_checksums(
            stage / _FILE_NAMES["checksums"], snapshot_id,
            {"database": database_entry, "objects": objects_entry, "manifest": manifest_entry},
        )
        verify_backup(stage, key, snapshot_id=snapshot_id)
        stage.rename(final)
        installed = True
        _set_snapshot_status(database_url, snapshot_id, "complete")
        warnings = _retain_four_weeklies(database_url, root)
        return {
            "snapshot_id": snapshot_id,
            "purpose": purpose,
            "path": str(final),
            "objects": len(object_items),
            "permissions_verified": permissions_verified,
            "retention_warnings": warnings,
        }
    except RecoveryError:
        if pinned:
            if not installed:
                try:
                    _cleanup_stage(stage, root)
                except RecoveryError:
                    pass
            _mark_failed(database_url, snapshot_id)
        raise
    except Exception:
        if pinned:
            if not installed:
                try:
                    _cleanup_stage(stage, root)
                except RecoveryError:
                    pass
            _mark_failed(database_url, snapshot_id)
        raise RecoveryError(
            f"Backup failed for snapshot {snapshot_id}; its references remain protective"
        ) from None


def restore_backup(
    bundle_dir: str | Path,
    key: bytes,
    target_database_url: str,
    target_media_root: str | Path,
    erasure_replayer: Callable[[list[dict[str, str]], str], object] | None = None,
    *,
    erasure_ledger_file: str | Path | None = None,
    erasure_cutoff_at: str | None = None,
    confirm_erasure_quiescence: bool = False,
    timeout: int = 1800,
) -> dict:
    """Restore only to a new isolated target, after full archive authentication."""
    if len(key) != 32:
        raise RecoveryError("Backup key must be 32 bytes")
    if erasure_ledger_file is None:
        raise RecoveryError("Restore requires a separately exported current erasure ledger")
    if erasure_cutoff_at is None:
        raise RecoveryError("Restore requires the confirmed erasure cutoff timestamp")
    if confirm_erasure_quiescence is not True:
        raise RecoveryError("Restore requires explicit confirmation that erasure fulfillment and writes are quiesced")
    cutoff_time = _parse_aware_timestamp(erasure_cutoff_at, "Erasure cutoff")
    if cutoff_time > datetime.now(timezone.utc):
        raise RecoveryError("Erasure cutoff cannot be in the future")
    if erasure_replayer is not None and not callable(erasure_replayer):
        raise RecoveryError("Erasure replay callback is invalid")
    target_url = validate_restore_database_url(target_database_url)
    candidate_bundle = Path(bundle_dir).expanduser()
    if candidate_bundle.is_symlink():
        raise RecoveryError("Backup directory must not be a symbolic link")
    bundle = candidate_bundle.resolve(strict=True)
    if not _SNAPSHOT_ID.fullmatch(bundle.name):
        raise RecoveryError("Restore requires a finalized backup directory named with its snapshot UUID")
    manifest = verify_backup(bundle, key)
    ledger_id, ledger_exported_at, erased_accounts = verify_erasure_ledger(
        erasure_ledger_file,
        key,
        backup_created_at=manifest["created_at"],
        erasure_cutoff_at=cutoff_time.isoformat(),
    )
    if erasure_replayer is None:
        erasure_replayer = _resolve_erasure_replayer()
    candidate_media_root = Path(target_media_root).expanduser()
    if candidate_media_root.is_symlink() or candidate_media_root.parent.is_symlink():
        raise RecoveryError("Restore media root must not use symbolic links")
    media_root = candidate_media_root.resolve()
    _assert_external_path(media_root)
    if not re.fullmatch(r"intraspot_restore_[a-z0-9_]+", media_root.name):
        raise RecoveryError("Restore media root must be a new intraspot_restore_* directory")
    if media_root.exists() or media_root.is_symlink():
        raise RecoveryError("Restore media root must not already exist")
    if (_is_relative_to(media_root, bundle) or _is_relative_to(bundle, media_root)):
        raise RecoveryError("Restore media root must be separate from the backup archive")
    parent = media_root.parent
    if not parent.exists() or not parent.is_dir() or parent.is_symlink():
        raise RecoveryError("Restore media root parent must already exist")
    staging = parent / f".{media_root.name}.{bundle.name}.restore-partial"
    journal = parent / f".{media_root.name}.{bundle.name}.restore-journal.json"
    if staging.exists() or staging.is_symlink() or journal.exists():
        raise RecoveryError("A restore journal or staging directory already exists")
    _verify_target_empty(target_url)
    _, target_env = _database_url_parts(target_database_url)
    process_env = os.environ.copy() | target_env
    journal_data = {
        "snapshot_id": bundle.name,
        "erasure_ledger_id": ledger_id,
        "erasure_ledger_exported_at": ledger_exported_at,
        "erasure_cutoff_at": cutoff_time.isoformat(),
        "erasure_quiescence_confirmed": True,
        "target_database": target_url.database,
        "media_root": media_root.name,
        "status": "in_progress",
        "step": "staging_objects",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_journal(journal, journal_data)
    try:
        _make_private_directory(staging)
        _restore_objects(bundle, key, manifest, staging)
        journal_data["step"] = "restoring_database"
        _write_journal(journal, journal_data)
        _restore_database(
            bundle, key, target_database_url, manifest, process_env, staging,
            timeout=timeout,
        )
        journal_data["step"] = "replaying_erasures"
        _write_journal(journal, journal_data)
        erasure_replayer(erased_accounts, target_database_url)
        staging.rename(media_root)
        journal_data["step"] = "complete"
        journal_data["status"] = "complete"
        journal_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_journal(journal, journal_data)
        _verify_private_permissions(journal)
        return {"snapshot_id": bundle.name, "database": target_url.database, "media_root": str(media_root)}
    except Exception:
        journal_data["status"] = "failed_or_interrupted"
        journal_data["step"] = "operator_review_required"
        journal_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            _write_journal(journal, journal_data)
        except Exception:
            pass
        raise


def _verify_target_empty(url) -> None:
    try:
        connection = psycopg.connect(
            host=url.host, port=url.port, dbname=url.database, user=url.username,
            password=url.password, connect_timeout=5,
            **{key: value for key, value in url.query.items()
               if key in {"sslmode", "sslrootcert", "sslcert", "sslkey"} and isinstance(value, str)},
        )
    except Exception:
        raise RecoveryError("Could not connect to the isolated restore target") from None
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                  EXISTS (
                    SELECT 1 FROM pg_class AS c
                    JOIN pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname !~ '^pg_'
                      AND n.nspname <> 'information_schema'
                      AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
                  )
                  OR EXISTS (
                    SELECT 1 FROM pg_namespace
                    WHERE nspname !~ '^pg_'
                      AND nspname NOT IN ('information_schema', 'public')
                  )
            """)
            row = cursor.fetchone()
            if not row or row[0]:
                raise RecoveryError("Restore target is not empty")
    finally:
        connection.close()


def _write_journal(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        with _open_private_file(temporary) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _verify_private_permissions(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _restore_objects(bundle: Path, key: bytes, manifest: dict, staging: Path) -> None:
    expected = {item["id"]: item for item in manifest["objects"] if item["exists"]}
    reader = _ChunkReader(_decrypt_chunks(_bundle_paths(bundle)["objects"], key, "objects", bundle.name))
    seen = set()
    try:
        with tarfile.open(fileobj=reader, mode="r|") as archive:
            for member in archive:
                if not member.isfile() or not _OBJECT_NAME.fullmatch(member.name):
                    raise RecoveryError("Media archive contains an unsafe entry")
                media_id = member.name[:-5]
                item = expected.get(media_id)
                if item is None or media_id in seen or member.size != item["size"]:
                    raise RecoveryError("Media archive does not match its encrypted manifest")
                source = archive.extractfile(member)
                if source is None:
                    raise RecoveryError("Media archive entry could not be read")
                target = staging / member.name
                digest = hashlib.sha256()
                size = 0
                with _open_private_file(target) as output:
                    while chunk := source.read(CHUNK_SIZE):
                        output.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if digest.hexdigest() != item["sha256"] or size != item["size"]:
                    target.unlink(missing_ok=True)
                    raise RecoveryError("Restored media object checksum mismatch")
                seen.add(media_id)
        reader.drain()
    except (tarfile.TarError, OSError):
        raise RecoveryError("Media archive is invalid") from None
    if seen != set(expected):
        raise RecoveryError("Media archive is missing retained objects")


def _stage_authenticated_database(
    bundle: Path, key: bytes, manifest: dict, staging: Path,
) -> Path:
    _verify_private_permissions(staging, require_private=True)
    path = staging / f".authenticated-database-{uuid4().hex}.tmp"
    digest = hashlib.sha256()
    size = 0
    try:
        with _open_private_file(path) as output:
            for chunk in _decrypt_chunks(
                _bundle_paths(bundle)["database"], key, "database", bundle.name,
            ):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            output.flush()
            os.fsync(output.fileno())
        expected = manifest["database"]
        if digest.hexdigest() != expected["sha256"] or size != expected["size"]:
            raise RecoveryError("Decrypted database checksum mismatch")
        _verify_private_permissions(path, require_private=True)
        return path
    except RecoveryError:
        path.unlink(missing_ok=True)
        raise
    except Exception:
        path.unlink(missing_ok=True)
        raise RecoveryError("Could not stage the authenticated database dump") from None


def _restore_database(
    bundle: Path,
    key: bytes,
    database_url: str,
    manifest: dict,
    env: dict[str, str],
    staging: Path,
    *,
    timeout: int,
) -> None:
    authenticated_dump = _stage_authenticated_database(bundle, key, manifest, staging)
    try:
        url, _ = _database_url_parts(database_url)
        target = validate_restore_database_url(database_url)
        args = [
            "--no-psqlrc", "--set=ON_ERROR_STOP=1", "--single-transaction",
            "--host", url.host, "--port", str(url.port),
            "--username", url.username or "", "--dbname", target.database,
        ]
        command, env = _postgres_command("psql", url, env, args)
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, env=env, bufsize=0,
            )
        except OSError:
            raise RecoveryError("Could not start psql") from None
        deadline = time.monotonic() + timeout
        try:
            with authenticated_dump.open("rb") as dump:
                while chunk := dump.read(CHUNK_SIZE):
                    if time.monotonic() >= deadline:
                        raise RecoveryError("psql restore exceeded its configured timeout")
                    if process.poll() is not None:
                        raise RecoveryError("psql exited before the authenticated dump was fully consumed")
                    try:
                        process.stdin.write(chunk)
                    except OSError:
                        raise RecoveryError("psql closed the restore stream before completion") from None
            process.stdin.close()
            try:
                code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise RecoveryError("psql restore exceeded its configured timeout") from None
            if code != 0:
                raise RecoveryError(f"psql restore failed with exit code {code}")
        except Exception:
            try:
                if process.poll() is None and process.stdin and not process.stdin.closed:
                    process.stdin.write(b"\nSELECT 1/0;\n")
                    process.stdin.close()
                    process.wait(timeout=5)
            except Exception:
                _terminate_process(process)
            raise
    finally:
        authenticated_dump.unlink(missing_ok=True)


def _resolve_erasure_replayer() -> Callable[[dict, str], object]:
    try:
        from app.account_erasure import replay_erasures
    except Exception:
        raise RecoveryError("Restore is blocked until app.account_erasure.replay_erasures is available") from None
    if not callable(replay_erasures):
        raise RecoveryError("Restore is blocked until app.account_erasure.replay_erasures is available")
    return replay_erasures


def list_snapshots(database_url: str) -> list[dict]:
    url, _ = _database_url_parts(database_url)
    engine = configured_engine() if database_url == get_settings().database_url else __import__(
        "sqlalchemy"
    ).create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    try:
        with Session(engine) as session:
            rows = session.scalars(
                select(BackupSnapshot).order_by(BackupSnapshot.created_at.desc())
            ).all()
            return [{
                "id": row.id, "created_at": row.created_at.isoformat(),
                "purpose": row.purpose, "status": row.status,
                "retired_at": row.retired_at.isoformat() if row.retired_at else None,
            } for row in rows]
    except Exception:
        raise RecoveryError("Could not list backup snapshots") from None
    finally:
        if engine is not configured_engine():
            engine.dispose()
