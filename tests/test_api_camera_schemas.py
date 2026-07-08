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
        site_name = None
        building_name = None
        floor_name = None

    resp = CameraResponse.model_validate(_FakeCam())
    assert resp.camera_id == 1
    assert resp.shutter_type == "rolling"
    assert resp.site_name is None
    assert resp.building_name is None
    assert resp.floor_name is None


def test_camera_response_hierarchy_fields_populated() -> None:
    class _FakeCam:
        camera_id = 2
        name = "Bay 3"
        rtsp_url = "rtsp://host/bay3"
        is_active = True
        capability_tier = "MID"
        shutter_type = "global"
        profile_data = None
        profiled_at = None
        model_overrides = None
        worker_group = None
        site_name = "Plant A"
        building_name = "Block 1"
        floor_name = "Ground Floor"

    resp = CameraResponse.model_validate(_FakeCam())
    assert resp.site_name == "Plant A"
    assert resp.building_name == "Block 1"
    assert resp.floor_name == "Ground Floor"


def test_camera_update_includes_hierarchy_fields() -> None:
    u = CameraUpdate(site_name="Plant A", building_name="Block 1", floor_name="Ground Floor")
    assert u.site_name == "Plant A"
    assert u.building_name == "Block 1"
    assert u.floor_name == "Ground Floor"


def test_camera_update_hierarchy_fields_optional() -> None:
    u = CameraUpdate()
    assert u.site_name is None
    assert u.building_name is None
    assert u.floor_name is None
