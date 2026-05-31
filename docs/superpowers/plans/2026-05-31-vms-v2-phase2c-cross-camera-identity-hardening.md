# Cross-Camera Identity Hardening (Crowd-Resilient Re-ID) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Harden cross-camera re-ID so it remains reliable under high crowd density (20+ persons/camera, 52 cameras) without false merges or identity fragmentation.

**Architecture:** Three layered improvements on `vms/identity/engine.py`: (1) each `_TrackletEntry` grows a rolling **gallery** of N=8 embeddings and is **promoted to confirmed** after accumulating enough sightings — confirmed tracks use a lower similarity threshold and a longer stale TTL; (2) a new **`CameraTopology`** singleton loaded from config eliminates cross-camera candidates with physically impossible transit times; (3) a **`BodyEmbedder`** (OSNet ONNX) provides a face-independent appearance embedding stored in `Tracklet.body_embedding`, used as fallback in `IdentityEngine` when face detection fails in crowds.

**Tech Stack:** ONNX Runtime (existing), NumPy, pydantic-settings, pytest. New model: OSNet x1.0 Market-1501 (512-dim, ~2MB ONNX).

**Spec refs:** `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` §K Phase 2a; `docs/superpowers/specs/2026-05-27-vms-production-readiness.md` §Re-ID SLOs.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `vms/config.py` | 5 new re-ID settings |
| Modify | `vms/identity/engine.py` | Gallery, confirmed promotion, two-tier threshold, body fallback, two-tier TTL |
| Create | `vms/identity/topology.py` | `CameraTopology`: load from JSON config, `transit_ok()` |
| Modify | `vms/inference/messages.py` | `body_embedding` field on `Tracklet`, update serialization |
| Create | `vms/inference/body_embedder.py` | `BodyEmbedder` ONNX wrapper (OSNet x1.0) |
| Modify | `vms/inference/engine.py` | `_extract_body_embeddings` helper, wire `BodyEmbedder` into `__init__` |
| Modify | `tests/test_identity_engine.py` | Remove `last_embedding` from direct `_TrackletEntry` constructions |
| Create | `tests/test_identity_gallery.py` | Gallery buffer, confirmed promotion, two-tier threshold + TTL tests |
| Create | `tests/test_camera_topology.py` | `CameraTopology` unit tests |
| Modify | `tests/test_inference_messages.py` | Add `body_embedding` round-trip tests |
| Create | `tests/test_inference_body_embedder.py` | `BodyEmbedder` ONNX unit tests (mocked session) |
| Create | `tests/test_e2e_crowd_reid.py` | E2E: 20 persons × 4 cameras stability + eviction bounds |

---

## Task 1: New Config Settings

**Files:** Modify `vms/config.py`

- [ ] **Step 1.1: Write the failing test**

Add to `tests/test_config.py` (it already exists — append these tests):

```python
def test_settings_gallery_defaults() -> None:
    from vms.config import Settings
    s = Settings(db_url="postgresql://x", jwt_secret="x")
    assert s.reid_gallery_size == 8
    assert s.reid_confirm_after_sightings == 3
    assert s.reid_confirmed_sim == 0.60
    assert s.reid_confirmed_stale_ms == 600_000
    assert s.reid_camera_topology_json == "{}"
```

- [ ] **Step 1.2: Run test to verify it fails**

```powershell
pytest tests/test_config.py::test_settings_gallery_defaults -v
```
Expected: `AttributeError: 'Settings' object has no attribute 'reid_gallery_size'`

- [ ] **Step 1.3: Add settings to `vms/config.py`**

After the `reid_stale_ms` line (currently `reid_stale_ms: int = 300_000`), add:

```python
    reid_gallery_size: int = 8
    reid_confirm_after_sightings: int = 3
    reid_confirmed_sim: float = 0.60
    reid_confirmed_stale_ms: int = 600_000
    reid_camera_topology_json: str = "{}"
```

- [ ] **Step 1.4: Run test to verify it passes**

```powershell
pytest tests/test_config.py::test_settings_gallery_defaults -v
```
Expected: PASS

- [ ] **Step 1.5: Full suite check**

```powershell
pytest --tb=short -q
```
Expected: all existing tests still pass.

- [ ] **Step 1.6: Commit**

```powershell
git add vms/config.py tests/test_config.py
git commit -m "feat(config): add gallery + confirmed-track re-ID settings"
```

---

## Task 2: CameraTopology Spatial-Temporal Gate

**Files:** Create `vms/identity/topology.py`, create `tests/test_camera_topology.py`

- [ ] **Step 2.1: Write failing tests**

Create `tests/test_camera_topology.py`:

```python
from __future__ import annotations

from vms.identity.topology import CameraTopology


def test_unknown_pair_allows_match() -> None:
    t = CameraTopology("{}")
    assert t.transit_ok(1, 2, elapsed_ms=5_000) is True


def test_within_window_allows() -> None:
    t = CameraTopology('{"1-2": {"min_ms": 2000, "max_ms": 120000}}')
    assert t.transit_ok(1, 2, elapsed_ms=30_000) is True


def test_too_fast_rejects() -> None:
    t = CameraTopology('{"1-2": {"min_ms": 2000, "max_ms": 120000}}')
    assert t.transit_ok(1, 2, elapsed_ms=500) is False


def test_too_slow_rejects() -> None:
    t = CameraTopology('{"1-2": {"min_ms": 2000, "max_ms": 120000}}')
    assert t.transit_ok(1, 2, elapsed_ms=200_000) is False


def test_symmetric_lookup() -> None:
    t = CameraTopology('{"1-2": {"min_ms": 2000, "max_ms": 120000}}')
    assert t.transit_ok(2, 1, elapsed_ms=30_000) is True


def test_invalid_json_allows_all() -> None:
    t = CameraTopology("{bad json")
    assert t.transit_ok(1, 2, elapsed_ms=5_000) is True


def test_same_camera_always_allowed() -> None:
    t = CameraTopology("{}")
    assert t.transit_ok(1, 1, elapsed_ms=0) is True


def test_multiple_pairs() -> None:
    t = CameraTopology('{"1-2": {"min_ms": 1000, "max_ms": 60000}, "2-3": {"min_ms": 5000, "max_ms": 30000}}')
    assert t.transit_ok(1, 2, elapsed_ms=5_000) is True
    assert t.transit_ok(2, 3, elapsed_ms=3_000) is False  # too fast for 2-3
    assert t.transit_ok(1, 3, elapsed_ms=3_000) is True   # no rule for 1-3 → allow
```

