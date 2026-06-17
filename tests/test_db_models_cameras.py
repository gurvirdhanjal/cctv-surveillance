"""Tests for Camera ORM — shutter_type and model_overrides fields."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vms.db.models import Camera


def _camera(**kwargs: object) -> Camera:
    defaults = {"name": "Test Cam", "rtsp_url": "rtsp://host/stream", "capability_tier": "FULL"}
    defaults.update(kwargs)
    return Camera(**defaults)


def test_camera_shutter_type_defaults_to_unknown(db_session: Session) -> None:
    cam = _camera()
    db_session.add(cam)
    db_session.flush()
    assert cam.shutter_type == "unknown"


def test_camera_shutter_type_accepts_valid_values(db_session: Session) -> None:
    for val in ("rolling", "global", "unknown"):
        cam = _camera(name=f"cam_{val}", shutter_type=val)
        db_session.add(cam)
        db_session.flush()
        assert cam.shutter_type == val


def test_camera_shutter_type_rejects_invalid_value(db_session: Session) -> None:
    cam = _camera(shutter_type="ccd")
    db_session.add(cam)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_camera_model_overrides_defaults_to_none(db_session: Session) -> None:
    cam = _camera()
    db_session.add(cam)
    db_session.flush()
    assert cam.model_overrides is None


def test_camera_model_overrides_stores_json_string(db_session: Session) -> None:
    payload = '{"models": {"face_embedder": "adaface_ir50_acme"}, "thresholds": {}}'
    cam = _camera(model_overrides=payload)
    db_session.add(cam)
    db_session.flush()
    db_session.refresh(cam)
    assert cam.model_overrides == payload
