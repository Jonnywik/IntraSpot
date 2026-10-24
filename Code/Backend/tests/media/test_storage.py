from uuid import UUID, uuid4

import pytest

from app.core.config import get_settings
from app.domains.media import storage


def test_atomic_storage_persists_across_reads_and_never_overwrites_collision(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), 'media_root', tmp_path)
    first, second = uuid4(), uuid4()
    (tmp_path / f'{first}.webp').write_bytes(b'previous image')
    identities = iter([first, second])
    monkeypatch.setattr(storage, 'uuid4', lambda: next(identities))
    identifier = storage.store_webp(b'normalized new image')
    assert UUID(identifier) == second
    assert storage.read_webp(str(first)) == b'previous image'
    assert storage.read_webp(identifier) == b'normalized new image'
    assert not list(tmp_path.glob('.media-*.tmp'))
    assert storage.read_webp('../outside') is None


def test_failed_atomic_install_preserves_previous_file_and_cleans_reserved_name(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), 'media_root', tmp_path)
    previous = uuid4()
    (tmp_path / f'{previous}.webp').write_bytes(b'previous image')
    def unavailable(*_args):
        raise PermissionError('synthetic failure')
    monkeypatch.setattr(storage.os, 'replace', unavailable)
    with pytest.raises(storage.MediaStorageError):
        storage.store_webp(b'normalized new image')
    assert list(tmp_path.iterdir()) == [tmp_path / f'{previous}.webp']
    assert storage.read_webp(str(previous)) == b'previous image'