- [ ] **Step 2.2: Run to verify they fail**

```powershell
pytest tests/test_camera_topology.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.identity.topology'`

- [ ] **Step 2.3: Create `vms/identity/topology.py`**

```python
"""Camera pair transit-time gate for cross-camera re-ID.

Config format (VMS_REID_CAMERA_TOPOLOGY_JSON):
  {"1-2": {"min_ms": 2000, "max_ms": 120000}, "2-3": {...}, ...}

Key is always "{min_id}-{max_id}" (sorted ascending, hyphen-separated).
Unknown pairs are unconditionally allowed (fail-open — no false negatives).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PairWindow:
    min_ms: int
    max_ms: int


class CameraTopology:
    """Checks whether a cross-camera transit time is physically plausible."""

    def __init__(self, topology_json: str) -> None:
        self._pairs: dict[str, _PairWindow] = {}
        try:
            raw: dict[str, dict[str, int]] = json.loads(topology_json)
        except (json.JSONDecodeError, ValueError):
            logger.warning("CameraTopology: invalid JSON — all cross-camera matches allowed")
            return
        for key, val in raw.items():
            try:
                self._pairs[key] = _PairWindow(
                    min_ms=int(val["min_ms"]), max_ms=int(val["max_ms"])
                )
            except (KeyError, ValueError):
                logger.warning("CameraTopology: skipping malformed pair entry %r", key)

    def transit_ok(self, cam_a: int, cam_b: int, elapsed_ms: int) -> bool:
        """Return True if transit from cam_a to cam_b in elapsed_ms is plausible.

        Unknown pairs are unconditionally allowed (fail-open).
        """
        key = f"{min(cam_a, cam_b)}-{max(cam_a, cam_b)}"
        window = self._pairs.get(key)
        if window is None:
            return True
        return window.min_ms <= elapsed_ms <= window.max_ms
```

- [ ] **Step 2.4: Run to verify they pass**

```powershell
pytest tests/test_camera_topology.py -v
```
Expected: all 8 tests PASS.

- [ ] **Step 2.5: Full suite check**

```powershell
pytest --tb=short -q
```

- [ ] **Step 2.6: Commit**

```powershell
git add vms/identity/topology.py tests/test_camera_topology.py
git commit -m "feat(identity): CameraTopology spatial-temporal gate"
```

---

## Task 3: Gallery Buffer + Confirmed Promotion in IdentityEngine

**Files:** Rewrite `vms/identity/engine.py`, update `tests/test_identity_engine.py`, create `tests/test_identity_gallery.py`

This task replaces `last_embedding` with a rolling `gallery`, adds `body_gallery` for face-absent scenarios, adds `confirmed` and `sighting_count` fields, and rewires `_cross_camera_match` to use gallery-aware similarity with the topology gate and two-tier TTL.

### Step 3.1 — Fix the existing engine tests first (they will break after the rewrite)

The existing `tests/test_identity_engine.py` constructs `_TrackletEntry` directly with `last_embedding=None` on lines 75–84, 93–99, and 110–116. After the rewrite, `last_embedding` won't exist. Update those three constructions before changing the engine.

- [ ] **Step 3.1a: Update `tests/test_identity_engine.py`**

Replace the three `_TrackletEntry(...)` calls (lines 75–81, 93–99, 110–116) to remove `last_embedding=None` and add the new fields that have defaults:

```python
# OLD (lines 75–81):
engine._registry[(1, 42)] = _TrackletEntry(
    global_track_id=uuid.uuid4(),
    person_id=None,
    last_embedding=None,
    last_seen_ms=old_ms,
    camera_id=1,
)

# NEW:
engine._registry[(1, 42)] = _TrackletEntry(
    global_track_id=uuid.uuid4(),
    person_id=None,
    last_seen_ms=old_ms,
    camera_id=1,
)
```

Apply the same `last_embedding=None` removal to the constructions at lines 93–99 and 110–116. All other test logic stays the same.

- [ ] **Step 3.1b: Write failing gallery tests**

Create `tests/test_identity_gallery.py`:

