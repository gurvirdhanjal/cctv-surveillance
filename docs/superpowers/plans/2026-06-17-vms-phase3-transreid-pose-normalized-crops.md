# TransReID Body Re-ID Hardening — Pose-Normalized Crops

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED**

**Goal:** Improve cross-camera body Re-ID stability by feeding `TransReIDBodyEmbedder` a
pose-normalized torso crop (shoulders→hips rectangle) instead of the raw person bounding box.
The raw bbox includes limbs, background clutter, and a pose-dependent aspect ratio that makes the
768-dim embedding drift when the same person appears bending/running in one camera and walking
upright in another. The torso rectangle, built from COCO keypoints 5/6/11/12, is the most
pose-invariant and discriminative region for body Re-ID. This plan also removes the now-dead
OSNet `BodyEmbedder` path and corrects stale OSNet-era comments.

**Architecture:**
- `extract_torso_crop()` is a pure, O(1)-per-detection helper in `vms/inference/body_embedder.py`
  (a handful of numpy/min-max ops — no DB, no Redis, no model call). It sits between the raw-bbox
  crop and `body_embedder.embed()` inside the per-frame `_extract_body_embeddings` path in
  `vms/inference/engine.py`.
- It consumes the keypoints already produced by YOLOv8x-Pose and carried on
  `Tracklet.keypoints: tuple[tuple[float, float, float], ...]` (17 COCO points, each `(x, y, conf)`).
- It degrades gracefully: when keypoints are missing, low-confidence, or produce a degenerate rect,
  it falls back to the full-bbox crop, so behaviour is never worse than today.
- Embedder thresholds (`reid_body_confirmed_sim`, `reid_body_cross_cam_sim`) are NOT touched — those
  are calibrated and changing them is a mandatory `/advisor` trigger (CLAUDE.md §0.5). Pose
  normalization tightens the input distribution but the thresholds stay as-is until re-calibration
  on real footage, which is out of scope here.

**Tech Stack:** Python 3.13, numpy, OpenCV (cv2), onnxruntime (TransReID ONNX), pydantic-settings
(`vms/config.py`), pytest.

**Spec refs:**
- CLAUDE.md §3 Known Gaps — "Body Re-ID upgrade: TransReID-SSL ViT-B/16+ICS MSMT17" row (status
  correction); "Key technical gotchas" — TransReID input spec, calibrated thresholds.
- CLAUDE.md §0.2 Simplicity First, §0.3 Surgical Changes, §4.2 TDD, §5 coding standards,
  §0.6 / §12 performance-sensitive path rules (`_extract_body_embeddings`).
- `docs/superpowers/plans/2026-06-17-vms-phase3-crosscam-accuracy.md` (cross-camera accuracy — this
  plan further hardens the body-embedding input that feeds those merges).

---

## Pre-task notes (read before starting)

1. **Keypoint availability in `_extract_body_embeddings`.** `Tracklet.keypoints` is populated by the
   pose tracker upstream. The CURRENT `_extract_body_embeddings` rebuilds each `Tracklet` WITHOUT
   carrying `keypoints` forward (see `engine.py` ~line 100–110 — only `local_track_id`, `camera_id`,
   `bbox`, `confidence`, `embedding`, `body_embedding`, `body_quality_norm` are set). The input
   tracklets to this function still carry keypoints, so reading `t.keypoints` inside the loop is
   valid. **When rebuilding the result Tracklet, preserve `t.keypoints` and `t.face_visible`** so the
   downstream `_score_ppe` / DTO serialization is unaffected. This is a latent bug-adjacent omission;
   fixing it is in-scope for Task 2 because the crop logic depends on keypoints being read here, and
   the rebuilt tracklet must not silently drop fields it already had.

2. **COCO keypoint indices (from prompt, confirmed in `messages.py`):** left_shoulder=5,
   right_shoulder=6, left_hip=11, right_hip=12. Each entry is `(x, y, conf)`. Coordinates are in
   full-frame pixel space (same space as `bbox`).

3. **`bbox` format:** `tuple[int, int, int, int]` = `(x1, y1, x2, y2)` in frame pixels.

