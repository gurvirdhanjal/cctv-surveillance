"""Tests for AnomalyDetector ORM model."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vms.db.models import AnomalyDetector


def test_anomaly_detector_seeded_rows_exist(db_session: Session) -> None:
    """The phase2b migration seeds 6 default detector rows."""
    rows = db_session.query(AnomalyDetector).order_by(AnomalyDetector.alert_type).all()
    types = [r.alert_type for r in rows]
    assert "VIOLENCE" in types
    assert "LOITERING" in types
    assert "INTRUSION" in types
    for r in rows:
        assert r.detector_id is not None
        assert r.is_enabled is True
        assert r.created_at is not None


def test_anomaly_detector_alert_type_unique(db_session: Session) -> None:
    """Duplicate alert_type violates the unique constraint."""
    db_session.add(
        AnomalyDetector(
            alert_type="VIOLENCE",
            class_path="vms.anomaly.detectors.violence.ViolenceDetectorDuplicate",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_anomaly_detector_can_be_disabled(db_session: Session) -> None:
    """Disabling a detector by toggling is_enabled."""
    det = db_session.query(AnomalyDetector).filter_by(alert_type="INTRUSION").one()
    det.is_enabled = False
    db_session.flush()
    refreshed = db_session.query(AnomalyDetector).filter_by(alert_type="INTRUSION").one()
    assert refreshed.is_enabled is False
