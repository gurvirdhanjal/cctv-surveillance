# Phase 6a — YOLO ONNX Export + Detector Interval + TensorRT EP

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: IN PROGRESS — Task 1**

**Goal:** 10-camera MVP on RTX 2000 Ada Gen (16 GB, compute cap 8.9). Three targeted wins:
(1) Detector interval — YOLO skips frames, BoT-SORT coasts (§6.0.25);
(2) YOLO ONNX export + optional TRT engine (§6.0.5 + §6.1 YOLO path);
(3) TensorRT EP for SCRFD + AdaFace + TransReID — 2–3× on the face pipeline (§6.1).
All three are independently shippable and gated behind config flags (off by default).

**Architecture:**
- `detector_interval_frames` in `PerCameraTracker`: on skip frames return cached tracklets,
  counter-modulo triggers YOLO runs. Cascade stages (SCRFD, AdaFace) are exempt — they keep
  the existing keypoint gate. Only the primary YOLO detector is interval-throttled.
- `vms/inference/ort_providers.py`: shared helper that builds the ORT provider list for all
  three ONNX models (SCRFD, AdaFace, TransReID). Reads `gpu_tensorrt_enabled` from settings.
  TRT EP is first when enabled; falls through to CUDA EP then CPU EP otherwise.
- YOLO export: `scripts/export_yolo_onnx.py` (§6.0.5) + `scripts/export_yolo_trt.py` (§6.1).
  Ultralytics handles both formats natively via `YOLO.export()`. Setting
  `VMS_YOLOV8X_POSE_MODEL=models/yolov8x-pose.engine` activates TRT for YOLO; Ultralytics'
  `.track()` call is unchanged — no new post-processing code.

**Tech Stack:** onnxruntime-gpu 1.22.0 (TensorRT EP), Ultralytics 8.4.x (ONNX/TRT export),
Python 3.13, CUDA 12.4, RTX 2000 Ada (TensorRT 10.x via ORT bundled).

**Spec refs:** §6.0.25 (detector interval), §6.0.5 (ONNX normalization), §6.1 (TRT FP16),
§5 (config keys). Phase 6 spec: `docs/superpowers/specs/2026-06-13-vms-gpu-acceleration.md`.

**Deployment sequence (operator):**
```
# Step 1 — export ONNX (one-time, ~2 min)
python scripts/export_yolo_onnx.py

# Step 2 — export TRT engine (one-time, ~5 min on Ada; cached after)
python scripts/export_yolo_trt.py

# Step 3 — enable via env vars
VMS_GPU_TENSORRT_ENABLED=true
VMS_GPU_TENSORRT_FP16=true
VMS_YOLOV8X_POSE_MODEL=models/yolov8x-pose.engine   # YOLO TRT
VMS_DETECTOR_INTERVAL_FRAMES=2                        # halve YOLO load; tune to 3 if headroom allows
```

---

## Tasks

### Task 1 — Config keys for Phase 6a (§5)
- [x] Add to `vms/config.py`:
  - `detector_interval_frames: int = 1`
  - `gpu_tensorrt_enabled: bool = False`
  - `gpu_tensorrt_fp16: bool = True`
  - `gpu_tensorrt_engine_cache_dir: str = "models/trt_engines"`
  - `gpu_tensorrt_workspace_mb: int = 4096`
  - `gpu_onnx_export_dir: str = "models/onnx_exported"`
- [x] Add `test_phase6a_config_defaults` to `tests/test_config.py`
- [x] Quality gate: ruff + mypy + pytest tests/test_config.py

### Task 2 — Detector interval in `PerCameraTracker` (§6.0.25)
- [x] Add `_frame_counter: int` + `_last_tracklets: list[Tracklet]` state to `__init__`
- [x] In `update()`: check `(counter % interval) == 0`; on skip return `_last_tracklets`;
      save tracklets to `_last_tracklets` before every return from a real YOLO run
- [x] New test file `tests/inference/test_detector_interval.py`:
  - `test_interval_1_calls_yolo_every_frame` (backward-compat: interval=1 is no-op)
  - `test_interval_2_halves_yolo_calls`
  - `test_interval_3_runs_every_third_frame`
  - `test_skip_returns_last_tracklets`
- [x] Quality gate: ruff + mypy + pytest tests/inference/test_detector_interval.py

### Task 3 — ORT provider helper + TRT EP for SCRFD / AdaFace / TransReID (§6.1)
- [x] New `vms/inference/ort_providers.py` with `build_ort_providers() -> list[Any]`:
      when `gpu_tensorrt_enabled=False` return `["CUDAExecutionProvider", "CPUExecutionProvider"]`;
      when True return `[("TensorrtExecutionProvider", {...}), "CUDA...", "CPU..."]` and
      `os.makedirs(cache_dir, exist_ok=True)`
- [x] New test file `tests/inference/test_ort_providers.py`:
  - `test_default_returns_cuda_cpu_only`
  - `test_trt_enabled_puts_trt_first`
  - `test_trt_creates_cache_dir`
- [x] Update `vms/inference/detector.py` `SCRFDDetector.from_path()`: replace hardcoded
      providers with `build_ort_providers()`; add warm-up pass when TRT enabled
- [x] Update `vms/inference/embedder.py` `AdaFaceEmbedder.from_path()`: same
- [x] Update `vms/inference/body_embedder.py` `TransReIDBodyEmbedder.__init__()`: same
- [x] Quality gate: ruff + mypy + pytest tests/inference/test_ort_providers.py

### Task 4 — YOLO ONNX export script (§6.0.5)
- [x] New `scripts/export_yolo_onnx.py`:
  - Loads `yolov8x-pose.pt`, calls `model.export(format="onnx", imgsz=640, opset=17, simplify=True)`
  - Runs dummy inference on both .pt and .onnx models; logs detection counts (numeric validation)
  - Prints `VMS_YOLOV8X_POSE_MODEL=<path>` usage hint on success
- [x] Quality gate: ruff + mypy scripts/export_yolo_onnx.py

### Task 5 — YOLO TRT engine export script (§6.1)
- [x] New `scripts/export_yolo_trt.py`:
  - Accepts `.pt` or `.onnx` source; calls `model.export(format="engine", half=True, device=0)`
  - FP16 default: RTX 2000 Ada (compute cap 8.9) has strong FP16 support
  - Logs estimated build time warning (2–5 min first run, cached after)
  - Prints `VMS_YOLOV8X_POSE_MODEL=<path>` usage hint on success
- [x] Quality gate: ruff + mypy scripts/export_yolo_trt.py

### Task 6 — Commit
- [x] `feat: phase 6a — detector interval + TRT EP for ONNX models + YOLO export scripts`
- [x] Verify full suite: `pytest`

---

## Benchmark gate (post-deploy, manual)

Run `python scripts/multi_cam_pipeline_test.py` with 5 cameras before and after enabling
`VMS_GPU_TENSORRT_ENABLED=true` + `VMS_DETECTOR_INTERVAL_FRAMES=2`. Then scale to 10 cameras.
Target: ≤50 ms/frame end-to-end at 10 cameras (CLAUDE.md §0.6).

If 10 cameras is not achieved: cross-camera YOLO batching (share one model, batch N frames)
is the next lever — separate plan task, requires `PerCameraTracker` architectural refactor.
