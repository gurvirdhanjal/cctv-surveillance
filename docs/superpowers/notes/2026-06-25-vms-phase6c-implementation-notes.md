# Phase 6c — Triton + ONNX Scalability Implementation Notes

> Companion to `docs/superpowers/plans/2026-06-25-vms-phase6c-triton-onnx-scalability.md`.
> Records decisions made, problems hit, and anything surprising during execution.

---

## Task 1 — `TritonModelClient` gRPC wrapper

`_import_grpc()` module-level factory defers `tritonclient.grpc` import to first call,
making the import patchable in tests without touching `sys.modules`. Two-patch test
pattern: patch `_discover_model_io` (skips real gRPC metadata query) and
`TritonModelClient` constructor (skips real gRPC connection).

---

## Task 2 — Triton model-repo generator

`build_triton_repo.py` queries ONNX graphs at runtime for tensor names/shapes, so
`config.pbtxt` generation is robust to model updates. TRT cache directory is created
per-model inside the repo to keep plan files co-located with their config.

---

## Task 3 — `InferenceBackend` Protocol + `OrtInferenceBackend`

`@runtime_checkable` Protocol chosen (not ABC) so existing tests can keep mocking the
concrete `SCRFDDetector`/`AdaFaceEmbedder` objects directly — no retrofit needed.
`OrtInferenceBackend` is a thin adapter; all real logic stays in the wrapped objects.

---

## Task 4 — `TritonInferenceBackend`

Test frame for the ORT-vs-Triton cosine identity guard must be random noise, not solid
gray. Solid-gray frames have zero Laplacian variance → fail the `min_blur=25.0` gate →
embed() returns None → cosine check has nothing to compare. Fix: use
`frame_rng.integers(50, 200, (200, 200, 3), dtype=np.uint8)`.

---

## Task 5 — Wire backend factory into InferenceEngine

`_extract_body_embeddings` and `_score_ppe` signature changed from accepting raw
`TransReIDBodyEmbedder | None` / `PPEModel | None` to `backend: InferenceBackend`.
This caused 7 regressions in `tests/test_inference_engine.py`; fixed by updating
all 7 tests to use `mock_backend.embed_body` / `mock_backend.score_ppe` instead of
`embedder.embed` / `ppe_model.score_crop`.

---

## Task 6 — ROI crop in PerCameraTracker

Resize target is fixed at 640×640 (never variable). Variable resolutions would cause
TRT to generate a new engine plan per unique (H, W) pair, destroying the plan cache.
The fix is permanently enshrined in a code comment in `tracker.py`.

Motion mask captured in `_last_motion_mask` as a side effect of `_motion_gate_passes`,
set to `None` when the gate is disabled or when no baseline exists (first frame).
`_compute_roi_bbox` uses `cv2.findNonZero` + `cv2.boundingRect` — both handle
zero-nonzero masks gracefully by returning `None`.

---

## Task 7 — OSNet ONNX export

`models/manifest.json` created and added to `.gitignore` exception (`!models/manifest.json`).
The `models/` directory was previously fully ignored (correct for binary model files),
but `manifest.json` is reference metadata that must be tracked in git.

OSNet AIN x1.0 checkpoint format: `{"state_dict": {...}}` wrapper (torchreid convention).
`torch.load(..., weights_only=True)` requires the state dict to use only safe tensor types;
confirmed working with the MSMT17 checkpoint from kaiyangzhou/osnet on HuggingFace.

**Opset choice:** 17. Reasons: (a) matches onnxruntime ≥ 1.18 used in the Triton ORT
backend; (b) supports all ops in OSNet AIN (conv2d, bn, relu, adaptive avg pool);
(c) has broader Triton ORT backend compatibility than opset 12 (the old stub used 12).

---

## Task 8 — MoViNet A2 ONNX evaluation decision

**Verdict: No ONNX export. MoViNet A2 Stream is already replaced. Native-torch warm-up added.**

**Background:** The plan was written assuming MoViNet A2 Stream (TensorFlow SavedModel)
was still in active use. During Phase 3/4 implementation, MoViNet was replaced with
`R(2+1)D-18` (torchvision) for two reasons:
1. No TensorFlow dependency — R(2+1)D-18 runs on the same CUDA stack as the rest of the
   model stack.
2. Simpler stateless clip-buffer architecture — no per-frame recurrent streaming state to
   manage across cameras.

`ViolenceModel._load` still detects the MoViNet SavedModel path (directory check) and
auto-switches to R(2+1)D-18 for backward compatibility with existing deployment configs.

**tf2onnx attempted?** No. Given MoViNet is already replaced, attempting the export would
produce an artifact that is not deployed and provides no production value. The decision
is documented here instead.

**Warm-up added:** `_warm_up_model(model, device, clip_frames, h, w)` helper added to
`vms/inference/violence.py`. Called at the end of `_load()` after `model.to(device).eval()`.
This pre-compiles CUDA kernels so the first live production frame does not stall.
Two unit tests added in `tests/inference/test_movinet_warmup.py`.

**R(2+1)D-18 stays in-process (not Triton):** The model is stateless (clip buffer managed
in Python) but 16-frame clip batching does not align well with Triton's single-frame
dynamic batching. Per-camera frame buffers are maintained in the Python process. Triton
would require client-side buffer management with session state — out of scope.

---

## Task 9 — WSL2 Triton deployment runbook

See `docs/runbooks/triton-wsl2.md` (created in this task).

**Docker Desktop path discovered during Task 10 setup:** Docker Desktop 29.x already provides
GPU passthrough to containers (`docker run --gpus all` works from PowerShell without any
additional NVIDIA toolkit installation). The runbook was updated to document this as
"Path A" (developer/pilot) alongside the original rootless-Docker-in-WSL2 "Path B"
(production/enterprise). For this developer machine (Windows 11 Pro, RTX 2000 Ada,
driver 595.71), Path A is the active deployment path.

**Triton model repo built** (`python scripts/build_triton_repo.py`) — 4 models confirmed:
`scrfd`, `adaface`, `transreid`, `ppe`. All ONNX files present in `models/`.

**`.wslconfig` applied**: 32 GB host → `memory=28GB`, `swap=16GB`. WSL2 confirmed at 27 GiB
after `wsl --shutdown` + restart.

---

## Task 10 — End-to-end smoke test

Requires live camera hardware and a running Triton server. Hardware-gated.
