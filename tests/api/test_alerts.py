"""Tests for GET /api/alerts and GET /api/state/snapshot Guard view filtering."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.api.schemas import AlertResponse
from vms.db.models import Alert, Camera


def _auth(role: str = "guard") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_camera(db: Session, name: str = "cam_alert") -> Camera:
    cam = Camera(name=name, rtsp_url=f"rtsp://{name}", capability_tier="FULL")
    db.add(cam)
    db.flush()
    return cam


def _seed_alert(
    db: Session,
    camera_id: int | None,
    alert_type: str,
    state: str = "active",
) -> Alert:
    a = Alert(
        alert_type=alert_type,
        severity="HIGH",
        state=state,
        camera_id=camera_id,
        triggered_at=_utcnow(),
        dedup_key=f"{alert_type}:{camera_id}:{id(db)}",
    )
    db.add(a)
    db.flush()
    return a


@pytest.mark.asyncio
async def test_guard_view_excludes_system_critical_alerts(db_session: Session) -> None:
    cam = _seed_camera(db_session, "cam_guard_test")
    security_alert = _seed_alert(db_session, cam.camera_id, "UNKNOWN_PERSON")
    sys_alert = _seed_alert(db_session, None, "SYSTEM_CRITICAL")

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/alerts", headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        returned_ids = {a["alert_id"] for a in data}
        assert security_alert.alert_id in returned_ids
        assert sys_alert.alert_id not in returned_ids
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_guard_view_excludes_system_critical_from_snapshot(
    db_session: Session,
) -> None:
    cam = _seed_camera(db_session, "cam_snap_test")
    security_alert = _seed_alert(db_session, cam.camera_id, "INTRUSION")
    sys_alert = _seed_alert(db_session, None, "SYSTEM_CRITICAL")

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/state/snapshot", headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        alert_ids = {a["alert_id"] for a in data["active_alerts"]}
        assert security_alert.alert_id in alert_ids
        assert sys_alert.alert_id not in alert_ids
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_alert_schema_accepts_null_camera_id(db_session: Session) -> None:
    sys_alert = _seed_alert(db_session, None, "SYSTEM_CRITICAL")
    db_session.refresh(sys_alert)

    parsed = AlertResponse.model_validate(sys_alert)
    assert parsed.camera_id is None
    assert parsed.alert_type == "SYSTEM_CRITICAL"


@pytest.mark.asyncio
async def test_list_alerts_returns_non_system_critical_alert_types(
    db_session: Session,
) -> None:
    cam = _seed_camera(db_session, "cam_list_test")
    _seed_alert(db_session, cam.camera_id, "INTRUSION")
    _seed_alert(db_session, cam.camera_id, "LOITERING")
    _seed_alert(db_session, None, "SYSTEM_CRITICAL")

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/alerts", headers=_auth())
        assert resp.status_code == 200
        types = {a["alert_type"] for a in resp.json()}
        assert "SYSTEM_CRITICAL" not in types
        assert "INTRUSION" in types
        assert "LOITERING" in types
    finally:
        app.dependency_overrides.pop(get_db, None)
