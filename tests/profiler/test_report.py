"""Tests for Site Readiness Report PDF generation."""

from __future__ import annotations

from vms.api.schemas import ProfileData
from vms.profiler.report import generate_readiness_report


def _make_cam_row(
    camera_id: int = 1,
    name: str = "Loading Bay",
    tier: str = "FULL",
    shutter: str = "rolling",
    tier_reason: str = ">=1080p AND fps>=12",
    profile_data: ProfileData | None = None,
) -> dict[str, object]:
    return {
        "camera_id": camera_id,
        "name": name,
        "capability_tier": tier,
        "shutter_type": shutter,
        "tier_reason": tier_reason,
        "profile_data": profile_data,
    }


def test_generate_report_returns_bytes() -> None:
    rows = [_make_cam_row()]
    pdf_bytes = generate_readiness_report(rows)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0


def test_generate_report_is_valid_pdf() -> None:
    rows = [_make_cam_row()]
    pdf_bytes = generate_readiness_report(rows)
    assert pdf_bytes[:4] == b"%PDF"


def test_generate_report_multiple_cameras() -> None:
    rows = [
        _make_cam_row(camera_id=1, name="Gate 1", tier="FULL"),
        _make_cam_row(camera_id=2, name="Gate 2", tier="MID"),
        _make_cam_row(camera_id=3, name="Warehouse", tier="LOW"),
    ]
    pdf_bytes = generate_readiness_report(rows)
    assert pdf_bytes[:4] == b"%PDF"


def test_generate_report_with_full_profile_data() -> None:
    pd = ProfileData(
        resolution_w=1920,
        resolution_h=1080,
        fps_measured=25.0,
        focus_score=55.0,
        suggested_tier="FULL",
        tier_reason=">=1080p AND fps>=12 AND focus>=30",
    )
    rows = [_make_cam_row(profile_data=pd)]
    pdf_bytes = generate_readiness_report(rows)
    assert pdf_bytes[:4] == b"%PDF"


def test_generate_report_empty_camera_list() -> None:
    pdf_bytes = generate_readiness_report([])
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
