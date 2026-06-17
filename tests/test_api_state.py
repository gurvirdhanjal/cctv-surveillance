"""Tests for GET /api/state/snapshot."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from vms.api.main import app
from vms.api.routes.state import set_head_count_aggregator
from vms.identity.head_count import HeadCountAggregator


def _auth(role: str = "manager") -> dict[str, str]:
    from vms.api.deps import create_access_token

    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


@pytest.mark.asyncio
async def test_snapshot_returns_payload_shape() -> None:
    agg = HeadCountAggregator()
    set_head_count_aggregator(agg)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/state/snapshot", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert "ts" in body
    assert "schema_version" in body
    assert body["schema_version"] == "1"
    assert "head_count" in body
    assert "active_alerts" in body
    assert "cameras" in body


@pytest.mark.asyncio
async def test_snapshot_requires_auth() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/state/snapshot")
    assert r.status_code in (401, 403)
