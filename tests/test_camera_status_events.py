"""Tests for camera_status_events + record_camera_status_transition (Phase 4P Task 2)."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.camera_status import record_camera_status_transition
from vms.db.models import Camera, CameraStatusEvent
from vms.ingestion.worker import CameraConfig, IngestionWorker


def _auth(role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _seed_camera(db: Session) -> int:
    cam = Camera(name=f"CS_{uuid.uuid4().hex[:6]}", rtsp_url="rtsp://x", capability_tier="FULL")
    db.add(cam)
    db.flush()
    return cam.camera_id


def _rows(db: Session, camera_id: int) -> list[CameraStatusEvent]:
    return list(
        db.execute(
            select(CameraStatusEvent)
            .where(CameraStatusEvent.camera_id == camera_id)
            .order_by(CameraStatusEvent.at, CameraStatusEvent.id)
        )
        .scalars()
        .all()
    )


# -- helper semantics ---------------------------------------------------------


def test_transition_helper_first_call_writes_baseline_row(db_session: Session) -> None:
    cam = _seed_camera(db_session)

    wrote = record_camera_status_transition(db_session, camera_id=cam, status="online")
    db_session.flush()

    assert wrote is True
    rows = _rows(db_session, cam)
    assert len(rows) == 1
    assert rows[0].status == "online"
    assert rows[0].at is not None


def test_transition_helper_same_status_writes_no_row(db_session: Session) -> None:
    cam = _seed_camera(db_session)
    record_camera_status_transition(db_session, camera_id=cam, status="online")
    db_session.flush()

    wrote = record_camera_status_transition(db_session, camera_id=cam, status="online")
    db_session.flush()

    assert wrote is False
    assert len(_rows(db_session, cam)) == 1


def test_transition_helper_flap_writes_exactly_two_rows(db_session: Session) -> None:
    """After the online baseline, an offline->online flap adds exactly 2 rows."""
    cam = _seed_camera(db_session)
    record_camera_status_transition(db_session, camera_id=cam, status="online")
    db_session.flush()

    record_camera_status_transition(db_session, camera_id=cam, status="offline")
    record_camera_status_transition(db_session, camera_id=cam, status="online")
    db_session.flush()

    rows = _rows(db_session, cam)
    assert [r.status for r in rows] == ["online", "offline", "online"]


def test_status_check_constraint_rejects_unknown_status(db_session: Session) -> None:
    cam = _seed_camera(db_session)
    with pytest.raises(IntegrityError):
        record_camera_status_transition(db_session, camera_id=cam, status="flaky")
        db_session.flush()


# -- ingestion worker hook ----------------------------------------------------


async def test_worker_mark_inactive_records_offline_transition(db_session: Session) -> None:
    cam_id = _seed_camera(db_session)
    worker = IngestionWorker(
        CameraConfig(camera_id=cam_id, rtsp_url="rtsp://x", worker_group=0),
        redis_client=None,  # type: ignore[arg-type]  # unused by _mark_camera_inactive
        session_factory=lambda: db_session,
    )

    await worker._mark_camera_inactive()

    cam = db_session.get(Camera, cam_id)
    assert cam is not None and cam.is_active is False
    rows = _rows(db_session, cam_id)
    assert [r.status for r in rows] == ["offline"]


# -- cameras PATCH hook -------------------------------------------------------


async def test_patch_is_active_toggle_records_transitions(db_session: Session) -> None:
    cam_id = _seed_camera(db_session)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r1 = await c.patch(f"/api/cameras/{cam_id}", json={"is_active": False}, headers=_auth())
            r2 = await c.patch(f"/api/cameras/{cam_id}", json={"is_active": True}, headers=_auth())
            # no-op PATCH: already active, and a name-only PATCH touches no status
            r3 = await c.patch(f"/api/cameras/{cam_id}", json={"is_active": True}, headers=_auth())
            r4 = await c.patch(f"/api/cameras/{cam_id}", json={"name": "Renamed"}, headers=_auth())
    finally:
        app.dependency_overrides.clear()

    assert r1.status_code == r2.status_code == r3.status_code == r4.status_code == 200
    rows = _rows(db_session, cam_id)
    assert [r.status for r in rows] == ["offline", "online"]
