"""Tests for ShutterProfile config resolver."""

from __future__ import annotations

import json

import pytest

from vms.inference.shutter_profile import ResolvedSetting, resolve_camera_config

BASE = {
    "base_adaface_min_sim": 0.72,
    "base_scrfd_conf": 0.60,
    "base_burst_frames": 3,
    "base_body_weight": 1.0,
}


def test_global_shutter_returns_base_values() -> None:
    result = resolve_camera_config(shutter_type="global", model_overrides_json=None, **BASE)
    assert result["adaface_min_sim"] == ResolvedSetting(value=0.72, source="global_default")
    assert result["scrfd_conf"] == ResolvedSetting(value=0.60, source="global_default")
    assert result["burst_frames"] == ResolvedSetting(value=3, source="global_default")
    assert result["body_weight_multiplier"] == ResolvedSetting(value=1.0, source="global_default")


def test_unknown_shutter_returns_base_values() -> None:
    result = resolve_camera_config(shutter_type="unknown", model_overrides_json=None, **BASE)
    assert result["adaface_min_sim"].source == "global_default"


def test_rolling_shutter_applies_delta_to_adaface() -> None:
    result = resolve_camera_config(shutter_type="rolling", model_overrides_json=None, **BASE)
    assert result["adaface_min_sim"].value == pytest.approx(0.62)
    assert result["adaface_min_sim"].source == "shutter:rolling"


def test_rolling_shutter_applies_delta_to_scrfd() -> None:
    result = resolve_camera_config(shutter_type="rolling", model_overrides_json=None, **BASE)
    assert result["scrfd_conf"].value == pytest.approx(0.50)
    assert result["scrfd_conf"].source == "shutter:rolling"


def test_rolling_shutter_sets_burst_frames_absolute() -> None:
    result = resolve_camera_config(shutter_type="rolling", model_overrides_json=None, **BASE)
    assert result["burst_frames"] == ResolvedSetting(value=5, source="shutter:rolling")


def test_rolling_shutter_sets_body_weight_absolute() -> None:
    result = resolve_camera_config(shutter_type="rolling", model_overrides_json=None, **BASE)
    assert result["body_weight_multiplier"] == ResolvedSetting(value=1.2, source="shutter:rolling")


def test_manual_override_wins_over_rolling() -> None:
    overrides = json.dumps({"adaface_min_sim": 0.85, "scrfd_conf": 0.70})
    result = resolve_camera_config(shutter_type="rolling", model_overrides_json=overrides, **BASE)
    assert result["adaface_min_sim"] == ResolvedSetting(value=0.85, source="manual_override")
    assert result["scrfd_conf"] == ResolvedSetting(value=0.70, source="manual_override")
    assert result["burst_frames"].source == "shutter:rolling"


def test_manual_override_wins_over_global() -> None:
    overrides = json.dumps({"burst_frames": 8})
    result = resolve_camera_config(shutter_type="global", model_overrides_json=overrides, **BASE)
    assert result["burst_frames"] == ResolvedSetting(value=8, source="manual_override")


def test_invalid_json_overrides_ignored() -> None:
    result = resolve_camera_config(shutter_type="rolling", model_overrides_json="{bad json", **BASE)
    assert result["adaface_min_sim"].source == "shutter:rolling"


def test_non_dict_json_overrides_ignored() -> None:
    result = resolve_camera_config(shutter_type="global", model_overrides_json="[1, 2, 3]", **BASE)
    assert result["adaface_min_sim"].source == "global_default"