```python
"""Tests for gallery buffer, confirmed promotion, and two-tier re-ID in IdentityEngine."""

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
        db_url="x", jwt_secret="x",
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
    monkeypatch.setattr("vms.identity.engine.get_settings",
                        lambda: _s(reid_confirm_after_sightings=3))
    engine = _make_engine()
    emb = _norm_emb(0)
    engine.assign_global_track_id(1, 1, emb)
    assert not engine._registry[(1, 1)].confirmed
    engine.assign_global_track_id(1, 1, emb)
    assert not engine._registry[(1, 1)].confirmed
    engine.assign_global_track_id(1, 1, emb)
    assert engine._registry[(1, 1)].confirmed


def test_cross_camera_gallery_match_reuses_global_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _s(
        reid_confirm_after_sightings=2, reid_cross_cam_sim=0.65, reid_confirmed_sim=0.60,
        reid_margin=0.03,
    ))
    engine = _make_engine()
    base = _norm_emb(0)
    near = _near_emb(base, noise=0.01)

    gid1 = engine.assign_global_track_id(1, 1, base)
    engine.assign_global_track_id(1, 1, near)   # 2 sightings → confirmed

    gid2 = engine.assign_global_track_id(2, 1, _near_emb(base, noise=0.01, seed=7))
    assert gid1 == gid2


def test_unconfirmed_strict_threshold_prevents_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _s(
        reid_confirm_after_sightings=10,   # needs 10 sightings — never confirmed
        reid_cross_cam_sim=0.999,           # impossibly strict for unconfirmed
        reid_confirmed_sim=0.60,
        reid_margin=0.0,
    ))
    engine = _make_engine()
    base = _norm_emb(0)
    gid1 = engine.assign_global_track_id(1, 1, base)
    # only 1 sighting on cam1 → not confirmed → uses reid_cross_cam_sim=0.999
    gid2 = engine.assign_global_track_id(2, 1, _near_emb(base, noise=0.005))
    assert gid1 != gid2


def test_confirmed_track_survives_longer_stale_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _s(
        reid_confirm_after_sightings=2,
        reid_stale_ms=1_000,
        reid_confirmed_stale_ms=600_000,
    ))
    engine = _make_engine()
    emb = _norm_emb(0)
    engine.assign_global_track_id(1, 1, emb)
    engine.assign_global_track_id(1, 1, emb)
    assert engine._registry[(1, 1)].confirmed

    # Evict at last_seen + 5s (> reid_stale_ms=1000 but < reid_confirmed_stale_ms=600000)
    evicted = engine.evict_stale(
        now_ms=engine._registry[(1, 1)].last_seen_ms + 5_000
    )
    assert evicted == 0


def test_unconfirmed_track_evicted_at_stale_ms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _s(
        reid_confirm_after_sightings=5,  # needs 5 sightings
        reid_stale_ms=1_000,
        reid_confirmed_stale_ms=600_000,
    ))
    engine = _make_engine()
    emb = _norm_emb(0)
    engine.assign_global_track_id(1, 1, emb)  # 1 sighting — not confirmed
    assert not engine._registry[(1, 1)].confirmed

    evicted = engine.evict_stale(
        now_ms=engine._registry[(1, 1)].last_seen_ms + 2_000
    )
    assert evicted == 1


def test_topology_gate_rejects_impossible_transit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _s(
        reid_confirm_after_sightings=2,
        reid_cross_cam_sim=0.65,
        reid_confirmed_sim=0.60,
        reid_margin=0.0,
        reid_camera_topology_json='{"1-2": {"min_ms": 30000, "max_ms": 120000}}',
    ))
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
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _s(
        reid_confirm_after_sightings=2, reid_cross_cam_sim=0.65,
        reid_confirmed_sim=0.60, reid_margin=0.0,
    ))
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
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _s(
        reid_confirm_after_sightings=2, reid_cross_cam_sim=0.65,
        reid_confirmed_sim=0.60, reid_margin=0.0,
    ))
    engine = _make_engine()
    face = _norm_emb(0)
    body = _norm_emb(99)  # unrelated embedding space

    # Cam1: has both face and body; face should win
    gid1 = engine.assign_global_track_id(1, 1, embedding=face, body_embedding=body)
    engine.assign_global_track_id(1, 1, embedding=face, body_embedding=body)
    assert len(engine._registry[(1, 1)].gallery) == 2
    assert engine._registry[(1, 1)].body_gallery == []

    # Cam2: similar face → matches via face gallery
    gid2 = engine.assign_global_track_id(2, 1, embedding=_near_emb(face, noise=0.01),
                                          body_embedding=_norm_emb(88))
    assert gid1 == gid2
```

- [ ] **Step 3.1c: Run all gallery tests — confirm they all fail**

```powershell
pytest tests/test_identity_gallery.py -v
```
Expected: fails with `AttributeError` on `gallery`, `body_gallery`, `confirmed`, `sighting_count` — these don't exist yet.

### Step 3.2 — Rewrite engine.py

- [ ] **Step 3.2a: Replace `vms/identity/engine.py` with the new implementation**

