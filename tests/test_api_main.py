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


@pytest.mark.asyncio
async def test_integrity_error_returns_422(db_session: Session) -> None:
    """SAIntegrityError raised inside a route is caught and returned as 422."""
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    from fastapi import APIRouter
    from vms.api.deps import get_db
    from vms.api.main import app

    _test_router = APIRouter()

    @_test_router.post("/test-integrity-error")
    def _raise_integrity() -> None:
        raise SAIntegrityError("INSERT ...", {}, Exception("unique constraint"))

    app.include_router(_test_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/test-integrity-error")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.routes[:] = [route for route in app.routes if getattr(route, "path", None) != "/api/test-integrity-error"]

    assert r.status_code == 422
    assert "detail" in r.json()
