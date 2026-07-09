"""Tests for /api/users CRUD (Phase 4P Task 7)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db, verify_password
from vms.api.main import app
from vms.db.models import AuditLog, Camera, User, UserCameraPermission


def _seed_user(db: Session, role: str = "guard", active: bool = True) -> User:
    user = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        password_hash="x",
        role=role,
        is_active=active,
    )
    db.add(user)
    db.flush()
    return user


def _seed_camera(db: Session) -> int:
    cam = Camera(name=f"US_{uuid.uuid4().hex[:6]}", rtsp_url="rtsp://x", capability_tier="FULL")
    db.add(cam)
    db.flush()
    return cam.camera_id


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.user_id, user.role)}"}


async def _req(
    db: Session,
    method: str,
    path: str,
    headers: dict[str, str],
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.request(method, path, json=body, headers=headers)
    finally:
        app.dependency_overrides.clear()
    return resp.status_code, (resp.json() if resp.content else {})


def _audit_count(db: Session, event_type: str, target_id: str) -> int:
    rows = (
        db.execute(
            select(AuditLog).where(
                AuditLog.event_type == event_type, AuditLog.target_id == target_id
            )
        )
        .scalars()
        .all()
    )
    return len(rows)


# -- list ---------------------------------------------------------------------


async def test_list_users_admin_only_and_never_leaks_hashes(db_session: Session) -> None:
    admin = _seed_user(db_session, role="admin")
    _seed_user(db_session, role="guard")

    status, body = await _req(db_session, "GET", "/api/users", _auth(admin))

    assert status == 200
    assert any(u["username"] == admin.username for u in body)
    assert "password_hash" not in json.dumps(body)

    manager = _seed_user(db_session, role="manager")
    status, _ = await _req(db_session, "GET", "/api/users", _auth(manager))
    assert status == 403


# -- create -------------------------------------------------------------------


async def test_create_user_hashes_password_and_audits(db_session: Session) -> None:
    admin = _seed_user(db_session, role="admin")
    payload = {
        "username": f"new_{uuid.uuid4().hex[:8]}",
        "email": f"{uuid.uuid4().hex[:8]}@plant.local",
        "password": "s3cret-pass",
        "role": "manager",
    }

    status, body = await _req(db_session, "POST", "/api/users", _auth(admin), payload)

    assert status == 201
    assert "password" not in body and "password_hash" not in body
    created = db_session.get(User, body["user_id"])
    assert created is not None
    assert verify_password("s3cret-pass", created.password_hash)
    assert _audit_count(db_session, "USER_CREATED", str(body["user_id"])) == 1


async def test_create_user_duplicate_username_returns_409(db_session: Session) -> None:
    admin = _seed_user(db_session, role="admin")
    existing = _seed_user(db_session)
    payload = {"username": existing.username, "password": "s3cret-pass", "role": "guard"}

    status, _ = await _req(db_session, "POST", "/api/users", _auth(admin), payload)
    assert status == 409


async def test_create_user_duplicate_email_returns_409(db_session: Session) -> None:
    admin = _seed_user(db_session, role="admin")
    email = f"{uuid.uuid4().hex[:8]}@plant.local"
    p1 = {
        "username": f"a_{uuid.uuid4().hex[:6]}",
        "email": email,
        "password": "s3cret-pass",
        "role": "guard",
    }
    p2 = {
        "username": f"b_{uuid.uuid4().hex[:6]}",
        "email": email,
        "password": "s3cret-pass",
        "role": "guard",
    }

    status, _ = await _req(db_session, "POST", "/api/users", _auth(admin), p1)
    assert status == 201
    status, _ = await _req(db_session, "POST", "/api/users", _auth(admin), p2)
    assert status == 409


async def test_create_user_invalid_role_returns_422(db_session: Session) -> None:
    admin = _seed_user(db_session, role="admin")
    payload = {
        "username": f"x_{uuid.uuid4().hex[:6]}",
        "password": "s3cret-pass",
        "role": "superuser",
    }
    status, _ = await _req(db_session, "POST", "/api/users", _auth(admin), payload)
    assert status == 422


async def test_create_user_non_admin_returns_403(db_session: Session) -> None:
    manager = _seed_user(db_session, role="manager")
    payload = {"username": f"x_{uuid.uuid4().hex[:6]}", "password": "s3cret-pass", "role": "guard"}
    status, _ = await _req(db_session, "POST", "/api/users", _auth(manager), payload)
    assert status == 403


# -- update -------------------------------------------------------------------


async def test_patch_role_and_camera_permissions(db_session: Session) -> None:
    admin = _seed_user(db_session, role="admin")
    target = _seed_user(db_session, role="guard")
    cam_a = _seed_camera(db_session)
    cam_b = _seed_camera(db_session)
    db_session.add(UserCameraPermission(user_id=target.user_id, camera_id=cam_a))
    db_session.flush()

    status, body = await _req(
        db_session,
        "PATCH",
        f"/api/users/{target.user_id}",
        _auth(admin),
        {"role": "manager", "camera_ids": [cam_b]},
    )

    assert status == 200
    assert body["role"] == "manager"
    assert body["camera_ids"] == [cam_b]
    perm_rows = (
        db_session.execute(
            select(UserCameraPermission.camera_id).where(
                UserCameraPermission.user_id == target.user_id
            )
        )
        .scalars()
        .all()
    )
    assert list(perm_rows) == [cam_b]
    assert _audit_count(db_session, "USER_UPDATED", str(target.user_id)) == 1


async def test_patch_self_demotion_returns_409(db_session: Session) -> None:
    admin = _seed_user(db_session, role="admin")

    status, _ = await _req(
        db_session, "PATCH", f"/api/users/{admin.user_id}", _auth(admin), {"role": "manager"}
    )
    assert status == 409


async def test_demoting_last_active_admin_returns_409(db_session: Session) -> None:
    acting = _seed_user(db_session, role="admin")
    lone_admin = _seed_user(db_session, role="admin")
    # Neutralize committed admins from other suite runs (rolled back with this txn)
    db_session.execute(
        update(User)
        .where(User.role == "admin", User.user_id.notin_([lone_admin.user_id]))
        .values(is_active=False)
    )
    db_session.flush()

    status, _ = await _req(
        db_session,
        "PATCH",
        f"/api/users/{lone_admin.user_id}",
        _auth(acting),
        {"role": "guard"},
    )
    assert status == 409

    status, _ = await _req(
        db_session,
        "PATCH",
        f"/api/users/{lone_admin.user_id}",
        _auth(acting),
        {"is_active": False},
    )
    assert status == 409


# -- deactivate ---------------------------------------------------------------


async def test_delete_soft_deactivates_never_removes_row(db_session: Session) -> None:
    admin = _seed_user(db_session, role="admin")
    target = _seed_user(db_session, role="guard")

    status, _ = await _req(db_session, "DELETE", f"/api/users/{target.user_id}", _auth(admin))

    assert status == 204
    row = db_session.get(User, target.user_id)
    assert row is not None
    assert row.is_active is False
    assert _audit_count(db_session, "USER_DEACTIVATED", str(target.user_id)) == 1


# -- reset password -----------------------------------------------------------


async def test_reset_password_sets_new_hash_and_audits(db_session: Session) -> None:
    admin = _seed_user(db_session, role="admin")
    target = _seed_user(db_session, role="guard")

    status, body = await _req(
        db_session,
        "POST",
        f"/api/users/{target.user_id}/reset-password",
        _auth(admin),
        {"new_password": "brand-new-pass"},
    )

    assert status == 200
    assert "password_hash" not in json.dumps(body)
    db_session.refresh(target)
    assert verify_password("brand-new-pass", target.password_hash)
    assert _audit_count(db_session, "USER_PASSWORD_RESET", str(target.user_id)) == 1


async def test_users_unknown_id_returns_404(db_session: Session) -> None:
    admin = _seed_user(db_session, role="admin")
    status, _ = await _req(
        db_session, "PATCH", "/api/users/999999", _auth(admin), {"role": "guard"}
    )
    assert status == 404


async def test_users_unauthenticated_returns_401(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/users")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 401