```python
"""Identity engine: tracklet registry, cross-camera re-ID, person identification.

Cross-camera matching algorithm:
  1. (cam_id, local_track_id) known → return cached global_track_id; update gallery.
  2. Unknown + has embedding →
       a. Spatial-temporal gate: skip entries with implausible transit time.
       b. Gallery similarity: max cosine(query, gallery[i]) across all gallery entries.
          Face queries compare against face gallery; body queries against body gallery.
       c. Threshold: confirmed entry → reid_confirmed_sim; unconfirmed → reid_cross_cam_sim.
       d. Margin gate: best_sim − second_sim >= reid_margin.
       e. Match → reuse global_track_id; no match → new UUID.
  3. Unknown + no embedding → new UUID.

Face embedding always takes priority over body embedding for gallery storage.
Body embedding is only stored when face is absent, enabling crowd-dense scenarios
where face detection fails (occlusion, helmets, angle).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from vms.config import get_settings
from vms.identity.reid import ReIdService
from vms.identity.topology import CameraTopology

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class _TrackletEntry:
    global_track_id: uuid.UUID
    person_id: int | None
    last_seen_ms: int
    camera_id: int
    gallery: list[np.ndarray[Any, Any]] = field(default_factory=list)
    body_gallery: list[np.ndarray[Any, Any]] = field(default_factory=list)
    sighting_count: int = 0
    confirmed: bool = False


class IdentityEngine:
    """Stateful per-process identity assignment for detection frames."""

    def __init__(self, reid_service: ReIdService) -> None:
        self._reid = reid_service
        self._registry: dict[tuple[int, int], _TrackletEntry] = {}
        self._topology: CameraTopology | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assign_global_track_id(
        self,
        camera_id: int,
        local_track_id: int,
        embedding: tuple[float, ...] | None,
        body_embedding: tuple[float, ...] | None = None,
    ) -> uuid.UUID:
        """Return a stable global_track_id for (camera_id, local_track_id).

        Face embedding takes priority for gallery storage.
        Body embedding is used only when face is absent.
        """
        key = (camera_id, local_track_id)
        now_ms = time.time_ns() // 1_000_000
        settings = get_settings()

        if key in self._registry:
            entry = self._registry[key]
            entry.last_seen_ms = now_ms
            self._update_galleries(entry, embedding, body_embedding, settings)
            return entry.global_track_id

        emb_arr = np.array(embedding, dtype=np.float32) if embedding else None
        body_arr = np.array(body_embedding, dtype=np.float32) if body_embedding else None

        # Cross-camera match: face preferred, body as fallback
        query = emb_arr if emb_arr is not None else body_arr
        query_type = "face" if emb_arr is not None else "body"
        matched_gid = (
            self._cross_camera_match(query, query_type, camera_id, now_ms)
            if query is not None
            else None
        )
        gid = matched_gid if matched_gid is not None else uuid.uuid4()
        entry = _TrackletEntry(
            global_track_id=gid,
            person_id=None,
            last_seen_ms=now_ms,
            camera_id=camera_id,
        )
        self._update_galleries(entry, embedding, body_embedding, settings)
        self._registry[key] = entry
        return gid

    def identify_person(self, embedding: tuple[float, ...]) -> int | None:
        """Return person_id from FAISS if embedding is non-empty, else None."""
        if not embedding:
            return None
        return self._reid.identify(np.array(embedding, dtype=np.float32))

    def faiss_apply_add(self, embedding_id: int, person_id: int, db: Session) -> None:
        """Fetch embedding from DB and add it to the FAISS index."""
        from vms.db.models import PersonEmbedding

        row = db.get(PersonEmbedding, embedding_id)
        if row is None:
            logger.warning("faiss_dirty add: embedding_id=%d not found in DB", embedding_id)
            return
        vec = np.array(row.embedding, dtype=np.float32)
        self._reid.apply_add(embedding_id, person_id, vec)

    def faiss_apply_remove(self, embedding_ids: list[int]) -> None:
        """Remove embeddings from the FAISS index."""
        self._reid.apply_remove(embedding_ids)

    def evict_stale(self, now_ms: int | None = None) -> int:
        """Remove tracklets not seen within their stale TTL.

        Confirmed tracklets: reid_confirmed_stale_ms (default 10 min).
        Unconfirmed tracklets: reid_stale_ms (default 5 min).
        Returns evicted count.
        """
        if now_ms is None:
            now_ms = time.time_ns() // 1_000_000
        settings = get_settings()
        stale = [
            k
            for k, e in self._registry.items()
            if now_ms - e.last_seen_ms > (
                settings.reid_confirmed_stale_ms if e.confirmed else settings.reid_stale_ms
            )
        ]
        for k in stale:
            del self._registry[k]
        return len(stale)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_topology(self) -> CameraTopology:
        if self._topology is None:
            self._topology = CameraTopology(get_settings().reid_camera_topology_json)
        return self._topology

    def _update_galleries(
        self,
        entry: _TrackletEntry,
        embedding: tuple[float, ...] | None,
        body_embedding: tuple[float, ...] | None,
        settings: Any,
    ) -> None:
        """Append to face gallery (priority) or body gallery (fallback). Update confirmed."""
        if embedding:
            entry.gallery.append(np.array(embedding, dtype=np.float32))
            if len(entry.gallery) > settings.reid_gallery_size:
                entry.gallery = entry.gallery[-settings.reid_gallery_size :]
        elif body_embedding:
            entry.body_gallery.append(np.array(body_embedding, dtype=np.float32))
            if len(entry.body_gallery) > settings.reid_gallery_size:
                entry.body_gallery = entry.body_gallery[-settings.reid_gallery_size :]

        if embedding or body_embedding:
            entry.sighting_count += 1
            if not entry.confirmed and entry.sighting_count >= settings.reid_confirm_after_sightings:
                entry.confirmed = True

    def _gallery_sim(
        self,
        query_norm: np.ndarray[Any, Any],
        gallery: list[np.ndarray[Any, Any]],
    ) -> float:
        """Return max cosine similarity between a normalized query and any gallery entry."""
        best = -1.0
        for g in gallery:
            g_norm = g / (np.linalg.norm(g) + 1e-8)
            sim = float(np.dot(query_norm, g_norm))
            if sim > best:
                best = sim
        return best

    def _cross_camera_match(
        self,
        query: np.ndarray[Any, Any],
        query_type: str,
        camera_id: int,
        now_ms: int,
    ) -> uuid.UUID | None:
        """Scan other-camera tracklets for a gallery-aware match with topology gate.

        query_type: "face" → compare against entry.gallery;
                    "body" → compare against entry.body_gallery.
        """
        settings = get_settings()
        topology = self._get_topology()
        q = query / (np.linalg.norm(query) + 1e-8)
        best_sim = -1.0
        second_sim = -1.0
        best_gid: uuid.UUID | None = None
        best_confirmed = False

        for (cam, _), entry in self._registry.items():
            if cam == camera_id:
                continue

            # Two-tier stale check
            stale_limit = (
                settings.reid_confirmed_stale_ms if entry.confirmed else settings.reid_stale_ms
            )
            if now_ms - entry.last_seen_ms > stale_limit:
                continue

            # Choose gallery by query type
            target_gallery = entry.gallery if query_type == "face" else entry.body_gallery
            if not target_gallery:
                continue

            # Spatial-temporal gate
            elapsed_ms = now_ms - entry.last_seen_ms
            if not topology.transit_ok(camera_id, cam, elapsed_ms):
                continue

            sim = self._gallery_sim(q, target_gallery)
            if sim > best_sim:
                second_sim = best_sim
                best_sim = sim
                best_gid = entry.global_track_id
                best_confirmed = entry.confirmed
            elif sim > second_sim:
                second_sim = sim

        threshold = settings.reid_confirmed_sim if best_confirmed else settings.reid_cross_cam_sim
        if best_sim < threshold:
            return None
        margin = best_sim - second_sim if second_sim > -1.0 else best_sim
        if margin < settings.reid_margin:
            return None
        return best_gid
```

