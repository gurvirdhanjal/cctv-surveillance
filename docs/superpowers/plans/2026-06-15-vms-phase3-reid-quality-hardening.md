# ReID Quality Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [x]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Prevent the ReID error cascade (bad crop → corrupted gallery → wrong enrollment →
polluted FAISS → amplified future errors) by adding three layers of protection:
(A) hybrid crop quality estimation — heuristic hard-reject gates + pre-norm embedding norm as
soft quality signal; (B) temporal quality-windowed gallery sub-sampling to stop correlated
consecutive frames flooding the 8-slot gallery; (C) cosine-dedup check at DB enrollment time
to block near-duplicate embeddings from entering `person_embeddings`.

**Architecture:**
- **Quality gate** lives in `vms/inference/embedder.py` (face) and `vms/inference/engine.py`
  (body). Hard rejects happen before embedding; pre-norm norm is captured and propagated on
  `FaceWithEmbedding.face_quality_norm` and `Tracklet.body_quality_norm`.
- **Temporal windowed gallery** replaces the FIFO append in
  `vms/identity/engine.py _update_galleries`. Each `_TrackletEntry` tracks the current
  time-window start and best quality seen; within a window only the highest-quality embedding
  is kept; a new window always adds.
- **Enrollment dedup** lives in `vms/api/routes/persons.py`. Before writing a new row to
  `person_embeddings`, load existing embeddings for that person and reject if any exceeds
  `reid_enroll_dedup_sim`.

All new thresholds go into `vms/config.py` with conservative defaults so the system behaves
exactly as before until thresholds are calibrated on real footage.

**Tech Stack:** Python 3.10.11 · NumPy 1.26 · OpenCV 4.9 · SQLAlchemy 2.x · pytest 8.x
(no new dependencies)

**Spec refs:**
- v2 §K identity hardening invariants
- v2 §G capacity model (≤ 50 ms/frame budget — quality checks must be O(1) per crop)
- `docs/superpowers/specs/2026-05-27-vms-production-readiness.md` §6 capacity claims
- CLAUDE.md §17 architectural invariants (DB before FAISS; thresholds in config)
- CLAUDE.md §0.5 mandatory `/advisor` before tightening `reid_*`/`adaface_*` thresholds

**Advisor decision record:** `/advisor` session 2026-06-15 recommended:
- Decision A: Hybrid (heuristics + embedding norm) over pure heuristics or pure learned score
- Decision B: Temporal spacing + quality filter over cosine-distance threshold or reservoir sampling
- Decision C: Enrollment-only dedup over full gallery health (full consolidation/pruning deferred)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `vms/config.py` | 3 new settings; wire `min_blur` |
| Modify | `vms/inference/messages.py` | `face_quality_norm` on `FaceWithEmbedding`; `body_quality_norm` on `Tracklet`; serialization round-trip |
| Modify | `vms/inference/embedder.py` | Blur hard-reject gate; capture pre-norm L2; populate `face_quality_norm` |
| Modify | `vms/inference/engine.py` | Body blur gate; capture body pre-norm L2; populate `body_quality_norm` on `Tracklet` |
| Modify | `vms/identity/engine.py` | Replace FIFO `_update_galleries` with temporal quality-windowed logic; add window state to `_TrackletEntry` |
| Modify | `vms/api/routes/persons.py` | Enrollment dedup check before `person_embeddings` INSERT |
| Modify | `tests/test_inference_messages.py` | Round-trip tests for new DTO fields |
| Modify | `tests/test_inference_embedder.py` | Blur reject test; quality norm populated test |
| Create | `tests/test_identity_quality_gallery.py` | Window sub-sampling: within-window dedup, cross-window add, quality priority |
| Create | `tests/test_persons_enroll_dedup.py` | Enrollment dedup: near-dup skipped, distinct added, exact threshold boundary |

---

## Pre-flight

- [x] **Baseline test count**

```powershell
python -m pytest tests/ -q --tb=no
```

Record the number. All tasks must leave this green.

---

## Task 1: New Config Settings

**Files:** Modify `vms/config.py`

Three new settings plus wiring the dormant `min_blur`. All defaults are conservative —
they match current behaviour exactly (no rejections) until calibrated on real footage.

