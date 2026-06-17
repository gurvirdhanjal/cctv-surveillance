"""Tests for ViolenceDetector."""

from __future__ import annotations

from vms.anomaly.base import DetectorContext, Severity
from vms.anomaly.detectors.violence import ViolenceDetector
from vms.inference.messages import DetectionFrame


def _ctx(score: float | None) -> DetectorContext:
    frame = DetectionFrame(
        camera_id=1,
        seq_id=1,
        timestamp_ms=1_700_000_000_000,
        tracklets=(),
        face_embeddings=(),
        violence_score=score,
    )
    return DetectorContext(
        frame=frame,
        zone_lookup={},
        active_track_zones={},
        head_count={},
        violence_score=score,
    )


def test_fires_when_score_above_threshold() -> None:
    det = ViolenceDetector({})
    ev = det.evaluate(_ctx(0.81))
    assert ev is not None
    assert ev.severity is Severity.CRITICAL
    assert ev.payload["score"] == 0.81


def test_does_not_fire_below_threshold() -> None:
    det = ViolenceDetector({})
    assert det.evaluate(_ctx(0.40)) is None


def test_should_run_skips_when_score_is_none() -> None:
    det = ViolenceDetector({})
    assert det.should_run(_ctx(None)) is False


def test_config_threshold_overrides_default() -> None:
    det = ViolenceDetector({"threshold": 0.90})
    assert det.evaluate(_ctx(0.85)) is None