- [ ] **Step 3.2b: Run the updated existing engine tests**

```powershell
pytest tests/test_identity_engine.py -v
```
Expected: all 7 existing tests PASS (the `last_embedding` removal in Step 3.1a makes them compatible).

- [ ] **Step 3.2c: Run the new gallery tests**

```powershell
pytest tests/test_identity_gallery.py -v
```
Expected: all 10 tests PASS.

- [ ] **Step 3.2d: Run full identity suite**

```powershell
pytest tests/test_identity_engine.py tests/test_identity_gallery.py tests/test_identity_reid.py tests/test_identity_faiss_index.py tests/test_identity_head_count.py tests/test_identity_zone_presence.py tests/test_identity_faiss_dirty.py tests/test_identity_faiss_consumer.py -v
```
Expected: all pass.

- [ ] **Step 3.2e: Full suite check**

```powershell
pytest --tb=short -q
```

- [ ] **Step 3.2f: Lint + type-check**

```powershell
ruff check vms/identity/engine.py vms/identity/topology.py
mypy vms/identity/engine.py vms/identity/topology.py
black vms/identity/engine.py vms/identity/topology.py
```

- [ ] **Step 3.2g: Commit**

```powershell
git add vms/identity/engine.py vms/identity/topology.py vms/config.py tests/test_identity_engine.py tests/test_identity_gallery.py tests/test_camera_topology.py
git commit -m "feat(identity): gallery buffer, confirmed promotion, topology gate, two-tier TTL"
```

---

## Task 4: Body Embedding in Tracklet + Serialization

**Files:** Modify `vms/inference/messages.py`, add tests to `tests/test_inference_messages.py`

- [ ] **Step 4.1: Write failing tests**

Append to `tests/test_inference_messages.py`:

```python
def test_tracklet_body_embedding_defaults_empty() -> None:
    t = Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 100, 200), confidence=0.9)
    assert t.body_embedding == ()


def test_tracklet_body_embedding_stored() -> None:
    t = Tracklet(
        local_track_id=1, camera_id=1, bbox=(0, 0, 100, 200), confidence=0.9,
        body_embedding=(0.3, 0.4, 0.5),
    )
    assert t.body_embedding == (0.3, 0.4, 0.5)


def test_detection_frame_body_embedding_redis_roundtrip() -> None:
    t = Tracklet(
        local_track_id=2, camera_id=3, bbox=(10, 20, 50, 80), confidence=0.8,
        embedding=(1.0, 2.0),
        body_embedding=(3.0, 4.0),
    )
    frame = DetectionFrame(
        camera_id=3, seq_id=1, timestamp_ms=1000, tracklets=(t,), face_embeddings=()
    )
    restored = DetectionFrame.from_redis_fields(frame.to_redis_fields())
    assert restored.tracklets[0].body_embedding == (3.0, 4.0)


def test_detection_frame_body_embedding_absent_roundtrips_empty() -> None:
    t = Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 10, 10), confidence=0.9)
    frame = DetectionFrame(
        camera_id=1, seq_id=0, timestamp_ms=0, tracklets=(t,), face_embeddings=()
    )
    restored = DetectionFrame.from_redis_fields(frame.to_redis_fields())
    assert restored.tracklets[0].body_embedding == ()
```

- [ ] **Step 4.2: Run to verify they fail**

```powershell
pytest tests/test_inference_messages.py::test_tracklet_body_embedding_defaults_empty tests/test_inference_messages.py::test_tracklet_body_embedding_stored tests/test_inference_messages.py::test_detection_frame_body_embedding_redis_roundtrip tests/test_inference_messages.py::test_detection_frame_body_embedding_absent_roundtrips_empty -v
```
Expected: `TypeError: Tracklet.__init__() got an unexpected keyword argument 'body_embedding'`

- [ ] **Step 4.3: Update `vms/inference/messages.py`**

In `Tracklet`, add `body_embedding` after `embedding`:
```python
@dataclass(frozen=True)
class Tracklet:
    local_track_id: int
    camera_id: int
    bbox: tuple[int, int, int, int]
    confidence: float
    embedding: tuple[float, ...] = ()
    body_embedding: tuple[float, ...] = ()
```

In `DetectionFrame.to_redis_fields`, add `"body_embedding": list(t.body_embedding)` to the tracklet dict inside the list comprehension:
```python
tracklets_json = json.dumps(
    [
        {
            "local_track_id": t.local_track_id,
            "camera_id": t.camera_id,
            "bbox": list(t.bbox),
            "confidence": t.confidence,
            "embedding": list(t.embedding),
            "body_embedding": list(t.body_embedding),
        }
        for t in self.tracklets
    ]
)
```

In `DetectionFrame.from_redis_fields`, add `body_embedding` to the `Tracklet(...)` constructor inside the tracklets comprehension:
```python
tracklets = tuple(
    Tracklet(
        local_track_id=int(t["local_track_id"]),
        camera_id=int(t["camera_id"]),
        bbox=cast(tuple[int, int, int, int], tuple(int(v) for v in t["bbox"])),
        confidence=float(t["confidence"]),
        embedding=tuple(float(v) for v in t.get("embedding", [])),
        body_embedding=tuple(float(v) for v in t.get("body_embedding", [])),
    )
    for t in raw_tracklets
)
```