4. **`_MIN_H = 16`, `_MIN_W = 8`** already exist as module constants in `body_embedder.py`; reuse
   them for the minimum-size check (do not introduce new size constants).

5. **Performance:** `extract_torso_crop` must be O(1) per detection — only min/max over 4 points,
   arithmetic, clamping, and one numpy slice. No loops over pixels, no model calls, no I/O.

6. **OSNet is fully dead:** model file deleted, `osnet_ain_model = ""` default, torchreid not
   installed, `create_body_embedder` skips it whenever the path is empty. The only non-test caller of
   `create_body_embedder` is `scripts/multi_cam_pipeline_test.py:648` which passes
   `osnet_path=settings.osnet_ain_model` — that call site must be updated in Task 3.

---

## Task 1 — Cleanup stale OSNet references (comments + docs only, no behaviour change)

**Files touched:**
- `vms/inference/body_embedder.py`
- `vms/identity/engine.py`
- `CLAUDE.md`

**Steps:**
- [ ] In `vms/inference/body_embedder.py`, fix the `TransReIDBodyEmbedder` docstring NOTE
      (currently around line 101):
      ```
      NOTE: reid_body_confirmed_sim (currently 0.51, calibrated for OSNet) must be
      re-calibrated on real footage before deploying this embedder in production.
      Mandatory /advisor before changing that threshold (CLAUDE.md §0.5).
      ```
      Replace with text reflecting reality: thresholds `reid_body_confirmed_sim=0.65` and
      `reid_body_cross_cam_sim=0.70` are calibrated for TransReID (2026-06-16); any further change is
      a mandatory `/advisor` trigger (CLAUDE.md §0.5). Do not restate the old OSNet 0.51 value as
      current.
- [ ] In `vms/identity/engine.py` (matching-priority docstring, around line 95), change
      `1. Body Re-ID (OSNet) — angle-invariant, works from top-down CCTV views.` to
      `1. Body Re-ID (TransReID) — angle-invariant, works from top-down CCTV views.`
