"""Tests for _apply_spa_mount (Phase 4G.8 — SPA production wiring)."""

from __future__ import annotations

import pathlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vms.api.main import _apply_spa_mount
from vms.config import Settings


@pytest.fixture()
def dist_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "dist"
    d.mkdir()
    (d / "index.html").write_text("<html><body>SPA</body></html>")
    assets = d / "assets"
    assets.mkdir()
    (assets / "main.js").write_text("console.log('hello')")
    (d / "favicon.ico").write_bytes(b"\x00" * 16)
    return d


def _spa_settings(enabled: bool = True) -> Settings:
    return Settings.model_construct(serve_frontend=enabled)


# ── serve_frontend=False ──────────────────────────────────────────────────────


def test_serve_frontend_disabled_leaves_no_catch_all(dist_dir: pathlib.Path) -> None:
    app = FastAPI()
    _apply_spa_mount(app, _spa_settings(enabled=False), dist_path=dist_dir)
    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/admin/cameras")
    assert r.status_code == 404


def test_serve_frontend_missing_dist_skips_silently(tmp_path: pathlib.Path) -> None:
    app = FastAPI()
    non_existent = tmp_path / "no_dist"
    _apply_spa_mount(app, _spa_settings(), dist_path=non_existent)
    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/")
    assert r.status_code == 404


# ── serve_frontend=True ───────────────────────────────────────────────────────


def test_spa_root_returns_index_html(dist_dir: pathlib.Path) -> None:
    app = FastAPI()
    _apply_spa_mount(app, _spa_settings(), dist_path=dist_dir)
    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/")
    assert r.status_code == 200
    assert "<html>" in r.text


def test_spa_deep_route_returns_index_html(dist_dir: pathlib.Path) -> None:
    app = FastAPI()
    _apply_spa_mount(app, _spa_settings(), dist_path=dist_dir)
    client = TestClient(app, raise_server_exceptions=True)
    for path in ("/admin/cameras", "/live", "/admin/persons/42"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} → {r.status_code}"
        assert "<html>" in r.text


def test_spa_serves_real_file_when_it_exists(dist_dir: pathlib.Path) -> None:
    app = FastAPI()
    _apply_spa_mount(app, _spa_settings(), dist_path=dist_dir)
    client = TestClient(app, raise_server_exceptions=True)
    # favicon.ico exists directly in dist/
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")


def test_spa_assets_dir_mounted(dist_dir: pathlib.Path) -> None:
    app = FastAPI()
    _apply_spa_mount(app, _spa_settings(), dist_path=dist_dir)
    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/assets/main.js")
    assert r.status_code == 200
    assert "hello" in r.text


def test_spa_api_route_takes_precedence(dist_dir: pathlib.Path) -> None:
    """API routes registered before the mount must not be swallowed by the catch-all."""
    app = FastAPI()

    @app.get("/api/health")
    async def _health() -> dict[str, str]:
        return {"status": "ok"}

    _apply_spa_mount(app, _spa_settings(), dist_path=dist_dir)
    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_spa_skips_assets_mount_when_assets_dir_absent(tmp_path: pathlib.Path) -> None:
    """When dist/ exists but has no assets/ sub-dir, mount still works."""
    d = tmp_path / "dist"
    d.mkdir()
    (d / "index.html").write_text("<html>minimal</html>")
    app = FastAPI()
    _apply_spa_mount(app, _spa_settings(), dist_path=d)
    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/admin")
    assert r.status_code == 200
    assert "minimal" in r.text