- [x] **Step 1.1: Write failing tests**

Append to `tests/test_config.py`:

```python
def test_settings_reid_quality_defaults() -> None:
    from vms.config import Settings
    s = Settings(db_url="postgresql://x", jwt_secret="x")
    # min_blur already exists; these three must be new
    assert s.reid_quality_window_s == 2.0
    assert s.reid_quality_norm_floor == 0.0
    assert s.reid_enroll_dedup_sim == 0.95
```

- [x] **Step 1.2: Confirm failure**

```powershell
pytest tests/test_config.py::test_settings_reid_quality_defaults -v
```

Expected: `AttributeError` on one of the new fields.

- [x] **Step 1.3: Add settings to `vms/config.py`**

After the `reid_body_cross_cam_sim` line, add:

```python
    # ReID quality hardening (Phase 3) — all defaults conservative (no-op until calibrated)
    # Blur hard-reject: min_blur already defined above (Laplacian variance; 25.0 is unused placeholder)
    reid_quality_window_s: float = 2.0        # temporal window; keep best crop per window
    reid_quality_norm_floor: float = 0.0      # pre-norm L2 floor; 0.0 = accept all
    reid_enroll_dedup_sim: float = 0.95       # cosine sim ceiling for enrollment dedup
```

- [x] **Step 1.4: Confirm pass**

```powershell
pytest tests/test_config.py::test_settings_reid_quality_defaults -v
```

Expected: PASS.

- [x] **Step 1.5: Full suite check**

```powershell
pytest --tb=short -q
```

Expected: all existing tests still pass.

- [x] **Step 1.6: Commit**

```
feat(config): add reid quality hardening settings
```

---

## Task 2: Quality Norm Fields on Message DTOs

**Files:** Modify `vms/inference/messages.py`

Add `face_quality_norm` to `FaceWithEmbedding` and `body_quality_norm` to `Tracklet`.
Default `1.0` means "full quality" — existing callers that don't populate it are unaffected.
Add serialization/deserialization so the values survive the Redis round-trip.

- [x] **Step 2.1: Write failing tests**

Append to `tests/test_inference_messages.py`:

```python
def test_face_with_embedding_quality_norm_default() -> None:
    f = FaceWithEmbedding(
        bbox=(0, 0, 100, 100), confidence=0.9, embedding=(0.1,) * 512
    )
    assert f.face_quality_norm == 1.0


def test_tracklet_body_quality_norm_default() -> None:
    t = Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 50, 100), confidence=0.8)
    assert t.body_quality_norm == 1.0


def test_detection_frame_round_trip_quality_norms() -> None:
    """Quality norms survive Redis serialization round-trip."""
    t = Tracklet(
        local_track_id=1,
        camera_id=2,
        bbox=(0, 0, 50, 100),
        confidence=0.8,
        body_quality_norm=0.73,
    )
    f = FaceWithEmbedding(
        bbox=(10, 10, 50, 50),
        confidence=0.9,
        embedding=(0.1,) * 512,
        face_quality_norm=0.55,
    )
    frame = DetectionFrame(
        camera_id=2, seq_id=1, timestamp_ms=1000,
        tracklets=(t,), face_embeddings=(f,),
    )
    fields = frame.to_redis_fields()
    restored = DetectionFrame.from_redis_fields(fields)
    assert abs(restored.tracklets[0].body_quality_norm - 0.73) < 1e-4
    assert abs(restored.face_embeddings[0].face_quality_norm - 0.55) < 1e-4
```

- [x] **Step 2.2: Confirm failure**

```powershell
pytest tests/test_inference_messages.py -k "quality_norm" -v
```

Expected: `AttributeError`.

- [x] **Step 2.3: Add `face_quality_norm` to `FaceWithEmbedding`**

In `vms/inference/messages.py`, add the field to `FaceWithEmbedding`:

```python
@dataclass(frozen=True)
class FaceWithEmbedding:
    bbox: tuple[int, int, int, int]
    confidence: float
    embedding: tuple[float, ...]
    keypoints: tuple[tuple[float, float], ...] = ()
    face_quality_norm: float = 1.0  # pre-L2-normalisation embedding norm; 1.0 = full quality
```

- [x] **Step 2.4: Add `body_quality_norm` to `Tracklet`**

