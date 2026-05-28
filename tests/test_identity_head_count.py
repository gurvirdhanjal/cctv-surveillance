"""Tests for HeadCountAggregator."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from vms.identity.head_count import HeadCountAggregator


def test_on_event_increments_zone_count() -> None:
    agg = HeadCountAggregator()
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    agg.on_tracking_event(gid, zone_id=3, ts=now)
    snap = agg.snapshot()
    assert snap.by_zone == {3: 1}
    assert snap.plant_total == 1


def test_same_gid_moves_between_zones() -> None:
    agg = HeadCountAggregator()
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    agg.on_tracking_event(gid, zone_id=3, ts=now)
    agg.on_tracking_event(gid, zone_id=5, ts=now + timedelta(seconds=1))
    snap = agg.snapshot()
    assert snap.by_zone.get(3, 0) == 0
    assert snap.by_zone[5] == 1


def test_evict_stale_removes_old_tracks() -> None:
    agg = HeadCountAggregator()
    gid_old = uuid.uuid4()
    gid_new = uuid.uuid4()
    base = datetime(2026, 5, 15, 12, 0, 0)
    agg.on_tracking_event(gid_old, zone_id=3, ts=base)
    agg.on_tracking_event(gid_new, zone_id=3, ts=base + timedelta(seconds=20))
    agg.evict_stale(now=base + timedelta(seconds=35), ttl_s=30)
    snap = agg.snapshot()
    assert snap.by_zone[3] == 1


def test_snapshot_serialisation() -> None:
    agg = HeadCountAggregator()
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    agg.on_tracking_event(gid, zone_id=3, ts=now)
    snap = agg.snapshot()
    d = snap.to_dict()
    assert d["plant_total"] == 1
    assert d["by_zone"] == {3: 1}
    assert "ts" in d


def test_zone_none_is_ignored() -> None:
    agg = HeadCountAggregator()
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    agg.on_tracking_event(gid, zone_id=None, ts=now)
    assert agg.snapshot().plant_total == 0
