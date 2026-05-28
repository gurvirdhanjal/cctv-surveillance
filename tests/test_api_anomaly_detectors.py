"""Tests for GET /api/anomaly-detectors and /api/anomaly-detectors/health."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.main import app


def _auth(role: str = "manager") -> dict[str, str]:
    from vms.api.deps import create_access_token

    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


@pytest.mark.asyncio
async def test_list_anomaly_detectors_returns_six_seeded(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/anomaly-detectors", headers=_auth())
    assert r.status_code == 200
    types = sorted(d["alert_type"] for d in r.json())
    assert types == [
        "CROWD_DENSITY",
        "INTRUSION",
        "LOITERING",
        "PERSON_LOST",
        "UNKNOWN_PERSON",
        "VIOLENCE",
    ]


@pytest.mark.asyncio
async def test_detector_health_returns_empty_when_unwired() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/anomaly-detectors/health", headers=_auth())
    assert r.status_code == 200
    assert isinstance(r.json(), dict)
