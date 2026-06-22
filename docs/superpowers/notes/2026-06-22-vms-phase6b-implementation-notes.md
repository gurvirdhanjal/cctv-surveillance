# Phase 6b — TensorRT FP16 Implementation Notes

## /advisor session — 2026-06-22

**Question posed:** Can we enable TensorRT FP16 now for the 10-12 camera MVP? What are
the caveats, what is the accuracy hardening needed, and what are the ordered next steps?

**Model used:** Claude Opus 4.8

---

### Key decisions

**Go/No-go: GO — with scoped definition**

TRT enablement is two independent switches, not one. This was the most important finding:

- `VMS_GPU_TENSORRT_ENABLED=true` → affects SCRFD, AdaFace, TransReID, PPE (all ORT-based).
  Requires the mini-baseline FP16 cosine-drift check before enabling on embedders (AdaFace,
  TransReID). SCRFD and PPE (detectors) are low-risk and can be enabled immediately.

- `VMS_YOLOV8X_POSE_MODEL=models/yolo26m-pose.engine` → affects YOLO only. Ultralytics
  handles `.engine` files natively, completely bypassing `VMS_GPU_TENSORRT_ENABLED`. This
  is the biggest throughput win and has trivial accuracy risk — GO immediately.

**Full §6.0 harness: DEFERRED**