In `vms/inference/messages.py`, add after `ppe_mask_conf`:

```python
    body_quality_norm: float = 1.0  # pre-L2-normalisation body embedding norm; 1.0 = full quality
```

- [x] **Step 2.5: Update `to_redis_fields` serialization**

In `DetectionFrame.to_redis_fields`, add `"body_quality_norm"` to the tracklet dict and
`"face_quality_norm"` to the face dict:

Tracklet dict entry (add after `ppe_mask_conf`):
```python
                    "body_quality_norm": t.body_quality_norm,
```

Face dict entry (add after `"embedding"`):
```python
                    "face_quality_norm": f.face_quality_norm,
```

- [x] **Step 2.6: Update `from_redis_fields` deserialization**

In the `Tracklet(...)` constructor call inside `from_redis_fields`, add:
```python
                body_quality_norm=float(t.get("body_quality_norm", 1.0)),
```

In the `FaceWithEmbedding(...)` constructor call, add:
```python
                face_quality_norm=float(f.get("face_quality_norm", 1.0)),
```

- [x] **Step 2.7: Confirm tests pass**

```powershell
pytest tests/test_inference_messages.py -v
```

Expected: all pass.

- [x] **Step 2.8: Full suite check**

```powershell
pytest --tb=short -q
```

- [x] **Step 2.9: Commit**

```
feat(inference): add face_quality_norm and body_quality_norm to message DTOs
```

---

## Task 3: Hard-Reject Gates + Pre-Norm Capture in Face Embedder

**Files:** Modify `vms/inference/embedder.py`

Wire the dormant `min_blur` threshold. Compute Laplacian variance on the face crop and
reject (return `None`) when below threshold. Capture pre-normalisation L2 and return it
via `FaceWithEmbedding.face_quality_norm`. Both changes are O(1) per crop.

- [x] **Step 3.1: Write failing tests**

Append to `tests/test_inference_embedder.py`:

```python
def test_embedder_rejects_blurry_crop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Laplacian variance below min_blur → embed() returns None."""
    import numpy as np
    from vms.inference.embedder import AdaFaceEmbedder
    from vms.inference.messages import FaceWithEmbedding

    emb = AdaFaceEmbedder.__new__(AdaFaceEmbedder)
    emb._min_face_px = 10
    emb._min_blur = 25.0

    # Uniform grey crop → Laplacian variance ≈ 0 (very blurry)
    blurry_frame = np.full((200, 200, 3), 128, dtype=np.uint8)
    face = FaceWithEmbedding(bbox=(0, 0, 80, 80), confidence=0.9, embedding=())

    # Patch _preprocess + _sess so we don't need real model weights
    monkeypatch.setattr(emb, "_preprocess", lambda crop: np.zeros((1, 3, 112, 112)))

    class _FakeSess:
        def run(self, _out, _inp):  # type: ignore[override]
            return [np.random.randn(1, 512).astype(np.float32)]

    emb._sess = _FakeSess()
    emb._input_name = "input"

    result = emb.embed(face, blurry_frame)
    assert result is None


def test_embedder_populates_quality_norm(monkeypatch: pytest.MonkeyPatch) -> None:
    """face_quality_norm is pre-norm L2 of raw embedding output."""
    import numpy as np
    from vms.inference.embedder import AdaFaceEmbedder
    from vms.inference.messages import FaceWithEmbedding

    emb = AdaFaceEmbedder.__new__(AdaFaceEmbedder)
    emb._min_face_px = 10
    emb._min_blur = 0.0  # disable blur reject

    # Sharp crop: checkerboard → high Laplacian variance
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    frame[::2, ::2] = 255

    face = FaceWithEmbedding(bbox=(0, 0, 100, 100), confidence=0.9, embedding=())

    raw_vec = np.full((1, 512), 2.0, dtype=np.float32)  # norm = 2.0 * sqrt(512)
    expected_norm = float(np.linalg.norm(raw_vec[0]))

    monkeypatch.setattr(emb, "_preprocess", lambda crop: np.zeros((1, 3, 112, 112)))

    class _FakeSess:
        def run(self, _out, _inp):  # type: ignore[override]
            return [raw_vec.copy()]

    emb._sess = _FakeSess()
    emb._input_name = "input"

    result = emb.embed(face, frame)
    assert result is not None
    assert abs(result.face_quality_norm - expected_norm) < 0.01
```

