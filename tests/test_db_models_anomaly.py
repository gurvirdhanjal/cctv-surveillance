"""Tests for AnomalyDetector ORM model."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vms.db.models import AnomalyDetector


def test_anomaly_detector_insert(db_session: Session) -> None:
    det = AnomalyDetector(
        alert_type="VIOLENCE",
        class_path="vms.anomaly.violence.ViolenceDetector",
    )
    db_session.add(det)
    db_session.commit()
    assert det.detector_id is not None
    assert det.is_enabled is True
    assert det.created_at is not None


def test_anomaly_detector_alert_type_unique(db_session: Session) -> None:
    db_session.add(
        AnomalyDetector(
            alert_type="LOITERING",
            class_path="vms.anomaly.loitering.LoiteringDetector",
        )
    )
    db_session.commit()
    db_session.add(
        AnomalyDetector(
            alert_type="LOITERING",
            class_path="vms.anomaly.loitering.LoiteringDetectorV2",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_anomaly_detector_can_be_disabled(db_session: Session) -> None:
    det = AnomalyDetector(
        alert_type="INTRUSION",
        class_path="vms.anomaly.intrusion.IntrusionDetector",
        is_enabled=False,
    )
    db_session.add(det)
    db_session.commit()
    assert det.is_enabled is False
