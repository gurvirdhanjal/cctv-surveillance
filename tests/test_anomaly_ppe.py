"""Tests for PPEDetector."""

from __future__ import annotations

from datetime import datetime, timezone

from vms.anomaly.base import DetectorContext
from vms.anomaly.detectors.ppe import PPEDetector
from vms.inference.messages import DetectionFrame, Tracklet


def _make_ctx(
    tracklets: tuple[Tracklet, ...] = (),
    violence_score: float | None = None,
    camera_id: int = 1,
) -> DetectorContext:
    frame = DetectionFrame(
        camera_id=camera_id,
        seq_id=0,
        timestamp_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        tracklets=tracklets,
        face_embeddings=(),
        violence_score=violence_score,
    )
    return DetectorContext(
        frame=frame,
        zone_lookup={},
        active_track_zones={},
        head_count={},
        violence_score=violence_score,
    )


def _make_detector(**kwargs: object) -> PPEDetector:
    return PPEDetector(dict(kwargs))


# ------------------------------------------------------------------
# should_run
# ------------------------------------------------------------------


def test_ppe_detector_should_run_false_when_no_tracklets() -> None:
    det = _make_detector()
    ctx = _make_ctx(tracklets=())
    assert det.should_run(ctx) is False


def test_ppe_detector_should_run_false_when_scores_absent() -> None:
    """Tracklets present but PPE model never ran — ppe fields are None."""
    t = Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 50, 100), confidence=0.9)
    ctx = _make_ctx(tracklets=(t,))
    assert _make_detector().should_run(ctx) is False


def test_ppe_detector_should_run_true_when_any_score_present() -> None:
    t = Tracklet(
        local_track_id=1,
        camera_id=1,
        bbox=(0, 0, 50, 100),
        confidence=0.9,
        ppe_helmet_conf=0.8,
        ppe_vest_conf=0.9,
    )
    ctx = _make_ctx(tracklets=(t,))
    assert _make_detector().should_run(ctx) is True


# ------------------------------------------------------------------
# evaluate — compliance
# ------------------------------------------------------------------


def test_ppe_detector_evaluate_returns_none_when_compliant() -> None:
    """Both scores above threshold — no violation."""
    t = Tracklet(
        local_track_id=1,
        camera_id=1,
        bbox=(0, 0, 50, 100),
        confidence=0.9,
        ppe_helmet_conf=0.9,
        ppe_vest_conf=0.8,
    )
    det = _make_detector(helmet_threshold=0.5, vest_threshold=0.5)
    ctx = _make_ctx(tracklets=(t,))
    assert det.evaluate(ctx) is None


def test_ppe_detector_evaluate_returns_event_when_helmet_missing() -> None:
    """Helmet confidence below threshold → PPE_VIOLATION event."""
    t = Tracklet(
        local_track_id=5,
        camera_id=2,
        bbox=(10, 20, 60, 120),
        confidence=0.85,
        ppe_helmet_conf=0.2,  # below 0.5 threshold → violation
        ppe_vest_conf=0.9,  # compliant
    )
    det = _make_detector(helmet_threshold=0.5, vest_threshold=0.5)
    ctx = _make_ctx(tracklets=(t,), camera_id=2)
    event = det.evaluate(ctx)
    assert event is not None
    assert event.alert_type == "PPE_VIOLATION"
    assert event.camera_id == 2
    assert event.payload["local_track_id"] == 5
    assert "helmet" in event.payload["violations"]
    assert "vest" not in event.payload["violations"]
    assert abs(event.payload["ppe_helmet_conf"] - 0.2) < 1e-6


def test_ppe_detector_evaluate_returns_event_when_vest_missing() -> None:
    t = Tracklet(
        local_track_id=3,
        camera_id=1,
        bbox=(0, 0, 50, 100),
        confidence=0.9,
        ppe_helmet_conf=0.95,
        ppe_vest_conf=0.1,  # below threshold
    )
    det = _make_detector()
    event = det.evaluate(_make_ctx(tracklets=(t,)))
    assert event is not None
    assert "vest" in event.payload["violations"]
    assert "helmet" not in event.payload["violations"]


def test_ppe_detector_evaluate_returns_event_when_both_missing() -> None:
    t = Tracklet(
        local_track_id=7,
        camera_id=1,
        bbox=(0, 0, 50, 100),
        confidence=0.9,
        ppe_helmet_conf=0.1,
        ppe_vest_conf=0.1,
    )
    event = _make_detector().evaluate(_make_ctx(tracklets=(t,)))
    assert event is not None
    assert "helmet" in event.payload["violations"]
    assert "vest" in event.payload["violations"]


def test_ppe_detector_evaluate_returns_none_when_ppe_scores_absent() -> None:
    """should_run guards against this, but evaluate must also be safe."""
    t = Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 50, 100), confidence=0.9)
    assert _make_detector().evaluate(_make_ctx(tracklets=(t,))) is None


