# Phase 6c — Triton Inference Server Integration + ONNX Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: IN PROGRESS — Task 7**

**Goal:** Move GPU kernel execution for the ONNX model stack (SCRFD, AdaFace, TransReID body,
PPE) out of in-process ONNX Runtime and behind a Triton Inference Server gRPC endpoint, so the
system scales from the Phase 6b 12-camera MVP to 52 cameras (and beyond) by **changing `.env`
values only** — zero code changes at scale-up time. Triton's dynamic batching collapses the
per-camera CUDA kernel dispatch that stops amortizing past ~30 cameras. The Redis Streams bus,
the identity resolution order, and all thresholds are untouched (CLAUDE.md §17 invariants).
Also complete ONNX normalization (OSNet, MoViNet evaluation) and finish the §6.0.25 ROI-crop
config that has keys but no code.

**Architecture:**

The lever is a **single config switch with two code paths behind one interface**:

- `VMS_GPU_TRITON_URL=""` (default) → in-process ORT path. Existing behavior, byte-for-byte
  unchanged. This is what Phase 6b ships and what the test suite exercises by default.
- `VMS_GPU_TRITON_URL="localhost:8001"` → Triton gRPC client path. The **same** Python pre/post
  processing (letterbox, NMS decode, 5-point affine alignment, BGR→RGB normalization) runs on
  CPU; only the GPU kernel call (`sess.run(...)`) is replaced by a `tritonclient.grpc` `infer()`.

This is achieved with an **`InferenceBackend` Protocol** (structural typing, not class
inheritance) that both an `OrtInferenceBackend` and a `TritonInferenceBackend` satisfy. The
backend exposes exactly four methods used by `InferenceEngine`: `detect(frame)`,
`embed(face, frame)`, `embed_body(crop)`, `score_ppe(crop)`. A factory function
`_build_inference_backend(settings)` selects which concrete backend `InferenceEngine.__init__`
holds. The detector/embedder/body-embedder/PPE classes themselves are **not modified** — they
stay standalone-usable so existing tests keep mocking them directly. The ORT backend is a thin
adapter that delegates to those existing objects; the Triton backend reuses their pre/post
helpers but swaps the kernel call.

Key design decisions (opinionated, non-negotiable in this plan):

1. **gRPC, not HTTP.** `tritonclient.grpc` has lower per-call latency for the dense FP32 tensor
   payloads we send (640×640×3 SCRFD input ≈ 4.9 MB). HTTP/JSON base64 framing roughly doubles
   wire cost. Use port 8001 (Triton gRPC), not 8000 (HTTP).
2. **Fail fast, no silent fallback.** If `gpu_triton_url` is set but the server is unreachable
   at startup, raise `RuntimeError`. A silent fallback to ORT would mask a misconfigured 52-cam
   deployment and quietly halve throughput. CLAUDE.md discipline: surface the error.
3. **Factory/strategy, not inheritance.** The two backends share an interface, not a base class.
   No `OrtBackend(BaseBackend)` hierarchy — the existing detector/embedder classes are not in
   our inheritance tree and we will not retrofit them into one.
4. **Pre/post-processing stays in Python.** It is cheap CPU work and moving it would mean
   maintaining two copies of the NMS/alignment logic. Only the kernel launch moves.
5. **YOLO/BoT-SORT stays in-process.** Ultralytics holds per-camera tracker state across frames
   (`persist=True`); it is stateful and cannot move to Triton's stateless batching without a
   redesign. Deferred to a future §6.5 task; not in scope here.
6. **Triton runs in WSL2.** Triton server is Linux-only. On the Windows-first deployment it runs
   in WSL2 with NVIDIA GPU passthrough, rootless Docker, NVIDIA driver ≥ 535 on the host. The
   Python client (`tritonclient`) runs natively on Windows and connects over `localhost:8001`.

Multi-GPU needs **no code in this plan**: `cameras.worker_group` already partitions cameras to
separate `InferenceEngine` processes. Two GPUs = two Triton instances (or one Triton with two
model instances pinned per GPU via `instance_group` in `config.pbtxt`); each engine points its
`VMS_GPU_TRITON_URL` at the right endpoint. Config only.

