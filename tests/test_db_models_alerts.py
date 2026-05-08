"""Tests for alert ORM models: Alert, AlertRouting, AlertDispatch."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vms.db.models import Alert, AlertDispatch, AlertRouting, Camera

_TS = datetime(2026, 5, 1, 9, 0, 0)
_TS2 = datetime(2026, 5, 1, 9, 5, 0)


def _cam(db_session: Session) -> Camera:
    cam = Camera(name="alert-cam", rtsp_url="rtsp://a/s")
    db_session.add(cam)
    db_session.commit()
    return cam


def test_alert_insert_defaults(db_session: Session) -> None:
    cam = _cam(db_session)
    alert = Alert(
        alert_type="INTRUSION",
        severity="HIGH",
        camera_id=cam.camera_id,
        triggered_at=_TS,
    )
    db_session.add(alert)
    db_session.commit()
    assert alert.alert_id is not None
    assert alert.state == "active"


def test_alert_resolution_order_violation(db_session: Session) -> None:
    cam = _cam(db_session)
    # acknowledged_at before triggered_at — invalid
    alert = Alert(
        alert_type="VIOLENCE",
        severity="CRITICAL",
        camera_id=cam.camera_id,
        triggered_at=_TS2,
        acknowledged_at=_TS,  # earlier than triggered_at
    )
    db_session.add(alert)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_alert_routing_insert(db_session: Session) -> None:
    routing = AlertRouting(channel="EMAIL", target="ops@example.com")
    db_session.add(routing)
    db_session.commit()
    assert routing.routing_id is not None
    assert routing.is_active is True


def test_alert_routing_invalid_channel(db_session: Session) -> None:
    routing = AlertRouting(channel="PAGER", target="555-1234")
    db_session.add(routing)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_alert_dispatch_insert(db_session: Session) -> None:
    cam = _cam(db_session)
    alert = Alert(
        alert_type="LOITERING",
        severity="MEDIUM",
        camera_id=cam.camera_id,
        triggered_at=_TS,
    )
    db_session.add(alert)
    db_session.commit()
    dispatch = AlertDispatch(
        alert_id=alert.alert_id,
        channel="SLACK",
        target="#security",
        success=True,
    )
    db_session.add(dispatch)
    db_session.commit()
    assert dispatch.dispatch_id is not None


def test_alert_cascade_deletes_dispatches(db_session: Session) -> None:
    cam = _cam(db_session)
    alert = Alert(
        alert_type="CROWD_DENSITY",
        severity="LOW",
        camera_id=cam.camera_id,
        triggered_at=_TS,
    )
    db_session.add(alert)
    db_session.commit()
    dispatch = AlertDispatch(
        alert_id=alert.alert_id, channel="WEBSOCKET", target="ws", success=False
    )
    db_session.add(dispatch)
    db_session.commit()
    dispatch_id = dispatch.dispatch_id
    db_session.delete(alert)
    db_session.commit()
    assert db_session.get(AlertDispatch, dispatch_id) is None
