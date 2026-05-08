"""Tests for topology ORM models: Camera, Zone."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vms.db.models import Camera, Zone


def test_camera_insert_and_query(db_session: Session) -> None:
    cam = Camera(name="Line1-Cam1", rtsp_url="rtsp://10.0.0.1/stream")
    db_session.add(cam)
    db_session.commit()
    result = db_session.get(Camera, cam.camera_id)
    assert result is not None
    assert result.name == "Line1-Cam1"
    assert result.capability_tier == "FULL"
    assert result.is_active is True


def test_camera_tier_default_full(db_session: Session) -> None:
    cam = Camera(name="cam", rtsp_url="rtsp://x/s")
    db_session.add(cam)
    db_session.commit()
    assert cam.capability_tier == "FULL"


def test_camera_tier_invalid_rejected(db_session: Session) -> None:
    cam = Camera(name="bad", rtsp_url="rtsp://x/s", capability_tier="ULTRA")
    db_session.add(cam)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_zone_insert_and_query(db_session: Session) -> None:
    zone = Zone(name="Assembly Floor")
    db_session.add(zone)
    db_session.commit()
    result = db_session.get(Zone, zone.zone_id)
    assert result is not None
    assert result.name == "Assembly Floor"
    assert result.is_restricted is False
    assert result.loiter_threshold_s == 180


def test_zone_restricted_flag(db_session: Session) -> None:
    zone = Zone(name="Server Room", is_restricted=True, max_capacity=3)
    db_session.add(zone)
    db_session.commit()
    assert zone.is_restricted is True
    assert zone.max_capacity == 3
