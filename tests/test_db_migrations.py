"""Phase 2b migration round-trip and schema verification tests."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_phase2b_migration_adds_alerts_dedup_key(db_session: Session) -> None:
    insp = inspect(db_session.bind)
    cols = {c["name"] for c in insp.get_columns("alerts")}
    assert "dedup_key" in cols


@pytest.mark.integration
def test_phase2b_migration_adds_alerts_state_check(db_session: Session) -> None:
    """alerts.state CHECK constraint forbids unknown states."""
    from vms.db.models import Camera

    cam = Camera(name="MigC", rtsp_url="rtsp://x/1", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        db_session.execute(
            text(
                "INSERT INTO alerts (alert_type, severity, state, camera_id, triggered_at) "
                "VALUES ('UNKNOWN_PERSON', 'HIGH', 'NOT_A_STATE', :cid, NOW())"
            ),
            {"cid": cam.camera_id},
        )
        db_session.flush()


@pytest.mark.integration
def test_phase2b_migration_seeds_six_default_detectors(db_session: Session) -> None:
    rows = db_session.execute(
        text("SELECT alert_type FROM anomaly_detectors ORDER BY alert_type")
    ).all()
    types = [r[0] for r in rows]
    assert types == [
        "CROWD_DENSITY",
        "INTRUSION",
        "LOITERING",
        "PERSON_LOST",
        "UNKNOWN_PERSON",
        "VIOLENCE",
    ]