- [x] **Step 3.2: Confirm failure**

```powershell
pytest tests/test_inference_embedder.py -k "blur or quality_norm" -v
```

Expected: `AttributeError` on `_min_blur` or assertion failure.

- [x] **Step 3.3: Modify `vms/inference/embedder.py`**

In `AdaFaceEmbedder.__init__` (or the factory `load` method that constructs it), store
`min_blur` from settings:

```python
self._min_blur: float = get_settings().min_blur
```

In `AdaFaceEmbedder.embed`, after the crop is extracted and before `_preprocess`, add:

```python
        # Hard-reject blurry crops (Laplacian variance gate).
        lap_var = float(cv2.Laplacian(crop, cv2.CV_64F).var())
        if lap_var < self._min_blur:
            return None
```

After `emb_array = raw[0][0].astype(np.float32)`, capture the pre-norm L2 and pass it
through:

```python
        norm = np.linalg.norm(emb_array)
        quality_norm = float(norm)          # pre-normalisation L2 — quality proxy
        if norm > 0:
            emb_array = emb_array / norm
        embedding = tuple(float(v) for v in emb_array)
        return FaceWithEmbedding(
            bbox=face.bbox,
            confidence=face.confidence,
            embedding=embedding,
            face_quality_norm=quality_norm,
        )
```

- [x] **Step 3.4: Confirm tests pass**

```powershell
pytest tests/test_inference_embedder.py -v
```

Expected: all pass including new tests.

- [x] **Step 3.5: Full suite check**

```powershell
pytest --tb=short -q
```

- [x] **Step 3.6: Commit**

```
feat(embedder): blur hard-reject gate + pre-norm quality signal on face embeddings
```

---

## Task 4: Body Blur Gate + Quality Norm in Inference Engine

**Files:** Modify `vms/inference/engine.py`

Add a `_blur_score` helper. Before calling `body_embedder.embed()`, compute Laplacian
variance on the person crop; if below `min_blur`, skip body embedding for that tracklet.
Capture body pre-norm L2 from `BodyEmbedder.embed()` and set `body_quality_norm` on the
`Tracklet` DTO.

Note: `BodyEmbedder` (torchreid wrapper) L2-normalises internally. We need to either:
(a) modify `BodyEmbedder.embed()` to return the pre-norm value alongside the embedding, or
(b) compute it as `np.linalg.norm(raw_output)` before the normalisation step inside
`body_embedder.py`. Option (b) keeps the interface change minimal.

- [x] **Step 4.1: Modify `vms/inference/body_embedder.py`**

`BodyEmbedder.embed()` currently returns `tuple[float, ...]`. Change the signature to
return `tuple[tuple[float, ...], float]` — embedding + pre-norm quality:

```python
def embed(self, crop_bgr: np.ndarray[Any, np.dtype[Any]]) -> tuple[tuple[float, ...], float]:
    """Return (L2-normalised embedding, pre-norm L2)."""
    ...
    feat = self._extractor(img)[0]               # shape (512,)
    quality_norm = float(np.linalg.norm(feat))
    if quality_norm > 0:
        feat = feat / quality_norm
    return tuple(float(v) for v in feat), quality_norm
```

Update the `_NullBodyEmbedder` stub to return `((), 0.0)`.

- [x] **Step 4.2: Add blur helper to `vms/inference/engine.py`**

Add a module-level helper (no per-frame allocation):

```python
def _blur_score(crop_bgr: np.ndarray[Any, np.dtype[Any]]) -> float:
    """Laplacian variance — higher = sharper."""
    return float(cv2.Laplacian(crop_bgr, cv2.CV_64F).var())
```

- [x] **Step 4.3: Update body embedding call site in `engine.py`**

In the section that calls `body_embedder.embed(crop)`, replace with:

```python
    blur = _blur_score(body_crop)
    if blur >= settings.min_blur:
        body_emb_tuple, body_quality = self._body_embedder.embed(body_crop)
    else:
        body_emb_tuple, body_quality = (), 0.0
```

