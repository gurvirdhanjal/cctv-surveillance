"""Unit tests for vms.storage.factory — get_storage() singleton."""

from __future__ import annotations

import pathlib

import pytest

from vms.storage.backends import LocalStorageBackend, StorageBackend


def test_get_storage_returns_local_backend_by_default(tmp_path: pathlib.Path) -> None:
    from unittest.mock import patch

    from vms.config import Settings
    from vms.storage.factory import clear_storage_cache, get_storage

    clear_storage_cache()
    fake = Settings(  # type: ignore[call-arg]
        db_url="postgresql://x/y",
        jwt_secret="s",
        storage_backend="local",
        storage_local_dir=str(tmp_path),
    )
    with patch("vms.storage.factory.get_settings", return_value=fake):
        backend = get_storage()
    assert isinstance(backend, LocalStorageBackend)
    assert isinstance(backend, StorageBackend)
    clear_storage_cache()


def test_get_storage_raises_for_unknown_backend() -> None:
    from unittest.mock import patch

    from vms.config import Settings
    from vms.storage.factory import clear_storage_cache, get_storage

    clear_storage_cache()
    fake = Settings(  # type: ignore[call-arg]
        db_url="postgresql://x/y",
        jwt_secret="s",
        storage_backend="invalid",
    )
    with patch("vms.storage.factory.get_settings", return_value=fake), pytest.raises(ValueError):
        get_storage()
    clear_storage_cache()


def test_get_storage_is_singleton(tmp_path: pathlib.Path) -> None:
    from unittest.mock import patch

    from vms.config import Settings
    from vms.storage.factory import clear_storage_cache, get_storage

    clear_storage_cache()
    fake = Settings(  # type: ignore[call-arg]
        db_url="postgresql://x/y",
        jwt_secret="s",
        storage_backend="local",
        storage_local_dir=str(tmp_path),
    )
    with patch("vms.storage.factory.get_settings", return_value=fake):
        b1 = get_storage()
        b2 = get_storage()
    assert b1 is b2
    clear_storage_cache()


def test_clear_storage_cache_allows_new_instance(tmp_path: pathlib.Path) -> None:
    from unittest.mock import patch

    from vms.config import Settings
    from vms.storage.factory import clear_storage_cache, get_storage

    clear_storage_cache()
    fake = Settings(  # type: ignore[call-arg]
        db_url="postgresql://x/y",
        jwt_secret="s",
        storage_backend="local",
        storage_local_dir=str(tmp_path),
    )
    with patch("vms.storage.factory.get_settings", return_value=fake):
        b1 = get_storage()
        clear_storage_cache()
        b2 = get_storage()
    assert b1 is not b2
    clear_storage_cache()
