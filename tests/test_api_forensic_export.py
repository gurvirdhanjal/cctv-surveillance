"""Tests for clip-export job endpoints (Phase 4P Task 6)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.models import AuditLog, Camera, ExportJob, User, UserCameraPermission


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_user(db: Session, role: str = "manager") -> User:
    user = User(username=f"exp_{uuid.uuid4().hex[:8]}", password_hash="x", role=role)
    db.add(user)
    db.flush()
    return user


def _seed_camera(db: Session) -> int:
    cam = Camera(name=f"EX_{uuid.uuid4().hex[:6]}", rtsp_url="rtsp://x", capability_tier="FULL")
    db.add(cam)
    db.flush()
    return cam.camera_id


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.user_id, user.role)}"}


def _body(camera_id: int, window_s: int = 60) -> dict[str, Any]:
    frm = _utcnow() - timedelta(minutes=10)
    return {
        "camera_id": camera_id,
        "from_ts": frm.isoformat(),
        "to_ts": (frm + timedelta(seconds=window_s)).isoformat(),
        "reason": "incident review",
    }


async def _post(db: Session, body: dict[str, Any], headers: dict[str, str]) -> tuple[int, Any]:
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/forensic/export", json=body, headers=headers)
    finally:
        app.dependency_overrides.clear()
    return resp.status_code, (resp.json() if resp.content else {})


async def _get(db: Session, job_id: str, headers: dict[str, str]) -> tuple[int, Any]:
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/forensic/export/{job_id}", headers=headers)
    finally:
        app.dependency_overrides.clear()
    return resp.status_code, (resp.json() if resp.content else {})


async def test_export_returns_202_queued_and_audits(db_session: Session) -> None:
    user = _seed_user(db_session)
    cam = _seed_camera(db_session)

    status, body = await _post(db_session, _body(cam), _auth(user))

    assert status == 202
    assert body["state"] == "QUEUED"
    job_id = uuid.UUID(body["job_id"])

    job = db_session.get(ExportJob, job_id)
    assert job is not None
    assert job.requested_by == user.user_id
    assert job.camera_id == cam
    assert job.state == "QUEUED"  # no worker in this phase — honestly queued

    audit = (
        db_session.execute(
            select(AuditLog).where(
                AuditLog.event_type == "CLIP_EXPORT_REQUESTED",
                AuditLog.target_id == str(job_id),
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


async def test_export_window_too_large_returns_422(db_session: Session) -> None:
    user = _seed_user(db_session)
    cam = _seed_camera(db_session)

    status, _ = await _post(db_session, _body(cam, window_s=301), _auth(user))
    assert status == 422


async def test_export_from_after_to_returns_422(db_session: Session) -> None:
    user = _seed_user(db_session)
    cam = _seed_camera(db_session)
    body = _body(cam)
    body["from_ts"], body["to_ts"] = body["to_ts"], body["from_ts"]

    status, _ = await _post(db_session, body, _auth(user))
    assert status == 422


async def test_export_wrong_camera_scope_returns_403(db_session: Session) -> None:
    user = _seed_user(db_session)
    cam_allowed = _seed_camera(db_session)
    cam_denied = _seed_camera(db_session)
    db_session.add(UserCameraPermission(user_id=user.user_id, camera_id=cam_allowed))
    db_session.flush()

    status, _ = await _post(db_session, _body(cam_denied), _auth(user))
    assert status == 403


async def test_export_unknown_camera_returns_404(db_session: Session) -> None:
    user = _seed_user(db_session)
    status, _ = await _post(db_session, _body(999999), _auth(user))
    assert status == 404


async def test_export_unauthenticated_returns_401(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/forensic/export", json=_body(1))
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 401


async def test_export_status_owner_and_admin_only(db_session: Session) -> None:
    owner = _seed_user(db_session)
    other = _seed_user(db_session)
    admin = _seed_user(db_session, role="admin")
    cam = _seed_camera(db_session)

    status, body = await _post(db_session, _body(cam), _auth(owner))
    assert status == 202
    job_id = body["job_id"]

    status, body = await _get(db_session, job_id, _auth(owner))
    assert status == 200
    assert body["state"] == "QUEUED"
    assert body["camera_id"] == cam

    status, _ = await _get(db_session, job_id, _auth(admin))
    assert status == 200

    status, _ = await _get(db_session, job_id, _auth(other))
    assert status == 403


async def test_export_status_unknown_job_returns_404(db_session: Session) -> None:
    user = _seed_user(db_session)
    status, _ = await _get(db_session, str(uuid.uuid4()), _auth(user))
    assert status == 404
