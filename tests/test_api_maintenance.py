"""Tests for GET/POST/PATCH/DELETE /api/maintenance and /api/maintenance/calendar."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.models import Camera, MaintenanceWindow, User


def _auth(role: str = "manager") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


def _seed_user(db: Session, role: str = "manager") -> int:
    """Seed a user and return its id (POST needs a real created_by FK target)."""
    u = User(username=f"mw_op_{id(db)}", password_hash="x", role=role, is_active=True)
    db.add(u)
    db.flush()
    return u.user_id


def _auth_for(user_id: int, role: str = "manager") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


def _mock_redis() -> AsyncMock:
    mock = AsyncMock()
    mock.publish = AsyncMock(return_value=1)
    return mock


@pytest.mark.asyncio
async def test_list_maintenance_windows(db_session: Session) -> None:
    from vms.api.deps import get_db

    u = User(username="m_op", password_hash="x", role="admin", is_active=True)
    db_session.add(u)
    db_session.flush()
    c = Camera(name="MC", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(c)
    db_session.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(
        MaintenanceWindow(
            name="mw1",
            scope_type="CAMERA",
            scope_id=c.camera_id,
            schedule_type="ONE_TIME",
            starts_at=now,
            ends_at=now + timedelta(hours=1),
            created_by=u.user_id,
        )
    )
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.get("/api/maintenance", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    names = [w["name"] for w in r.json()]
    assert "mw1" in names


@pytest.mark.asyncio
async def test_post_maintenance_one_time_succeeds(db_session: Session) -> None:
    uid = _seed_user(db_session)
    cam = Camera(name="PC1", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    mock_r = _mock_redis()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.maintenance.get_api_redis", return_value=mock_r):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
                r = await cli.post(
                    "/api/maintenance",
                    json={
                        "name": "ot-window",
                        "scope_type": "CAMERA",
                        "scope_id": cam.camera_id,
                        "schedule_type": "ONE_TIME",
                        "starts_at": now.isoformat(),
                        "ends_at": (now + timedelta(hours=2)).isoformat(),
                    },
                    headers=_auth_for(uid),
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "ot-window"
    assert body["is_active"] is True
    row = db_session.get(MaintenanceWindow, body["window_id"])
    assert row is not None
    assert row.created_by == uid
    mock_r.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_maintenance_recurring_succeeds(db_session: Session) -> None:
    uid = _seed_user(db_session)
    cam = Camera(name="PC2", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()

    mock_r = _mock_redis()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.maintenance.get_api_redis", return_value=mock_r):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
                r = await cli.post(
                    "/api/maintenance",
                    json={
                        "name": "weekly-window",
                        "scope_type": "ZONE",
                        "scope_id": 1,
                        "schedule_type": "RECURRING",
                        "cron_expr": "0 14 * * 6",
                        "duration_minutes": 120,
                        "suppress_alert_types": ["INTRUSION", "LOITERING"],
                    },
                    headers=_auth_for(uid),
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 201
    body = r.json()
    assert body["schedule_type"] == "RECURRING"
    assert body["cron_expr"] == "0 14 * * 6"
    mock_r.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_maintenance_one_time_missing_starts_at_returns_422(
    db_session: Session,
) -> None:
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.post(
                "/api/maintenance",
                json={
                    "name": "bad-ot",
                    "scope_type": "CAMERA",
                    "scope_id": 1,
                    "schedule_type": "ONE_TIME",
                    "ends_at": (now + timedelta(hours=1)).isoformat(),
                },
                headers=_auth_for(uid),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_maintenance_recurring_missing_cron_returns_422(
    db_session: Session,
) -> None:
    uid = _seed_user(db_session)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.post(
                "/api/maintenance",
                json={
                    "name": "bad-recurring",
                    "scope_type": "ZONE",
                    "scope_id": 1,
                    "schedule_type": "RECURRING",
                    "duration_minutes": 60,
                },
                headers=_auth_for(uid),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_maintenance_ends_at_before_starts_at_returns_422(
    db_session: Session,
) -> None:
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.post(
                "/api/maintenance",
                json={
                    "name": "inverted",
                    "scope_type": "CAMERA",
                    "scope_id": 1,
                    "schedule_type": "ONE_TIME",
                    "starts_at": (now + timedelta(hours=2)).isoformat(),
                    "ends_at": now.isoformat(),
                },
                headers=_auth_for(uid),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_maintenance_updates_name(db_session: Session) -> None:
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    window = MaintenanceWindow(
        name="original",
        scope_type="CAMERA",
        scope_id=1,
        schedule_type="ONE_TIME",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=uid,
    )
    db_session.add(window)
    db_session.flush()

    mock_r = _mock_redis()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.maintenance.get_api_redis", return_value=mock_r):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
                r = await cli.patch(
                    f"/api/maintenance/{window.window_id}",
                    json={"name": "renamed"},
                    headers=_auth_for(uid),
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
    assert r.json()["name"] == "renamed"
    db_session.refresh(window)
    assert window.name == "renamed"
    mock_r.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_patch_maintenance_updates_cron(db_session: Session) -> None:
    uid = _seed_user(db_session)
    window = MaintenanceWindow(
        name="recurring",
        scope_type="ZONE",
        scope_id=1,
        schedule_type="RECURRING",
        cron_expr="0 10 * * 1",
        duration_minutes=60,
        created_by=uid,
    )
    db_session.add(window)
    db_session.flush()

    mock_r = _mock_redis()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.maintenance.get_api_redis", return_value=mock_r):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
                r = await cli.patch(
                    f"/api/maintenance/{window.window_id}",
                    json={"cron_expr": "0 14 * * 5"},
                    headers=_auth_for(uid),
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
    assert r.json()["cron_expr"] == "0 14 * * 5"


@pytest.mark.asyncio
async def test_patch_maintenance_schedule_change_missing_starts_at_returns_422(
    db_session: Session,
) -> None:
    uid = _seed_user(db_session)
    window = MaintenanceWindow(
        name="recurring",
        scope_type="ZONE",
        scope_id=1,
        schedule_type="RECURRING",
        cron_expr="0 10 * * 1",
        duration_minutes=60,
        created_by=uid,
    )
    db_session.add(window)
    db_session.flush()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.patch(
                f"/api/maintenance/{window.window_id}",
                json={"schedule_type": "ONE_TIME"},
                headers=_auth_for(uid),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_maintenance_not_found_returns_404(db_session: Session) -> None:
    uid = _seed_user(db_session)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.patch(
                "/api/maintenance/99999",
                json={"name": "ghost"},
                headers=_auth_for(uid),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_maintenance_unauthenticated_returns_401() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
        r = await cli.post(
            "/api/maintenance",
            json={
                "name": "unauth",
                "scope_type": "CAMERA",
                "scope_id": 1,
                "schedule_type": "ONE_TIME",
                "starts_at": "2026-01-01T00:00:00",
                "ends_at": "2026-01-01T01:00:00",
            },
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_delete_maintenance_soft_deletes(db_session: Session) -> None:
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    window = MaintenanceWindow(
        name="to-delete",
        scope_type="CAMERA",
        scope_id=1,
        schedule_type="ONE_TIME",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=uid,
    )
    db_session.add(window)
    db_session.flush()
    wid = window.window_id

    mock_r = _mock_redis()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.maintenance.get_api_redis", return_value=mock_r):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
                r = await cli.delete(f"/api/maintenance/{wid}", headers=_auth_for(uid))
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 204
    db_session.refresh(window)
    assert window.is_active is False
    mock_r.publish.assert_awaited_once()

    # Window must no longer appear in the active list.
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r2 = await cli.get("/api/maintenance", headers=_auth_for(uid))
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r2.status_code == 200
    assert all(w["window_id"] != wid for w in r2.json())


@pytest.mark.asyncio
async def test_delete_maintenance_inactive_returns_404(db_session: Session) -> None:
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    window = MaintenanceWindow(
        name="already-gone",
        scope_type="CAMERA",
        scope_id=1,
        schedule_type="ONE_TIME",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=uid,
        is_active=False,
    )
    db_session.add(window)
    db_session.flush()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.delete(f"/api/maintenance/{window.window_id}", headers=_auth_for(uid))
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_maintenance_unknown_id_returns_404(db_session: Session) -> None:
    uid = _seed_user(db_session)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.delete("/api/maintenance/99999", headers=_auth_for(uid))
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 404


# ── Calendar tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_maintenance_succeeds_when_redis_unavailable(db_session: Session) -> None:
    """POST must return 201 and persist the window even when Redis is unreachable."""
    uid = _seed_user(db_session)
    cam = Camera(name="RDown1", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    broken_redis = AsyncMock()
    broken_redis.publish = AsyncMock(side_effect=ConnectionError("Redis down"))
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.maintenance.get_api_redis", return_value=broken_redis):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
                r = await cli.post(
                    "/api/maintenance",
                    json={
                        "name": "redis-down-ot",
                        "scope_type": "CAMERA",
                        "scope_id": cam.camera_id,
                        "schedule_type": "ONE_TIME",
                        "starts_at": now.isoformat(),
                        "ends_at": (now + timedelta(hours=1)).isoformat(),
                    },
                    headers=_auth_for(uid),
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 201
    wid = r.json()["window_id"]
    row = db_session.get(MaintenanceWindow, wid)
    assert row is not None
    assert row.name == "redis-down-ot"


@pytest.mark.asyncio
async def test_patch_maintenance_succeeds_when_redis_unavailable(db_session: Session) -> None:
    """PATCH must return 200 and persist the update even when Redis is unreachable."""
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    window = MaintenanceWindow(
        name="before-patch",
        scope_type="CAMERA",
        scope_id=1,
        schedule_type="ONE_TIME",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=uid,
    )
    db_session.add(window)
    db_session.flush()

    broken_redis = AsyncMock()
    broken_redis.publish = AsyncMock(side_effect=ConnectionError("Redis down"))
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.maintenance.get_api_redis", return_value=broken_redis):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
                r = await cli.patch(
                    f"/api/maintenance/{window.window_id}",
                    json={"name": "after-patch"},
                    headers=_auth_for(uid),
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
    assert r.json()["name"] == "after-patch"
    db_session.refresh(window)
    assert window.name == "after-patch"


@pytest.mark.asyncio
async def test_delete_maintenance_succeeds_when_redis_unavailable(db_session: Session) -> None:
    """DELETE must return 204 and soft-delete the window even when Redis is unreachable."""
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    window = MaintenanceWindow(
        name="to-delete-rdown",
        scope_type="CAMERA",
        scope_id=1,
        schedule_type="ONE_TIME",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=uid,
    )
    db_session.add(window)
    db_session.flush()
    wid = window.window_id

    broken_redis = AsyncMock()
    broken_redis.publish = AsyncMock(side_effect=ConnectionError("Redis down"))
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.maintenance.get_api_redis", return_value=broken_redis):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
                r = await cli.delete(f"/api/maintenance/{wid}", headers=_auth_for(uid))
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 204
    db_session.refresh(window)
    assert window.is_active is False


# ── Calendar tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_calendar_one_time_in_range(db_session: Session) -> None:
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    window = MaintenanceWindow(
        name="cal-ot",
        scope_type="CAMERA",
        scope_id=1,
        schedule_type="ONE_TIME",
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        created_by=uid,
    )
    db_session.add(window)
    db_session.flush()

    from_str = now.isoformat()
    to_str = (now + timedelta(hours=3)).isoformat()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.get(
                "/api/maintenance/calendar",
                params={"from": from_str, "to": to_str},
                headers=_auth_for(uid),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
    body = r.json()
    assert body["total_slots"] == 1
    slot = body["slots"][0]
    assert slot["window_id"] == window.window_id
    assert slot["is_recurring"] is False


@pytest.mark.asyncio
async def test_get_calendar_one_time_outside_range_not_returned(
    db_session: Session,
) -> None:
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    window = MaintenanceWindow(
        name="cal-ot-out",
        scope_type="CAMERA",
        scope_id=1,
        schedule_type="ONE_TIME",
        starts_at=now + timedelta(days=5),
        ends_at=now + timedelta(days=5, hours=1),
        created_by=uid,
    )
    db_session.add(window)
    db_session.flush()

    from_str = now.isoformat()
    to_str = (now + timedelta(hours=3)).isoformat()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.get(
                "/api/maintenance/calendar",
                params={"from": from_str, "to": to_str},
                headers=_auth_for(uid),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
    assert r.json()["total_slots"] == 0


@pytest.mark.asyncio
async def test_get_calendar_recurring_four_occurrences(db_session: Session) -> None:
    uid = _seed_user(db_session)
    # Saturday 14:00 weekly, 120 min. Monday range for 28 days = 4 Saturdays.
    monday = datetime(2026, 7, 6, 0, 0, 0)  # a Monday
    window = MaintenanceWindow(
        name="cal-rec",
        scope_type="ZONE",
        scope_id=1,
        schedule_type="RECURRING",
        cron_expr="0 14 * * 6",
        duration_minutes=120,
        created_by=uid,
    )
    db_session.add(window)
    db_session.flush()

    from_str = monday.isoformat()
    to_str = (monday + timedelta(days=28)).isoformat()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.get(
                "/api/maintenance/calendar",
                params={"from": from_str, "to": to_str},
                headers=_auth_for(uid),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
    body = r.json()
    assert body["total_slots"] == 4
    for slot in body["slots"]:
        assert slot["is_recurring"] is True
        assert slot["window_id"] == window.window_id


@pytest.mark.asyncio
async def test_get_calendar_range_exceeds_max_returns_400(db_session: Session) -> None:
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.get(
                "/api/maintenance/calendar",
                params={
                    "from": now.isoformat(),
                    "to": (now + timedelta(days=91)).isoformat(),
                },
                headers=_auth_for(uid),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 400


@pytest.mark.asyncio
async def test_get_calendar_no_windows_returns_empty(db_session: Session) -> None:
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.get(
                "/api/maintenance/calendar",
                params={
                    "from": now.isoformat(),
                    "to": (now + timedelta(hours=3)).isoformat(),
                },
                headers=_auth_for(uid),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
    body = r.json()
    assert body["slots"] == []
    assert body["total_slots"] == 0


@pytest.mark.asyncio
async def test_get_calendar_inverted_range_returns_422(db_session: Session) -> None:
    uid = _seed_user(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
            r = await cli.get(
                "/api/maintenance/calendar",
                params={
                    "from": (now + timedelta(hours=3)).isoformat(),
                    "to": now.isoformat(),
                },
                headers=_auth_for(uid),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 422
