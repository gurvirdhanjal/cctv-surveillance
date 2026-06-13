"""Tests for vms/scheduler/jobs.py — SYSTEM_CRITICAL alert creation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from vms.db.models import Alert, Camera
from vms.scheduler.jobs import _emit_critical_alert


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_emit_critical_alert_creates_system_critical_row(db_session: Session) -> None:
    _emit_critical_alert(component="test_component", detail="something broke")

    alert = (
        db_session.query(Alert)
        .filter_by(alert_type="SYSTEM_CRITICAL")
        .order_by(Alert.alert_id.desc())
        .first()
    )
    assert alert is not None
    assert alert.alert_type == "SYSTEM_CRITICAL"
    assert alert.severity == "CRITICAL"
    assert alert.state == "active"
    assert alert.camera_id is None
    assert alert.dedup_key is not None
    assert "test_component" in alert.dedup_key


def test_emit_critical_alert_dedup_key_no_collision_with_real_alerts(
    db_session: Session,
) -> None:
    cam = Camera(name="cam_dedup", rtsp_url="rtsp://dedup", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()

    real_alert = Alert(
        alert_type="UNKNOWN_PERSON",
        severity="HIGH",
        state="active",
        camera_id=cam.camera_id,
        triggered_at=_utcnow(),
        dedup_key=f"unknown_person:{cam.camera_id}:track_abc",
    )
    db_session.add(real_alert)
    db_session.flush()

    _emit_critical_alert(component="audit_chain_verify", detail="Broken chain at audit_id=42")

    sys_alert = (
        db_session.query(Alert)
        .filter_by(alert_type="SYSTEM_CRITICAL")
        .order_by(Alert.alert_id.desc())
        .first()
    )
    assert sys_alert is not None
    assert sys_alert.dedup_key != real_alert.dedup_key
    assert sys_alert.dedup_key is not None
    assert sys_alert.dedup_key.startswith("scheduler:")


def test_emit_critical_alert_camera_id_is_null(db_session: Session) -> None:
    _emit_critical_alert(component="worker_heartbeat_check", detail="Workers absent: heartbeat:w1")

    alert = (
        db_session.query(Alert)
        .filter(
            Alert.alert_type == "SYSTEM_CRITICAL",
            Alert.dedup_key.contains("worker_heartbeat_check"),
        )
        .order_by(Alert.alert_id.desc())
        .first()
    )
    assert alert is not None
    assert alert.camera_id is None


def test_emit_critical_alert_survives_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock, patch

    # SessionLocal is a lazy import inside _emit_critical_alert, so patch the source module.
    with patch("vms.db.session.SessionLocal") as mock_sl:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.add.side_effect = RuntimeError("DB unavailable")
        mock_sl.return_value = mock_session

        # Must not raise — _emit_critical_alert swallows exceptions
        _emit_critical_alert(component="partition_manager", detail="partition create failed")


def test_emit_critical_alert_uses_system_critical_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_emit_critical_alert must create SYSTEM_CRITICAL alert with camera_id=None."""
    from unittest.mock import MagicMock

    added_alerts: list[object] = []

    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: s
    mock_session.__exit__ = MagicMock(return_value=False)

    def fake_add(obj: object) -> None:
        added_alerts.append(obj)

    mock_session.add = fake_add
    monkeypatch.setattr("vms.scheduler.jobs.SessionLocal", lambda: mock_session)

    _emit_critical_alert(detail="disk full", component="partition_create")

    assert len(added_alerts) == 1
    alert = added_alerts[0]
    assert alert.alert_type == "SYSTEM_CRITICAL", (
        f"Expected SYSTEM_CRITICAL, got {alert.alert_type}"
    )
    assert alert.camera_id is None, (
        f"camera_id must be None for system alerts, got {alert.camera_id}"
    )
    assert alert.severity == "CRITICAL"


def test_emit_critical_alert_dedup_key_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dedup_key must be prefixed 'scheduler:' so Guard view filter works correctly."""
    from unittest.mock import MagicMock

    added_alerts: list[object] = []

    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: s
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.add = lambda obj: added_alerts.append(obj)
    monkeypatch.setattr("vms.scheduler.jobs.SessionLocal", lambda: mock_session)

    _emit_critical_alert(detail="chain broken at audit_id=5", component="audit_chain_verify")

    assert len(added_alerts) == 1
    key = added_alerts[0].dedup_key
    assert key.startswith("scheduler:"), f"dedup_key must start with 'scheduler:', got {key!r}"


def test_emit_critical_alert_db_failure_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the DB write fails, _emit_critical_alert logs and swallows the exception."""
    from unittest.mock import MagicMock

    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: s
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.add = MagicMock(side_effect=RuntimeError("DB unavailable"))
    monkeypatch.setattr("vms.scheduler.jobs.SessionLocal", lambda: mock_session)

    _emit_critical_alert(detail="test", component="test")
