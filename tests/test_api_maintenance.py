"""Tests for GET /api/maintenance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.main import app
from vms.db.models import Camera, MaintenanceWindow, User


def _auth(role: str = "manager") -> dict[str, str]:
    from vms.api.deps import create_access_token

    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


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
