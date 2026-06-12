"""Tests for GET/PATCH /api/anomaly-detectors and /api/anomaly-detectors/health."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.models import AnomalyDetector


def _auth(role: str = "manager") -> dict[str, str]:
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_detector_disable_sets_is_enabled_false(db_session: Session) -> None:
    detector = (
        db_session.query(AnomalyDetector).filter(AnomalyDetector.alert_type == "INTRUSION").first()
    )
    assert detector is not None

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch("vms.api.routes.anomaly_detectors.get_api_redis") as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.publish = AsyncMock(return_value=1)
            mock_get_redis.return_value = mock_redis
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.patch(
                    f"/api/anomaly-detectors/{detector.detector_id}",
                    json={"is_enabled": False},
                    headers=_auth("manager"),
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
    assert r.json()["is_enabled"] is False
    db_session.refresh(detector)
    assert detector.is_enabled is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_detector_invalid_config_json_returns_422(db_session: Session) -> None:
    detector = (
        db_session.query(AnomalyDetector).filter(AnomalyDetector.alert_type == "INTRUSION").first()
    )
    assert detector is not None

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/anomaly-detectors/{detector.detector_id}",
                json={"config_json": "not-a-dict"},
                headers=_auth("manager"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 422
