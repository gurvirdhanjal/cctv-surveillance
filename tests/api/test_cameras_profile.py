"""Tests for POST /api/cameras/{id}/profile -- real profiler invocation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.main import app
from vms.api.schemas import ProfileData
from vms.db.models import Camera


def _auth(role: str = "admin") -> dict[str, str]:
    from vms.api.deps import create_access_token

    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


def _fake_profile_data() -> ProfileData:
    return ProfileData(
        resolution_w=1920,
        resolution_h=1080,
        fps_measured=25.0,
        focus_score=50.0,
        frame_drop_rate=0.0,
        is_analog_via_encoder=False,
        suggested_tier="FULL",
        tier_reason=">=1080p AND fps>=12 AND focus>=30",
        shutter_suggestion="rolling",
        shutter_confidence=0.75,
        codec="H264",
    )


@pytest.mark.asyncio
async def test_post_profile_triggers_profiler_and_stores_results(
    db_session: Session,
) -> None:
    """POST /api/cameras/{id}/profile runs the profiler and stores results."""
    from vms.api.deps import get_db

    cam = Camera(name="ProfileTest", rtsp_url="rtsp://test/cam")
    db_session.add(cam)
    db_session.flush()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.cameras.CameraProfiler") as mock_cls:
            inst = MagicMock()
            inst.probe.return_value = _fake_profile_data()
            mock_cls.return_value = inst

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.post(
                    f"/api/cameras/{cam.camera_id}/profile",
                    headers=_auth(),
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["capability_tier"] == "FULL"
    assert body["shutter_type"] == "rolling"
    assert body["tier_reason"] is not None
    mock_cls.assert_called_once()


@pytest.mark.asyncio
async def test_post_profile_404_on_unknown_camera(db_session: Session) -> None:
    from vms.api.deps import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post("/api/cameras/99999/profile", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_profile_rtsp_failure_returns_422(db_session: Session) -> None:
    """If the profiler raises RuntimeError (bad RTSP), the API returns 422."""
    from vms.api.deps import get_db

    cam = Camera(name="BadRTSP", rtsp_url="rtsp://unreachable/cam")
    db_session.add(cam)
    db_session.flush()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.cameras.CameraProfiler") as mock_cls:
            inst = MagicMock()
            inst.probe.side_effect = RuntimeError("Cannot open RTSP stream")
            mock_cls.return_value = inst

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.post(
                    f"/api/cameras/{cam.camera_id}/profile",
                    headers=_auth(),
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 422
    assert "RTSP probe failed" in resp.json()["detail"]
