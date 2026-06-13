"""Tests for GET /api/audit/verify and GET /api/audit/export."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.api.schemas import AuditVerifyResponse
from vms.db.audit import compute_row_hash, write_audit_event
from vms.db.models import AuditLog


def _auth(role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_events(db: Session, n: int) -> tuple[datetime, datetime]:
    """Write n events via write_audit_event; return (first_ts, last_ts)."""
    first_ts = last_ts = _utcnow()
    for i in range(n):
        row = write_audit_event(
            db,
            event_type=f"TEST_EVENT_{i}",
            target_type="test",
            target_id=str(i),
        )
        if i == 0:
            first_ts = row.event_ts
        last_ts = row.event_ts
    return first_ts, last_ts


# ── schemas_importable ────────────────────────────────────────────────────────


def test_schemas_importable() -> None:
    resp = AuditVerifyResponse(rows_checked=0, broken_chain_at=None)
    assert resp.rows_checked == 0
    assert resp.broken_chain_at is None


# ── audit/verify ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_verify_clean_chain(db_session: Session) -> None:
    first_ts, last_ts = _seed_events(db_session, 5)
    from_s = (first_ts - timedelta(seconds=1)).isoformat()
    to_s = (last_ts + timedelta(seconds=1)).isoformat()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/audit/verify?from={from_s}&to={to_s}", headers=_auth())
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["rows_checked"] == 5
    assert data["broken_chain_at"] is None


@pytest.mark.asyncio
async def test_audit_verify_detects_tampered_row_hash(db_session: Session) -> None:
    first_ts, last_ts = _seed_events(db_session, 3)

    rows = db_session.query(AuditLog).order_by(AuditLog.audit_id.asc()).all()
    rows[2].row_hash = "a" * 64
    db_session.flush()

    from_s = (first_ts - timedelta(seconds=1)).isoformat()
    to_s = (last_ts + timedelta(seconds=1)).isoformat()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/audit/verify?from={from_s}&to={to_s}", headers=_auth())
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["broken_chain_at"] is not None
    assert data["rows_checked"] == 2  # rows 0 and 1 passed before the bad row


@pytest.mark.asyncio
async def test_audit_verify_detects_broken_chain_link(db_session: Session) -> None:
    """Corrupt prev_hash + recompute row_hash — hash integrity passes but linkage fails."""
    first_ts, last_ts = _seed_events(db_session, 4)

    rows = db_session.query(AuditLog).order_by(AuditLog.audit_id.asc()).all()
    fake_prev = "b" * 64
    rows[2].prev_hash = fake_prev
    rows[2].row_hash = compute_row_hash(
        audit_id=rows[2].audit_id,
        event_type=rows[2].event_type,
        actor_user_id=rows[2].actor_user_id,
        target_type=rows[2].target_type,
        target_id=rows[2].target_id,
        payload=rows[2].payload,
        prev_hash=fake_prev,
        event_ts=rows[2].event_ts,
    )
    db_session.flush()

    from_s = (first_ts - timedelta(seconds=1)).isoformat()
    to_s = (last_ts + timedelta(seconds=1)).isoformat()

    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/audit/verify?from={from_s}&to={to_s}", headers=_auth())
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["broken_chain_at"] is not None
    assert data["rows_checked"] == 2


@pytest.mark.asyncio
async def test_audit_verify_empty_range(db_session: Session) -> None:
    future = _utcnow() + timedelta(days=1)
    from_s = future.isoformat()
    to_s = (future + timedelta(days=1)).isoformat()

    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/audit/verify?from={from_s}&to={to_s}", headers=_auth())
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"rows_checked": 0, "broken_chain_at": None}


@pytest.mark.asyncio
async def test_audit_verify_invalid_range_returns_422(db_session: Session) -> None:
    now = _utcnow()
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            f"/api/audit/verify?from={(now + timedelta(days=1)).isoformat()}&to={now.isoformat()}",
            headers=_auth(),
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_audit_verify_requires_auth(db_session: Session) -> None:
    now = _utcnow()
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            f"/api/audit/verify?from={now.isoformat()}&to={(now + timedelta(days=1)).isoformat()}"
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_audit_verify_guard_role_forbidden(db_session: Session) -> None:
    now = _utcnow()
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            f"/api/audit/verify?from={now.isoformat()}&to={(now + timedelta(days=1)).isoformat()}",
            headers=_auth("guard"),
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403
