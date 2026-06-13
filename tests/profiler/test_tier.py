"""Tests for CameraProfiler tier assignment logic."""
import pytest
from vms.api.schemas import ProfileData
from vms.profiler.tier import assign_tier


def _data(**kwargs: object) -> ProfileData:
    """Helper: build ProfileData with sensible defaults, override via kwargs."""
    defaults: dict[str, object] = {
        "resolution_w": 1920,
        "resolution_h": 1080,
        "fps_measured": 15.0,
        "focus_score": 40.0,
        "is_analog_via_encoder": False,
        "frame_drop_rate": 0.01,
    }
    defaults.update(kwargs)
    return ProfileData(**defaults)


def test_assign_tier_full_all_criteria_met() -> None:
    tier, reason = assign_tier(_data())
    assert tier == "FULL"
    assert "1080p" in reason or "fps" in reason


def test_assign_tier_low_resolution() -> None:
    tier, reason = assign_tier(_data(resolution_h=480))
    assert tier == "LOW"
    assert "<720p" in reason


def test_assign_tier_low_fps() -> None:
    tier, reason = assign_tier(_data(fps_measured=5.0))
    assert tier == "LOW"
    assert "<8fps" in reason


def test_assign_tier_low_analog_via_encoder() -> None:
    tier, reason = assign_tier(_data(is_analog_via_encoder=True))
    assert tier == "LOW"
    assert "analog" in reason.lower()


def test_assign_tier_low_focus() -> None:
    tier, reason = assign_tier(_data(focus_score=10.0))
    assert tier == "LOW"
    assert "focus" in reason.lower()


def test_assign_tier_mid_720p() -> None:
    tier, reason = assign_tier(_data(resolution_h=720))
    assert tier == "MID"


def test_assign_tier_mid_fps_borderline() -> None:
    tier, reason = assign_tier(_data(fps_measured=10.0))
    assert tier == "MID"


def test_assign_tier_mid_focus_borderline() -> None:
    tier, reason = assign_tier(_data(focus_score=20.0))
    assert tier == "MID"


def test_assign_tier_uses_config_thresholds() -> None:
    from vms.config import get_settings
    s = get_settings()
    # Exactly at full threshold — should be FULL
    tier, _ = assign_tier(_data(
        resolution_h=s.profiler_res_full_min_h,
        fps_measured=s.profiler_fps_full_min,
        focus_score=s.profiler_focus_full_min,
    ))
    assert tier == "FULL"


def test_assign_tier_none_data_returns_full() -> None:
    """When data is missing (None fields), default to FULL (best-effort)."""
    tier, reason = assign_tier(ProfileData())
    assert tier == "FULL"
