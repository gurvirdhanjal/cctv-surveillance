"""Tests for UnknownPersonDetector."""

from __future__ import annotations

import uuid

from vms.anomaly.base import DetectorContext, Severity
from vms.anomaly.detectors.unknown_person import UnknownPersonDetector
from vms.inference.messages import DetectionFrame, Tracklet


def _ctx_with_tracklet(
    *,
    person_id_known: bool,
    zone_id: int | None = 1,
) -> tuple[DetectorContext, uuid.UUID]:
    gid = uuid.uuid4()
    tl = Tracklet(local_track_id=1, camera_id=4, bbox=(0, 0, 10, 10), confidence=0.9)
    frame = DetectionFrame(
        camera_id=4,
        seq_id=1,
        timestamp_ms=1_700_000_000_000,
        tracklets=(tl,),
        face_embeddings=(),
    )
    track_zones = {gid: zone_id} if zone_id is not None else {}
    ctx = DetectorContext(
        frame=frame,
        zone_lookup={},
        active_track_zones=track_zones,
        head_count={},
        violence_score=None,
    )
    return ctx, gid


def test_fires_when_tracklet_has_no_person_id() -> None:
    det = UnknownPersonDetector({})
    ctx, gid = _ctx_with_tracklet(person_id_known=False)
    det._gid_for_tracklet = lambda tl, ctx: gid  # type: ignore[method-assign]
    det._person_id_for = lambda gid, ctx: None  # type: ignore[method-assign]
    assert det.should_run(ctx) is True
    ev = det.evaluate(ctx)
    assert ev is not None
    assert ev.alert_type == "UNKNOWN_PERSON"
    assert ev.severity is Severity.HIGH
    assert ev.dedup_key.startswith("UNKNOWN_PERSON:")
    assert ev.global_track_id == gid


def test_does_not_fire_when_person_known() -> None:
    det = UnknownPersonDetector({})
    ctx, gid = _ctx_with_tracklet(person_id_known=True)
    det._gid_for_tracklet = lambda tl, ctx: gid  # type: ignore[method-assign]
    det._person_id_for = lambda gid, ctx: 7  # type: ignore[method-assign]
    assert det.evaluate(ctx) is None


def test_should_run_short_circuits_when_no_tracklets() -> None:
    det = UnknownPersonDetector({})
    frame = DetectionFrame(
        camera_id=4,
        seq_id=1,
        timestamp_ms=1_700_000_000_000,
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
    assert det.should_run(ctx) is False