**Tech Stack:** Python 3.13, `tritonclient[grpc]` (new dependency), NVIDIA Triton Inference
Server 24.xx (Linux container, WSL2), onnxruntime-gpu 1.22.0 (ORT path retained), CUDA 12.4,
TensorRT 10.x, RTX 2000 Ada (compute cap 8.9, 16 GB). Models already in `models/`:
`scrfd_10g_bnkps.onnx`, `adaface_ir101_webface12m.onnx`, `transreid_body_msmt17.onnx`,
`sh17_ppe_yolov8l.onnx`, `yolo26m-pose.onnx`.

**Spec refs:**
- §6.0.5 (ONNX normalization), §6.4 (Triton integration + compatibility matrix) —
  `docs/superpowers/specs/2026-06-13-vms-gpu-acceleration.md`
- §G (capacity model — 52-camera target) — `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md`
- §2.5 (MoViNet stateful streaming) — gpu-acceleration spec
- CLAUDE.md §0.5 (mandatory /advisor for identity thresholds), §4.4 (operational priority),
  §17 (architectural invariants)

**Identity-correctness guard (CLAUDE.md §4.4 priority #2):** The Triton path must produce
embeddings numerically identical (cosine ≥ 0.9999) to the ORT path for the same input, because
both execute the same ONNX graph on the same GPU — Triton is a dispatch layer, not a different
kernel. Task 4 asserts this; Task 10 re-checks end-to-end. **No threshold (`adaface_min_sim`,
`reid_body_*`) is touched in this phase.** If the cosine check fails, STOP — mandatory /advisor.

---

## Pre-flight checklist (do before Task 1)

- [ ] Confirm all five ONNX models present: `vms-models verify`
- [ ] Confirm `gpu_triton_url`, `gpu_onnx_export_dir`, `motion_gate_roi_*` keys exist in
      `vms/config.py` (per Phase 6b — they do; do not re-add)
- [ ] Add `tritonclient[grpc]` to `requirements.txt` (or `pyproject.toml` deps) — pin a version
      compatible with the Triton server tag chosen in Task 9
- [ ] Confirm WSL2 + NVIDIA driver ≥ 535 available on the target host (runbook detail in Task 9;
      not blocking for Tasks 1–8, which are unit-testable without a live server)

---

## Tasks

### Task 1 — `TritonModelClient` + startup health check

**New file:** `vms/inference/triton_client.py`
**Test file:** `tests/inference/test_triton_client.py`

A thin wrapper around `tritonclient.grpc.InferenceServerClient` for a single model. One public
method `infer(tensor) -> list[np.ndarray]` and a `check_health()` that fails fast.

`TritonModelClient(url: str, model_name: str, input_name: str, output_names: list[str],
input_dtype: str = "FP32")`:
- Lazily constructs the gRPC client (import `tritonclient` inside `__init__`, not at module top,
  so the dependency is optional for ORT-only deployments and tests).
- `check_health()` calls `is_server_live()` + `is_model_ready(model_name)`; raises `RuntimeError`
  with the URL and model name if either is false. No fallback.
- `infer(tensor)` builds one `InferInput` (named `input_name`, shape `tensor.shape`, dtype
  `input_dtype`), sets data from the numpy array, requests the `output_names`, calls
  `client.infer(...)`, and returns `[result.as_numpy(name) for name in output_names]`.

**RED → GREEN:**
- [x] Write `test_triton_client_infer_builds_input_and_returns_outputs` — patch
      `tritonclient.grpc.InferenceServerClient` with a Mock; assert `infer()` passes a correctly
      named/shaped `InferInput`, requests the right outputs, and returns the mocked `as_numpy`
      arrays in `output_names` order.
- [x] Write `test_triton_client_check_health_raises_when_server_not_live` — mock
      `is_server_live()` → False; assert `RuntimeError` mentioning the URL.
- [x] Write `test_triton_client_check_health_raises_when_model_not_ready` — server live but
      `is_model_ready()` → False; assert `RuntimeError` mentioning the model name.
- [x] Run tests → confirm RED (module/class does not exist yet).
- [x] Implement `vms/inference/triton_client.py`.
- [x] Run tests → confirm GREEN. (6/6 pass; commit 1e0ea458)

**Quality gate:** `black vms/ tests/`, `ruff check vms/ tests/`, `mypy vms/`, `pytest tests/inference/test_triton_client.py -v`, then full `pytest`.
**Commit:** `feat: phase 6c — TritonModelClient gRPC wrapper with fail-fast health check`

---

### Task 2 — Triton model repository generator (`scripts/build_triton_repo.py`)

**New file:** `scripts/build_triton_repo.py`
**Test file:** `tests/scripts/test_build_triton_repo.py`

Operator-run script (once per deployment) that materializes the Triton model repository from the
ONNX files already in `models/`. Output is gitignored (it contains copies of model files).

Generates this layout under `gpu_onnx_export_dir`'s sibling `models/triton_repo/` (or a
`--out` arg):
```
models/triton_repo/
  scrfd/     config.pbtxt   1/model.onnx
  adaface/   config.pbtxt   1/model.onnx
  transreid/ config.pbtxt   1/model.onnx
  ppe/       config.pbtxt   1/model.onnx
```