Then when constructing the `Tracklet`, set `body_quality_norm=body_quality`.

- [x] **Step 4.4: Update all call sites that unpack `BodyEmbedder.embed()`**

Search for `body_embedder.embed(` in the codebase and update each call to unpack the
two-tuple. Run mypy to catch any missed sites:

```powershell
mypy vms/ --strict
```

- [x] **Step 4.5: Confirm tests pass**

```powershell
pytest tests/ -v --tb=short
```

- [x] **Step 4.6: Commit**

```
feat(inference): body blur gate + body_quality_norm from pre-norm L2
```

---

## Task 5: Temporal Quality-Windowed Gallery Sub-sampling

**Files:** Modify `vms/identity/engine.py`

Replace the FIFO append in `_update_galleries` with per-dimension time-windowed
best-pick logic. Within each `reid_quality_window_s` second window, only the
highest-quality embedding is kept. A new window always appends. FIFO eviction
(`reid_gallery_size`) still applies across windows — oldest window drops first.

The `_TrackletEntry` dataclass gains four tracking fields:
- `face_window_start_ms: int = 0`
- `face_window_best_quality: float = -1.0`
- `body_window_start_ms: int = 0`
- `body_window_best_quality: float = -1.0`

- [x] **Step 5.1: Write failing tests**

Create `tests/test_identity_quality_gallery.py`:

```python
"""Tests for temporal quality-windowed gallery sub-sampling."""
from __future__ import annotations
import pytest


def _make_engine() -> object:
    """Return a minimal IdentityEngine with no FAISS/DB deps."""
    from unittest.mock import MagicMock
    from vms.identity.engine import IdentityEngine
    engine = IdentityEngine.__new__(IdentityEngine)
    engine._registry = {}
    engine._topology = None
    engine._settings = None
    return engine


def _make_entry() -> object:
    from vms.identity.engine import _TrackletEntry
    import uuid
    return _TrackletEntry(
        global_track_id=uuid.uuid4(),
        camera_id=1,
        local_track_id=42,
        first_seen_ms=0,
        last_seen_ms=0,
    )


class _FakeSettings:
    reid_gallery_size = 8
    reid_confirm_after_sightings = 3
    reid_quality_window_s = 2.0
    reid_quality_norm_floor = 0.0


def test_within_window_lower_quality_rejected() -> None:
    """Second embedding in same window with lower quality must not replace first."""
    engine = _make_engine()
    entry = _make_entry()
    s = _FakeSettings()

    high_q = (0.5,) * 512
    low_q  = (0.1,) * 512

    engine._update_galleries(entry, high_q, None, s, timestamp_ms=1000, face_quality=10.0, body_quality=0.0)
    engine._update_galleries(entry, low_q,  None, s, timestamp_ms=1500, face_quality=5.0,  body_quality=0.0)

    assert len(entry.gallery) == 1
    assert entry.gallery[0][0] == pytest.approx(0.5, abs=1e-4)


def test_within_window_higher_quality_replaces() -> None:
    """Second embedding in same window with higher quality replaces first."""
    engine = _make_engine()
    entry = _make_entry()
    s = _FakeSettings()

    low_q  = (0.1,) * 512
    high_q = (0.5,) * 512

    engine._update_galleries(entry, low_q,  None, s, timestamp_ms=1000, face_quality=3.0,  body_quality=0.0)
    engine._update_galleries(entry, high_q, None, s, timestamp_ms=1500, face_quality=9.0, body_quality=0.0)

    assert len(entry.gallery) == 1
    assert entry.gallery[0][0] == pytest.approx(0.5, abs=1e-4)


def test_new_window_always_appends() -> None:
    """Embedding in a new window always appends regardless of quality."""
    engine = _make_engine()
    entry = _make_entry()
    s = _FakeSettings()

    emb1 = (0.5,) * 512
    emb2 = (0.2,) * 512

    engine._update_galleries(entry, emb1, None, s, timestamp_ms=0,    face_quality=9.0, body_quality=0.0)
    engine._update_galleries(entry, emb2, None, s, timestamp_ms=3000, face_quality=1.0, body_quality=0.0)  # new window

    assert len(entry.gallery) == 2


def test_gallery_respects_max_size() -> None:
    """Gallery never exceeds reid_gallery_size slots."""
    engine = _make_engine()
    entry = _make_entry()
    s = _FakeSettings()

    for i in range(20):
        emb = (float(i),) + (0.0,) * 511
        engine._update_galleries(
            entry, emb, None, s,
            timestamp_ms=i * 3000,  # each in a new window
            face_quality=float(i),
            body_quality=0.0,
        )

    assert len(entry.gallery) <= s.reid_gallery_size


def test_quality_norm_floor_rejects_low_norm() -> None:
    """Embeddings with quality below reid_quality_norm_floor are discarded."""
    engine = _make_engine()
    entry = _make_entry()

    class _StrictSettings(_FakeSettings):
        reid_quality_norm_floor = 5.0  # require quality >= 5.0

    emb = (0.3,) * 512
    engine._update_galleries(entry, emb, None, _StrictSettings(), timestamp_ms=0, face_quality=2.0, body_quality=0.0)

    assert len(entry.gallery) == 0  # rejected by norm floor
```