The spec says "build §6.0 harness first." The advisor narrowed this obligation to its
load-bearing core: the §6.0 harness exists to protect identity correctness (priority #2) and
to back capacity claims. At 12 cameras we are not making a 52-cam capacity claim. The
throughput half of the harness is deferred. The accuracy half (cosine-drift check) is not
deferrable and is implemented as the Task 3 mini-baseline.

**Threshold freeze: mandatory during TRT enablement**

No `reid_*` / `adaface_*` / `adaface_min_sim` threshold may change in the same step as
enabling TRT. Threshold recalibration is a separate /advisor call, only after Task 3 produces
real FP16 drift numbers. This is the CLAUDE.md §0.5 rule applied directly.

**Detector interval: hold at 1 for MVP**

`detector_interval_frames` must remain 1 throughout Phase 6b. Enabling both TRT and interval
skipping simultaneously makes any accuracy regression unattributable. Interval tuning is
deferred post-MVP and measured separately (§6.0.25).

---

### Code gap found: warm-up missing in body_embedder.py and ppe.py

SCRFD (`detector.py:124`) and AdaFace (`embedder.py:153`) have TRT warm-up passes.
`body_embedder.py` and `ppe.py` call `build_ort_providers()` but have NO warm-up.
Without it, the first live camera frame triggers a 2-5 min TRT engine build stall.
**This must be fixed (Task 2) before enabling `VMS_GPU_TENSORRT_ENABLED=true`.**

---

### Accuracy hardening — CAM105 / CAM200 (100% face rejection)

**Evidence scope (critical caveat added 2026-06-22):**

The calibration observations below came from a SINGLE test-pipeline run. They are sufficient
to establish the methodology and direction, but NOT sufficient to finalize per-camera
deployment decisions. Day/night variation, shift-change traffic, and different worker
distances have not been sampled. The 7 remaining production cameras (beyond the 5 tested)
have no characterization data at all. Task 5 adds a mandatory multi-run characterization
procedure before any permanent override is applied.

**Provisional findings (from test run only — confirm before deployment):**

- CAM105/CAM200: `body_q min` is 2.1-2.9 (Laplacian). Face crops are blurry and unreliable
  for AdaFace. Provisionally classified as body-Re-ID primary. **Must be confirmed with
  broader sampling (day/night, shift-change, varied distance) before locking in.**

- CAM110: 0 faces detected. Provisionally classified as detection-limited. **Must be
  confirmed — could be angle or lighting that varies by time of day.**

- CAM141/CAM144: 57-99% face-embed rate. Classified as Face+Body from test run.
  These are the reference cameras; their thresholds should not change.

**Standing decisions (valid regardless of sampling breadth):**

- Do NOT globally lower `min_blur`. Per-camera overrides only, and only after confirming
  each camera's classification with multi-run data.
- No `reid_*` / `adaface_*` threshold change in this phase — separate mandatory /advisor.
- Face-embed rate on CAM141/CAM144 is the canary: if it changes after any override, stop.

---

### Hardware-specific notes (RTX 2000 Ada, 16 GB)

- **Workspace:** spec assumes 32 GB. Set `VMS_GPU_TENSORRT_WORKSPACE_MB=2048` (not 4096).
  Workspace is a build-time ceiling, not permanent VRAM. 2048 MB is sufficient for all models.
- **VRAM target at 12 cams:** stay under 14 GB. Monitor `nvidia-smi` during Task 4 and Task 5.
- **Engine portability:** if the card is upgraded for 52 cams, `models/trt_engines/` and
  `yolo26m-pose.engine` must be rebuilt. They are gitignored and derived — never commit them.
- **Driver updates:** delete `models/trt_engines/` after any NVIDIA driver update to force
  clean rebuild. Add to the deploy runbook.

---

### Benchmark numbers (Task 4 results — 2026-06-22)

**TRT engine build (first run, RTX 2000 Ada):**
- SCRFD: ~37 s
- AdaFace: ~34 s
- TransReID: ~27 s
- PPE (YOLOv8l): ~3 min 9 s
- Total first-run build time: ~5 minutes; subsequent loads from cache (models/trt_engines/)

**Per-model inference latency — TensorrtExecutionProvider FP16:**

| Model | Provider | mean ms | p95 ms |
|---|---|---|---|
| SCRFD (640x640) | TensorrtExecutionProvider | 2.3 ms | 2.6 ms |
| AdaFace (112x112) | TensorrtExecutionProvider | 2.2 ms | 2.2 ms |
| TransReID (384x128) | TensorrtExecutionProvider | 4.2 ms | 4.8 ms |
| PPE YOLOv8l (640x640) | TensorrtExecutionProvider | 6.7 ms | 7.3 ms |

CPU baseline (CPUExecutionProvider, same machine):
- SCRFD: 20.5 ms, AdaFace: 230.9 ms, TransReID: 34.8 ms, PPE: 127.1 ms
- Total serial CPU: 413 ms vs TRT serial: 15.4 ms → **27x speedup**

**VRAM during TRT inference:** 1,125 MB / 16,380 MB (6.9%) — well under the 14 GB safety limit.
**GPU util during active inference:** 97% (correct — fully utilizing GPU during burst inference).

**Active provider assertion:** All four models log warm-up complete and NO fallback warnings. TRT EP confirmed active.

**Installation notes (path issues encountered):**
- `onnxruntime-gpu 1.22.0` requires `nvinfer_10.dll` (TRT 10.x). TRT 11 was installed (nvinfer_11.dll) — downgraded to `tensorrt-cu12==10.9.0.34`.
- TRT DLLs live in `venv/Lib/site-packages/tensorrt_libs/` — NOT on system PATH. Added PATH injection to `multi_cam_pipeline_test.py` and `trt_fp16_drift_check.py` alongside the existing torch/lib injection.
- Ultralytics 8.4.x requires `nvidia-modelopt` for TRT engine export (new dependency). This attempted to upgrade torch to 2.12.1 and caused partial torch corruption. YOLO TRT engine export is BLOCKED until modelopt install path is resolved (see Task 4 notes below).

**YOLO TRT export (blocked):**
- `scripts/export_yolo_trt.py` failed: Ultralytics 8.4.x auto-installs `nvidia-modelopt[onnx]` which requires torch>=2.8 — incompatible with pinned torch 2.6.0+cu124.
- The install attempt partially corrupted torch (Access Denied on `torch/_C.pyd`). Torch reinstalled from `pytorch.org/whl/cu124`.
- Workaround options: (A) downgrade Ultralytics to 8.3.x, (B) install modelopt in a separate env, (C) use ORT TRT EP for YOLO as well (bypass Ultralytics engine path entirely).
- YOLO still runs on CUDA EP via Ultralytics. FP16 speedup for YOLO is deferred.

**FP16 drift check:** Not yet run (requires crop collection — Task 3 prerequisite). Script ready at `scripts/trt_fp16_drift_check.py`.

| Metric | Value |
|---|---|
| ms/frame — SCRFD TRT FP16 | 2.3 ms |
| ms/frame — AdaFace TRT FP16 | 2.2 ms |
| ms/frame — TransReID TRT FP16 | 4.2 ms |
| ms/frame — PPE TRT FP16 | 6.7 ms |
| VRAM at steady state (5-cam) | 1,125 MB / 16,380 MB |
| FP16 cosine drift — AdaFace (mean / min) | pending Task 3 run |
| FP16 cosine drift — TransReID (mean / min) | pending Task 3 run |
| ms/frame at 12 cams — TRT FP16 | pending Task 5 |
