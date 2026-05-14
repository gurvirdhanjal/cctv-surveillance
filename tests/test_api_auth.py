"""Tests for POST /api/auth/token."""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from vms.api.deps import hash_password
from vms.api.main import app
from vms.db.models import User
from vms.db.session import SessionLocal


def _create_user(username: str, password: str, role: str = "guard", is_active: bool = True) -> int:
    """Insert a user directly via a committed session; return user_id."""
    with SessionLocal() as session:
        user = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            is_active=is_active,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return int(user.user_id)


def _delete_user(username: str) -> None:
    """Remove a test user by username."""
    with SessionLocal() as session:
        user = session.query(User).filter_by(username=username).first()
        if user:
            session.delete(user)
            session.commit()


@pytest.mark.asyncio
async def test_login_returns_token() -> None:
    uname = f"testop_{uuid.uuid4().hex[:8]}"
    _create_user(uname, "correcthorse")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/auth/token",
                json={"username": uname, "password": "correcthorse"},
            )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
    finally:
        _delete_user(uname)


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401() -> None:
    uname = f"testop2_{uuid.uuid4().hex[:8]}"
    _create_user(uname, "correcthorse")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/auth/token",
                json={"username": uname, "password": "wrongpassword"},
            )
        assert response.status_code == 401
    finally:
        _delete_user(uname)


@pytest.mark.asyncio
async def test_login_inactive_user_returns_401() -> None:
    uname = f"inactiveop_{uuid.uuid4().hex[:8]}"
    _create_user(uname, "pw", is_active=False)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/auth/token",
                json={"username": uname, "password": "pw"},
            )
        assert response.status_code == 401
    finally:
        _delete_user(uname)


@pytest.mark.asyncio
async def test_login_unknown_user_returns_401() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/token",
            json={"username": "nobody_xyz_404", "password": "pw"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_writes_audit_log() -> None:
    from vms.db.models import AuditLog

    uname = f"audited_{uuid.uuid4().hex[:8]}"
    user_id = _create_user(uname, "pw123", role="manager")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/auth/token",
                json={"username": uname, "password": "pw123"},
            )
        assert response.status_code == 200

        with SessionLocal() as fresh:
            row = (
                fresh.query(AuditLog)
                .filter_by(event_type="LOGIN_SUCCESS", actor_user_id=user_id)
                .order_by(AuditLog.audit_id.desc())
                .first()
            )
        assert row is not None
        assert row.actor_user_id == user_id
    finally:
        _delete_user(uname)
