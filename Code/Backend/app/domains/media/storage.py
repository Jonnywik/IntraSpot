from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import get_settings


class MediaStorageError(OSError):
    """A media file could not be written or read."""


def store_webp(content: bytes) -> str:
    root = get_settings().media_root
    temporary_path: Path | None = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".media-", suffix=".tmp", dir=root, delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())

        for _ in range(3):
            media_id = str(uuid4())
            destination = root / f"{media_id}.webp"
            try:
                # Reserve only a new name; replacement may never overwrite an
                # existing asset, including a UUID collision or symbolic link.
                descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(descriptor)
            except FileExistsError:
                continue
            try:
                os.replace(temporary_path, destination)
                temporary_path = None
                return media_id
            except OSError:
                destination.unlink(missing_ok=True)
                raise
        raise MediaStorageError
    except MediaStorageError:
        raise
    except OSError:
        raise MediaStorageError from None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def read_webp(media_id: str) -> bytes | None:
    try:
        parsed = UUID(media_id)
    except (ValueError, AttributeError):
        return None
    if str(parsed) != media_id.lower():
        return None
    try:
        return (get_settings().media_root / f"{parsed}.webp").read_bytes()
    except OSError:
        return None
