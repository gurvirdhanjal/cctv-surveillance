"""Tests for /api/cameras CRUD and configuration endpoints."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.main import app
from vms.db.models import Camera


def _auth(role: str = "admin") -> dict[str, str]:
    from vms.api.deps import create_access_token

    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


# ---------------------------------------------------------------------------
# GET /api/cameras
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_cameras_returns_all(db_session: Session) -> None:
    from vms.api.deps import get_db

    db_session.add(Camera(name="Cam A", rtsp_url="rtsp://a", capability_tier="FULL"))
    db_session.add(Camera(name="Cam B", rtsp_url="rtsp://b", capability_tier="MID"))
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/cameras", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    names = [cam["name"] for cam in r.json()]
    assert "Cam A" in names
    assert "Cam B" in names


@pytest.mark.asyncio
async def test_list_cameras_requires_auth() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/cameras")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/cameras
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_camera_returns_201(db_session: Session) -> None:
    from vms.api.deps import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/cameras",
                json={"name": "Gate 1", "rtsp_url": "rtsp://gate1", "capability_tier": "FULL"},
                headers=_auth(),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Gate 1"
    assert body["shutter_type"] == "unknown"
    assert body["capability_tier"] == "FULL"


@pytest.mark.asyncio
async def test_create_camera_rejects_invalid_tier(db_session: Session) -> None:
    from vms.api.deps import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/cameras",
                json={"name": "X", "rtsp_url": "rtsp://x", "capability_tier": "ULTRA"},
                headers=_auth(),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/cameras/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_camera_returns_detail(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(
        name="Floor 3", rtsp_url="rtsp://f3", capability_tier="FULL", shutter_type="global"
    )
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/cameras/{cam.camera_id}", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert r.json()["shutter_type"] == "global"


@pytest.mark.asyncio
async def test_get_camera_404_for_missing(db_session: Session) -> None:
    from vms.api.deps import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/cameras/99999", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/cameras/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_camera_returns_204(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(name="Temp Cam", rtsp_url="rtsp://temp", capability_tier="LOW")
    db_session.add(cam)
    db_session.flush()
    cam_id = cam.camera_id
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.delete(f"/api/cameras/{cam_id}", headers=_auth("admin"))
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 204
    assert db_session.get(Camera, cam_id) is None


@pytest.mark.asyncio
async def test_delete_camera_404_for_missing(db_session: Session) -> None:
    from vms.api.deps import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.delete("/api/cameras/99999", headers=_auth("admin"))
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_camera_requires_admin() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete("/api/cameras/1", headers=_auth("guard"))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/cameras/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_camera_updates_name(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(name="Old Name", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/cameras/{cam.camera_id}",
                json={"name": "New Name"},
                headers=_auth(),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"


# ---------------------------------------------------------------------------
# PATCH /api/cameras/{id}/hardware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_hardware_requires_super_admin(db_session: Session) -> None:
    import fakeredis.aioredis

    from vms.api.deps import get_api_redis, get_db

    cam = Camera(name="H1", rtsp_url="rtsp://h1", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    fake_redis = fakeredis.aioredis.FakeRedis()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_api_redis] = lambda: fake_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/cameras/{cam.camera_id}/hardware",
                json={"shutter_type": "global"},
                headers=_auth("admin"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_api_redis, None)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_patch_hardware_super_admin_updates_shutter_type(db_session: Session) -> None:
    import fakeredis.aioredis

    from vms.api.deps import get_api_redis, get_db

    cam = Camera(name="H2", rtsp_url="rtsp://h2", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    fake_redis = fakeredis.aioredis.FakeRedis()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_api_redis] = lambda: fake_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/cameras/{cam.camera_id}/hardware",
                json={"shutter_type": "rolling"},
                headers=_auth("super_admin"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_api_redis, None)
    assert r.status_code == 200
    assert r.json()["shutter_type"] == "rolling"


@pytest.mark.asyncio
async def test_patch_hardware_rejects_invalid_shutter_type(db_session: Session) -> None:
    import fakeredis.aioredis

    from vms.api.deps import get_api_redis, get_db

    cam = Camera(name="H3", rtsp_url="rtsp://h3", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    fake_redis = fakeredis.aioredis.FakeRedis()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_api_redis] = lambda: fake_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/cameras/{cam.camera_id}/hardware",
                json={"shutter_type": "ccd"},
                headers=_auth("super_admin"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_api_redis, None)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/cameras/{id}/overrides
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_overrides_saves_model_overrides_json(db_session: Session) -> None:
    import fakeredis.aioredis

    from vms.api.deps import get_api_redis, get_db

    cam = Camera(name="O1", rtsp_url="rtsp://o1", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    fake_redis = fakeredis.aioredis.FakeRedis()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_api_redis] = lambda: fake_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/cameras/{cam.camera_id}/overrides",
                json={"thresholds": {"adaface_min_sim": 0.85}, "models": {}},
                headers=_auth("admin"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_api_redis, None)
    assert r.status_code == 200
    saved = json.loads(r.json()["model_overrides"])
    assert saved["adaface_min_sim"] == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_patch_overrides_admin_allowed(db_session: Session) -> None:
    import fakeredis.aioredis

    from vms.api.deps import get_api_redis, get_db

    cam = Camera(name="O2", rtsp_url="rtsp://o2", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    fake_redis = fakeredis.aioredis.FakeRedis()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_api_redis] = lambda: fake_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/cameras/{cam.camera_id}/overrides",
                json={"thresholds": {}, "models": {}},
                headers=_auth("admin"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_api_redis, None)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/cameras/{id}/resolved-config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolved_config_rolling_returns_shutter_adjusted_values(
    db_session: Session,
) -> None:
    from vms.api.deps import get_db

    cam = Camera(name="RC1", rtsp_url="rtsp://rc1", capability_tier="FULL", shutter_type="rolling")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/cameras/{cam.camera_id}/resolved-config", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    settings = r.json()["settings"]
    assert settings["adaface_min_sim"]["source"] == "shutter:rolling"
    assert settings["burst_frames"]["value"] == 5


@pytest.mark.asyncio
async def test_resolved_config_global_returns_default_values(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(name="RC2", rtsp_url="rtsp://rc2", capability_tier="FULL", shutter_type="global")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/cameras/{cam.camera_id}/resolved-config", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    settings = r.json()["settings"]
    assert settings["adaface_min_sim"]["source"] == "global_default"
    assert settings["burst_frames"]["value"] == 3


@pytest.mark.asyncio
async def test_resolved_config_manual_override_wins_over_shutter(
    db_session: Session,
) -> None:
    from vms.api.deps import get_db

    overrides = json.dumps({"adaface_min_sim": 0.95})
    cam = Camera(
        name="RC3",
        rtsp_url="rtsp://rc3",
        capability_tier="FULL",
        shutter_type="rolling",
        model_overrides=overrides,
    )
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/cameras/{cam.camera_id}/resolved-config", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert r.json()["settings"]["adaface_min_sim"]["source"] == "manual_override"
    assert r.json()["settings"]["adaface_min_sim"]["value"] == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# POST /api/cameras/{id}/profile  and  GET /api/cameras/{id}/profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_profile_triggers_profiler(db_session: Session) -> None:
    from unittest.mock import MagicMock, patch

    from vms.api.deps import get_db
    from vms.api.schemas import ProfileData

    cam = Camera(name="P1", rtsp_url="rtsp://p1", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    fake_data = ProfileData(
        resolution_w=1920,
        resolution_h=1080,
        fps_measured=15.0,
        focus_score=42.0,
        suggested_tier="FULL",
        tier_reason=">=1080p",
        shutter_suggestion="rolling",
        shutter_confidence=0.87,
    )
    try:
        with patch("vms.api.routes.cameras.CameraProfiler") as mock_cls:
            inst = MagicMock()
            inst.probe.return_value = fake_data
            mock_cls.return_value = inst
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.post(
                    f"/api/cameras/{cam.camera_id}/profile",
                    headers=_auth(),
                )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert r.json()["capability_tier"] == "FULL"


@pytest.mark.asyncio
async def test_get_profile_returns_last_profile_data(db_session: Session) -> None:
    from vms.api.deps import get_db

    profile = {
        "resolution_w": 1280,
        "resolution_h": 720,
        "fps_measured": 10.0,
        "focus_score": 28.0,
        "shutter_suggestion": "rolling",
        "shutter_confidence": 0.75,
        "suggested_tier": "MID",
    }
    cam = Camera(
        name="P2",
        rtsp_url="rtsp://p2",
        capability_tier="FULL",
        profile_data=json.dumps(profile),
    )
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/cameras/{cam.camera_id}/profile", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    body = r.json()
    assert body["profile_data"]["fps_measured"] == pytest.approx(10.0)
    assert body["profile_data"]["shutter_suggestion"] == "rolling"


# ---------------------------------------------------------------------------
# POST /api/cameras/{id}/recalibrate-required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recalibrate_required_sets_timestamp(db_session: Session) -> None:
    """POST /cameras/{id}/recalibrate-required sets recalibrate_required_at and returns 200."""
    from vms.api.deps import get_db

    cam = Camera(name="RecalCam", rtsp_url="rtsp://recal", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(f"/api/cameras/{cam.camera_id}/recalibrate-required", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    body = r.json()
    assert body["recalibrate_required_at"] is not None


@pytest.mark.asyncio
async def test_recalibrate_required_404_for_unknown_camera(db_session: Session) -> None:
    """POST /cameras/9999/recalibrate-required returns 404."""
    from vms.api.deps import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/cameras/9999/recalibrate-required", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_recalibrate_required_requires_auth() -> None:
    """POST /cameras/{id}/recalibrate-required returns 401 when unauthenticated."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/cameras/1/recalibrate-required")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_profile_data_full_fields() -> None:
    """ProfileData must accept the full set of measured fields."""
    from vms.api.schemas import ProfileData

    pd = ProfileData(
        resolution_w=1920,
        resolution_h=1080,
        fps_measured=15.0,
        focus_score=42.0,
        frame_drop_rate=0.02,
        brightness_mean=128.0,
        is_analog_via_encoder=False,
        tier_reason=">=1080p AND fps>=12 AND focus>=30",
        codec="H264",
        shutter_suggestion="rolling",
        shutter_confidence=0.82,
        suggested_tier="FULL",
    )
    assert pd.resolution_w == 1920
    assert pd.tier_reason == ">=1080p AND fps>=12 AND focus>=30"