- [ ] **Step 4.4: Run to verify they pass**

```powershell
pytest tests/test_inference_messages.py -v
```
Expected: all tests PASS (new + existing).

- [ ] **Step 4.5: Full suite check**

```powershell
pytest --tb=short -q
```

- [ ] **Step 4.6: Commit**

```powershell
git add vms/inference/messages.py tests/test_inference_messages.py
git commit -m "feat(inference): add body_embedding to Tracklet with backward-compat redis serialization"
```

---

## Task 5: BodyEmbedder ONNX Wrapper

**Files:** Create `vms/inference/body_embedder.py`, create `tests/test_inference_body_embedder.py`

OSNet x1.0 Market-1501: input `[1, 3, 256, 128]` RGB float32 (ImageNet-normalized), output `[1, 512]` L2-normalized.

- [ ] **Step 5.1: Write failing tests**

Create `tests/test_inference_body_embedder.py`:

```python
"""Unit tests for BodyEmbedder. Uses a mock ONNX session — no model file required."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from vms.inference.body_embedder import BodyEmbedder


def _mock_session(out_dim: int = 512) -> MagicMock:
    session = MagicMock()
    out = np.random.default_rng(0).standard_normal((1, out_dim)).astype(np.float32)
    session.run.return_value = [out]
    session.get_inputs.return_value = [MagicMock(name="input")]
    return session


def test_body_embedder_returns_512_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.inference.body_embedder.ort.InferenceSession",
        lambda *a, **kw: _mock_session(),
    )
    emb = BodyEmbedder("x.onnx").embed(np.zeros((64, 32, 3), dtype=np.uint8))
    assert isinstance(emb, tuple) and len(emb) == 512


def test_body_embedder_output_is_l2_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.inference.body_embedder.ort.InferenceSession",
        lambda *a, **kw: _mock_session(),
    )
    emb = BodyEmbedder("x.onnx").embed(np.zeros((64, 32, 3), dtype=np.uint8))
    norm = float(np.linalg.norm(np.array(emb, dtype=np.float32)))
    assert abs(norm - 1.0) < 1e-5


def test_body_embedder_tiny_crop_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.inference.body_embedder.ort.InferenceSession",
        lambda *a, **kw: _mock_session(),
    )
    emb = BodyEmbedder("x.onnx").embed(np.zeros((15, 7, 3), dtype=np.uint8))
    assert emb == ()


def test_body_embedder_minimum_crop_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.inference.body_embedder.ort.InferenceSession",
        lambda *a, **kw: _mock_session(),
    )
    emb = BodyEmbedder("x.onnx").embed(np.zeros((16, 8, 3), dtype=np.uint8))
    assert len(emb) == 512
```

- [ ] **Step 5.2: Run to verify they fail**

```powershell
pytest tests/test_inference_body_embedder.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.inference.body_embedder'`

- [ ] **Step 5.3: Create `vms/inference/body_embedder.py`**

```python
"""OSNet body Re-ID embedder — ONNX inference wrapper.

Model: osnet_x1_0 trained on Market-1501, 512-dim L2-normalized output.
Input tensor: [1, 3, 256, 128] float32 RGB, ImageNet mean/std normalized.
Minimum crop size: 16h × 8w pixels; returns () for smaller crops.
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort

logger = logging.getLogger(__name__)

_H = 256
_W = 128
_MIN_H = 16
_MIN_W = 8
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)


class BodyEmbedder:
    """Wraps OSNet ONNX model for 512-dim body appearance embeddings."""

    def __init__(self, model_path: str) -> None:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        self._session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self._input_name: str = self._session.get_inputs()[0].name

    def embed(self, crop_bgr: np.ndarray[Any, Any]) -> tuple[float, ...]:
        """Return 512-dim L2-normalized embedding, or () if crop is too small."""
        h, w = crop_bgr.shape[:2]
        if h < _MIN_H or w < _MIN_W:
            return ()
        resized = cv2.resize(crop_bgr, (_W, _H), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        chw = np.transpose(rgb, (2, 0, 1))
        chw = (chw - _MEAN) / _STD
        tensor = chw[np.newaxis]  # (1, 3, 256, 128)
        output: list[np.ndarray[Any, Any]] = self._session.run(
            None, {self._input_name: tensor}
        )
        vec = output[0][0].astype(np.float32)
        vec /= np.linalg.norm(vec) + 1e-8
        return tuple(float(x) for x in vec)
```

- [ ] **Step 5.4: Run to verify they pass**

```powershell
pytest tests/test_inference_body_embedder.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 5.5: Full suite check**

```powershell
pytest --tb=short -q
```

- [ ] **Step 5.6: Commit**

```powershell
git add vms/inference/body_embedder.py tests/test_inference_body_embedder.py
git commit -m "feat(inference): BodyEmbedder OSNet ONNX wrapper"
```

---

## Task 6: Wire BodyEmbedder into InferenceEngine

**Files:** Modify `vms/inference/engine.py`, add tests to `tests/test_inference_engine.py`

- [ ] **Step 6.1: Write failing tests**

Append to `tests/test_inference_engine.py`:

```python
def test_extract_body_embeddings_populates_tracklets() -> None:
    from unittest.mock import MagicMock
    import numpy as np
    from vms.inference.engine import _extract_body_embeddings
    from vms.inference.messages import Tracklet

    embedder = MagicMock()
    embedder.embed.return_value = tuple([0.1] * 512)

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracklets = (
        Tracklet(local_track_id=1, camera_id=1, bbox=(10, 20, 60, 120), confidence=0.9),
        Tracklet(local_track_id=2, camera_id=1, bbox=(200, 100, 280, 300), confidence=0.8),
    )
    result = _extract_body_embeddings(frame, tracklets, embedder)
    assert len(result) == 2
    assert result[0].body_embedding == tuple([0.1] * 512)
    assert result[1].body_embedding == tuple([0.1] * 512)
    assert embedder.embed.call_count == 2