- [x] **Step 5.2: Confirm failure**

```powershell
pytest tests/test_identity_quality_gallery.py -v
```

Expected: `TypeError` or `AttributeError` on the new `_update_galleries` signature.

- [x] **Step 5.3: Add window state fields to `_TrackletEntry`**

In `vms/identity/engine.py`, find the `_TrackletEntry` dataclass definition and add:

```python
    face_window_start_ms: int = 0
    face_window_best_quality: float = -1.0
    body_window_start_ms: int = 0
    body_window_best_quality: float = -1.0
```

- [x] **Step 5.4: Replace `_update_galleries` with windowed logic**

```python
def _update_galleries(
    self,
    entry: _TrackletEntry,
    embedding: tuple[float, ...] | None,
    body_embedding: tuple[float, ...] | None,
    settings: Any,
    timestamp_ms: int,
    face_quality: float,
    body_quality: float,
) -> None:
    window_ms = int(settings.reid_quality_window_s * 1000)
    norm_floor: float = settings.reid_quality_norm_floor

    if embedding:
        if face_quality >= norm_floor:
            in_window = (timestamp_ms - entry.face_window_start_ms) < window_ms
            if in_window:
                if face_quality > entry.face_window_best_quality:
                    # Replace last entry in gallery (same window, better crop)
                    if entry.gallery:
                        entry.gallery[-1] = np.array(embedding, dtype=np.float32)
                    else:
                        entry.gallery.append(np.array(embedding, dtype=np.float32))
                    entry.face_window_best_quality = face_quality
                # else: same window, lower quality — discard
            else:
                # New window: always append
                entry.gallery.append(np.array(embedding, dtype=np.float32))
                if len(entry.gallery) > settings.reid_gallery_size:
                    entry.gallery = entry.gallery[-settings.reid_gallery_size:]
                entry.face_window_start_ms = timestamp_ms
                entry.face_window_best_quality = face_quality

    if body_embedding:
        if body_quality >= norm_floor:
            in_window = (timestamp_ms - entry.body_window_start_ms) < window_ms
            if in_window:
                if body_quality > entry.body_window_best_quality:
                    if entry.body_gallery:
                        entry.body_gallery[-1] = np.array(body_embedding, dtype=np.float32)
                    else:
                        entry.body_gallery.append(np.array(body_embedding, dtype=np.float32))
                    entry.body_window_best_quality = body_quality
            else:
                entry.body_gallery.append(np.array(body_embedding, dtype=np.float32))
                if len(entry.body_gallery) > settings.reid_gallery_size:
                    entry.body_gallery = entry.body_gallery[-settings.reid_gallery_size:]
                entry.body_window_start_ms = timestamp_ms
                entry.body_window_best_quality = body_quality

    if embedding or body_embedding:
        entry.sighting_count += 1
        if (
            not entry.confirmed
            and entry.sighting_count >= settings.reid_confirm_after_sightings
        ):
            entry.confirmed = True
```

- [x] **Step 5.5: Update all call sites of `_update_galleries`**

Find every call to `self._update_galleries(...)` in `engine.py` and add the three new
keyword arguments: `timestamp_ms=`, `face_quality=`, `body_quality=`. Pass the
`timestamp_ms` from the `DetectionFrame` and quality norms from the tracklet/face DTOs.

