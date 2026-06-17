"""Tests for LoiteringDetector."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from vms.anomaly.base import DetectorContext, ZoneLookup
from vms.anomaly.detectors.loitering import LoiteringDetector
from vms.inference.messages import DetectionFrame


def _zone(zid: int, thresh: int = 180) -> ZoneLookup:
    return ZoneLookup(
        zone_id=zid,
        name=f"Z{zid}",
        is_restricted=False,
        max_capacity=None,
        allowed_hours=None,
        loiter_threshold_s=thresh,
        polygon_json=None,
    )


def _ctx(
    track_zones: dict[uuid.UUID, int], zones: dict[int, ZoneLookup], when: datetime
) -> DetectorContext:
    ts_ms = int(when.replace(tzinfo=timezone.utc).timestamp() * 1000)
    frame = DetectionFrame(
        camera_id=1,
        seq_id=1,
        timestamp_ms=ts_ms,
        tracklets=(),
        face_embeddings=(),
    )
    return DetectorContext(
        frame=frame,
        zone_lookup=zones,
        active_track_zones=track_zones,
        head_count={},
        violence_score=None,
    )


def test_fires_when_dwell_exceeds_threshold() -> None:
    det = LoiteringDetector({})
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    entered = now - timedelta(seconds=200)
    det._entered_at = lambda gid, zone_id, ctx: entered  # type: ignore[method-assign]
    ev = det.evaluate(_ctx({gid: 3}, {3: _zone(3, 180)}, now))
    assert ev is not None
    assert ev.alert_type == "LOITERING"
    assert ev.payload["dwell_s"] >= 200


def test_does_not_fire_under_threshold() -> None:
    det = LoiteringDetector({})
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    entered = now - timedelta(seconds=100)
    det._entered_at = lambda gid, zone_id, ctx: entered  # type: ignore[method-assign]
    assert det.evaluate(_ctx({gid: 3}, {3: _zone(3, 180)}, now)) is None


def test_skips_when_no_entered_at() -> None:
    det = LoiteringDetector({})
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    det._entered_at = lambda gid, zone_id, ctx: None  # type: ignore[method-assign]
    assert det.evaluate(_ctx({gid: 3}, {3: _zone(3, 180)}, now)) is None
