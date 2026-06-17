"""Tests for GET /api/alerts."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.main import app
from vms.db.models import Alert, Camera


def _auth(role: str = "manager") -> dict[str, str]:
    from vms.api.deps import create_access_token

    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


def _utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_alerts_list_returns_filtered_results(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(name="AC1", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    db_session.add(
        Alert(
            alert_type="VIOLENCE",
            severity="CRITICAL",
            state="active",
            camera_id=cam.camera_id,
            triggered_at=_utc_naive(),
            dedup_key="d1",
        )
    )
    db_session.add(
        Alert(
            alert_type="UNKNOWN_PERSON",
            severity="HIGH",
            state="resolved",
            camera_id=cam.camera_id,
            triggered_at=_utc_naive(),
            dedup_key="d2",
        )
    )
    db_session.flush()
    # Override get_db so the route sees the same session (same transaction)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/alerts?state=active", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    body = r.json()
    types = [a["alert_type"] for a in body]
    assert "VIOLENCE" in types
    assert "UNKNOWN_PERSON" not in types


@pytest.mark.asyncio
async def test_alerts_list_filter_by_alert_type(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/alerts?alert_type=VIOLENCE", headers=_auth())
    assert r.status_code == 200
