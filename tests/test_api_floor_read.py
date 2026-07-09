"""Tests for floor-plan read APIs: list, heatmap, live positions (Phase 4P Task 8c)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.models import Camera, FloorPlan, TrackingEvent, User, UserCameraPermission


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _auth(role: str = "manager", user_id: int = 1) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


def _seed_plan(db: Session, scale: float = 0.05) -> int:
    plan = FloorPlan(name=f"FP_{uuid.uuid4().hex[:6]}", image_path="p.png", scale_m_per_px=scale)
    db.add(plan)
    db.flush()
    return plan.id


def _seed_camera(db: Session, floor_plan_id: int | None = None) -> int:
    cam = Camera(
        name=f"FR_{uuid.uuid4().hex[:6]}",
        rtsp_url="rtsp://x",
        capability_tier="FULL",
        floor_plan_id=floor_plan_id,
    )
    db.add(cam)
    db.flush()
    return cam.camera_id


def _seed_event(
    db: Session,
    camera_id: int,
    ts: datetime,
    floor: tuple[float, float] | None,
    gid: uuid.UUID | None = None,
    person_id: int | None = None,
) -> uuid.UUID:
    gid = gid or uuid.uuid4()
    db.add(
        TrackingEvent(
            camera_id=camera_id,
            local_track_id=f"t{uuid.uuid4().hex[:6]}",
            global_track_id=gid,
            person_id=person_id,
            event_ts=ts,
            ingest_ts=ts,
            bbox_x1=10,
            bbox_y1=10,
            bbox_x2=50,
            bbox_y2=90,
            floor_x=floor[0] if floor else None,
            floor_y=floor[1] if floor else None,
            seq_id=1,
        )
    )
    db.flush()
    return gid


async def _get(path: str, db: Session, role: str = "manager", user_id: int = 1) -> tuple[int, Any]:
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(path, headers=_auth(role, user_id))
    finally:
        app.dependency_overrides.clear()
    return resp.status_code, (resp.json() if resp.content else {})


def _unique_window(hours_ago: int = 5, span_h: int = 1) -> tuple[str, str]:
    """Past window with per-run-unique sub-hour offset (Redis cache-key isolation)."""
    now = _utcnow()
    frm = now.replace(minute=0, second=now.second, microsecond=now.microsecond) - timedelta(
        hours=hours_ago
    )
    return frm.isoformat(), (frm + timedelta(hours=span_h)).isoformat()


# -- floor plans list -----------------------------------------------------------


async def test_floor_plans_list_with_camera_counts(db_session: Session) -> None:
    plan = _seed_plan(db_session)
    _seed_camera(db_session, floor_plan_id=plan)
    _seed_camera(db_session, floor_plan_id=plan)
    _seed_camera(db_session)  # not on the plan

    status, body = await _get("/api/floor-plans", db_session, role="guard")

    assert status == 200
    mine = next(p for p in body if p["id"] == plan)
    assert mine["camera_count"] == 2
    assert mine["scale_m_per_px"] == 0.05


async def test_floor_plans_unauthenticated_returns_401(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/floor-plans")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 401


# -- heatmap ---------------------------------------------------------------------


async def test_heatmap_bins_floor_coords_exactly(db_session: Session) -> None:
    plan = _seed_plan(db_session, scale=0.05)  # bucket_m=1.0 -> bin = 20 px
    cam = _seed_camera(db_session, floor_plan_id=plan)
    off_plan_cam = _seed_camera(db_session)
    frm, to = _unique_window()
    t0 = datetime.fromisoformat(frm) + timedelta(minutes=5)

    _seed_event(db_session, cam, t0, (10.0, 10.0))  # cell (0, 0)
    _seed_event(db_session, cam, t0 + timedelta(seconds=1), (25.0, 10.0))  # cell (1, 0)
    _seed_event(db_session, cam, t0 + timedelta(seconds=2), (26.0, 11.0))  # cell (1, 0)
    _seed_event(db_session, cam, t0 + timedelta(seconds=3), None)  # no floor -> excluded
    _seed_event(db_session, off_plan_cam, t0, (10.0, 10.0))  # camera off-plan -> excluded

    status, body = await _get(
        f"/api/analytics/heatmap?floor_plan_id={plan}&from={frm}&to={to}&bucket_m=1.0",
        db_session,
    )

    assert status == 200
    assert body["bucket_m"] == 1.0
    assert body["bin_px"] == 20.0
    cells = {(c["x"], c["y"]): c["count"] for c in body["cells"]}
    assert cells == {(0, 0): 1, (1, 0): 2}


async def test_heatmap_window_and_bucket_validation(db_session: Session) -> None:
    plan = _seed_plan(db_session)
    now = _utcnow()
    frm = (now - timedelta(hours=80)).isoformat()
    to = now.isoformat()

    status, _ = await _get(
        f"/api/analytics/heatmap?floor_plan_id={plan}&from={frm}&to={to}", db_session
    )
    assert status == 422  # window > VMS_HEATMAP_MAX_WINDOW_H

    frm2, to2 = _unique_window()
    status, _ = await _get(
        f"/api/analytics/heatmap?floor_plan_id={plan}&from={frm2}&to={to2}&bucket_m=0",
        db_session,
    )
    assert status == 422


async def test_heatmap_unknown_plan_returns_404(db_session: Session) -> None:
    frm, to = _unique_window()
    status, _ = await _get(
        f"/api/analytics/heatmap?floor_plan_id=999999&from={frm}&to={to}", db_session
    )
    assert status == 404


async def test_heatmap_below_manager_returns_403(db_session: Session) -> None:
    plan = _seed_plan(db_session)
    frm, to = _unique_window()
    status, _ = await _get(
        f"/api/analytics/heatmap?floor_plan_id={plan}&from={frm}&to={to}",
        db_session,
        role="guard",
    )
    assert status == 403


async def test_heatmap_camera_permission_filters_events(db_session: Session) -> None:
    plan = _seed_plan(db_session)
    cam_a = _seed_camera(db_session, floor_plan_id=plan)
    cam_b = _seed_camera(db_session, floor_plan_id=plan)
    frm, to = _unique_window()
    t0 = datetime.fromisoformat(frm) + timedelta(minutes=5)
    _seed_event(db_session, cam_a, t0, (10.0, 10.0))
    _seed_event(db_session, cam_b, t0, (10.0, 10.0))

    scoped = User(username=f"fr_{uuid.uuid4().hex[:8]}", password_hash="x", role="manager")
    db_session.add(scoped)
    db_session.flush()
    db_session.add(UserCameraPermission(user_id=scoped.user_id, camera_id=cam_a))
    db_session.flush()

    status, body = await _get(
        f"/api/analytics/heatmap?floor_plan_id={plan}&from={frm}&to={to}",
        db_session,
        user_id=scoped.user_id,
    )

    assert status == 200
    assert sum(c["count"] for c in body["cells"]) == 1


# -- live floor positions ---------------------------------------------------------


async def test_live_floor_positions_latest_per_track(db_session: Session) -> None:
    plan = _seed_plan(db_session)
    cam = _seed_camera(db_session, floor_plan_id=plan)
    now = _utcnow()
    gid = uuid.uuid4()

    _seed_event(db_session, cam, now - timedelta(seconds=3), (10.0, 10.0), gid=gid)
    _seed_event(db_session, cam, now - timedelta(seconds=1), (12.0, 14.0), gid=gid)  # latest wins
    _seed_event(db_session, cam, now - timedelta(seconds=60), (99.0, 99.0))  # too old
    _seed_event(db_session, cam, now - timedelta(seconds=1), None)  # no floor -> excluded

    status, body = await _get(
        f"/api/live/floor-positions?floor_plan_id={plan}", db_session, role="guard"
    )

    assert status == 200
    assert len(body["positions"]) == 1
    pos = body["positions"][0]
    assert pos["global_track_id"] == str(gid)
    assert pos["floor_x"] == 12.0
    assert pos["floor_y"] == 14.0
    assert pos["camera_id"] == cam


async def test_live_floor_positions_unknown_plan_returns_404(db_session: Session) -> None:
    status, _ = await _get(
        "/api/live/floor-positions?floor_plan_id=999999", db_session, role="guard"
    )
    assert status == 404