Run mypy to catch missed call sites:

```powershell
mypy vms/ --strict
```

- [x] **Step 5.6: Confirm tests pass**

```powershell
pytest tests/test_identity_quality_gallery.py -v
pytest tests/test_identity_engine.py -v
```

Expected: all pass.

- [x] **Step 5.7: Full suite check**

```powershell
pytest --tb=short -q
```

- [x] **Step 5.8: Commit**

```
feat(identity): temporal quality-windowed gallery sub-sampling
```

---

## Task 6: Enrollment Dedup Check

**Files:** Modify `vms/api/routes/persons.py`

Before writing a new row to `person_embeddings`, load existing embeddings for that person
and compute cosine similarity. If any existing embedding exceeds `reid_enroll_dedup_sim`,
return `200 OK` with `{"enrolled": False, "reason": "near_duplicate"}` instead of
inserting. This stops near-duplicate embeddings from entering the FAISS index.

The check uses the L2-normalised embeddings already stored in DB (same form as FAISS
search) so no new model is needed.

- [x] **Step 6.1: Write failing tests**

Create `tests/test_persons_enroll_dedup.py`:

```python
"""Tests for near-duplicate enrollment rejection."""
from __future__ import annotations
import math
import numpy as np
import pytest
from fastapi.testclient import TestClient


def _make_embedding(seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(512).astype(np.float32)
    v /= np.linalg.norm(v)
    return v.tolist()


def _near_dup(emb: list[float], noise: float = 0.01) -> list[float]:
    """Return a slightly perturbed version of emb (cosine sim ≈ 1 - noise²/2)."""
    v = np.array(emb, dtype=np.float32)
    delta = np.random.default_rng(99).standard_normal(512).astype(np.float32)
    delta *= noise / np.linalg.norm(delta)
    v2 = v + delta
    v2 /= np.linalg.norm(v2)
    return v2.tolist()


@pytest.mark.integration
def test_near_duplicate_enrollment_rejected(client: TestClient, db_session: object) -> None:
    """Second enrollment with cosine sim >= reid_enroll_dedup_sim returns enrolled=False."""
    # Create person
    r = client.post("/api/persons", json={"name": "Test Person", "employee_id": "T001"})
    assert r.status_code == 201
    person_id = r.json()["id"]

    emb = _make_embedding(seed=1)

    # First enrollment succeeds
    r1 = client.post(f"/api/persons/{person_id}/embeddings", json={"embedding": emb})
    assert r1.status_code == 201

    # Near-duplicate enrollment is rejected
    r2 = client.post(f"/api/persons/{person_id}/embeddings", json={"embedding": _near_dup(emb, noise=0.005)})
    assert r2.status_code == 200
    body = r2.json()
    assert body["enrolled"] is False
    assert body["reason"] == "near_duplicate"


@pytest.mark.integration
def test_distinct_enrollment_accepted(client: TestClient, db_session: object) -> None:
    """Second enrollment with cosine sim < reid_enroll_dedup_sim is accepted."""
    r = client.post("/api/persons", json={"name": "Test Person 2", "employee_id": "T002"})
    person_id = r.json()["id"]

    emb1 = _make_embedding(seed=2)
    emb2 = _make_embedding(seed=999)  # orthogonal, low sim

    client.post(f"/api/persons/{person_id}/embeddings", json={"embedding": emb1})
    r2 = client.post(f"/api/persons/{person_id}/embeddings", json={"embedding": emb2})

    assert r2.status_code == 201
    assert r2.json().get("enrolled", True) is True
```

- [x] **Step 6.2: Confirm failure**

```powershell
pytest tests/test_persons_enroll_dedup.py -v --ignore-glob="*integration*" -m "not integration"
```

(Integration tests will be run after the DB is wired — for now confirm the test file loads.)

- [x] **Step 6.3: Add dedup helper to `vms/api/routes/persons.py`**

Add a private helper near the top of the route module:

