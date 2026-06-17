"""Tests for IntrusionDetector."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from vms.anomaly.base import DetectorContext, Severity, ZoneLookup
from vms.anomaly.detectors.intrusion import IntrusionDetector
from vms.inference.messages import DetectionFrame


def _zone(
    zid: int,
    allowed: list[dict[str, object]] | None,
    restricted: bool = True,
) -> ZoneLookup:
    return ZoneLookup(
        zone_id=zid,
        name=f"Z{zid}",
        is_restricted=restricted,
        max_capacity=None,
        allowed_hours=json.dumps(allowed) if allowed is not None else None,
        loiter_threshold_s=180,
        polygon_json=None,
    )


def _ctx(
    track_zones: dict[uuid.UUID, int], zones: dict[int, ZoneLookup], when: datetime
) -> DetectorContext:
    # Treat naive `when` as UTC (our codebase convention) to get correct epoch ms
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


def test_fires_outside_allowed_hours() -> None:
    det = IntrusionDetector({})
    gid = uuid.uuid4()
    z = _zone(5, [{"days": [1, 2, 3, 4, 5], "start": "08:00", "end": "18:00"}])
    when = datetime(2026, 5, 16, 22, 30)  # Saturday 22:30
    ev = det.evaluate(_ctx({gid: 5}, {5: z}, when))
    assert ev is not None
    assert ev.severity is Severity.CRITICAL
    assert ev.zone_id == 5


def test_does_not_fire_inside_allowed_hours() -> None:
    det = IntrusionDetector({})
    gid = uuid.uuid4()
    z = _zone(5, [{"days": [1, 2, 3, 4, 5], "start": "08:00", "end": "18:00"}])
    when = datetime(2026, 5, 18, 10, 30)  # Monday 10:30
    assert det.evaluate(_ctx({gid: 5}, {5: z}, when)) is None


def test_fires_always_when_no_allowed_hours() -> None:
    det = IntrusionDetector({})
    gid = uuid.uuid4()
    z = _zone(5, None)
    when = datetime(2026, 5, 18, 10, 30)
    assert det.evaluate(_ctx({gid: 5}, {5: z}, when)) is not None


def test_skips_unrestricted_zones() -> None:
    det = IntrusionDetector({})
    gid = uuid.uuid4()
    z = _zone(5, None, restricted=False)
    when = datetime(2026, 5, 18, 10, 30)
    assert det.evaluate(_ctx({gid: 5}, {5: z}, when)) is None


def test_should_run_short_circuits_when_no_active_tracks() -> None:
    det = IntrusionDetector({})
    when = datetime(2026, 5, 18, 10, 30)
    assert det.should_run(_ctx({}, {}, when)) is False


def test_malformed_allowed_hours_treated_as_always_restricted() -> None:
    det = IntrusionDetector({})
    gid = uuid.uuid4()
    z = ZoneLookup(
        zone_id=5,
        name="Z5",
        is_restricted=True,
        max_capacity=None,
        allowed_hours="not valid {{",
        loiter_threshold_s=180,
        polygon_json=None,
    )
    when = datetime(2026, 5, 18, 10, 30)
    assert det.evaluate(_ctx({gid: 5}, {5: z}, when)) is not None
