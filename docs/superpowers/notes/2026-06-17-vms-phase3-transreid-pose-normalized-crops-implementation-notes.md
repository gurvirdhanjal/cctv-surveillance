# Phase 3 TransReID Pose-Normalized Crops — Implementation Notes

**Date:** 2026-06-17
**Plan:** `docs/superpowers/plans/2026-06-17-vms-phase3-transreid-pose-normalized-crops.md`
**Commits:** `89f3482`, `583368f`, `b341d03`
**Tests at close:** 678 passed, 3 deselected

---

## Decisions made

**3-of-4 confidence gate (not 4-of-4).** Requiring all four torso landmarks is too strict; a
partially occluded shoulder or hip is common in crowded plant-floor scenes. Requiring at least 3
recovers most valid torso crops while still excluding poses where the torso region is undefined
(e.g. person bending forward with both hips invisible). Fail-open: 2-or-fewer always falls back
to the full bbox.

**Blur/size gate operates on the full bbox, torso crop is the embed input.** The sanity gate
(min_body_bbox_px, min_blur) answers "is this detection worth embedding at all?" and is
naturally measured on the full person box. `extract_torso_crop` is an inner refinement applied
only after the gate passes.

**`_MIN_H = 16`, `_MIN_W = 8` reused from existing module constants.** The torso crop minimum
size check uses the same thresholds as the embedder's own `embed()` guard. Keeps one source of
truth; no new numeric literals in production code.

---

## Bugs and gotchas

**Latent keypoints/face_visible drop in `_extract_body_embeddings`.** The original code rebuilt
each `Tracklet` without carrying forward `keypoints` and `face_visible`. Since `_score_ppe` runs
immediately after and reads `t.keypoints` for its own crop, this was silently zeroing out the PPE
path for any tracklet that had been through the body-embedding loop. Fixed in Task 2 by adding
`keypoints=t.keypoints, face_visible=t.face_visible` to the rebuilt Tracklet constructor. This
bug predated this plan and was classified "bug-adjacent latent omission" — the crop logic
depended on reading `t.keypoints`, which made fixing it in-scope.

**`ruff RUF002/RUF003`** — multiplication sign `×` in a comment (carried over from prior session)
was flagged as an ambiguous Unicode character. Replaced with `x`. The `×` char was in a test
file comment, not production code. Added `from typing import Any` to `test_inference_engine.py`
after ruff flagged `F821` (undefined name `Any` used in a type annotation in a stub class).

**`mypy unused-ignore`** — a `# type: ignore[return-value]` on the `extract_torso_crop` return
was unnecessary because mypy inferred `np.ndarray[Any, Any]` correctly from the numpy slice.
Removed.

---

## Test count and coverage

| Module | Coverage note |
|---|---|
| `vms/inference/engine.py` | 84% — new tests cover the torso-crop branch and keypoints preservation |
| `vms/inference/body_embedder.py` | 56% — ONNX model loading / embed() path excluded from default suite (requires model file); not regressed |
| `vms/config.py` | covered by `test_config.py` — two new defaults verified |

Full suite: **678 passed, 3 deselected** (3 deselected = `@pytest.mark.integration` tests that
require a live PostgreSQL container).

New tests added this plan: 8 in `TestExtractTorsoCrop`, 3 in `test_inference_engine.py`,
1 in `test_config.py` = 12 new tests total (678 − 666 from prior plan).
