"""Unit tests for vms.storage.media — write_thumbnail and write_snapshot helpers."""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock


def test_write_thumbnail_returns_key_with_thumbnails_prefix(tmp_path: pathlib.Path) -> None:
    from vms.storage.backends import LocalStorageBackend
    from vms.storage.media import write_thumbnail

    backend = LocalStorageBackend(str(tmp_path))
    key = write_thumbnail(person_id=1, data=b"img", storage=backend)
    assert key.startswith("thumbnails/")


def test_write_snapshot_returns_key_with_snapshots_prefix(tmp_path: pathlib.Path) -> None:
    from vms.storage.backends import LocalStorageBackend
    from vms.storage.media import write_snapshot

    backend = LocalStorageBackend(str(tmp_path))
    key = write_snapshot(camera_id=5, data=b"snap", storage=backend)
    assert key.startswith("snapshots/")


def test_write_thumbnail_key_stored_via_backend() -> None:
    from vms.storage.media import write_thumbnail

    mock_backend = MagicMock()
    key = write_thumbnail(person_id=42, data=b"data", storage=mock_backend)
    mock_backend.write.assert_called_once_with(key, b"data")


def test_write_snapshot_key_stored_via_backend() -> None:
    from vms.storage.media import write_snapshot

    mock_backend = MagicMock()
    key = write_snapshot(camera_id=7, data=b"frame", storage=mock_backend)
    mock_backend.write.assert_called_once_with(key, b"frame")


def test_write_thumbnail_data_retrievable(tmp_path: pathlib.Path) -> None:
    from vms.storage.backends import LocalStorageBackend
    from vms.storage.media import write_thumbnail

    backend = LocalStorageBackend(str(tmp_path))
    data = b"\xff\xd8\xff"
    key = write_thumbnail(person_id=1, data=data, storage=backend)
    assert backend.read(key) == data
