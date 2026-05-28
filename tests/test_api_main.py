"""Tests for static media mount and startup behaviour in vms.api.main."""

from __future__ import annotations

import pathlib
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vms.api.main import _apply_media_mount


def test_media_route_mounted_for_local_backend(tmp_path: pathlib.Path) -> None:
    """/media is mounted when storage_backend=='local' and directory exists."""
    from vms.config import Settings

    fake = Settings(  # type: ignore[call-arg]
        db_url="postgresql://x/y",
        jwt_secret="s",
        storage_backend="local",
        storage_local_dir=str(tmp_path),
    )
    test_app = FastAPI()
    _apply_media_mount(test_app, fake)
    routes = [r.path for r in test_app.routes]
    assert "/media" in routes


def test_media_route_not_mounted_for_minio_backend() -> None:
    """No /media route when storage_backend=='minio'."""
    from vms.config import Settings

    fake = Settings(  # type: ignore[call-arg]
        db_url="postgresql://x/y",
        jwt_secret="s",
        storage_backend="minio",
        minio_endpoint="http://minio:9000",
    )
    test_app = FastAPI()
    _apply_media_mount(test_app, fake)
    routes = [r.path for r in test_app.routes]
    assert "/media" not in routes


def test_media_route_not_mounted_when_dir_missing() -> None:
    """No /media route when local dir doesn't exist yet."""
    from vms.config import Settings

    fake = Settings(  # type: ignore[call-arg]
        db_url="postgresql://x/y",
        jwt_secret="s",
        storage_backend="local",
        storage_local_dir="/nonexistent/path/that/does/not/exist",
    )
    test_app = FastAPI()
    _apply_media_mount(test_app, fake)
    routes = [r.path for r in test_app.routes]
    assert "/media" not in routes


def test_media_mount_serves_static_files(tmp_path: pathlib.Path) -> None:
    """Mounted route is a StaticFiles instance."""
    from vms.config import Settings

    fake = Settings(  # type: ignore[call-arg]
        db_url="postgresql://x/y",
        jwt_secret="s",
        storage_backend="local",
        storage_local_dir=str(tmp_path),
    )
    test_app = FastAPI()
    _apply_media_mount(test_app, fake)
    media_routes = [r for r in test_app.routes if getattr(r, "path", None) == "/media"]
    assert len(media_routes) == 1
    assert isinstance(media_routes[0].app, StaticFiles)  # type: ignore[union-attr]


def test_startup_calls_ensure_future_partitions() -> None:
    """ensure_future_partitions is called once during app startup."""
    from vms.api.main import _call_ensure_future_partitions

    with patch("vms.api.main.ensure_future_partitions") as mock_ensure:
        _call_ensure_future_partitions()
    mock_ensure.assert_called_once()