Each `config.pbtxt` is generated from a small per-model spec table inside the script (name,
platform `onnxruntime_onnx`, `max_batch_size`, input name + dims, output names + dims, dynamic
batching block). Input/output **names** are read from the ONNX graph itself (via `onnx.load` +
`graph.input`/`graph.output`) so the config never drifts from the model — the script must not
hard-code names that could go stale. The script copies (or symlinks on WSL) each ONNX into the
versioned `1/` dir.

Dynamic batching block written into every config:
```
dynamic_batching {
  max_queue_delay_microseconds: 1000
}
instance_group [ { count: 1 kind: KIND_GPU } ]
```
`max_batch_size` per model: SCRFD/AdaFace/TransReID/PPE all set to a config-driven value
(default 8) — Triton collects up to that many per-camera requests within the 1 ms window and
fires one kernel. The leading batch dim in each input/output `dims` is omitted (Triton prepends
it from `max_batch_size`).

**RED → GREEN:**
- [x] Write `test_build_triton_repo_creates_four_model_dirs` — run against a tmp dir with stub
      ONNX files (tiny valid graphs built with `onnx.helper`); assert the four dirs +
      `config.pbtxt` + `1/model.onnx` exist.
- [x] Write `test_build_triton_repo_config_uses_onnx_graph_io_names` — build a stub ONNX with a
      known input/output name; assert the generated `config.pbtxt` references those exact names
      (not hard-coded ones).
- [x] Write `test_build_triton_repo_config_contains_dynamic_batching_block` — assert each config
      contains `dynamic_batching` and `max_queue_delay_microseconds: 1000`.
- [x] Run tests → confirm RED.
- [x] Implement `scripts/build_triton_repo.py`; add `models/triton_repo/` to `.gitignore`.
- [x] Run tests → confirm GREEN. (5/5 pass; commit 870ce5cf)

**Quality gate:** full gate + `pytest tests/scripts/test_build_triton_repo.py -v`.
**Commit:** `feat: phase 6c — Triton model-repo generator (config.pbtxt from ONNX graph IO)`

---

### Task 3 — `InferenceBackend` Protocol + ORT backend adapter

**New file:** `vms/inference/backend.py`
**Test file:** `tests/inference/test_inference_backend.py`

Define the seam that makes Triton substitutable. No behavior change yet — this task only
introduces the interface and an ORT adapter that delegates to the existing objects.

```python
class InferenceBackend(Protocol):
    def detect(self, frame_bgr: np.ndarray) -> tuple[Face, ...]: ...
    def embed(self, face: Face, frame_bgr: np.ndarray) -> FaceWithEmbedding | None: ...
    def embed_body(self, torso_crop: np.ndarray) -> tuple[tuple[float, ...], float]: ...
    def score_ppe(self, crop_bgr: np.ndarray) -> dict[str, float] | None: ...
```

