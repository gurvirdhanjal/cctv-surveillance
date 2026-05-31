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
        last_seen_ms=old_ms,
        camera_id=2,
    )
    evicted = engine.evict_stale()  # no now_ms arg — should use current time
    assert evicted == 1


# ---------------------------------------------------------------------------
# assign_and_identify: cross-camera facial recognition anchoring
# ---------------------------------------------------------------------------

def test_assign_and_identify_returns_person_id_when_face_matches() -> None:
    """Known employee identified on entry-gate camera gets person_id attached."""
    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = 7   # employee #7
    engine = IdentityEngine(reid_service=reid)
    emb = _unit_vec(seed=0)

    gid, pid = engine.assign_and_identify(camera_id=1, local_track_id=1, embedding=emb)
    assert pid == 7
    assert engine._registry[(1, 1)].person_id == 7


def test_assign_and_identify_returns_none_for_unknown_person() -> None:
    """Unknown visitor: FAISS finds no match, person_id stays None."""
    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = None
    engine = IdentityEngine(reid_service=reid)
    emb = _unit_vec(seed=0)

    gid, pid = engine.assign_and_identify(camera_id=1, local_track_id=1, embedding=emb)
    assert pid is None
    assert engine._registry[(1, 1)].person_id is None


def test_assign_and_identify_anchors_person_id_across_cameras() -> None:
    """Person identified on cam1 (entry gate) is auto-identified on cam2 (floor) via gid."""
    reid = MagicMock(spec=ReIdService)
    # Entry gate cam1: FAISS recognises employee #5
    reid.identify.return_value = 5
    engine = IdentityEngine(reid_service=reid)

    face_emb = _unit_vec(seed=0)
    # Nearly identical embedding — triggers cross-camera gallery match
    arr = np.array(face_emb, dtype=np.float32)
    arr += np.random.default_rng(99).standard_normal(512).astype(np.float32) * 0.001
    arr /= np.linalg.norm(arr)
    near_emb = tuple(float(x) for x in arr)

    # Entry gate: identified as employee #5
    gid1, pid1 = engine.assign_and_identify(camera_id=1, local_track_id=1, embedding=face_emb)
    assert pid1 == 5

    # Floor camera: FAISS won't run (no embedding passed), but person_id inherited via gid
    reid.identify.return_value = None   # floor cam has no frontal face
    gid2, pid2 = engine.assign_and_identify(camera_id=2, local_track_id=1, embedding=near_emb)
    assert gid1 == gid2            # same person
    assert pid2 == 5               # identity inherited across cameras


def test_assign_and_identify_no_face_no_identification() -> None:
    """Body-only tracklet (no face): person_id stays None unless anchored from elsewhere."""
    engine = _make_engine()
    body_emb = _unit_vec(seed=10)

    gid, pid = engine.assign_and_identify(
        camera_id=1, local_track_id=1, embedding=None, body_embedding=body_emb
    )
    assert pid is None


def test_get_person_id_returns_resolved_value() -> None:
    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = 12
    engine = IdentityEngine(reid_service=reid)

    engine.assign_and_identify(camera_id=3, local_track_id=5, embedding=_unit_vec(seed=3))
    assert engine.get_person_id(camera_id=3, local_track_id=5) == 12


def test_get_person_id_returns_none_for_unknown_track() -> None:
    engine = _make_engine()
    assert engine.get_person_id(camera_id=99, local_track_id=99) is None