- [ ] In `CLAUDE.md` §3 Known Gaps table, the "Body Re-ID upgrade: TransReID-SSL ViT-B/16+ICS MSMT17"
      row says "Supervised MSMT17 checkpoint not downloaded." The supervised ONNX
      (`transreid_body_msmt17.onnx`) is deployed and `TransReIDBodyEmbedder` is in production.
      Mark this row **DONE** (strike-through title + "DONE — TransReID ViT-B/16+ICS supervised
      MSMT17 ONNX deployed; `TransReIDBodyEmbedder` in `body_embedder.py`; thresholds calibrated
      2026-06-16") in the same style as the other DONE rows. Do NOT delete the row — keep the audit
      trail.

**No tests required** (comment/doc-only change). Run the full suite as a regression guard.

**Verify:**
- [ ] `grep -rn "OSNet" vms/identity/engine.py` returns nothing for the matching-priority line.
- [ ] `grep -rn "0.51" vms/inference/body_embedder.py` returns nothing.
- [ ] Quality gate (black, ruff, mypy --strict, pytest full suite) passes — see DoD.

**Commit:** `docs: correct stale OSNet references to TransReID in body Re-ID`

---

## Task 2 — Pose-normalized torso crop extraction

**Files touched:**
- `vms/config.py` (two new settings)
- `vms/inference/body_embedder.py` (new `extract_torso_crop` function + constants)
- `vms/inference/engine.py` (call `extract_torso_crop` in `_extract_body_embeddings`; preserve
  `keypoints`/`face_visible` on the rebuilt Tracklet)
- `tests/test_inference_body_embedder.py` (new tests for `extract_torso_crop`)
- `tests/test_config.py` (assert the two new defaults)
- `tests/test_inference_engine.py` (new test: engine uses torso crop / falls back) — create if a
  suitable engine test module does not already exist; otherwise add to the existing one.

### 2a. Config keys (TDD)

- [ ] **RED:** Add to `tests/test_config.py` a test asserting:
      `s.torso_kp_conf_threshold == 0.3` and `s.torso_crop_pad_fraction == 0.20`. Run — confirm it
      fails (AttributeError / missing field) for the expected reason.
- [ ] **GREEN:** Add to `vms/config.py` (near the other `reid_body_*` / body settings):
      ```python
      torso_kp_conf_threshold: float = 0.3
      torso_crop_pad_fraction: float = 0.20
      ```
      (env vars `VMS_TORSO_KP_CONF_THRESHOLD`, `VMS_TORSO_CROP_PAD_FRACTION` via the existing
      `VMS_` prefix mechanism.) Re-run — confirm GREEN.

### 2b. `extract_torso_crop` (TDD)

- [ ] **RED:** Add tests to `tests/test_inference_body_embedder.py` (see test list below). Run —
      confirm they fail because `extract_torso_crop` does not exist.
- [ ] **GREEN:** Implement in `vms/inference/body_embedder.py`:

      **Signature:**
      ```python
      def extract_torso_crop(
          frame_bgr: np.ndarray[Any, Any],
          bbox: tuple[int, int, int, int],
          keypoints: tuple[tuple[float, float, float], ...],
          conf_threshold: float,
          pad_fraction: float,
      ) -> np.ndarray[Any, Any]:
          ...
      ```
      Returns a BGR crop (numpy view/slice into `frame_bgr`). Never returns `None` — on any
      fallback condition it returns the full-bbox crop (clamped to frame bounds).

      **Logic (exact):**
      1. Compute the full-bbox crop as the fallback up front:
         `x1, y1, x2, y2 = bbox`; clamp `x1c=max(0,x1)`, `y1c=max(0,y1)`,
         `x2c=min(w,x2)`, `y2c=min(h,y2)` where `h, w = frame_bgr.shape[:2]`;
         `fallback = frame_bgr[y1c:y2c, x1c:x2c]`.
      2. If `len(keypoints) < 17`, return `fallback` (no pose data).
      3. Gather the four torso landmarks by index: `5` (left_shoulder), `6` (right_shoulder),
         `11` (left_hip), `12` (right_hip). Keep only those with `conf >= conf_threshold`.
      4. **Confidence gate:** if fewer than 3 of the 4 torso keypoints pass, return `fallback`.
      5. Build the torso rect from the valid points: `min_x, min_y, max_x, max_y` over their
         `(x, y)`. Add padding: `pad_x = (max_x - min_x) * pad_fraction`,
         `pad_y = (max_y - min_y) * pad_fraction`; expand the rect by `pad_x`/`pad_y` on each side.
      6. Convert to int and clamp to frame bounds: `tx1=max(0,int(min_x-pad_x))`,
         `ty1=max(0,int(min_y-pad_y))`, `tx2=min(w,int(max_x+pad_x))`,
         `ty2=min(h,int(max_y+pad_y))`.
      7. **Minimum size check:** if `(ty2 - ty1) < _MIN_H` or `(tx2 - tx1) < _MIN_W`, return
         `fallback`.
      8. Otherwise return `frame_bgr[ty1:ty2, tx1:tx2]`.

      No comments except a single WHY note if needed (e.g. why 3-of-4 rather than 4-of-4); do not
      annotate the obvious steps.

- [ ] Re-run the `extract_torso_crop` tests — confirm GREEN.

### 2c. Wire into `_extract_body_embeddings` (TDD)

- [ ] **RED:** Add an engine-level test (see test list) asserting that when a tracklet has valid
      torso keypoints, `_extract_body_embeddings` passes a smaller (torso) crop to the embedder, and
      when keypoints are absent it passes the full-bbox crop. Use a stub embedder that records the
      crop shape it received. Run — confirm it fails (engine still slices raw bbox).
- [ ] **GREEN:** In `vms/inference/engine.py::_extract_body_embeddings`, after computing the clamped
      bbox crop and passing the existing `min_px` / `min_blur` gates, replace the
      `body_embedder.embed(crop)` input: call
      `extract_torso_crop(frame_bgr, t.bbox, t.keypoints, settings.torso_kp_conf_threshold,
      settings.torso_crop_pad_fraction)` and pass THAT crop to `body_embedder.embed(...)`.
      - Keep the existing pre-gates (min bbox px, blur) operating on the full-bbox crop as today —
        the blur/size sanity check is on the person box; torso extraction is an inner refinement.
      - Run blur on the full crop (unchanged) but embed the torso crop.
      - **Preserve fields on the rebuilt `Tracklet`:** add `keypoints=t.keypoints` and
        `face_visible=t.face_visible` to the rebuilt `Tracklet(...)` so no upstream pose/face data
        is dropped (see Pre-task note 1).
      - Import `extract_torso_crop` from `vms.inference.body_embedder` (extend the existing import on
        line 19).
- [ ] Re-run engine test — confirm GREEN.

**Verify:**
- [ ] `extract_torso_crop` performs only min/max + arithmetic + one slice (O(1) per detection); no
      loops/IO/model calls — manual review.
- [ ] `_extract_body_embeddings` rebuilt Tracklet now carries `keypoints` and `face_visible`.
- [ ] Quality gate passes; coverage on `vms/inference/` ≥ 80%.

**Commit:** `feat: pose-normalized torso crop for TransReID body Re-ID`

#### Test list for Task 2 (names + what each verifies)

In `tests/test_inference_body_embedder.py`:
- [ ] `test_extract_torso_crop_all_keypoints_returns_torso_rect` — 4 high-conf torso kpts inside a
      bbox produce a crop strictly smaller than the bbox and located at the shoulder→hip span (assert
      the returned slice height/width matches the padded min/max of the 4 points, clamped).
- [ ] `test_extract_torso_crop_three_of_four_keypoints_still_uses_torso` — exactly 3 of 4 above
      threshold → torso rect (not fallback).
- [ ] `test_extract_torso_crop_two_keypoints_falls_back_to_bbox` — only 2 above threshold → returns
      full-bbox crop (assert shape equals clamped bbox crop).
- [ ] `test_extract_torso_crop_no_keypoints_falls_back_to_bbox` — `keypoints=()` → full-bbox crop.
- [ ] `test_extract_torso_crop_low_confidence_keypoints_fall_back` — 4 points present but all
      `conf < conf_threshold` → full-bbox crop.
- [ ] `test_extract_torso_crop_padding_expands_rect` — with `pad_fraction=0.20`, the returned rect is
      wider/taller than the bare shoulder/hip min-max by the expected pad, clamped to frame.
- [ ] `test_extract_torso_crop_clamps_to_frame_bounds` — torso landmarks near the frame edge so
      padding would exceed the frame → returned slice indices stay within `[0, w] / [0, h]`.
- [ ] `test_extract_torso_crop_degenerate_rect_falls_back_to_bbox` — collapsed torso rect (points so
      close that padded rect < `_MIN_H`×`_MIN_W`) → full-bbox crop.

In `tests/test_config.py`:
- [ ] `test_settings_torso_crop_defaults` — `torso_kp_conf_threshold == 0.3`,
      `torso_crop_pad_fraction == 0.20`.

In `tests/test_inference_engine.py` (or the existing engine test module):
- [ ] `test_extract_body_embeddings_uses_torso_crop_when_keypoints_present` — stub embedder records
      received crop shape; tracklet with valid torso kpts → embedder receives the torso (smaller)
      crop.
- [ ] `test_extract_body_embeddings_falls_back_to_bbox_without_keypoints` — tracklet with
      `keypoints=()` → embedder receives full-bbox crop.
- [ ] `test_extract_body_embeddings_preserves_keypoints_and_face_visible` — output tracklet retains
      `keypoints` and `face_visible` from the input.

---

## Task 3 — Remove `BodyEmbedder` (OSNet) dead code

**Files touched:**
- `vms/inference/body_embedder.py` (remove `BodyEmbedder`; simplify `create_body_embedder`;
  module docstring)
- `vms/config.py` (remove `osnet_ain_model`)
- `vms/inference/engine.py` (type hints / imports referencing `BodyEmbedder`)
- `scripts/multi_cam_pipeline_test.py` (remove `osnet_path=` arg at the `create_body_embedder` call)
- `tests/test_inference_body_embedder.py` (remove `BodyEmbedder` tests)
- `tests/test_config.py` (remove the `osnet_ain_model == ""` assertion at line 121)

**Steps:**
- [ ] **RED first (config):** Remove the `osnet_ain_model` assertion from `tests/test_config.py`
      (line 121) and add/keep an assertion that `osnet_ain_model` is no longer an attribute
      (`not hasattr(s, "osnet_ain_model")`). Run — confirm it fails while the field still exists.
- [ ] Remove `osnet_ain_model: str = ""` from `vms/config.py`. Re-run the config test — GREEN.
- [ ] Remove `class BodyEmbedder` (lines ~35–84) from `vms/inference/body_embedder.py`.
- [ ] Update the module docstring (lines 3–11) to describe only `TransReIDBodyEmbedder` (drop the
      two-implementation framing and the OSNet block).
- [ ] Simplify `create_body_embedder` to TransReID-only:
      ```python
      def create_body_embedder(transreid_path: str = "") -> TransReIDBodyEmbedder | None:
          """Return a TransReIDBodyEmbedder when the ONNX path exists, else None."""
          if transreid_path and os.path.exists(transreid_path):
              return TransReIDBodyEmbedder(transreid_path)
          return None
      ```
      Remove the `osnet_path` and `device` parameters and the inner `import os` (use the
      module-level `os` import already present at line 16).
- [ ] In `vms/inference/engine.py`: update the import on line 19 to
      `from vms.inference.body_embedder import TransReIDBodyEmbedder, extract_torso_crop`
      (drop `BodyEmbedder`). Update the two type hints (`_extract_body_embeddings` param line 72 and
      `InferenceEngine.__init__` `body_embedder` param line 165) from
      `BodyEmbedder | TransReIDBodyEmbedder | None` to `TransReIDBodyEmbedder | None`.
- [ ] In `scripts/multi_cam_pipeline_test.py` (line ~648): change the call to
      `create_body_embedder(transreid_path=settings.transreid_body_model)` — remove the
      `osnet_path=settings.osnet_ain_model` argument.
- [ ] In `tests/test_inference_body_embedder.py`: delete any tests that instantiate `BodyEmbedder`
      or assert OSNet behaviour, and any `create_body_embedder(..., osnet_path=...)` calls. Keep /
      adjust tests that exercise `create_body_embedder` with the TransReID path and the None case.

**Verify:**
- [ ] `grep -rn "BodyEmbedder\b" vms/ scripts/ tests/` shows only `TransReIDBodyEmbedder` (no bare
      `BodyEmbedder`).
- [ ] `grep -rn "osnet" vms/ scripts/` (case-insensitive) returns nothing in production/scripts.
- [ ] `mypy --strict vms/` clean (no dangling `BodyEmbedder` union members).
- [ ] Full suite passes; coverage on `vms/inference/` ≥ 80%.

**Commit:** `refactor: remove dead OSNet BodyEmbedder path`

---

## Definition of Done (all tasks)

A task is done only when ALL of these hold (CLAUDE.md §11):

- [ ] Task-scoped test(s) pass: `pytest <task test file> -v`.
- [ ] Full suite green: `pytest`.
- [ ] Format applied: `black vms/ tests/`.
- [ ] Lint clean: `ruff check vms/ tests/`.
- [ ] Type-check clean (strict): `mypy vms/`.
- [ ] Coverage at/above target: `pytest --cov=vms` with `vms/inference/` ≥ 80%.
- [ ] No `print()`; logging only (no new logging needed here).
- [ ] No new bare numeric literals in production code — the two new tunables live in
      `vms/config.py` (`torso_kp_conf_threshold`, `torso_crop_pad_fraction`); `_MIN_H`/`_MIN_W`
      reuse existing module constants.
- [ ] `extract_torso_crop` confirmed O(1) per detection (no loops/IO/model calls) — performance-path
      rule (CLAUDE.md §0.6 / §12).
- [ ] Thresholds `reid_body_confirmed_sim` / `reid_body_cross_cam_sim` UNCHANGED.
- [ ] One conventional commit per task (no AI co-author footer).
- [ ] This plan's checkboxes marked done; `**Status:**` line updated
      (`NOT STARTED` → `IN PROGRESS` → `COMPLETE`).
- [ ] CLAUDE.md §3 Known Gaps "Body Re-ID upgrade" row marked DONE (Task 1).
- [ ] Implementation notes written to
      `docs/superpowers/notes/2026-06-17-vms-phase3-transreid-pose-normalized-crops-implementation-notes.md`
      after the final task (use the `phase-wrap-up` skill).
