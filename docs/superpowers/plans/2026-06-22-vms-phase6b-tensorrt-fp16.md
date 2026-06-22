# Phase 6b — TensorRT FP16 Enablement + 12-Camera MVP

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: IN PROGRESS — Task 5**

**Goal:** Enable TensorRT FP16 on RTX 2000 Ada (16 GB, compute cap 8.9) for all ONNX-via-ORT
models (SCRFD, AdaFace, TransReID, PPE) and for YOLO via a pre-built Ultralytics `.engine`.
Deliver a stable 10-12 camera MVP at ≤50 ms/frame end-to-end. Identity correctness (priority
#2) is protected throughout — no threshold changes ship without the FP16 cosine-drift gate
passing and a separate /advisor call.

**Architecture:**

TRT enablement is **two independent switches** — this is the most important architectural
fact in this plan:

1. `VMS_GPU_TENSORRT_ENABLED=true` — activates the TensorRT EP in `build_ort_providers()` for
   SCRFD, AdaFace, TransReID body, and PPE. These are all ONNX-via-ORT models. Risk: FP16
   embedding drift → identity gate (must pass mini-baseline cosine-drift check first).

2. `VMS_YOLOV8X_POSE_MODEL=models/yolo26m-pose.engine` — activates TRT for YOLO. Ultralytics
   handles the `.engine` file natively via its own TRT path. This is entirely separate from
   flag #1. Risk: trivial — detectors tolerate FP16.

Both switches must be validated independently before being used together. `detector_interval_frames`
is held at 1 for the entire MVP — adding interval skipping simultaneously would make any
regression unattributable. Interval tuning is a separate post-MVP task.

**Caveats addressed in this plan (from /advisor session 2026-06-22):**

| Caveat | Task that closes it |
|---|---|
| Warm-up gap: `body_embedder.py` + `ppe.py` have no TRT warm-up pass | Task 2 |
| TRT EP silent fallback: no startup assertion on active provider | Task 3 |
| FP16 embedding drift may break identity matching | Task 3 (mini-baseline) |
| 16 GB VRAM (half the spec's 32 GB) — workspace pressure at 12 cams | Task 4 (monitored) |
| Engine cache invalid after driver upgrade — not in runbook | Task 5 (runbook note) |
| CAM105/CAM200 100% face quality rejection needs per-camera fix | Task 5 |

**Deployment sequence (operator, after this plan completes):**
```
# Step 1 — export YOLO TRT engine (one-time, ~5 min; RTX 2000 Ada)
python scripts/export_yolo_trt.py

# Step 2 — enable via .env (do NOT commit these values)
VMS_GPU_TENSORRT_ENABLED=true
VMS_GPU_TENSORRT_FP16=true
VMS_GPU_TENSORRT_WORKSPACE_MB=2048        # conservative for 16 GB card
VMS_YOLOV8X_POSE_MODEL=models/yolo26m-pose.engine
VMS_DETECTOR_INTERVAL_FRAMES=1            # hold at 1 for MVP; tune separately later
```

**Tech Stack:** onnxruntime-gpu 1.22.0 (TensorRT EP), Ultralytics 8.4.x (YOLO .engine export),
Python 3.13, CUDA 12.4, TensorRT 10.x (bundled with ORT), RTX 2000 Ada (compute cap 8.9).

**Spec refs:**
- §6.0.5 (ONNX normalization / YOLO export) — `docs/superpowers/specs/2026-06-13-vms-gpu-acceleration.md`
- §6.1 (TRT FP16, provider list, warm-up, identity guard) — same spec
- §5 (config keys) — same spec
- /advisor session: 2026-06-22, documented in `docs/superpowers/notes/2026-06-22-vms-phase6b-advisor-session.md`

---

## Tasks

### Task 1 — Commit existing Phase 6a uncommitted work ✓

Two files from Phase 6a are modified but uncommitted: `vms/inference/ort_providers.py` and
`vms/inference/tracker.py` (motion gate + adaptive interval). These must be committed as a
clean baseline before Phase 6b layering begins.

- [ ] Run quality gate: `black vms/ tests/`, `ruff check vms/ tests/`, `mypy vms/`
- [ ] Run full test suite: `pytest` — confirm all pass
- [ ] Commit: `feat: phase 6a — ort_providers TRT EP helper + tracker motion gate / adaptive interval`
- [ ] Verify: `git status` shows no uncommitted changes in `vms/`

### Task 2 — Close the TRT warm-up gap in `body_embedder.py` and `ppe.py` ✓

SCRFD (`detector.py:124`) and AdaFace (`embedder.py:153`) already have a TRT warm-up pass
(a dummy zero-tensor `sess.run()` guarded by `if settings.gpu_tensorrt_enabled`). `body_embedder.py`
and `ppe.py` call `build_ort_providers()` but have **no warm-up pass** — without it, the first
live camera frame triggers the 2-5 min TRT engine build, stalling that camera's inference thread.

- [ ] In `vms/inference/body_embedder.py` `TransReIDBodyEmbedder.__init__()`:
  after `ort.InferenceSession(model_path, providers=providers)`, add:
  ```python
  if get_settings().gpu_tensorrt_enabled:
      dummy = np.zeros((1, 3, _INPUT_H, _INPUT_W), dtype=np.float32)
      self._sess.run(None, {self._sess.get_inputs()[0].name: dummy})
      logger.info("TransReIDBodyEmbedder TRT warm-up complete")
  ```
  (check what `_INPUT_H` / `_INPUT_W` constants are named in that file; use the actual
  input shape constants — do not hardcode 256/128 inline)

- [ ] In `vms/inference/ppe.py` PPE loader:
  after `ort.InferenceSession(path, providers=providers)`, add:
  ```python
  if get_settings().gpu_tensorrt_enabled:
      dummy = np.zeros((1, 3, _PPE_INPUT_SIZE, _PPE_INPUT_SIZE), dtype=np.float32)
      sess.run(None, {sess.get_inputs()[0].name: dummy})
      logger.info("PPE model TRT warm-up complete")
  ```
  (verify the input shape constant name in `ppe.py`)

- [ ] Add test `test_trt_warmup_runs_on_enabled` in `tests/inference/test_ort_providers.py`:
  mock `settings.gpu_tensorrt_enabled = True`, verify that each loader calls `sess.run`
  with a zero tensor on init (use `unittest.mock.patch`)

- [ ] Quality gate: `black vms/ tests/`, `ruff check vms/ tests/`, `mypy vms/`,
  `pytest tests/inference/test_ort_providers.py -v`
- [ ] Commit: `fix: add TRT warm-up pass to body_embedder and ppe model loaders`

### Task 3 — Mini-baseline: FP16 cosine-drift check (identity correctness gate) ✓

Before enabling FP16 on AdaFace and TransReID in production, prove that FP16 embeddings
remain close enough to FP32 that existing `reid_*` / `adaface_min_sim` thresholds hold.
This is the minimal, load-bearing half of the §6.0 accuracy harness — not the full throughput
harness (deferred), but non-negotiable for embedders.

The script runs a fixed set of face/body crops through each embedder twice — once via
`CUDAExecutionProvider` (FP32 reference) and once via `TensorrtExecutionProvider` (FP16) —
and reports pairwise cosine similarity between the two embeddings for each crop.

**Pass criterion:** cosine similarity FP16-vs-FP32 ≥ 0.999 for all crops across both AdaFace
and TransReID. If any crop falls below ~0.99, stop: do not enable FP16 on that model, raise
a mandatory /advisor call to assess whether thresholds need recalibration.

- [ ] New script `scripts/trt_fp16_drift_check.py`:
  - Accepts a directory of face crops (JPEGs) and a directory of body crops
  - Loads AdaFace embedder once with `CUDAExecutionProvider`, once with TRT FP16
  - Loads TransReID embedder once with `CUDAExecutionProvider`, once with TRT FP16
  - For each crop: compute FP32 embedding, FP16 embedding, cosine similarity
  - Prints per-model mean/min cosine similarity and pass/fail vs 0.999 threshold
  - Exits non-zero if any model fails the threshold (so it can be run in CI later)
  - Logs: `"[AdaFace] FP16 drift: mean={:.4f} min={:.4f} → PASS/FAIL"`

- [ ] Collect ≥50 face crops (from live calibration run: save frames when `face_embedded=True`)
  and ≥50 body crops from the multi-camera test. Store in `scripts/test_crops/` (gitignored).

- [ ] Run the script:
  ```
  python scripts/trt_fp16_drift_check.py \
      --face-crops scripts/test_crops/faces/ \
      --body-crops scripts/test_crops/bodies/
  ```

- [ ] **Gate decision:**
  - Both models PASS (≥0.999): proceed to Task 4, TRT FP16 enabled for all models.
  - Any model FAILS (<0.99): stop, open a mandatory /advisor call; do not enable FP16
    on the failing model; consider enabling only on passing models.

- [ ] Add `trt_fp16_drift_check.py` to ruff + mypy check scope
- [ ] Commit: `feat: add TRT FP16 cosine-drift check script (identity correctness gate)`

### Task 4 — Enable TRT in .env; assert active provider at startup; VRAM check ✓

This task activates TRT for real and verifies the production-safety assertions.

- [x] Add a startup provider assertion in `vms/inference/detector.py` `SCRFDDetector.from_path()`:
  after the TRT warm-up, assert:
  ```python
  if settings.gpu_tensorrt_enabled:
      active = sess.get_providers()
      if active[0] != "TensorrtExecutionProvider":
          logger.warning(
              "TRT EP requested but active provider is %s — check ONNX op compatibility",
              active[0],
          )
  ```
  Mirror this assertion in `embedder.py`, `body_embedder.py`, `ppe.py`.
  (Log a WARNING, not an exception — fallback to CUDA EP is safe; silent fallback is not.)
  **DONE — commit `63e4245`**

- [ ] Set in `.env` (not committed):
  ```
  VMS_GPU_TENSORRT_ENABLED=true
  VMS_GPU_TENSORRT_FP16=true
  VMS_GPU_TENSORRT_WORKSPACE_MB=2048
  VMS_DETECTOR_INTERVAL_FRAMES=1
  ```

- [ ] Run YOLO engine build (one-time):
  ```
  python scripts/export_yolo_trt.py
  ```
  Set `VMS_YOLOV8X_POSE_MODEL=models/yolo26m-pose.engine` in `.env`.

- [ ] Run `scripts/multi_cam_pipeline_test.py --cameras 105 110 141 144 200` and verify:
  - Startup logs show `"TensorRT EP enabled"` for all four ONNX models
  - All four models log `"... TRT warm-up complete"` before first camera attaches
  - No model logs a fallback warning (active provider assertion)
  - `nvidia-smi` VRAM ≤ 14 GB at steady state (safe headroom on 16 GB card)
  - Measured ms/frame is lower vs the CUDA-EP baseline (quantify: record before/after)

- [ ] If VRAM pressure observed: lower `VMS_GPU_TENSORRT_WORKSPACE_MB` to 1024 and retest.
  Workspace is a build-time allocation ceiling, not permanent; 1024 MB is sufficient for
  all three model sizes in this stack.

- [ ] Quality gate: `black vms/ tests/`, `ruff check vms/ tests/`, `mypy vms/`, `pytest`
- [ ] Commit: `feat: add TRT provider assertion at startup (warn on silent fallback)`

### Task 5 — Camera characterization across all production cameras

**Context and evidence scope (important):**

The calibration data used by the /advisor on 2026-06-22 came from a single test-pipeline
run on 5 cameras. That is sufficient to establish the methodology but NOT sufficient to lock
in per-camera deployment decisions. Specifically:

- CAM105/CAM200 classified as body-Re-ID primary based on one run; day/night variation,
  shift-change traffic density, and worker distance have not been sampled.
- CAM110 classified as detection-limited based on one run; angle and focal length at
  different times of day have not been verified.
- Cameras beyond the initial 5 (up to 12) have no characterization data at all.

**Per-camera conclusions must be confirmed, not assumed, before deployment.**

**Characterization run procedure:**

For each production camera in the 10-12 camera set:

- [ ] Run `scripts/multi_cam_pipeline_test.py` for ≥ 5 minutes per camera, covering:
  - At least one active-traffic period (workers present)
  - If possible: one day and one night/low-light period
  - Camera at closest expected worker distance and at farthest expected distance

- [ ] For each camera, record from the calibration stats output:

  | Camera | Face Detect % | Face Accept % | Avg Body Q | Avg Face Q | Min Body Q | Min Face Q |
  |--------|--------------|---------------|------------|------------|------------|------------|
  | CAM105 | | | | | | |
  | CAM110 | | | | | | |
  | CAM141 | | | | | | |
  | CAM144 | | | | | | |
  | CAM200 | | | | | | |
  | CAM___ | | | | | | |

- [ ] From the table, assign each camera a **primary modality**:
  - `Face+Body` — face accept % ≥ 50% AND avg face Q ≥ 14 (CAM141/CAM144 level)
  - `Body-primary` — face accept % < 20% OR avg body Q < 50 AND face Q unreliable
  - `Detection-limited` — face detect % < 5% regardless of accept rate
  - `Needs investigation` — inconsistent across runs; do not assign overrides yet

  **CAM105/CAM200 are provisionally Body-primary from the test run; confirm or revise
  after broader sampling. Do NOT treat the test-run result as the final classification.**

**Per-camera min_blur overrides (only after table is complete):**

- [ ] For cameras confirmed as Body-primary or Detection-limited: lower `min_blur` in
  `cameras.model_overrides` to match observed body_q minimums. Do NOT lower globally.
  Keep CAM141/CAM144-class cameras at their current threshold.

- [ ] Verify after any override:
  - Face-embed rate on Face+Body cameras (CAM141/CAM144 class) unchanged
  - No increase in `reid_body_confirmed_sim` hits (no threshold change — if similarity
    distribution shifts, raise a mandatory /advisor call per CLAUDE.md §0.5)

**Ramp to 12 cameras:**

- [ ] Add remaining cameras via `.env` `VMS_CAM_*_URL` vars (only after characterization
  table is complete for ALL production cameras being deployed)

- [ ] Run `scripts/multi_cam_pipeline_test.py --cameras <all 12>` and measure:
  - End-to-end ms/frame at 12 cameras ≤ 50 ms (CLAUDE.md §0.6 target)
  - `nvidia-smi` GPU utilization and VRAM at 12-camera steady state
  - No increase in frame drops vs 5-camera baseline
  - Identity-match rate on a known enrolled person (re-walk test) ≥ pre-TRT rate

- [ ] Record the completed characterization table and benchmark numbers in:
  `docs/superpowers/notes/2026-06-22-vms-phase6b-implementation-notes.md`

- [ ] Quality gate: `black vms/ tests/`, `ruff check vms/ tests/`, `mypy vms/`, `pytest`
- [ ] Commit: `feat: phase 6b — camera characterization table + 12-camera MVP validated`

---

## Benchmark gate (per-task, measured on real hardware)

| Metric | Baseline (CUDA EP) | Target (TRT FP16) | Measured |
|---|---|---|---|
| FP16 cosine drift — AdaFace | — | ≥ 0.999 | TBD (Task 3) |
| FP16 cosine drift — TransReID | — | ≥ 0.999 | TBD (Task 3) |
| ms/frame at 5 cams — CUDA EP | TBD (record before Task 4) | — | TBD |
| ms/frame at 5 cams — TRT FP16 | — | ≤ 30 ms | TBD (Task 4) |
| ms/frame at 12 cams — TRT FP16 | — | ≤ 50 ms | TBD (Task 5) |
| VRAM at 12-cam steady state | — | ≤ 14 GB | TBD (Task 5) |
| GPU utilization at 12 cams | — | < 80% (headroom) | TBD (Task 5) |

---

## Explicitly deferred (do not implement in this plan)

| Item | Why deferred | When |
|---|---|---|
| `detector_interval_frames` > 1 | Mixing TRT + interval skipping makes regressions unattributable; GPU headroom at 12 cams is sufficient | Post-MVP, measured separately per §6.0.25 |
| INT8 quantization (§6.2) | Embedder INT8 needs /advisor + full recalibration; detectors INT8 incremental gain not needed at 12 cams | Phase 6c, only if 52-cam target requires it |
| NVDEC hardware decode (§6.3) | CPU decode is not the bottleneck at 12 cams | Phase 6c |
| Triton cross-camera batching (§6.4) | 52-cam lever, not 12-cam | Phase 6d |
| Multi-GPU sharding (§6.5) | Second GPU is the 52-cam+ upgrade path | Phase 6e |
| `reid_*` / `adaface_min_sim` threshold recalibration | Requires real plant footage + /advisor; authorized only after Task 3 drift numbers confirm FP16 is safe | Separate /advisor call |
| Full §6.0 throughput harness | Only needed for 52-cam capacity claims; mini-baseline in Task 3 covers the identity-correctness obligation | Phase 6c prerequisite |

---

## Known risks (from /advisor session 2026-06-22)

1. **Engine cache silent invalidation** — after any NVIDIA driver update, delete
   `models/trt_engines/` to force a clean rebuild. Add to deploy runbook.
2. **16 GB VRAM** — spec assumes 32 GB. Monitor `nvidia-smi` during Task 4 and Task 5.
   If VRAM exceeds 14 GB, reduce workspace to 1024 MB and/or disable PPE TRT (it is
   trigger-gated and contributes the least to throughput).
3. **YOLO `.engine` is GPU-arch-specific** — must re-export if the card is upgraded.
   The `.engine` file is gitignored and derived; never commit it.
4. **MoViNet (violence model)** — stays on its native TF runtime. `VMS_GPU_TENSORRT_ENABLED`
   has no effect on it. This is expected and correct per spec §2.5.