def test_extract_body_embeddings_no_embedder_returns_empty() -> None:
    import numpy as np
    from vms.inference.engine import _extract_body_embeddings
    from vms.inference.messages import Tracklet

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracklets = (
        Tracklet(local_track_id=1, camera_id=1, bbox=(10, 20, 60, 120), confidence=0.9),
    )
    result = _extract_body_embeddings(frame, tracklets, None)
    assert result[0].body_embedding == ()


def test_extract_body_embeddings_clamps_bbox_to_frame() -> None:
    """Out-of-bounds bbox is clamped — no array index error."""
    from unittest.mock import MagicMock
    import numpy as np
    from vms.inference.engine import _extract_body_embeddings
    from vms.inference.messages import Tracklet

    embedder = MagicMock()
    embedder.embed.return_value = ()

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # bbox extends beyond frame
    tracklets = (
        Tracklet(local_track_id=1, camera_id=1, bbox=(-10, -10, 200, 200), confidence=0.9),
    )
    result = _extract_body_embeddings(frame, tracklets, embedder)
    assert len(result) == 1  # no crash
```

- [ ] **Step 6.2: Run to verify they fail**

```powershell
pytest tests/test_inference_engine.py::test_extract_body_embeddings_populates_tracklets tests/test_inference_engine.py::test_extract_body_embeddings_no_embedder_returns_empty tests/test_inference_engine.py::test_extract_body_embeddings_clamps_bbox_to_frame -v
```
Expected: `ImportError: cannot import name '_extract_body_embeddings'`

- [ ] **Step 6.3: Add `_extract_body_embeddings` to `vms/inference/engine.py`**

Add this import at the top of `vms/inference/engine.py` alongside existing imports:

```python
from vms.inference.body_embedder import BodyEmbedder
```

Add this standalone function (place it near `_associate_faces`):

```python
def _extract_body_embeddings(
    frame_bgr: np.ndarray[Any, Any],
    tracklets: tuple[Tracklet, ...],
    body_embedder: BodyEmbedder | None,
) -> tuple[Tracklet, ...]:
    """Return tracklets with body_embedding populated from person bbox crops.

    Bbox is clamped to frame dimensions before cropping.
    Returns original tracklets unchanged when body_embedder is None.
    """
    if body_embedder is None:
        return tracklets
    h, w = frame_bgr.shape[:2]
    result: list[Tracklet] = []
    for t in tracklets:
        x1, y1, x2, y2 = t.bbox
        x1c, y1c = max(0, x1), max(0, y1)
        x2c, y2c = min(w, x2), min(h, y2)
        crop = frame_bgr[y1c:y2c, x1c:x2c]
        body_emb = body_embedder.embed(crop) if crop.size > 0 else ()
        result.append(
            Tracklet(
                local_track_id=t.local_track_id,
                camera_id=t.camera_id,
                bbox=t.bbox,
                confidence=t.confidence,
                embedding=t.embedding,
                body_embedding=body_emb,
            )
        )
    return tuple(result)
```

- [ ] **Step 6.4: Add `body_embedder` parameter to `InferenceEngine.__init__`**

The existing signature ends with `violence: ViolenceModel | None = None`. Add after it:

```python
body_embedder: BodyEmbedder | None = None,
```

Store as `self._body_embedder = body_embedder`.

- [ ] **Step 6.5: Call `_extract_body_embeddings` in `_process_one_message`**

After tracklets are produced by `PerCameraTracker.update()` and before `DetectionFrame` is constructed, add:

```python
tracklets = _extract_body_embeddings(frame_bgr, tracklets, self._body_embedder)
```

- [ ] **Step 6.6: Run tests to verify they pass**

```powershell
pytest tests/test_inference_engine.py -v
```
Expected: all pass.

- [ ] **Step 6.7: Full suite check**

```powershell
pytest --tb=short -q
```

- [ ] **Step 6.8: Lint + type-check**

```powershell
ruff check vms/inference/engine.py vms/inference/body_embedder.py
mypy vms/inference/engine.py vms/inference/body_embedder.py
black vms/inference/engine.py vms/inference/body_embedder.py
```

- [ ] **Step 6.9: Commit**

```powershell
git add vms/inference/engine.py vms/inference/body_embedder.py tests/test_inference_engine.py
git commit -m "feat(inference): wire BodyEmbedder into InferenceEngine for body Re-ID"
```

---

## Task 7: E2E Crowd Density Integration Tests

**Files:** Create `tests/test_e2e_crowd_reid.py`

Validates end-to-end re-ID stability under simulated crowd: 20 persons × 4 cameras, noisy embeddings (uniform-dressed factory workers), confirmed gallery promotion, and eviction bounds.

- [ ] **Step 7.1: Write the integration tests**

Create `tests/test_e2e_crowd_reid.py`:

```python
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


def _person_emb(person_id: int) -> np.ndarray[object, np.dtype[np.float32]]:
    v = np.random.default_rng(person_id * 100).standard_normal(512).astype(np.float32)
    v /= np.linalg.norm(v) + 1e-8
    return v


def _noisy(emb: np.ndarray[object, np.dtype[np.float32]], noise: float = 0.03, seed: int = 0) -> tuple[float, ...]:
    v = emb + np.random.default_rng(seed).standard_normal(512).astype(np.float32) * noise
    v /= np.linalg.norm(v) + 1e-8
    return tuple(float(x) for x in v)


