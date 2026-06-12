"""API tests for alert routing CRUD."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token
from vms.api.main import app


def _auth(role: str = "admin", user_id: int = 1) -> dict[str, str]:
    token = create_access_token(user_id=user_id, role=role)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
async def test_list_routing_rules_returns_empty_initially(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/alert-routing", headers=_auth("guard"))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
async def test_create_routing_rule_requires_admin(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/alert-routing",
            json={"channel": "WEBHOOK", "target": "https://example.com"},
            headers=_auth("guard"),
        )
    assert resp.status_code == 403


@pytest.mark.integration
async def test_create_routing_rule_admin_succeeds(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/alert-routing",
            json={
                "channel": "WEBHOOK",
                "target": "https://example.com/hook",
                "alert_type": "VIOLENCE",
                "severity": "CRITICAL",
            },
            headers=_auth("admin"),
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["channel"] == "WEBHOOK"
    assert body["target"] == "https://example.com/hook"
    assert body["alert_type"] == "VIOLENCE"
    assert body["is_active"] is True
    assert "routing_id" in body


@pytest.mark.integration
async def test_delete_routing_rule_soft_deletes(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/alert-routing",
            json={"channel": "SLACK", "target": "#alerts"},
            headers=_auth("admin"),
        )
        assert create_resp.status_code == 201
        routing_id = create_resp.json()["routing_id"]

        del_resp = await client.delete(f"/api/alert-routing/{routing_id}", headers=_auth("admin"))
        assert del_resp.status_code == 204

        list_resp = await client.get("/api/alert-routing", headers=_auth("admin"))
    active_ids = [r["routing_id"] for r in list_resp.json()]
    assert routing_id not in active_ids


@pytest.mark.integration
async def test_create_routing_rule_rejects_invalid_channel(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/alert-routing",
            json={"channel": "PIGEON", "target": "coo"},
            headers=_auth("admin"),
        )
    assert resp.status_code == 422


@pytest.mark.integration
async def test_health_endpoint_still_passes_after_dispatcher_wired() -> None:
    """Regression: wiring the dispatcher must not break the health endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
