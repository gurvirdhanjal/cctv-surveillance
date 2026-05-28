"""Tests for CrowdDensityDetector."""

from __future__ import annotations

from vms.anomaly.base import DetectorContext, Severity, ZoneLookup
from vms.anomaly.detectors.crowd_density import CrowdDensityDetector
from vms.inference.messages import DetectionFrame


def _zone(zid: int, cap: int | None) -> ZoneLookup:
    return ZoneLookup(
        zone_id=zid,
        name=f"Z{zid}",
        is_restricted=False,
        max_capacity=cap,
        allowed_hours=None,
        loiter_threshold_s=180,
        polygon_json=None,
    )


def _ctx(head_count: dict[int, int], zones: dict[int, ZoneLookup]) -> DetectorContext:
    frame = DetectionFrame(
        camera_id=1,
        seq_id=1,
        timestamp_ms=1_700_000_000_000,
        tracklets=(),
        face_embeddings=(),
    )
    return DetectorContext(
        frame=frame,
        zone_lookup=zones,
        active_track_zones={},
        head_count=head_count,
        violence_score=None,
    )


def test_fires_when_count_exceeds_max_capacity() -> None:
    det = CrowdDensityDetector({})
    ctx = _ctx({3: 12}, {3: _zone(3, 10)})
    ev = det.evaluate(ctx)
    assert ev is not None
    assert ev.alert_type == "CROWD_DENSITY"
    assert ev.severity is Severity.MEDIUM
    assert ev.zone_id == 3
    assert ev.payload["count"] == 12
    assert ev.payload["max_capacity"] == 10
    assert ev.dedup_key == "CROWD_DENSITY:zone=3"


def test_does_not_fire_at_threshold() -> None:
    det = CrowdDensityDetector({})
    ctx = _ctx({3: 10}, {3: _zone(3, 10)})
    assert det.evaluate(ctx) is None


def test_skips_zones_with_no_max_capacity() -> None:
    det = CrowdDensityDetector({})
    ctx = _ctx({3: 100}, {3: _zone(3, None)})
    assert det.evaluate(ctx) is None


def test_should_run_skips_when_head_count_empty() -> None:
    det = CrowdDensityDetector({})
    ctx = _ctx({}, {})
    assert det.should_run(ctx) is False