def _settings(**overrides: object) -> object:
    from vms.config import Settings
    defaults: dict[str, object] = dict(
        db_url="x", jwt_secret="x",
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
    """20 persons confirmed on cam0, then seen on cams 1-3 — all get same global_track_id."""
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _settings())
    engine = _make_engine()
    n_persons, n_cameras = 20, 4
    person_embs = [_person_emb(p) for p in range(n_persons)]

    # Phase 1: confirm each person on camera 0 (4 sightings each)
    gids: dict[int, uuid.UUID] = {}
    for p in range(n_persons):
        for s in range(4):
            gid = engine.assign_global_track_id(
                camera_id=0, local_track_id=p,
                embedding=_noisy(person_embs[p], noise=0.02, seed=s),
            )
            gids[p] = gid

    for p in range(n_persons):
        assert engine._registry[(0, p)].confirmed, f"person {p} not confirmed"

    # Phase 2: each person appears on cameras 1-3 with noisy embeddings
    for cam in range(1, n_cameras):
        for p in range(n_persons):
            gid = engine.assign_global_track_id(
                camera_id=cam, local_track_id=p,
                embedding=_noisy(person_embs[p], noise=0.02, seed=cam * 100 + p),
            )
            assert gid == gids[p], (
                f"person {p} on cam {cam}: expected {gids[p]}, got {gid}"
            )


@pytest.mark.integration
def test_crowd_eviction_bounds_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """100 unconfirmed tracklets are all evicted after reid_stale_ms expires."""
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _settings(
        reid_stale_ms=5_000,
        reid_confirmed_stale_ms=10_000,
    ))
    engine = _make_engine()
    for i in range(100):
        engine.assign_global_track_id(1, i, _noisy(_person_emb(i)))

    evicted = engine.evict_stale(
        now_ms=engine._registry[(1, 0)].last_seen_ms + 6_000
    )
    assert evicted == 100
    assert len(engine._registry) == 0


@pytest.mark.integration
def test_confirmed_tracks_not_evicted_at_unconfirmed_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confirmed tracks survive past reid_stale_ms but are evicted at reid_confirmed_stale_ms."""
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _settings(
        reid_confirm_after_sightings=2,
        reid_stale_ms=1_000,
        reid_confirmed_stale_ms=30_000,
    ))
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
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _settings(
        reid_confirm_after_sightings=2,
        reid_cross_cam_sim=0.65,
        reid_confirmed_sim=0.60,
        reid_margin=0.0,
        reid_camera_topology_json='{"1-2": {"min_ms": 60000, "max_ms": 300000}}',
    ))
    engine = _make_engine()
    base = _noisy(_person_emb(0), noise=0.001)
    near = _noisy(_person_emb(0), noise=0.002, seed=1)

    gid1 = engine.assign_global_track_id(1, 1, base)
    engine.assign_global_track_id(1, 1, near)  # confirm
    assert engine._registry[(1, 1)].confirmed

    # Instantly appears on cam2 — elapsed ~0ms < min_ms=60000 → reject
    gid2 = engine.assign_global_track_id(2, 1, near)
    assert gid1 != gid2
```

- [ ] **Step 7.2: Run to verify they pass**

```powershell
pytest tests/test_e2e_crowd_reid.py -v -m integration
```
Expected: all 4 tests PASS.

- [ ] **Step 7.3: Run full suite (all 300+ tests)**

```powershell
pytest --tb=short -q
```
Expected: all pass.

- [ ] **Step 7.4: Final lint + type-check**

```powershell
ruff check vms/ tests/
mypy vms/
black vms/ tests/
```

- [ ] **Step 7.5: Commit**

```powershell
git add tests/test_e2e_crowd_reid.py
git commit -m "test(identity): E2E crowd re-ID stability + eviction + topology integration tests"
```

---

## Post-Plan: OSNet Model Download

OSNet is not in `models/` yet. After the plan is complete, download and register it:

```powershell
# Export OSNet to ONNX (requires torchreid + torch):
# pip install torchreid torch onnx
# python scripts/export_osnet_onnx.py   (write this script when needed)
# Then add to models/manifest.json and verify SHA-256.
```

The `BodyEmbedder` loads from `VMS_BODY_EMBEDDER_MODEL=models/osnet_x1_0_market1501.onnx` (or a hardcoded default). Until the model is downloaded, `InferenceEngine` is constructed with `body_embedder=None`, which means all `Tracklet.body_embedding` will be `()` — safe fallback, no crash.

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|---|---|
| Gallery buffer (rolling N=8 embeddings per tracklet) | Task 3 |
| Confirmed promotion after N sightings | Task 3 |
| Two-tier similarity threshold (confirmed vs unconfirmed) | Task 3 |
| Spatial-temporal gate (`CameraTopology`) | Task 2 |
| Two-tier stale TTL (confirmed 10 min, unconfirmed 5 min) | Task 3 (`evict_stale`) |
| Body embedding field on `Tracklet` + Redis serialization | Task 4 |
| `BodyEmbedder` ONNX wrapper (OSNet) | Task 5 |
| Wire body embedder into `InferenceEngine` | Task 6 |
| Body gallery fallback in `IdentityEngine` | Task 3 (`body_gallery`) |
| E2E crowd density integration tests | Task 7 |

### Placeholder Scan — None Found

All steps include complete code. No TBD/TODO/placeholder steps.

### Type Consistency

- `_TrackletEntry.gallery: list[np.ndarray[Any, Any]]` — consistent Tasks 3, 7
- `_TrackletEntry.body_gallery: list[np.ndarray[Any, Any]]` — consistent Tasks 3, 7
- `assign_global_track_id(..., body_embedding: tuple[float, ...] | None = None)` — default `None` preserves all existing callers
- `_gallery_sim(query_norm, gallery)` — same signature used in both face and body paths
- `BodyEmbedder.embed(crop_bgr) -> tuple[float, ...]` — matches `Tracklet.body_embedding` type exactly
- `_extract_body_embeddings(frame, tracklets, embedder | None) -> tuple[Tracklet, ...]` — consistent with `InferenceEngine._process_one_message` usage
