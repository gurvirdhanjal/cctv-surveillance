"""Tests for gallery buffer, confirmed promotion, and two-tier re-ID in IdentityEngine."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from vms.identity.engine import IdentityEngine
from vms.identity.reid import ReIdService


def _make_engine() -> IdentityEngine:
    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = None
    return IdentityEngine(reid_service=reid)


def _norm_emb(seed: int) -> tuple[float, ...]:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(512).astype(np.float32)
    v /= np.linalg.norm(v) + 1e-8
    return tuple(float(x) for x in v)


def _near_emb(base: tuple[float, ...], noise: float = 0.02, seed: int = 42) -> tuple[float, ...]:
    v = np.array(base, dtype=np.float32)
    v += np.random.default_rng(seed).standard_normal(512).astype(np.float32) * noise
    v /= np.linalg.norm(v) + 1e-8
    return tuple(float(x) for x in v)


def _s(**overrides: object) -> object:
    """Return a Settings-like object with sensible defaults + overrides."""
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


def test_gallery_grows_to_max_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _s(reid_gallery_size=4))
    engine = _make_engine()
    emb = _norm_emb(0)
    for _ in range(10):
        engine.assign_global_track_id(1, 1, emb)
    assert len(engine._registry[(1, 1)].gallery) == 4


def test_gallery_capped_at_most_recent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _s(reid_gallery_size=3))
    engine = _make_engine()
    embs = [_norm_emb(i) for i in range(5)]
    for e in embs:
        engine.assign_global_track_id(1, 1, e)
    gallery = engine._registry[(1, 1)].gallery
    assert len(gallery) == 3
    # last 3 embeddings are in gallery (most recent)
    for i, e in enumerate(embs[-3:]):
        expected = np.array(e, dtype=np.float32)
        assert np.allclose(gallery[i], expected)


def test_confirmed_promotion_after_n_sightings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.identity.engine.get_settings", lambda: _s(reid_confirm_after_sightings=3)
    )
    engine = _make_engine()
    emb = _norm_emb(0)
    engine.assign_global_track_id(1, 1, emb)
    assert not engine._registry[(1, 1)].confirmed
    engine.assign_global_track_id(1, 1, emb)
    assert not engine._registry[(1, 1)].confirmed
    engine.assign_global_track_id(1, 1, emb)
    assert engine._registry[(1, 1)].confirmed


def test_cross_camera_gallery_match_reuses_global_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.identity.engine.get_settings",
        lambda: _s(
            reid_confirm_after_sightings=2,
            reid_cross_cam_sim=0.65,
            reid_confirmed_sim=0.60,
            reid_margin=0.03,
        ),
    )
    engine = _make_engine()
    base = _norm_emb(0)
    near = _near_emb(base, noise=0.01)

    gid1 = engine.assign_global_track_id(1, 1, base)
    engine.assign_global_track_id(1, 1, near)  # 2 sightings → confirmed

    gid2 = engine.assign_global_track_id(2, 1, _near_emb(base, noise=0.01, seed=7))
    assert gid1 == gid2


def test_unconfirmed_strict_threshold_prevents_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.identity.engine.get_settings",
        lambda: _s(
            reid_confirm_after_sightings=10,  # needs 10 sightings — never confirmed
            reid_cross_cam_sim=0.999,  # impossibly strict for unconfirmed
            reid_confirmed_sim=0.60,
            reid_margin=0.0,
        ),
    )
    engine = _make_engine()
    base = _norm_emb(0)
    gid1 = engine.assign_global_track_id(1, 1, base)
    # only 1 sighting on cam1 → not confirmed → uses reid_cross_cam_sim=0.999
    gid2 = engine.assign_global_track_id(2, 1, _near_emb(base, noise=0.005))
    assert gid1 != gid2


def test_confirmed_track_survives_longer_stale_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.identity.engine.get_settings",
        lambda: _s(
            reid_confirm_after_sightings=2,
            reid_stale_ms=1_000,
            reid_confirmed_stale_ms=600_000,
        ),
    )
    engine = _make_engine()
    emb = _norm_emb(0)
    engine.assign_global_track_id(1, 1, emb)
    engine.assign_global_track_id(1, 1, emb)
    assert engine._registry[(1, 1)].confirmed

    # Evict at last_seen + 5s (> reid_stale_ms=1000 but < reid_confirmed_stale_ms=600000)
    evicted = engine.evict_stale(now_ms=engine._registry[(1, 1)].last_seen_ms + 5_000)
    assert evicted == 0


def test_unconfirmed_track_evicted_at_stale_ms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.identity.engine.get_settings",
        lambda: _s(
            reid_confirm_after_sightings=5,  # needs 5 sightings
            reid_stale_ms=1_000,
            reid_confirmed_stale_ms=600_000,
        ),
    )
    engine = _make_engine()
    emb = _norm_emb(0)
    engine.assign_global_track_id(1, 1, emb)  # 1 sighting — not confirmed
    assert not engine._registry[(1, 1)].confirmed

    evicted = engine.evict_stale(now_ms=engine._registry[(1, 1)].last_seen_ms + 2_000)
    assert evicted == 1


def test_topology_gate_rejects_impossible_transit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.identity.engine.get_settings",
        lambda: _s(
            reid_confirm_after_sightings=2,
            reid_cross_cam_sim=0.65,
            reid_confirmed_sim=0.60,
            reid_margin=0.0,
            reid_camera_topology_json='{"1-2": {"min_ms": 30000, "max_ms": 120000}}',
        ),
    )
    engine = _make_engine()
    base = _norm_emb(0)
    near = _near_emb(base, noise=0.005)

    # Build confirmed gallery on cam1
    gid1 = engine.assign_global_track_id(1, 1, base)
    engine.assign_global_track_id(1, 1, near)
    assert engine._registry[(1, 1)].confirmed

    # Immediately appear on cam2 — elapsed ≈ 0ms < min_ms=30000 → topology rejects
    gid2 = engine.assign_global_track_id(2, 1, near)
    assert gid1 != gid2


def test_body_embedding_gallery_used_when_no_face(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.identity.engine.get_settings",
        lambda: _s(
            reid_confirm_after_sightings=2,
            reid_cross_cam_sim=0.65,
            reid_confirmed_sim=0.60,
            reid_margin=0.0,
        ),
    )
    engine = _make_engine()
    body = _norm_emb(10)
    near_body = _near_emb(body, noise=0.01)

    # Cam1: no face — build body gallery
    gid1 = engine.assign_global_track_id(1, 1, embedding=None, body_embedding=body)
    engine.assign_global_track_id(1, 1, embedding=None, body_embedding=near_body)

    # Cam2: same person, no face, similar body
    gid2 = engine.assign_global_track_id(2, 1, embedding=None, body_embedding=near_body)
    assert gid1 == gid2


def test_face_takes_priority_over_body_for_gallery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.identity.engine.get_settings",
        lambda: _s(
            reid_confirm_after_sightings=2,
            reid_cross_cam_sim=0.65,
            reid_confirmed_sim=0.60,
            reid_margin=0.0,
        ),
    )
    engine = _make_engine()
    face = _norm_emb(0)
    body = _norm_emb(99)  # unrelated embedding space

    # Cam1: has both face and body; face should win
    gid1 = engine.assign_global_track_id(1, 1, embedding=face, body_embedding=body)
    engine.assign_global_track_id(1, 1, embedding=face, body_embedding=body)
    assert len(engine._registry[(1, 1)].gallery) == 2
    assert len(engine._registry[(1, 1)].body_gallery) == 2  # both galleries populate

    # Cam2: similar face → matches via face gallery
    gid2 = engine.assign_global_track_id(
        2, 1, embedding=_near_emb(face, noise=0.01), body_embedding=_norm_emb(88)
    )
    assert gid1 == gid2