```python
def _is_near_duplicate(
    new_emb: np.ndarray[Any, np.dtype[Any]],
    existing: list[Any],  # list of PersonEmbedding ORM rows
    threshold: float,
) -> bool:
    """Return True if any existing embedding has cosine sim >= threshold with new_emb."""
    for row in existing:
        stored = np.array(row.embedding_vector, dtype=np.float32)
        norm = np.linalg.norm(stored)
        if norm > 0:
            stored = stored / norm
        sim = float(np.dot(new_emb, stored))
        if sim >= threshold:
            return True
    return False
```

- [x] **Step 6.4: Wire dedup check into the enrollment route**

In `POST /api/persons/{id}/embeddings`, before the `db.add(new_embedding)` call, add:

```python
    settings = get_settings()
    existing_embs = db.query(PersonEmbedding).filter(
        PersonEmbedding.person_id == person_id,
        PersonEmbedding.is_active.is_(True),
    ).all()

    new_vec = np.array(embedding_data, dtype=np.float32)
    norm = np.linalg.norm(new_vec)
    if norm > 0:
        new_vec = new_vec / norm

    if _is_near_duplicate(new_vec, existing_embs, settings.reid_enroll_dedup_sim):
        return JSONResponse(
            status_code=200,
            content={"enrolled": False, "reason": "near_duplicate"},
        )
```

Ensure `import numpy as np` and `from fastapi.responses import JSONResponse` are at the top.

- [x] **Step 6.5: Confirm integration tests pass**

```powershell
pytest tests/test_persons_enroll_dedup.py -v -m integration
```

Expected: both pass.

- [x] **Step 6.6: Full suite check**

```powershell
pytest --tb=short -q
```

- [x] **Step 6.7: Lint and type-check**

```powershell
black vms/ tests/
ruff check vms/ tests/
mypy vms/ --strict
```

Expected: clean.

- [x] **Step 6.8: Commit**

```
feat(persons): cosine dedup check before person_embeddings enrollment
```

---

## Task 7: Verification Gate

- [x] **Step 7.1: Full test suite with coverage**

```powershell
pytest --cov=vms --cov-report=term-missing -q
```

Confirm:
- `vms/identity/engine.py` coverage ≥ 80%
- `vms/api/routes/persons.py` coverage ≥ 80%
- `vms/inference/embedder.py` coverage ≥ 70%
- Overall suite green

- [x] **Step 7.2: Verify conservative defaults do not change existing behaviour**

With all default settings (`reid_quality_norm_floor=0.0`, `min_blur=0.0` effective,
`reid_enroll_dedup_sim=0.95`), run the existing integration test suite and confirm no
regressions. The only visible behaviour change at defaults is: the enrollment endpoint
may return `200 + enrolled=false` instead of `201` for a true near-duplicate; this is
an intentional new behaviour.

- [x] **Step 7.3: Update CLAUDE.md §3 Known Open Gaps**

Add to the Known Open Gaps table:

| Gap | Spec ref | Notes |
|-----|----------|-------|
| `reid_quality_window_s`, `reid_quality_norm_floor` need calibration on real footage | Phase 3 ReID hardening | Conservative defaults (2.0s, 0.0) active; tighten only after calibration — mandatory `/advisor` trigger |
| Gallery health (dedup, consolidation, pruning scheduled job) | Phase 3 ReID hardening | Deferred; enrollment-only dedup is the current guard. Needs own spec before implementing. |

- [x] **Step 7.4: Final commit**

```
docs(claude-md): add reid quality calibration + gallery health to known gaps
```

---

## Definition of Done

This plan is complete when:

1. `pytest` passes (all tests including integration)
2. `ruff check vms/ tests/` — clean
3. `black vms/ tests/` — no changes
4. `mypy vms/ --strict` — clean
5. `FaceWithEmbedding.face_quality_norm` and `Tracklet.body_quality_norm` are populated at inference time and survive Redis round-trip
6. Blurry face crops (Laplacian variance < `min_blur`) are rejected by `embedder.py` before any ONNX inference
7. `_update_galleries` is windowed: consecutive frames within the same 2-second window produce at most one gallery slot
8. Enrollment endpoint returns `{"enrolled": false, "reason": "near_duplicate"}` for cosine sim ≥ 0.95 to existing embeddings
9. All three new config values appear in `vms/config.py` with conservative defaults
10. CLAUDE.md §3 gap table updated with calibration and gallery health notes
