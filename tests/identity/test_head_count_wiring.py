"""Pipeline passes person_id into the head counter (Phase 3 crosscam-accuracy, Task 3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from vms.identity.head_count import HeadCountAggregator


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_call_site_forwards_person_id_to_aggregator() -> None:
    # Contract test: when the orchestrator resolves an identity, the aggregator receives it.
    agg = HeadCountAggregator()
    gid = uuid.uuid4()
    ts = _now()
    # Simulate the orchestrator forwarding the resolved person_id.
    agg.on_tracking_event(gid, zone_id=4, ts=ts, person_id=7)
    assert agg.snapshot().by_zone[4] == 1
    # A second camera's gid for the same person_id must not inflate the count.
    agg.on_tracking_event(uuid.uuid4(), zone_id=4, ts=ts, person_id=7)
    assert agg.snapshot().by_zone[4] == 1


@pytest.mark.asyncio
async def test_orchestrator_feeds_person_id_from_identity_engine() -> None:
    """Orchestrator passes resolved person_id into head counter on each frame."""
    import uuid as _uuid

    # We don't need a real DB session for this test; we only need the aggregator to dedup.
    # Use patch to inject identity._registry with two gids sharing person_id=99.
    from unittest.mock import MagicMock

    from fakeredis.aioredis import FakeRedis
    from sqlalchemy.orm import Session

    # Import DB session fixture manually via conftest pattern (minimal inline approach).
    from tests.conftest import _create_schema  # noqa: F401 — ensure tables exist
    from vms.anomaly.orchestrator import AnomalyOrchestrator
    from vms.inference.messages import DetectionFrame

    gid1 = _uuid.uuid4()
    gid2 = _uuid.uuid4()

    # Build a minimal fake registry entry
    class _FakeEntry:
        def __init__(self, gid: uuid.UUID, pid: int | None) -> None:
            self.global_track_id = gid
            self.person_id = pid

    fake_identity = MagicMock()
    fake_identity._registry = {
        (1, 1): _FakeEntry(gid1, 99),
        (2, 1): _FakeEntry(gid2, 99),
    }

    agg = HeadCountAggregator()
    client = FakeRedis(decode_responses=True)

    orch = AnomalyOrchestrator(
        redis_client=client,
        session_factory=MagicMock(return_value=MagicMock(spec=Session)),
        detectors={},
    )
    orch._identity = fake_identity
    orch._head_count = agg

    # Simulate both cameras seeing gid1 and gid2 in zone 9.
    with (
        patch.object(orch, "_active_track_zones", return_value={gid1: 9, gid2: 9}),
        patch.object(orch, "_zone_tracker", new=MagicMock()),
        patch.object(orch, "_zone_lookup", return_value={}),
    ):
        ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        frame = DetectionFrame(
            camera_id=1,
            seq_id=1,
            timestamp_ms=ts_ms,
            tracklets=(),
            face_embeddings=(),
        )
        await orch.process_frame(frame)

    snap = agg.snapshot()
    assert (
        snap.plant_total == 1
    ), f"Expected 1 (same person_id=99 on two cameras), got {snap.plant_total}"
    assert snap.by_zone.get(9) == 1
