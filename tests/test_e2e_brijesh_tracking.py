"""E2E: Brijesh enters entry gate, tracked through facility via body Re-ID + BLE fallback.

Scenarios:
  1. Identified at entry gate (face) → person_id anchors to gid → inherited on floor cams
  2. Unknown visitor: no face match, no BLE → stays unknown throughout
  3. Fusion conflict: face says person 10, body anchor says person 99 → face wins
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from vms.identity.engine import IdentityEngine
from vms.identity.reid import ReIdService


def _make_engine(face_returns: int | None = 42) -> IdentityEngine:
    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = face_returns
    return IdentityEngine(reid_service=reid)


def _emb(seed: int, noise: float = 0.0) -> tuple[float, ...]:
    rng = np.random.default_rng(seed * 100)
    v = rng.standard_normal(512).astype(np.float32)
    if noise > 0:
        v += np.random.default_rng(seed).standard_normal(512).astype(np.float32) * noise
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
        reid_body_cross_cam_sim=0.65,
        reid_body_confirmed_sim=0.51,
        reid_margin=0.05,
        reid_stale_ms=300_000,
        reid_confirmed_stale_ms=600_000,
        reid_camera_topology_json="{}",
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


@pytest.mark.integration
def test_brijesh_identified_at_gate_tracked_through_facility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entry gate identifies Brijesh. Floor cams inherit identity via body Re-ID."""
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _settings())
    engine = _make_engine(face_returns=42)

    # Entry gate (cam=0): 4 sightings → confirm gallery + identify as Brijesh
    for _ in range(4):
        gid_gate, pid, via = engine.assign_and_identify(
            camera_id=0,
            local_track_id=1,
            embedding=_emb(0, noise=0.01),
            body_embedding=_emb(10, noise=0.01),
        )
    assert pid == 42 and via == "face"
    assert engine._registry[(0, 1)].confirmed

    # Floor cam 1 (cam=1): no frontal face — body Re-ID
    engine._reid.identify.return_value = None
    for _ in range(3):
        gid_c1, pid1, _via1 = engine.assign_and_identify(
            camera_id=1,
            local_track_id=1,
            embedding=None,
            body_embedding=_emb(10, noise=0.02),
        )
    assert gid_c1 == gid_gate
    assert pid1 == 42  # inherited via body gallery match

    # Floor cam 2 (cam=2): also body only
    for _ in range(3):
        gid_c2, pid2, _ = engine.assign_and_identify(
            camera_id=2,
            local_track_id=1,
            embedding=None,
            body_embedding=_emb(10, noise=0.02),
        )
    assert gid_c2 == gid_gate
    assert pid2 == 42


@pytest.mark.integration
def test_unknown_visitor_stays_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Visitor not in DB and no BLE badge → person_id stays None throughout."""
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _settings())
    engine = _make_engine(face_returns=None)

    _gid, pid, via = engine.assign_and_identify(
        camera_id=0,
        local_track_id=1,
        embedding=_emb(50),
        body_embedding=None,
        ble_person_id=None,
    )
    assert pid is None and via == "unknown"


@pytest.mark.integration
def test_ble_fallback_when_body_match_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """BLE badge confirms identity when camera can't match via face or body."""
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _settings())
    engine = _make_engine(face_returns=None)

    # Person walks into far corner — no prior gallery, BLE badge confirms it's Brijesh
    _gid, pid, via = engine.assign_and_identify(
        camera_id=5,
        local_track_id=3,
        embedding=None,
        body_embedding=None,
        ble_person_id=42,
    )
    assert pid == 42 and via == "ble"


@pytest.mark.integration
def test_fusion_conflict_face_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """When face says person 10 and body anchor says person 99, face wins."""
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _settings())

    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = 99
    engine = IdentityEngine(reid_service=reid)

    # Build body gallery anchored to person 99
    for _ in range(4):
        engine.assign_and_identify(camera_id=5, local_track_id=9, embedding=_emb(99, noise=0.005))
    assert engine._registry[(5, 9)].confirmed

    # Face now identifies as person 10 — face should win over body anchor
    reid.identify.return_value = 10
    near = _emb(99, noise=0.001)
    _, pid, via = engine.assign_and_identify(camera_id=6, local_track_id=1, embedding=near)
    assert pid == 10 and via == "face"
