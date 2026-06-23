"""Tests for Zones CRUD API — GET/POST/PATCH/DELETE /api/zones."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.models import Zone


def _auth(role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


_POLYGON = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]


def _seed_zone(db: Session, name: str = "Loading Bay", active: bool = True) -> Zone:
    z = Zone(
        name=name,
        is_active=active,
        loiter_threshold_s=180,
        polygon_json="[[0,0],[1,0],[1,1]]",
    )
    db.add(z)
    db.flush()
    return z


# ---------------------------------------------------------------------------
# GET /api/zones
# ---------------------------------------------------------------------------


async def test_list_zones_requires_auth() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/zones")
    assert r.status_code == 401


async def test_list_zones_returns_active_only(db_session: Session) -> None:
    _seed_zone(db_session, name="ActiveZone", active=True)
    _seed_zone(db_session, name="ArchivedZone", active=False)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/zones", headers=_auth("guard"))
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    names = [z["name"] for z in r.json()]
    assert "ActiveZone" in names
    assert "ArchivedZone" not in names


# ---------------------------------------------------------------------------
# POST /api/zones
# ---------------------------------------------------------------------------


async def test_create_zone_admin_succeeds(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/api/zones",
                json={"name": "Welding Bay", "polygon": _POLYGON, "loiter_threshold_s": 120},
                headers=_auth("admin"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Welding Bay"
    assert body["is_active"] is True
    assert len(body["polygon"]) == 4


async def test_create_zone_rejects_guard(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/api/zones",
                json={"name": "BadZone", "polygon": _POLYGON},
                headers=_auth("guard"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 403


async def test_create_zone_rejects_two_point_polygon() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/zones",
            json={"name": "BadPolygon", "polygon": [[0.0, 0.0], [1.0, 1.0]]},
            headers=_auth("admin"),
        )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/zones/{id}
# ---------------------------------------------------------------------------


async def test_patch_zone_updates_capacity(db_session: Session) -> None:
    z = _seed_zone(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                f"/api/zones/{z.zone_id}",
                json={"max_capacity": 25},
                headers=_auth("admin"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert r.json()["max_capacity"] == 25


async def test_patch_zone_not_found_returns_404() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.patch(
            "/api/zones/99999",
            json={"name": "Ghost"},
            headers=_auth("admin"),
        )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/zones/{id}  — soft delete
# ---------------------------------------------------------------------------


async def test_delete_zone_soft_deletes(db_session: Session) -> None:
    z = _seed_zone(db_session, name="ToArchive")
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.delete(f"/api/zones/{z.zone_id}", headers=_auth("admin"))
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 204
    db_session.expire(z)
    assert z.is_active is False


async def test_delete_zone_rejects_guard(db_session: Session) -> None:
    z = _seed_zone(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.delete(f"/api/zones/{z.zone_id}", headers=_auth("guard"))
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 403


async def test_delete_zone_excluded_from_list(db_session: Session) -> None:
    z = _seed_zone(db_session, name="WillArchive")
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.delete(f"/api/zones/{z.zone_id}", headers=_auth("admin"))
            r = await client.get("/api/zones", headers=_auth("guard"))
    finally:
        app.dependency_overrides.pop(get_db, None)
    names = [item["name"] for item in r.json()]
    assert "WillArchive" not in names
