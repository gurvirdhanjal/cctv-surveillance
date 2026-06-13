"""Tests for GET /api/forensic/clips/{id} and GET /api/forensic/search."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.models import Camera, PersonClipEmbedding


def _auth(role: str = "manager") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_camera(db: Session) -> int:
    cam = Camera(name=f"FC_{uuid.uuid4().hex[:6]}", rtsp_url="rtsp://x", capability_tier="FULL")
    db.add(cam)
    db.flush()
    return cam.camera_id


def _seed_clip(
    db: Session,
    track_id: uuid.UUID,
    camera_id: int,
    ts: datetime,
) -> PersonClipEmbedding:
    clip = PersonClipEmbedding(
        global_track_id=track_id,
        camera_id=camera_id,
        event_ts=ts,
        embedding=[0.0] * 512,
        snapshot_path="snapshots/2026/06/13/cam001/abc.jpg",
    )
    db.add(clip)
    db.flush()
    return clip


# -- clips endpoint -----------------------------------------------------------


@pytest.mark.asyncio
async def test_forensic_clips_returns_clips_within_window(db_session: Session) -> None:
    cam_id = _seed_camera(db_session)
    track_id = uuid.uuid4()
    now = _utcnow()

    _seed_clip(db_session, track_id, cam_id, now)
    _seed_clip(db_session, track_id, cam_id, now + timedelta(seconds=10))
    _seed_clip(db_session, track_id, cam_id, now + timedelta(seconds=120))  # outside +-30s

    around_ts = (now + timedelta(seconds=5)).isoformat()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                f"/api/forensic/clips/{track_id}?around_ts={around_ts}",
                headers=_auth(),
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(cl["global_track_id"] == str(track_id) for cl in data["clips"])
    assert all(cl["snapshot_url"].startswith("/media/") for cl in data["clips"])


@pytest.mark.asyncio
async def test_forensic_clips_no_around_ts_returns_all(db_session: Session) -> None:
    cam_id = _seed_camera(db_session)
    track_id = uuid.uuid4()
    now = _utcnow()

    for i in range(3):
        _seed_clip(db_session, track_id, cam_id, now + timedelta(minutes=i))

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/forensic/clips/{track_id}", headers=_auth())
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["total"] == 3


@pytest.mark.asyncio
async def test_forensic_clips_unknown_track_returns_empty_list(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/forensic/clips/{uuid.uuid4()}", headers=_auth())
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["clips"] == []


@pytest.mark.asyncio
async def test_forensic_clips_invalid_uuid_returns_422(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/forensic/clips/not-a-uuid", headers=_auth())
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_forensic_clips_requires_auth(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/forensic/clips/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_forensic_clips_guard_role_forbidden(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                f"/api/forensic/clips/{uuid.uuid4()}",
                headers=_auth("guard"),
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 403
