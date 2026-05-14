from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from vms.identity.engine import IdentityEngine
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
