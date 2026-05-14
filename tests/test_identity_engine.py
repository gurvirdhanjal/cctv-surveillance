from __future__ import annotations

import time as _time
import uuid
from unittest.mock import MagicMock

import numpy as np

from vms.identity.engine import IdentityEngine, _TrackletEntry
from vms.identity.reid import ReIdService


def _unit_vec(seed: int = 0) -> tuple[float, ...]:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(512).astype(np.float32)
    v /= np.linalg.norm(v)
    return tuple(float(x) for x in v)


def _make_engine() -> IdentityEngine:
    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = None
    return IdentityEngine(reid_service=reid)


def test_engine_same_camera_tracklet_gets_same_global_id() -> None:
    engine = _make_engine()
    gid1 = engine.assign_global_track_id(camera_id=1, local_track_id=5, embedding=None)
    gid2 = engine.assign_global_track_id(camera_id=1, local_track_id=5, embedding=None)
    assert gid1 == gid2


def test_engine_different_camera_unknown_embedding_gets_new_global_id() -> None:
    engine = _make_engine()
    gid1 = engine.assign_global_track_id(camera_id=1, local_track_id=5, embedding=None)
    gid2 = engine.assign_global_track_id(camera_id=2, local_track_id=5, embedding=None)
    assert gid1 != gid2


def test_engine_cross_camera_match_on_similar_embedding() -> None:
    engine = _make_engine()
    v = _unit_vec(seed=0)
    gid1 = engine.assign_global_track_id(camera_id=1, local_track_id=1, embedding=v)

    # Nearly identical embedding from camera 2 -> should inherit gid1
    arr = np.array(v, dtype=np.float32)
    arr += np.random.default_rng(1).standard_normal(512).astype(np.float32) * 0.001
    arr /= np.linalg.norm(arr)
    v2 = tuple(float(x) for x in arr)
    gid2 = engine.assign_global_track_id(camera_id=2, local_track_id=1, embedding=v2)

    assert gid1 == gid2


def test_engine_identify_person_delegates_to_reid_service() -> None:
    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = 42
    engine = IdentityEngine(reid_service=reid)
    emb = _unit_vec(seed=1)
    pid = engine.identify_person(emb)
    assert pid == 42
    reid.identify.assert_called_once()


def test_engine_identify_person_returns_none_for_empty_embedding() -> None:
    engine = _make_engine()
    assert engine.identify_person(()) is None


def test_evict_stale_removes_old_entries() -> None:
    engine = _make_engine()
    now_ms = int(_time.time() * 1000)
    old_ms = now_ms - 400_000  # 400s ago > 300_000ms threshold

    engine._registry[(1, 42)] = _TrackletEntry(
        global_track_id=uuid.uuid4(),
        person_id=None,
        last_embedding=None,
        last_seen_ms=old_ms,
        camera_id=1,
    )
    assert len(engine._registry) == 1
    evicted = engine.evict_stale(now_ms=now_ms)
    assert evicted == 1
    assert len(engine._registry) == 0


def test_evict_stale_keeps_fresh_entries() -> None:
    engine = _make_engine()
    now_ms = int(_time.time() * 1000)
    recent_ms = now_ms - 10_000  # 10s ago

    engine._registry[(1, 99)] = _TrackletEntry(
        global_track_id=uuid.uuid4(),
        person_id=None,
        last_embedding=None,
        last_seen_ms=recent_ms,
        camera_id=1,
    )
    evicted = engine.evict_stale(now_ms=now_ms)
    assert evicted == 0
    assert len(engine._registry) == 1


def test_evict_stale_uses_current_time_when_no_arg() -> None:
    engine = _make_engine()
    # entry last seen 10 minutes ago — definitely stale
    old_ms = int(_time.time() * 1000) - 600_000

    engine._registry[(2, 1)] = _TrackletEntry(
        global_track_id=uuid.uuid4(),
        person_id=None,
        last_embedding=None,
        last_seen_ms=old_ms,
        camera_id=2,
    )
    evicted = engine.evict_stale()  # no now_ms arg — should use current time
    assert evicted == 1