`OrtInferenceBackend` holds the existing `detector`, `embedder`, `body_embedder | None`,
`ppe | None` and delegates: `detect` → `detector.detect`, `embed` → `embedder.embed`,
`embed_body` → `body_embedder.embed` (returns `((), 0.0)` when `None`), `score_ppe` →
`ppe.score_crop` (returns `None` when `None`). This is a pure pass-through — its only job is to
give the Triton backend a sibling with an identical signature.

**RED → GREEN:**
- [x] Write `test_ort_backend_delegates_detect_and_embed` — inject mocked detector/embedder;
      assert calls forwarded with the same args and return values passed through.
- [x] Write `test_ort_backend_embed_body_returns_empty_when_no_body_embedder` — `body_embedder=None`
      → `((), 0.0)`.
- [x] Write `test_ort_backend_score_ppe_returns_none_when_no_ppe` — `ppe=None` → `None`.
- [x] Write a `Protocol`-conformance test: `assert isinstance(ort_backend, InferenceBackend)`
      using `@runtime_checkable`.
- [x] Run tests → confirm RED.
- [x] Implement `vms/inference/backend.py` (`InferenceBackend` Protocol + `OrtInferenceBackend`).
- [x] Run tests → confirm GREEN. (8/8 pass; commit ac3681d9)

**Quality gate:** full gate + targeted test file.
**Commit:** `refactor: phase 6c — InferenceBackend protocol + ORT adapter (no behavior change)`

---

### Task 4 — Triton backend implementation

**File changed:** `vms/inference/backend.py` (add `TritonInferenceBackend`)
**Test file:** `tests/inference/test_triton_backend.py`

`TritonInferenceBackend` satisfies the same `InferenceBackend` Protocol but routes the GPU
kernel through `TritonModelClient` (Task 1). It **reuses the existing Python pre/post helpers**
from `detector.py` / `embedder.py` / `body_embedder.py` / `ppe.py` (letterbox, NMS decode,
5-point affine alignment, BGR→RGB + `(px-127.5)/127.5` normalization, torso crop). To do this
without modifying those classes, expose their pre/post logic as module-level functions if they
are currently private methods, OR construct the existing object and call its preprocess /
postprocess steps directly while substituting the kernel call. Prefer the smallest change:
extract only the pre/post functions that are needed, keep them in their home module, leave the
class API intact.

Construction: the backend builds four `TritonModelClient` instances (scrfd, adaface, transreid,
ppe) from `gpu_triton_url`, then calls `check_health()` on each — fail fast at init.

Each method:
- `detect(frame)` → letterbox preprocess → `scrfd_client.infer(blob)` → existing SCRFD decode
  (pre-sigmoid, single `det_scale`, letterbox-aware — see CLAUDE.md gotcha) → faces.
- `embed(face, frame)` → 5-pt affine align + BGR→RGB + normalize → `adaface_client.infer(chip)`
  → L2-normalize → `FaceWithEmbedding`.
- `embed_body(torso)` → preprocess (256×128) → `transreid_client.infer(...)` → norm + quality.
- `score_ppe(crop)` → YOLO-style preprocess → `ppe_client.infer(...)` → existing SH17 class-index
  decode (helmet=10, vest=16, gloves=9, mask=5).

