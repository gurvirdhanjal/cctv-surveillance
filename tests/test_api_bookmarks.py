"""Tests for /api/bookmarks (Phase 4P Task 8)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.models import Bookmark, Camera, User, UserCameraPermission


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_user(db: Session, role: str = "guard") -> User:
    user = User(username=f"bm_{uuid.uuid4().hex[:8]}", password_hash="x", role=role)
    db.add(user)
    db.flush()
    return user


def _seed_camera(db: Session) -> int:
    cam = Camera(name=f"BM_{uuid.uuid4().hex[:6]}", rtsp_url="rtsp://x", capability_tier="FULL")
    db.add(cam)
    db.flush()
    return cam.camera_id


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.user_id, user.role)}"}


async def _req(
    db: Session,
    method: str,
    path: str,
    headers: dict[str, str],
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.request(method, path, json=body, headers=headers)
    finally:
        app.dependency_overrides.clear()
    return resp.status_code, (resp.json() if resp.content else {})


async def test_create_bookmark_returns_201(db_session: Session) -> None:
    user = _seed_user(db_session)
    cam = _seed_camera(db_session)
    body = {"camera_id": cam, "ts": _utcnow().isoformat(), "note": "forklift near dock"}

    status, resp = await _req(db_session, "POST", "/api/bookmarks", _auth(user), body)

    assert status == 201
    assert resp["camera_id"] == cam
    assert resp["note"] == "forklift near dock"
    row = db_session.get(Bookmark, resp["bookmark_id"])
    assert row is not None
    assert row.user_id == user.user_id


async def test_create_bookmark_wrong_camera_scope_returns_403(db_session: Session) -> None:
    user = _seed_user(db_session)
    cam_allowed = _seed_camera(db_session)
    cam_denied = _seed_camera(db_session)
    db_session.add(UserCameraPermission(user_id=user.user_id, camera_id=cam_allowed))
    db_session.flush()

    body = {"camera_id": cam_denied, "ts": _utcnow().isoformat()}
    status, _ = await _req(db_session, "POST", "/api/bookmarks", _auth(user), body)
    assert status == 403


async def test_list_returns_own_rows_only_with_camera_filter(db_session: Session) -> None:
    mine = _seed_user(db_session)
    other = _seed_user(db_session)
    cam_a = _seed_camera(db_session)
    cam_b = _seed_camera(db_session)
    ts = _utcnow().isoformat()

    await _req(db_session, "POST", "/api/bookmarks", _auth(mine), {"camera_id": cam_a, "ts": ts})
    await _req(db_session, "POST", "/api/bookmarks", _auth(mine), {"camera_id": cam_b, "ts": ts})
    await _req(db_session, "POST", "/api/bookmarks", _auth(other), {"camera_id": cam_a, "ts": ts})

    status, body = await _req(db_session, "GET", "/api/bookmarks", _auth(mine))
    assert status == 200
    assert len(body) == 2

    status, body = await _req(db_session, "GET", f"/api/bookmarks?camera_id={cam_a}", _auth(mine))
    assert status == 200
    assert len(body) == 1
    assert body[0]["camera_id"] == cam_a


async def test_delete_own_bookmark_204_others_404(db_session: Session) -> None:
    mine = _seed_user(db_session)
    other = _seed_user(db_session)
    cam = _seed_camera(db_session)
    ts = _utcnow().isoformat()

    _, created = await _req(
        db_session, "POST", "/api/bookmarks", _auth(mine), {"camera_id": cam, "ts": ts}
    )
    bookmark_id = created["bookmark_id"]

    # another user's delete: 404, never 403 -- existence must not leak
    status, _ = await _req(db_session, "DELETE", f"/api/bookmarks/{bookmark_id}", _auth(other))
    assert status == 404
    assert db_session.get(Bookmark, bookmark_id) is not None

    status, _ = await _req(db_session, "DELETE", f"/api/bookmarks/{bookmark_id}", _auth(mine))
    assert status == 204
    assert db_session.get(Bookmark, bookmark_id) is None


async def test_delete_unknown_bookmark_returns_404(db_session: Session) -> None:
    user = _seed_user(db_session)
    status, _ = await _req(db_session, "DELETE", "/api/bookmarks/999999", _auth(user))
    assert status == 404


async def test_bookmarks_unauthenticated_returns_401(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/bookmarks")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 401