def test_ppe_detector_dedup_key_is_per_tracklet() -> None:
    t = Tracklet(
        local_track_id=42,
        camera_id=3,
        bbox=(0, 0, 50, 100),
        confidence=0.9,
        ppe_helmet_conf=0.1,
        ppe_vest_conf=0.9,
    )
    event = _make_detector().evaluate(_make_ctx(tracklets=(t,), camera_id=3))
    assert event is not None
    assert event.dedup_key == "PPE_VIOLATION:cam=3:track=42"


def test_ppe_detector_returns_first_violation_in_frame() -> None:
    """evaluate() returns a single event — the first violating tracklet."""
    t1 = Tracklet(
        local_track_id=1,
        camera_id=1,
        bbox=(0, 0, 50, 100),
        confidence=0.9,
        ppe_helmet_conf=0.95,
        ppe_vest_conf=0.95,  # compliant
    )
    t2 = Tracklet(
        local_track_id=2,
        camera_id=1,
        bbox=(100, 0, 150, 100),
        confidence=0.9,
        ppe_helmet_conf=0.1,
        ppe_vest_conf=0.9,  # violation
    )
    event = _make_detector().evaluate(_make_ctx(tracklets=(t1, t2)))
    assert event is not None
    assert event.payload["local_track_id"] == 2


# ------------------------------------------------------------------
# fsm_config
# ------------------------------------------------------------------


def test_ppe_detector_fsm_config() -> None:
    cfg = _make_detector().fsm_config()
    assert cfg.sustain_ms == 3_000
    assert cfg.cooldown_ms == 120_000
    assert cfg.dedup_window_ms == 120_000


# ------------------------------------------------------------------
# Gloves + mask support
# ------------------------------------------------------------------


def test_ppe_detector_helmet_violation_detected() -> None:
    t = Tracklet(
        local_track_id=1,
        camera_id=1,
        bbox=(0, 0, 50, 100),
        confidence=0.9,
        ppe_helmet_conf=0.1,
        ppe_vest_conf=0.9,
    )
    event = _make_detector().evaluate(_make_ctx(tracklets=(t,)))
    assert event is not None
    assert "helmet" in event.payload["violations"]


def test_ppe_detector_vest_violation_detected() -> None:
    t = Tracklet(
        local_track_id=2,
        camera_id=1,
        bbox=(0, 0, 50, 100),
        confidence=0.9,
        ppe_helmet_conf=0.9,
        ppe_vest_conf=0.05,
    )
    event = _make_detector().evaluate(_make_ctx(tracklets=(t,)))
    assert event is not None
    assert "vest" in event.payload["violations"]


def test_ppe_detector_gloves_skipped_when_not_configured() -> None:
    """Gloves checking is opt-in (check_gloves=False by default)."""
    t = Tracklet(
        local_track_id=3,
        camera_id=1,
        bbox=(0, 0, 50, 100),
        confidence=0.9,
        ppe_helmet_conf=0.9,
        ppe_vest_conf=0.9,
        ppe_gloves_conf=0.0,  # would be a violation if checked
        ppe_mask_conf=0.9,
    )
    det = _make_detector()  # check_gloves defaults False
    assert det.evaluate(_make_ctx(tracklets=(t,))) is None


def test_ppe_detector_gloves_violation_when_enabled() -> None:
    t = Tracklet(
        local_track_id=4,
        camera_id=1,
        bbox=(0, 0, 50, 100),
        confidence=0.9,
        ppe_helmet_conf=0.9,
        ppe_vest_conf=0.9,
        ppe_gloves_conf=0.1,
        ppe_mask_conf=0.9,
    )
    det = _make_detector(check_gloves=True)
    event = det.evaluate(_make_ctx(tracklets=(t,)))
    assert event is not None
    assert "gloves" in event.payload["violations"]


def test_ppe_detector_mask_violation_when_enabled() -> None:
    t = Tracklet(
        local_track_id=5,
        camera_id=1,
        bbox=(0, 0, 50, 100),
        confidence=0.9,
        ppe_helmet_conf=0.9,
        ppe_vest_conf=0.9,
        ppe_gloves_conf=0.9,
        ppe_mask_conf=0.05,
    )
    det = _make_detector(check_mask=True)
    event = det.evaluate(_make_ctx(tracklets=(t,)))
    assert event is not None
    assert "mask" in event.payload["violations"]


def test_ppe_detector_should_run_false_when_no_scores_any_field() -> None:
    """should_run is False when all 4 PPE fields are None."""
    t = Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 50, 100), confidence=0.9)
    assert _make_detector().should_run(_make_ctx(tracklets=(t,))) is False


def test_ppe_detector_should_run_true_when_gloves_score_present() -> None:
    t = Tracklet(
        local_track_id=1,
        camera_id=1,
        bbox=(0, 0, 50, 100),
        confidence=0.9,
        ppe_gloves_conf=0.7,
    )
    assert _make_detector().should_run(_make_ctx(tracklets=(t,))) is True