**Identity guard (CLAUDE.md §4.4 #2):**
- [x] Write `test_triton_backend_embed_matches_ort_cosine` — feed the SAME fixed face chip
      through a mocked Triton client whose `infer()` returns the SAME raw tensor the ORT session
      would; assert post-processed embedding cosine vs the ORT-path embedding ≥ 0.9999. (This
      verifies the post-processing is shared/identical, since the kernel is mocked to be equal.)
      PASSED — cosine = 1.0 (identical code path, shared helpers). No /advisor needed.

**Other RED → GREEN:**
- [x] `test_triton_backend_detect_calls_client_and_decodes` — mock `scrfd_client.infer`; assert
      letterbox preprocess applied and decode produces faces.
- [x] `test_triton_backend_init_health_checks_all_models` — mock clients; assert `check_health`
      called on all four; one failing → `RuntimeError`.
- [x] `test_triton_backend_score_ppe_uses_sh17_class_indices` — assert correct class index map.
- [x] Run tests → confirm RED.
- [x] Implement `TritonInferenceBackend` (+ extract shared pre/post helpers minimally).
- [x] Run tests → confirm GREEN. (8/8 pass; commit 3d16e310)

**Quality gate:** full gate + targeted test file. mypy must pass (Protocol conformance).
**Commit:** `feat: phase 6c — Triton-backed inference backend (detect/embed/body/ppe via gRPC)`

---

### Task 5 — Wire backend factory into `InferenceEngine.__init__`

**File changed:** `vms/inference/engine.py`
**Test file:** `tests/inference/test_engine_backend_factory.py`

Add `_build_inference_backend(settings, detector, embedder, body_embedder, ppe) -> InferenceBackend`:
- `settings.gpu_triton_url == ""` → `OrtInferenceBackend(...)` (wraps the objects already passed
  to `InferenceEngine.__init__`).
- non-empty → `TritonInferenceBackend(url=settings.gpu_triton_url, ...)` (which health-checks at
  construction).

In `InferenceEngine.__init__`, after storing the existing fields, set
`self._backend = _build_inference_backend(get_settings(), detector, embedder, body_embedder, ppe)`.
The constructor signature is **unchanged** (still accepts `detector`, `embedder`, etc.) so all
existing engine tests keep working — the factory just wraps them.

In `_process_one_message`, replace the four direct calls with backend calls:
- `self._detector.detect(frame_bgr)` → `self._backend.detect(frame_bgr)`
- `self._embedder.embed(face, frame_bgr)` → `self._backend.embed(face, frame_bgr)`
- `_extract_body_embeddings(...)` and `_score_ppe(...)` are refactored to call
  `self._backend.embed_body(...)` / `self._backend.score_ppe(...)` instead of taking the
  embedder/ppe objects directly. Keep the crop/clamp/blur-gate logic exactly as-is (it is CPU
  pre-work that belongs to the engine, not the backend).

**RED → GREEN:**
- [x] `test_engine_factory_returns_ort_backend_when_triton_url_empty` — default settings →
      `OrtInferenceBackend`.
- [x] `test_engine_factory_returns_triton_backend_when_triton_url_set` — patch settings with a
      URL + mock `TritonInferenceBackend` health check; assert Triton backend selected.
- [x] `test_engine_process_message_uses_backend_detect` — existing engine flow still publishes a
      `DetectionFrame`; assert backend `detect`/`embed` are the call path (mock backend).
- [x] Run tests → confirm RED.
- [x] Implement factory + rewire `_process_one_message` + adjust `_extract_body_embeddings` /
      `_score_ppe` to use the backend.
- [x] Run full suite → confirm no regression in existing engine tests (GREEN).

**Quality gate:** full gate. Critical: `pytest tests/inference/ -v` must show zero regressions —
the default ORT path is byte-for-byte the old behavior.
**Commit:** `feat: phase 6c — InferenceEngine backend factory (ORT default, Triton via config)`

---

### Task 6 — ROI cropping in `PerCameraTracker.update()` (§6.0.25 completion)

**File changed:** `vms/inference/tracker.py`
**Test file:** `tests/inference/test_tracker_roi_crop.py`

`motion_gate_roi_crop_enabled` / `motion_gate_roi_margin_px` config keys exist but have no code.
When `motion_gate_roi_crop_enabled=True` AND the motion gate passed AND this is a real YOLO frame
(not coasting), compute the bounding box of changed pixels (from the frame-diff mask the motion
gate already produces), expand by `motion_gate_roi_margin_px`, clamp to frame, crop, **resize to
a fixed 640×640**, and run YOLO on that crop. Map detected bboxes/keypoints back to full-frame
coordinates before building `Tracklet`s. When `False` or on coasting frames: no change.

**Constraint (TRT cache stability):** resize must be to a fixed 640×640, never variable, so the
TRT engine cache key for the (in-process) YOLO path stays stable. Document this in a code comment
(this is a non-obvious WHY per CLAUDE.md §5).

Implementation note: the motion gate currently computes `changed_pct` but discards the per-pixel
mask. Capture the `diff > threshold` mask when ROI is enabled (frame_diff mode) or the MOG2
`fg_mask`, derive its bounding box via `cv2.boundingRect` on nonzero pixels.

**RED → GREEN:**
- [x] `test_roi_crop_disabled_passes_full_frame` — `motion_gate_roi_crop_enabled=False` → YOLO
      receives full frame (assert shape).
- [x] `test_roi_crop_enabled_resizes_to_640` — enabled + a localized motion patch → YOLO receives
      a 640×640 input.
- [x] `test_roi_crop_maps_bbox_back_to_full_frame` — a detection inside the crop maps to the
      correct full-frame coordinates.
- [x] `test_roi_crop_no_effect_on_coasting_frame` — interval-skipped frame returns cached
      tracklets unchanged regardless of ROI flag.
- [x] Run tests → confirm RED.
- [x] Implement ROI crop in `update()` (and capture the mask in `_motion_gate_passes` or a helper).
- [x] Run tests → confirm GREEN.

**Quality gate:** full gate + targeted test file.
**Commit:** `feat: phase 6c — ROI crop in PerCameraTracker (§6.0.25), fixed 640x640 for TRT cache`

---

### Task 7 — OSNet ONNX export script + numerical validation

**File changed:** `scripts/export_osnet_onnx.py` (currently a SUPERSEDED stub for Market-1501)
**Test file:** `tests/scripts/test_export_osnet_onnx.py`

Rewrite the stale stub to export the **actually deployed** `osnet_ain_x1_0` MSMT17 weights
(fetched by `scripts/download_osnet_ain_msmt17.py`) to ONNX:
- Input: `(1, 3, 256, 128)` FP32; Output: `(1, 512)` embedding.
- `torch.onnx.export` with `opset_version` matching the Triton ORT backend, dynamic batch axis
  on input and output (so Triton dynamic batching works), output to
  `models/osnet_ain_x1_0_msmt17.onnx`.
- **Numerical validation gate:** load the `.pth` model and the exported ONNX, run the SAME random
  `(1,3,256,128)` tensor through both, assert cosine similarity ≥ 0.9999 (priority #2 identity
  correctness — an export that drifts the embedding is a no-ship). Print the cosine and exit
  nonzero on failure.

**RED → GREEN:**
- [ ] `test_export_osnet_validation_helper_flags_drift` — unit-test the cosine-compare helper with
      a synthetic drifted pair → returns failure; identical pair → pass. (The full export needs
      torch + weights; gate the live export behind `@pytest.mark.integration`.)
- [ ] `test_export_osnet_onnx_io_shapes` (integration) — when weights present, assert exported
      graph input `(N,3,256,128)` / output `(N,512)`.
- [ ] Run tests → confirm RED.
- [ ] Rewrite `scripts/export_osnet_onnx.py`; add the ONNX to `models/manifest.json` (per §8 —
      never commit the file itself).
- [ ] Run tests → confirm GREEN.

**Quality gate:** full gate + targeted test file. Integration export run logged in notes with the
measured cosine.
**Commit:** `feat: phase 6c — OSNet AIN MSMT17 ONNX export + cosine drift validation`

---

### Task 8 — MoViNet A2 ONNX evaluation (decide + document + warm-up if native)

**File changed:** `scripts/` (new `scripts/export_movinet_onnx.py` if export succeeds) +
`vms/inference/violence.py` (warm-up if staying native-TF)
**Test file:** `tests/inference/test_movinet_warmup.py` (only if staying native)
**Notes:** `docs/superpowers/notes/2026-06-25-vms-phase6c-implementation-notes.md`

MoViNet A2 Stream is a **stateful** streaming model — it carries internal recurrent state across
frames (per CLAUDE.md / engine docstring). ONNX export of stateful TF streaming models is
historically hard. Per spec §2.5: evaluate, decide, document.

- [ ] Attempt `tf2onnx` conversion of the MoViNet A2 Stream SavedModel. Record exact command,
      version, and the failure/success in the notes file.
- [ ] **If export succeeds** and a numerical check passes (same clip → score within tolerance):
      add `scripts/export_movinet_onnx.py`, add to manifest, and note that it MAY later join the
      Triton repo (but it stays out of Triton for now — stateful streaming does not fit Triton's
      stateless dynamic batching without the sequence-batcher, which is out of scope).
- [ ] **If export fails / is impractical:** document the decision to keep MoViNet native-TF
      in-process. Then ensure a warm-up protocol exists in `ViolenceModel.__init__` (a dummy
      forward pass to JIT/build the streaming graph so the first live frame doesn't stall), and
      test it. Document the warm-up in the notes and the runbook.

Either way, the deliverable is a **documented decision** with evidence, not necessarily code.
This is the one task where "no code" is an acceptable outcome.

**Quality gate:** full gate (lint/type/test) on any code added; notes file updated regardless.
**Commit:** `docs: phase 6c — MoViNet A2 ONNX export evaluation + native-TF warm-up decision`
(or `feat:` if export + warm-up code lands).

---

### Task 9 — WSL2 Triton deployment runbook + §6.4 compatibility matrix (doc task)

**File changed:** `docs/EXPLAINER.md` (or a new `docs/runbooks/triton-wsl2.md`) +
`docs/superpowers/specs/2026-06-13-vms-gpu-acceleration.md` §6.4 compatibility-matrix rows.
**No code.**

Write the operator runbook for standing up Triton in WSL2 on the Windows host:
- [ ] WSL2 prerequisites: NVIDIA driver ≥ 535 on Windows host; `wsl --install`; Ubuntu 22.04;
      verify `nvidia-smi` inside WSL2 (GPU passthrough).
- [ ] `.wslconfig` template with **explicit** `memory` and `swap` (WSL2 ballooning can starve
      Triton — document concrete values for the 16 GB / target-RAM host).
- [ ] Rootless Docker install in WSL2 (no Docker Desktop license dependency) + NVIDIA Container
      Toolkit.
- [ ] `docker run` command for the Triton server: mount `models/triton_repo` (built in Task 2),
      expose 8001 (gRPC), `--gpus all`, `--shm-size`, the chosen `nvcr.io/nvidia/tritonserver:24.xx-py3`
      tag.
- [ ] How the Windows-native VMS connects: `VMS_GPU_TRITON_URL=localhost:8001`.
- [ ] Fill the spec §6.4 compatibility matrix rows discovered during MVP: Triton server tag ↔
      ORT backend version ↔ CUDA ↔ TensorRT ↔ driver. Mark any combos tested vs untested.
- [ ] Engine-cache invalidation note (TRT plans inside Triton must be rebuilt after a driver
      upgrade — same gotcha flagged in Phase 6b).

**Quality gate:** doc review only; no lint/test.
**Commit:** `docs: phase 6c — Triton WSL2 deployment runbook + §6.4 compatibility matrix`

---

### Task 10 — End-to-end 5-camera smoke test with Triton enabled

**File changed:** `scripts/multi_cam_pipeline_test.py` (extend) or new
`scripts/triton_smoke_test.py`
**Test:** manual/integration run, recorded in notes.

Validate the whole lever end-to-end on real hardware: 5 cameras, Triton server up, all four ONNX
models served, `VMS_GPU_TRITON_URL=localhost:8001`.

- [ ] Bring up Triton (Task 9 runbook) with the Task 2 repo.
- [ ] Run the 5-camera pipeline twice: once ORT (`VMS_GPU_TRITON_URL=""`), once Triton.
- [ ] **Throughput gate:** Triton-path end-to-end frame throughput ≥ ORT baseline (Triton should
      match or beat ORT at 5 cams; the real win is at 30+, but it must not regress at 5).
- [ ] **Identity gate (priority #2):** sample ≥ 50 face crops + ≥ 50 body crops, compare ORT-path
      vs Triton-path embeddings — cosine ≥ 0.9999 (reuse the `scripts/trt_fp16_drift_check.py`
      harness pattern). Any crop below → HARD STOP, mandatory /advisor.
- [ ] **Fail-fast check:** point `VMS_GPU_TRITON_URL` at a dead port → confirm `RuntimeError` at
      startup, not a silent ORT fallback.
- [ ] Record VRAM, throughput, and the two cosine distributions in the notes file.

**Quality gate:** full `pytest` (unit) green; integration smoke results recorded.
**Commit:** `test: phase 6c — Triton 5-camera end-to-end smoke + identity/throughput gates`

---

## Phase wrap-up (after Task 10)

- [ ] Invoke `phase-wrap-up` skill: run quality gate, set this plan's **Status: COMPLETE**, write
      `docs/superpowers/notes/2026-06-25-vms-phase6c-implementation-notes.md`, update CLAUDE.md §3
      (active phase → Phase 6c complete; note Triton scale-by-config now available), commit.
- [ ] Update CLAUDE.md §3 Known Gaps: mark §6.0.25 ROI crop DONE, §6.0.5 OSNet ONNX DONE,
      MoViNet decision recorded, §6.4 Triton client DONE.

---

## Scale-by-config reference — proof of "zero code changes at scale-up"

After this plan lands, moving from 12 → 52 → 100+ cameras is **only `.env` + `cameras` table +
Triton config edits**. No Python changes. The knobs:

| Cameras | `VMS_GPU_TRITON_URL` | Triton `max_batch_size` (config.pbtxt) | `cameras.worker_group` | Throttling (`VMS_*`) | GPUs |
|---|---|---|---|---|---|
| 1–12 (Phase 6b MVP) | `""` (in-process ORT) | n/a | all `0` | `detector_interval_frames=1`, motion gate off | 1 |
| 12–30 | `localhost:8001` | 8 | all `0` | motion gate on (`motion_gate_enabled=true`); `detector_interval_adaptive=true`, `detector_interval_max=4` | 1 |
| 30–52 | `localhost:8001` | 16 | split across 2 groups (`0`,`1`) → 2 InferenceEngine processes | adaptive interval + ROI crop (`motion_gate_roi_crop_enabled=true`) | 1 (then 2) |
| 52–100+ | per-engine URL (e.g. `localhost:8001` / `localhost:8002`) | 16–32 | N groups across N engines | adaptive interval + ROI + per-camera `model_overrides` | 2+ (one Triton per GPU, or `instance_group` KIND_GPU per device) |

Concretely, scale-up is:
1. `VMS_GPU_TRITON_URL` empty → set (turns on the Triton path; Task 5 factory does the rest).
2. Re-run `scripts/build_triton_repo.py` only if `max_batch_size` changes; bump the value in the
   per-model spec table, regenerate, restart the Triton container.
3. Assign cameras to additional `worker_group`s in the `cameras` table → systemd/process manager
   starts one more `InferenceEngine` per group (already supported, no code).
4. Turn on the throttling knobs already implemented in `tracker.py` (Phase 6b) + ROI (Task 6).
5. For a second GPU: start a second Triton (or one Triton with `instance_group` per device) and
   point the second engine's `VMS_GPU_TRITON_URL` at it.

None of steps 1–5 touch `vms/` Python source. That is the deliverable of this phase.

---

## Invariants preserved (CLAUDE.md §17 cross-check)

| Invariant | How this phase preserves it |
|---|---|
| Redis Streams are the inter-service bus | Only the in-process kernel call changes; engine still reads `frames:groupN` and writes `detections`. No new cross-module calls. |
| PostgreSQL is source of truth / FAISS derived | Untouched — this phase is inference-execution only. |
| Identity resolution order (Face ≻ Body ≻ BLE) | Untouched — `FusionResolver` is downstream of the detections stream. |
| Thresholds live in config | No threshold touched. `adaface_min_sim`, `reid_body_*` unchanged — Triton is a dispatch layer, not a new kernel. |
| Scheduler owns cron jobs | No new timers; Triton is a request/response server. |
| DB write before FAISS update | N/A — no DB or FAISS writes in this phase. |
