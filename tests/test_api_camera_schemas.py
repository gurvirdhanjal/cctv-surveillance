"""Tests for Camera Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vms.api.schemas import CameraCreate, CameraResponse, CameraUpdate


def test_camera_create_defaults() -> None:
    c = CameraCreate(name="Gate A", rtsp_url="rtsp://host/stream")
    assert c.capability_tier == "FULL"
    assert c.shutter_type == "unknown"
    assert c.worker_group is None


def test_camera_create_rejects_invalid_tier() -> None:
    with pytest.raises(ValidationError):
        CameraCreate(name="x", rtsp_url="rtsp://x", capability_tier="ULTRA")


def test_camera_create_rejects_invalid_shutter() -> None:
    with pytest.raises(ValidationError):
        CameraCreate(name="x", rtsp_url="rtsp://x", shutter_type="ccd")


def test_camera_create_rejects_name_too_long() -> None:
    with pytest.raises(ValidationError):
        CameraCreate(name="x" * 201, rtsp_url="rtsp://x")


def test_camera_update_all_optional() -> None:
    u = CameraUpdate()
    assert u.name is None
    assert u.rtsp_url is None
    assert u.is_active is None
    assert u.capability_tier is None
    assert u.shutter_type is None
    assert u.worker_group is None


def test_camera_update_rejects_invalid_tier() -> None:
    with pytest.raises(ValidationError):
        CameraUpdate(capability_tier="ULTRA")


def test_camera_update_rejects_invalid_shutter() -> None:
    with pytest.raises(ValidationError):
        CameraUpdate(shutter_type="ccd")


def test_camera_response_from_orm() -> None:
    class _FakeCam:
        camera_id = 1
        name = "Gate A"
        rtsp_url = "rtsp://host/stream"
        is_active = True
        capability_tier = "FULL"
        shutter_type = "rolling"
        profile_data = None
        profiled_at = None
        model_overrides = None
        worker_group = None

    resp = CameraResponse.model_validate(_FakeCam())
    assert resp.camera_id == 1
    assert resp.shutter_type == "rolling"
