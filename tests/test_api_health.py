"""Tests for GET /api/health."""

from __future__ import annotations

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
