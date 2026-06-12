"""Tests for GET/POST/PATCH/DELETE /api/maintenance and /api/maintenance/calendar."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.models import Camera, MaintenanceWindow, User


def _auth(role: str = "manager") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


def _seed_user(db: Session, role: str = "manager") -> int:
    """Seed a user and return its id (POST needs a real created_by FK target)."""
    u = User(username=f"mw_op_{id(db)}", password_hash="x", role=role, is_active=True)
    db.add(u)
    db.flush()
    return u.user_id


def _auth_for(user_id: int, role: str = "manager") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


def _mock_redis() -> AsyncMock:
    mock = AsyncMock()
    mock.publish = AsyncMock(return_value=1)
    return mock


@pytest.mark.asyncio
async def test_list_maintenance_windows(db_session: Session) -> None:
    from vms.api.deps import get_db

    u = User(username="m_op", password_hash="x", role="admin", is_active=True)
    db_session.add(u)
    db_session.flush()
    c = Camera(name="MC", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(c)
    db_session.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(
        MaintenanceWindow(
            name="mw1",
            scope_type="CAMERA",
            scope_id=c.camera_id,
            schedule_type="ONE_TIME",
            starts_at=now,
            ends_at=now + timedelta(hours=1),
            created_by=u.user_id,
        )
    )
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.get("/api/maintenance", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    names = [w["name"] for w in r.json()]
    assert "mw1" in names


@pytest.mark.asyncio
async def test_post_maintenance_one_time_succeeds(db_session: Session) -> None:
    uid = _seed_user(db_session)
    cam = Camera(name="PC1", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.maintenance.get_api_redis", return_value=_mock_redis()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
                r = await cli.post(
                    "/api/maintenance",
                    json={
                        "name": "ot-window",
                        "scope_type": "CAMERA",
                        "scope_id": cam.camera_id,
                        "schedule_type": "ONE_TIME",
                        "starts_at": now.isoformat(),
                        "ends_at": (now + timedelta(hours=2)).isoformat(),
                    },
                    headers=_auth_for(uid),
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "ot-window"
    assert body["is_active"] is True
    row = db_session.get(MaintenanceWindow, body["window_id"])
    assert row is not None
    assert row.created_by == uid


@pytest.mark.asyncio
async def test_post_maintenance_recurring_succeeds(db_session: Session) -> None:
    uid = _seed_user(db_session)
    cam = Camera(name="PC2", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.maintenance.get_api_redis", return_value=_mock_redis()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
                r = await cli.post(
                    "/api/maintenance",
                    json={
                        "name": "weekly-window",
                        "scope_type": "ZONE",
                        "scope_id": 1,
                        "schedule_type": "RECURRING",
                        "cron_expr": "0 14 * * 6",
                        "duration_minutes": 120,
                        "suppress_alert_types": ["INTRUSION", "LOITERING"],
                    },
                    headers=_auth_for(uid),
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 201
    body = r.json()
    assert body["schedule_type"] == "RECURRING"
    assert body["cron_expr"] == "0 14 * * 6"


@pytest.mark.asyncio
async def test_post_maintenance_one_time_missing_starts_at_returns_422(
    db_session: Session,
) -> None:
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.post(
                "/api/maintenance",
                json={
                    "name": "bad-ot",
                    "scope_type": "CAMERA",
                    "scope_id": 1,
                    "schedule_type": "ONE_TIME",
                    "ends_at": (now + timedelta(hours=1)).isoformat(),
                },
                headers=_auth_for(uid),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 422
