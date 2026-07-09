"""Tests for floor_plans + homography calibration API (Phase 4P Task 8b, spec §8.2.1)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.models import AuditLog, Camera, FloorPlan, User, UserCameraPermission


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _auth(role: str = "admin", user_id: int = 1) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


def _seed_camera(db: Session, recalibrate_required: bool = False) -> Camera:
    cam = Camera(name=f"HG_{uuid.uuid4().hex[:6]}", rtsp_url="rtsp://x", capability_tier="FULL")
    if recalibrate_required:
        cam.recalibrate_required_at = _utcnow()
    db.add(cam)
    db.flush()
    return cam


# Ground truth: floor = (2*x + 10, 3*y + 20) — a valid (affine) homography
def _floor(pt: tuple[float, float]) -> list[float]:
    return [2.0 * pt[0] + 10.0, 3.0 * pt[1] + 20.0]


_IMAGE_POINTS: list[tuple[float, float]] = [(0, 0), (100, 0), (0, 100), (100, 100), (50, 80)]


def _good_pairs() -> list[dict[str, list[float]]]:
    return [{"image": [x, y], "floor": _floor((x, y))} for x, y in _IMAGE_POINTS]


async def _put(
    db: Session, camera_id: int, body: dict[str, Any], headers: dict[str, str]
) -> tuple[int, Any]:
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.put(f"/api/cameras/{camera_id}/homography", json=body, headers=headers)
    finally:
        app.dependency_overrides.clear()
    return resp.status_code, (resp.json() if resp.content else {})


async def _get(db: Session, camera_id: int, headers: dict[str, str]) -> tuple[int, Any]:
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/cameras/{camera_id}/homography", headers=headers)
    finally:
        app.dependency_overrides.clear()
    return resp.status_code, (resp.json() if resp.content else {})


# -- schema -------------------------------------------------------------------


def test_floor_plan_scale_check_rejects_nonpositive(db_session: Session) -> None:
    db_session.add(
        FloorPlan(name=f"P_{uuid.uuid4().hex[:6]}", image_path="p.png", scale_m_per_px=0.05)
    )
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.add(
            FloorPlan(name=f"P_{uuid.uuid4().hex[:6]}", image_path="p.png", scale_m_per_px=0.0)
        )
        db_session.flush()


# -- calibrate (PUT) ----------------------------------------------------------


async def test_calibrate_stores_server_computed_matrix(db_session: Session) -> None:
    from vms.identity.homography import project_to_floor

    cam = _seed_camera(db_session, recalibrate_required=True)

    status, body = await _put(db_session, cam.camera_id, {"point_pairs": _good_pairs()}, _auth())

    assert status == 200
    assert body["rms_error_px"] < 1.0
    assert body["stale"] is False

    db_session.refresh(cam)
    assert cam.homography_matrix is not None
    matrix = json.loads(cam.homography_matrix)
    assert len(matrix) == 9
    assert cam.recalibrate_required_at is None

    # held-out check: bbox foot point (50, 80) must land on the ground-truth floor point
    projected = project_to_floor((40, 0, 60, 80), cam.homography_matrix)
    assert projected is not None
    assert abs(projected[0] - 110.0) < 1.0
    assert abs(projected[1] - 260.0) < 1.0

    audit = (
        db_session.execute(
            select(AuditLog).where(
                AuditLog.event_type == "CAMERA_CALIBRATED",
                AuditLog.target_id == str(cam.camera_id),
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


async def test_calibrate_with_floor_plan_links_camera(db_session: Session) -> None:
    cam = _seed_camera(db_session)
    plan = FloorPlan(name=f"P_{uuid.uuid4().hex[:6]}", image_path="p.png", scale_m_per_px=0.05)
    db_session.add(plan)
    db_session.flush()

    status, _ = await _put(
        db_session,
        cam.camera_id,
        {"point_pairs": _good_pairs(), "floor_plan_id": plan.id},
        _auth(),
    )

    assert status == 200
    db_session.refresh(cam)
    assert cam.floor_plan_id == plan.id


async def test_calibrate_fewer_than_four_pairs_returns_422(db_session: Session) -> None:
    cam = _seed_camera(db_session)
    status, _ = await _put(db_session, cam.camera_id, {"point_pairs": _good_pairs()[:3]}, _auth())
    assert status == 422


async def test_calibrate_collinear_points_returns_422(db_session: Session) -> None:
    cam = _seed_camera(db_session)
    pairs = [{"image": [float(i), float(i)], "floor": [float(i), float(i)]} for i in range(5)]
    status, _ = await _put(db_session, cam.camera_id, {"point_pairs": pairs}, _auth())
    assert status == 422


async def test_calibrate_high_rms_returns_422(db_session: Session) -> None:
    cam = _seed_camera(db_session)
    pairs = _good_pairs()
    pairs[4]["floor"] = [9999.0, -9999.0]  # wildly inconsistent 5th pair -> huge reprojection RMS
    status, _ = await _put(db_session, cam.camera_id, {"point_pairs": pairs}, _auth())
    assert status == 422


async def test_calibrate_below_admin_returns_403(db_session: Session) -> None:
    cam = _seed_camera(db_session)
    status, _ = await _put(
        db_session, cam.camera_id, {"point_pairs": _good_pairs()}, _auth(role="manager")
    )
    assert status == 403


async def test_calibrate_unknown_camera_returns_404(db_session: Session) -> None:
    status, _ = await _put(db_session, 999999, {"point_pairs": _good_pairs()}, _auth())
    assert status == 404


# -- read (GET) ---------------------------------------------------------------


async def test_get_homography_never_calibrated_returns_404(db_session: Session) -> None:
    cam = _seed_camera(db_session)
    status, _ = await _get(db_session, cam.camera_id, _auth(role="guard"))
    assert status == 404


async def test_get_homography_returns_matrix_metadata_and_staleness(db_session: Session) -> None:
    cam = _seed_camera(db_session)
    status, _ = await _put(db_session, cam.camera_id, {"point_pairs": _good_pairs()}, _auth())
    assert status == 200

    status, body = await _get(db_session, cam.camera_id, _auth(role="guard"))
    assert status == 200
    assert len(body["matrix"]) == 9
    assert len(body["point_pairs"]) == 5
    assert body["rms_error_px"] < 1.0
    assert body["stale"] is False

    cam.recalibrate_required_at = _utcnow()
    db_session.flush()
    status, body = await _get(db_session, cam.camera_id, _auth(role="guard"))
    assert status == 200
    assert body["stale"] is True


async def test_get_homography_camera_permission_scoped_returns_403(db_session: Session) -> None:
    cam = _seed_camera(db_session)
    other_cam = _seed_camera(db_session)
    await _put(db_session, cam.camera_id, {"point_pairs": _good_pairs()}, _auth())

    scoped = User(username=f"hg_{uuid.uuid4().hex[:8]}", password_hash="x", role="guard")
    db_session.add(scoped)
    db_session.flush()
    db_session.add(UserCameraPermission(user_id=scoped.user_id, camera_id=other_cam.camera_id))
    db_session.flush()

    status, _ = await _get(db_session, cam.camera_id, _auth(role="guard", user_id=scoped.user_id))
    assert status == 403


# -- end-to-end through the writer path ----------------------------------------


@pytest.mark.integration
async def test_calibrated_camera_populates_floor_coords_via_writer(db_session: Session) -> None:
    from vms.db.models import TrackingEvent
    from vms.inference.messages import DetectionFrame, Tracklet
    from vms.writer.db_writer import flush_detection_frame

    cam = _seed_camera(db_session)
    status, _ = await _put(db_session, cam.camera_id, {"point_pairs": _good_pairs()}, _auth())
    assert status == 200
    db_session.refresh(cam)

    frame = DetectionFrame(
        camera_id=cam.camera_id,
        seq_id=1,
        timestamp_ms=int(_utcnow().timestamp() * 1000),
        tracklets=(
            Tracklet(
                local_track_id=1,
                camera_id=cam.camera_id,
                bbox=(40, 0, 60, 80),
                confidence=0.9,
            ),
        ),
        face_embeddings=(),
    )
    flush_detection_frame(db_session, frame, homography_json=cam.homography_matrix)
    db_session.flush()

    row = db_session.execute(
        select(TrackingEvent).where(TrackingEvent.camera_id == cam.camera_id)
    ).scalar_one()
    assert row.floor_x is not None and row.floor_y is not None
    assert abs(row.floor_x - 110.0) < 1.0
    assert abs(row.floor_y - 260.0) < 1.0
