"""Tests for GET /api/health and GET /api/ready."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from vms.api.main import app


async def test_health_returns_200() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200


async def test_health_response_has_status_ok() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


async def test_ready_returns_200_when_db_and_redis_healthy() -> None:
    """GET /api/ready returns 200 when DB and Redis are reachable."""
    from vms.api import deps

    mock_db = MagicMock()
    mock_db.execute = MagicMock(return_value=None)
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    app.dependency_overrides[deps.get_db] = lambda: mock_db
    app.dependency_overrides[deps.get_api_redis] = lambda: mock_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/ready")
    finally:
        app.dependency_overrides.pop(deps.get_db, None)
        app.dependency_overrides.pop(deps.get_api_redis, None)
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert body["redis"] == "ok"


async def test_ready_returns_503_when_db_unavailable() -> None:
    """GET /api/ready returns 503 when DB is down."""
    from vms.api import deps

    mock_db = MagicMock()
    mock_db.execute = MagicMock(side_effect=Exception("DB connection refused"))
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    app.dependency_overrides[deps.get_db] = lambda: mock_db
    app.dependency_overrides[deps.get_api_redis] = lambda: mock_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/ready")
    finally:
        app.dependency_overrides.pop(deps.get_db, None)
        app.dependency_overrides.pop(deps.get_api_redis, None)
    assert r.status_code == 503
    body = r.json()
    assert body["db"] != "ok"
    assert body["redis"] == "ok"


async def test_ready_returns_503_when_redis_unavailable() -> None:
    """GET /api/ready returns 503 when Redis is down."""
    from vms.api import deps

    mock_db = MagicMock()
    mock_db.execute = MagicMock(return_value=None)
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=Exception("Redis connection refused"))

    app.dependency_overrides[deps.get_db] = lambda: mock_db
    app.dependency_overrides[deps.get_api_redis] = lambda: mock_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/ready")
    finally:
        app.dependency_overrides.pop(deps.get_db, None)
        app.dependency_overrides.pop(deps.get_api_redis, None)
    assert r.status_code == 503
    body = r.json()
    assert body["redis"] != "ok"
