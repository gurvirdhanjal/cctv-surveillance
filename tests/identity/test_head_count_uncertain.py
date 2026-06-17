"""uncertain_count on HeadCountSnapshot (Phase 3 crosscam-accuracy, Task 4)."""

import uuid
from datetime import datetime, timezone

from vms.identity.head_count import HeadCountAggregator


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_unknowns_in_overlapping_zone_increment_uncertain_count() -> None:
    # Cameras 1 and 2 overlap on zone 9; two unknowns there might be one person.
    agg = HeadCountAggregator(overlapping_zones={9})
    agg.on_tracking_event(uuid.uuid4(), zone_id=9, ts=_now(), person_id=None)
    agg.on_tracking_event(uuid.uuid4(), zone_id=9, ts=_now(), person_id=None)
    snap = agg.snapshot()
    assert snap.by_zone[9] == 2  # counted conservatively (both)
    assert snap.uncertain_count == 2


def test_identified_persons_never_uncertain() -> None:
    agg = HeadCountAggregator(overlapping_zones={9})
    agg.on_tracking_event(uuid.uuid4(), zone_id=9, ts=_now(), person_id=1)
    assert agg.snapshot().uncertain_count == 0


def test_uncertain_count_zero_without_overlap_declared() -> None:
    agg = HeadCountAggregator()  # no overlapping zones
    agg.on_tracking_event(uuid.uuid4(), zone_id=9, ts=_now(), person_id=None)
    snap = agg.snapshot()
    assert snap.uncertain_count == 0
    assert "uncertain_count" in snap.to_dict()
