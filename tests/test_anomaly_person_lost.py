"""Tests for PersonLostDetector."""

from __future__ import annotations

import time
import uuid

from vms.anomaly.base import DetectorContext
from vms.anomaly.detectors.person_lost import PersonLostDetector
from vms.inference.messages import DetectionFrame


def _ctx(last_seen: dict[uuid.UUID, int]) -> DetectorContext:
    frame = DetectionFrame(
        camera_id=0,
        seq_id=1,
        timestamp_ms=int(time.time() * 1000),
        tracklets=(),
        face_embeddings=(),
    )
    return DetectorContext(
        frame=frame,
        zone_lookup={},
        active_track_zones={g: 1 for g in last_seen},
        head_count={},
        violence_score=None,
    )


def test_fires_for_track_unseen_longer_than_threshold() -> None:
    det = PersonLostDetector({"lost_after_s": 30})
    gid = uuid.uuid4()
    now_ms = int(time.time() * 1000)
    det._registry_last_seen = lambda ctx: {gid: now_ms - 31_000}  # type: ignore[method-assign]
    ev = det.evaluate(_ctx({gid: now_ms - 31_000}))
    assert ev is not None
    assert ev.alert_type == "PERSON_LOST"
    assert ev.global_track_id == gid


def test_does_not_fire_for_fresh_track() -> None:
    det = PersonLostDetector({"lost_after_s": 30})
    gid = uuid.uuid4()
    now_ms = int(time.time() * 1000)
    det._registry_last_seen = lambda ctx: {gid: now_ms - 5_000}  # type: ignore[method-assign]
    assert det.evaluate(_ctx({gid: now_ms - 5_000})) is None


def test_should_run_always_true() -> None:
    det = PersonLostDetector({})
    frame = DetectionFrame(
        camera_id=0,
        seq_id=1,
        timestamp_ms=1,
        tracklets=(),
        face_embeddings=(),
    )
    ctx = DetectorContext(
        frame=frame,
        zone_lookup={},
        active_track_zones={},
        head_count={},
        violence_score=None,
    )
    assert det.should_run(ctx) is True
