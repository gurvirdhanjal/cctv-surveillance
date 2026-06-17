"""Headcount dedup by person_id (Phase 3 crosscam-accuracy plan, Task 2)."""

import uuid
from datetime import datetime, timezone

from vms.identity.head_count import HeadCountAggregator


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_same_person_two_cameras_same_zone_counts_once() -> None:
    agg = HeadCountAggregator()
    gid_cam1, gid_cam2 = uuid.uuid4(), uuid.uuid4()
    agg.on_tracking_event(gid_cam1, zone_id=7, ts=_now(), person_id=42)
    agg.on_tracking_event(gid_cam2, zone_id=7, ts=_now(), person_id=42)
    snap = agg.snapshot()
    assert snap.by_zone[7] == 1
    assert snap.plant_total == 1


def test_two_unknowns_same_zone_count_separately() -> None:
    agg = HeadCountAggregator()
    a, b = uuid.uuid4(), uuid.uuid4()
    agg.on_tracking_event(a, zone_id=3, ts=_now(), person_id=None)
    agg.on_tracking_event(b, zone_id=3, ts=_now(), person_id=None)
    assert agg.snapshot().by_zone[3] == 2


def test_identified_person_dedups_across_distinct_zones() -> None:
    # Identified person moves zones: latest zone wins, never double-counted plant-wide.
    agg = HeadCountAggregator()
    g1, g2 = uuid.uuid4(), uuid.uuid4()
    agg.on_tracking_event(g1, zone_id=1, ts=_now(), person_id=99)
    agg.on_tracking_event(g2, zone_id=2, ts=_now(), person_id=99)
    snap = agg.snapshot()
    assert snap.plant_total == 1
    assert snap.by_zone == {2: 1}


def test_person_id_none_keeps_legacy_gid_behaviour() -> None:
    agg = HeadCountAggregator()
    g = uuid.uuid4()
    agg.on_tracking_event(g, zone_id=5, ts=_now())  # no person_id kwarg -> defaults None
    assert agg.snapshot().by_zone[5] == 1
    agg.on_tracking_event(g, zone_id=None, ts=_now())
    assert agg.snapshot().by_zone == {}
