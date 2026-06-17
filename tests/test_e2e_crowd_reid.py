"""E2E: cross-camera re-ID stability under crowd density.

20 persons across 4 cameras. All embeddings are noisy (simulates factory-
floor conditions: partial occlusion, angle variation, similar uniforms).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import numpy as np
import pytest

from vms.identity.engine import IdentityEngine
from vms.identity.reid import ReIdService


def _make_engine() -> IdentityEngine:
    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = None
    return IdentityEngine(reid_service=reid)


def _person_emb(person_id: int) -> np.ndarray:  # type: ignore[type-arg]
    v = np.random.default_rng(person_id * 100).standard_normal(512).astype(np.float32)
    v /= np.linalg.norm(v) + 1e-8
    return v


def _noisy(emb: np.ndarray, noise: float = 0.03, seed: int = 0) -> tuple[float, ...]:  # type: ignore[type-arg]
    v = emb + np.random.default_rng(seed).standard_normal(512).astype(np.float32) * noise
    v /= np.linalg.norm(v) + 1e-8
    return tuple(float(x) for x in v)


def _settings(**overrides: object) -> object:
    from vms.config import Settings

    defaults: dict[str, object] = dict(
        db_url="x",
        jwt_secret="x",
        reid_gallery_size=8,
        reid_confirm_after_sightings=3,
        reid_cross_cam_sim=0.65,
        reid_confirmed_sim=0.60,
        reid_margin=0.05,
        reid_stale_ms=300_000,
        reid_confirmed_stale_ms=600_000,
        reid_camera_topology_json="{}",
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


@pytest.mark.integration
def test_crowd_20_persons_4_cameras_stable_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """20 persons confirmed on cam0, then seen on cams 1-3 -- all get same global_track_id."""
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _settings())
    engine = _make_engine()
    n_persons, n_cameras = 20, 4
    person_embs = [_person_emb(p) for p in range(n_persons)]

    # Phase 1: confirm each person on camera 0 (4 sightings each)
    gids: dict[int, uuid.UUID] = {}
    for p in range(n_persons):
        for s in range(4):
            gid = engine.assign_global_track_id(
                camera_id=0,
                local_track_id=p,
                embedding=_noisy(person_embs[p], noise=0.02, seed=s),
            )
            gids[p] = gid

    for p in range(n_persons):
        assert engine._registry[(0, p)].confirmed, f"person {p} not confirmed"

    # Phase 2: each person appears on cameras 1-3 with noisy embeddings
    for cam in range(1, n_cameras):
        for p in range(n_persons):
            gid = engine.assign_global_track_id(
                camera_id=cam,
                local_track_id=p,
                embedding=_noisy(person_embs[p], noise=0.02, seed=cam * 100 + p),
            )
            assert gid == gids[p], f"person {p} on cam {cam}: expected {gids[p]}, got {gid}"


@pytest.mark.integration
def test_crowd_eviction_bounds_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """100 unconfirmed tracklets are all evicted after reid_stale_ms expires."""
    monkeypatch.setattr(
        "vms.identity.engine.get_settings",
        lambda: _settings(
            reid_stale_ms=5_000,
            reid_confirmed_stale_ms=10_000,
        ),
    )
    engine = _make_engine()
    for i in range(100):
        engine.assign_global_track_id(1, i, _noisy(_person_emb(i)))

    evicted = engine.evict_stale(now_ms=engine._registry[(1, 0)].last_seen_ms + 6_000)
    assert evicted == 100
    assert len(engine._registry) == 0


@pytest.mark.integration
def test_confirmed_tracks_not_evicted_at_unconfirmed_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confirmed tracks survive past reid_stale_ms but are evicted at reid_confirmed_stale_ms."""
    monkeypatch.setattr(
        "vms.identity.engine.get_settings",
        lambda: _settings(
            reid_confirm_after_sightings=2,
            reid_stale_ms=1_000,
            reid_confirmed_stale_ms=30_000,
        ),
    )
    engine = _make_engine()
    emb = _noisy(_person_emb(0))
    engine.assign_global_track_id(1, 1, emb)
    engine.assign_global_track_id(1, 1, emb)
    assert engine._registry[(1, 1)].confirmed

    last_ms = engine._registry[(1, 1)].last_seen_ms
    # At stale_ms + 5s: unconfirmed would be evicted, confirmed should survive
    assert engine.evict_stale(now_ms=last_ms + 5_000) == 0
    # At confirmed_stale_ms + 1s: confirmed should now be evicted
    assert engine.evict_stale(now_ms=last_ms + 31_000) == 1


@pytest.mark.integration
def test_topology_gate_prevents_ghost_matches_across_distant_cameras(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two cameras 60s apart minimum: instant cross-camera appearance is rejected."""
    monkeypatch.setattr(
        "vms.identity.engine.get_settings",
        lambda: _settings(
            reid_confirm_after_sightings=2,
            reid_cross_cam_sim=0.65,
            reid_confirmed_sim=0.60,
            reid_margin=0.0,
            reid_camera_topology_json='{"1-2": {"min_ms": 60000, "max_ms": 300000}}',
        ),
    )
    engine = _make_engine()
    base = _noisy(_person_emb(0), noise=0.001)
    near = _noisy(_person_emb(0), noise=0.002, seed=1)

    gid1 = engine.assign_global_track_id(1, 1, base)
    engine.assign_global_track_id(1, 1, near)  # confirm
    assert engine._registry[(1, 1)].confirmed

    # Instantly appears on cam2 -- elapsed ~0ms < min_ms=60000 -> reject
    gid2 = engine.assign_global_track_id(2, 1, near)
    assert gid1 != gid2
