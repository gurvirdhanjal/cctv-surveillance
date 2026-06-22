# VMS GPU Acceleration — TensorRT, Quantization, NVDEC & Multi-GPU (Phase 6)
**Design Specification** · 2026-06-13
**Status:** Draft

**Supersedes (in part):** Extends `2026-05-01-vms-v2-hardened-design.md` §G (Capacity
model). §G's camera-capacity table assumes plain CUDA-EP ONNX inference; this spec
re-models capacity under TensorRT and defines the optimization phases that get us there.

---

## §0. Why this exists

A LinkedIn post on NVIDIA DeepStream framed the core insight well: at 52 cameras × 25 fps
you are looking at ~1,300 frames/second, and **the win is not a better model — it is a
smarter pipeline.** Three levers matter, in this order:

1. **Don't process every frame.** *Partially shipped.* We already drop stale frames
   (`stale_threshold_ms=200`), gate SCRFD+AdaFace on a visible frontal face
   (`face_kpt_min_conf`), and trigger-gate the heavy models (violence, PPE). **What we do not
   yet do** is decouple the *primary detector interval* from tracking: today YOLO runs on
   every processed frame. The post's comment thread (Nitin Rai / Utkarsh) describes the
   missing piece — run the primary detector every Nth frame and let the tracker *coast*
   between runs — which is a cheap early win captured in §6.0.25. **Critical caveat from those
   same comments:** this applies to the *primary detector only*; cascaded stages (face/body
   embedding) accumulate error when skipped, so they keep gate-based sampling, never a blind
   interval. This is also why identity (priority #2) is never traded for throughput (#4).
2. **Run the frames you keep on the GPU efficiently.** This is the gap. Today inference runs
   ONNX via the CUDA Execution Provider (or CPU fallback). We leave 2–5× on the table by not
   using TensorRT. **This spec closes that gap.**
3. **Decode on the GPU, not the CPU.** RTSP H.264 decode is currently CPU-bound (§G.1).
   NVDEC moves it to the GPU's dedicated video engine.

### Is ONNX still valid? Yes — it becomes the common intermediate format.

This is the most important decision in this spec, so it is stated first:

**We do not abandon ONNX, and we do not (initially) adopt DeepStream.** ONNX Runtime ships a
**TensorRT Execution Provider** that compiles `.onnx` graphs into optimized TensorRT engines
at load time. We keep every pre/post-processing path in `detector.py` / `embedder.py` /
`ppe.py` and the entire `InferenceEngine` call shape. For models already in ONNX, the only
change is the provider list:

```python
# today (vms/inference/detector.py:113, embedder.py:108, ppe.py:72)
providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

# Phase 6a
providers = ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
```

**But our model stack is mixed-format** (`.onnx`, `.pt`, `.pth`, TF SavedModel — see §2.5),
and the TensorRT EP only consumes ONNX. So the real role of ONNX here is as the **common
intermediate representation every model is exported into** before acceleration. That export
step is a prerequisite sub-phase (§2.5 / §6.0.5), not an afterthought.

DeepStream's advantage (GStreamer NVDEC + fully-batched CUDA inference in one process) is
real but it is a **rewrite of `ingestion/` and `inference/` and a hard CUDA/NVIDIA lock-in.**
We get ~80% of its inference benefit from the TensorRT EP with ~5% of the work, while staying
portable (CPU fallback still works for dev laptops and CI). DeepStream is evaluated, behind a
go/no-go gate, only in the final sub-phase (§6.6) if measured throughput still falls short.

---

## §1. Deployment target

| Property | Value |
|---|---|
| GPU count | 1 now, 2 available (operator can add the second) |
| VRAM per GPU | 32 GB |
| Exact SKU | **Unknown at spec time** — the design is GPU-architecture-agnostic (see §2) |
| Workload | 52 cameras (v1), horizontally scalable |

A 32 GB card is far more VRAM than the model stack needs (SCRFD + AdaFace + YOLOv8x-pose +
OSNet + MoViNet + optional PPE + CLIP ≈ 6–9 GB resident). **VRAM is not the bottleneck;
compute throughput is.** The surplus VRAM is what makes aggressive batching (§6.4) and a
second model replica per GPU feasible.

---

## §2. GPU-agnostic hardware detection (foundational — built first)

Because the SKU is unknown, every optimization decision is gated on a **runtime capability
probe**, not a hard-coded assumption. On inference-service startup we detect compute
capability (e.g. via `nvidia-smi --query-gpu=compute_cap` or the CUDA runtime) and branch:

| Arch | Compute cap | FP16 | INT8 | FP8 | Optimization profile |
|---|---|---|---|---|---|
| Volta (V100) | 7.0 | strong | **weak** | — | FP16 only; skip INT8 (§6.2 no-op) |
| Turing | 7.5 | strong | good | — | FP16 + INT8 |
| Ampere (A100/A40/RTX30) | 8.0 / 8.6 | strong | strong | — | FP16 + INT8 + TF32 |
| Ada (RTX40 / L40S) | 8.9 | strong | strong | — | FP16 + INT8 |
| Hopper (H100) | 9.0 | strong | strong | yes | FP16 + INT8 (+ FP8 future) |
| Unknown / no GPU | — | — | — | — | CUDA-EP or CPU fallback (current behaviour) |

The probe result is logged once at startup and drives which precision the TensorRT EP is
allowed to build. **No optimization is ever forced on hardware that does not benefit** — on a
V100, §6.2 (INT8) is a documented no-op; on a dev laptop with no GPU, the whole phase
degrades to today's CPU path with zero config.

A new module `vms/inference/gpu_profile.py` exposes `detect_gpu_profile() -> GpuProfile`
(frozen dataclass: `arch`, `compute_cap`, `vram_gb`, `nvdec_units`, `supports_int8`,
`supports_fp16`). All sub-phases read this; none re-probe.

---

## §2.5. Model format inventory — ONNX is the common target, not the current reality

Models arrive in whatever format Hugging Face / GitHub / Ultralytics ship them in. They are
**not all ONNX today**, and the format of any given model can change when it is re-downloaded
or swapped (`vms-models swap`). The pipeline therefore cannot assume ONNX — it must
**normalize to ONNX** as the first acceleration step.

| Model (config key) | Format today | Source | Path to TensorRT |
|---|---|---|---|
| SCRFD (`scrfd_model`) | `.onnx` | HF / InsightFace | Direct — already ONNX |
| AdaFace (`adaface_model`) | `.onnx` | HF | Direct — already ONNX |
| PPE SH17 (`ppe_model`) | `.onnx` (exported from `.pt`) | Ultralytics export | Direct — recipe already in config.py |
| YOLOv8x-pose (`yolov8x_pose_model`) | **`.pt`** | Ultralytics | `YOLO(...).export(format="onnx")` → then EP |
| OSNet AIN (`osnet_ain_model`) | **`.pth`** | torchreid state-dict | `torch.onnx.export(...)` → then EP |
| MoViNet A2 (`violence_model`) | **TF SavedModel** | TF Hub | `tf2onnx` — **stateful streaming, hard** (§ note below) |
| CLIP (forensic, future) | varies | open_clip / HF | Export when forensic phase lands |

**Design rule — never assume a fixed extension.** The loader inspects the actual file
(magic bytes / extension) and dispatches to the right exporter. A model re-downloaded in a
different format must still flow to ONNX without code changes — only a manifest entry recording
which exporter to use.

**MoViNet special case.** The A2 *Stream* model is stateful (it carries per-camera streaming
state across frames — see `engine.py` docstring). Exporting a stateful streaming graph to ONNX
is genuinely hard and may not be worth it: violence is already trigger-gated (runs on ~30% of
frames, only when ≥2 persons). **Decision deferred to its own evaluation** inside §6.0.5 — if
ONNX export is impractical, MoViNet stays on its native TF runtime and is simply excluded from
TensorRT acceleration. It is the smallest slice of the GPU budget, so this is acceptable.

The `.onnx` / `.pt` / `.pth` / SavedModel files all remain **gitignored and manifest-driven**
(CLAUDE.md §8) — exported ONNX artifacts and built TensorRT engines are derived files, cached
on disk, never committed.

---

## §3. Phase 6 sub-phases (escalating, each independently shippable)

Each sub-phase is a separate plan file and ends at a measurable gate. We stop escalating the
moment the throughput target (§4) is met — later sub-phases are only built if needed.

### §6.0 — Hardware probe + benchmark harness *(foundational)*
- Build `gpu_profile.py` (§2).
- Build a repeatable benchmark: fixed clip → measure end-to-end ms/frame and frames/sec/GPU
  for each precision, plus identity-match accuracy vs the FP32 baseline.
- **Gate:** baseline numbers recorded for the actual deployment GPU. Everything downstream is
  measured against these, not against vendor marketing figures.

### §6.0.25 — Detector-interval decoupling, motion gate, and ROI cropping *(cheap early wins, no TensorRT needed)*
The lowest-cost throughput levers, layered in before the harder TensorRT work. Directly from
the post's comment thread (Nitin Rai / Utkarsh Upadhyay). Three independent flags that compose:
fixed interval → motion gate → ROI crop. Each can be enabled or disabled independently.

**Fixed-interval decoupling (the baseline lever):**

- **Primary detector at an interval, tracker every frame.** Run YOLO person detection every
  `detector_interval_frames` frames; on the in-between frames, the tracker *coasts* — advancing
  existing tracks by their motion model (Kalman predict) without a fresh detection. Track IDs
  and box continuity are preserved; only the expensive detector pass is skipped.
- **Implementation reality (not a config flip):** ByteTrack/BoT-SORT are tracking-by-detection
  and Ultralytics runs detection every frame by design. `PerCameraTracker` must gain a
  predict-only step for skip frames. Moderate effort, but far cheaper than §6.1 and it stacks
  with it.
- **Cascade stages are exempt — non-negotiable.** Face embedding (SCRFD→AdaFace) and body
  embedding (→OSNet) are cascaded; the comments' "errors add up" warning plus operational
  priority #2 (never misidentify, CLAUDE.md §4.4) mean these keep their current gate-based
  sampling. The interval applies to the *primary detector only*, never to identity inference.
- **Per-tier / per-camera interval.** LOW-tier cameras (low motion, e.g. a back corridor) can
  skip more aggressively than FULL-tier; the interval is a per-camera override via
  `cameras.model_overrides`, defaulting to a global setting.
- **Distinct from `stale_threshold_ms`.** That drops whole frames under load (tracking dies on
  dropped frames); this keeps tracking alive every frame and only throttles the detector.

**Motion-gate pre-filter (`motion_gate_enabled`, default off):**

Before the fixed-interval check, an optional lightweight motion gate determines whether a
frame contains enough pixel-level change to warrant YOLO at all. If the scene is genuinely
static — an empty corridor, a parked forklift with no persons — the frame is skipped entirely
(no YOLO, no coasting update, existing tracks age normally). This fires on quiescent frames
that the fixed interval would still have processed.

- **Mechanism:** frame differencing (absolute per-channel mean pixel delta; fast, no state) or
  MOG2 background subtraction (more stable across lighting changes; maintains per-camera
  foreground model). `motion_gate_method: str = "frame_diff"` | `"mog2"`.
- **Threshold:** `motion_gate_min_pixel_diff_pct` — fraction of pixels that must exceed a
  per-channel delta before YOLO fires. Calibration target: false-negative rate < 1% on a
  representative clip (a person entering an otherwise-static scene). Too low → gate never
  suppresses; too high → slow-moving persons missed.
- **Track expiry interaction:** if the motion gate silences a camera for more than
  `track_max_coasting_frames` consecutive frames, existing tracks must be expired rather than
  coasted indefinitely. A permanently static scene should produce zero active tracks, not
  stale ghost tracks.
- **Composition with the fixed interval:** a frame must pass both the motion gate *and* fall
  on a YOLO interval to trigger detection. Either condition suppressing the frame is sufficient.
  The two levers are independent and additive.

**ROI cropping (`motion_gate_roi_crop_enabled`, default off):**

When a frame passes the motion gate and falls on a YOLO interval, crop the YOLO input to the
bounding-box union of active motion regions (from the motion gate diff) expanded by
`motion_gate_roi_margin_px`. This reduces effective input area — for a 2560×1440 camera with
motion only in a doorway, YOLO sees a 400×600 crop instead of the full frame.

- **TensorRT engine cache interaction (important for §6.1):** TensorRT engines compiled for a
  fixed input shape cannot accept variable crop sizes without a dynamic-shapes profile, which
  adds engine cache complexity. **Resolution:** resize every crop to a fixed canonical size
  (e.g. 640×640) before YOLO input. One engine, stable cache key. Slight quality cost on very
  small crops is acceptable; if accuracy loss on small/distant persons is measured as
  unacceptable in the §6.0.25 gate, ROI cropping is disabled and only the motion gate is
  retained. ROI cropping must be validated at interval=N *before* §6.1 TensorRT is added so
  the two interactions can be disentangled.
- Gated behind its own flag so it can be disabled without disabling the motion gate.

**Compound skip effect on identity coverage:**

A person entering frame on a YOLO-skip cycle will not receive a face-embedding pass until the
next YOLO frame. At interval=2 and 25 fps this is at most 80 ms; at interval=4 it is 160 ms.
A person who enters and exits between two YOLO frames is a missed identification, not merely a
late one. This risk motivates capping the interval for FULL-tier cameras and drives the
identity coverage metric in the gate:

- **Identity coverage rate:** fraction of person-frames that would have received a
  face-embedding pass under interval=1 that still receive one under interval=N. Target:
  ≥ 95% coverage at the configured interval. Measured on the §6.0 harness against a clip with
  person entries at varied phases of the interval cycle.

- **Gate:** measurable detector-GPU-time reduction on the §6.0 harness with **all four**
  metrics held within tolerance vs every-frame detection: (1) track continuity (ID-switch
  rate), (2) detection recall, (3) identity coverage rate (≥ 95%), (4) motion-gate
  false-negative rate (< 1% missed person-enters-frame events when `motion_gate_enabled`).
  Per-tier numbers reported separately. ROI-crop accuracy loss reported independently if
  `motion_gate_roi_crop_enabled`.

### §6.0.3 — Adaptive detector interval *(builds on §6.0.25; optional, measured separately)*
The fixed interval in §6.0.25 requires manual per-camera configuration to match actual scene
activity. An adaptive feedback loop removes that requirement and dynamically matches the
interval to real-time activity: a shift-change entrance gate (needs interval=1) and an empty
warehouse at 2am (can safely use interval=4) self-configure without operator intervention.

**Mechanism:**

- If the primary detector returns zero *new* person detections for `detector_adapt_window`
  consecutive YOLO frames, raise the interval by one step (up to `detector_interval_max`).
- If the detector returns ≥ 1 new person detection (a track ID not present in the preceding
  YOLO frame), immediately reset the interval to 1 for that camera.
- "New detection" means a person entering the field of view — not an existing track continuing.
  This boundary is important: resetting on track continuity would hold every active-scene
  camera at interval=1 even when no new persons are arriving, defeating the purpose.
- The interval is per-camera state, not global. One camera at interval=4 has no effect on a
  neighbouring camera at interval=1.

**Why this boundary is correct for the cascade:** resetting to interval=1 on a new-person
detection ensures the first YOLO frame after someone enters is immediately followed by
SCRFD→AdaFace, minimising the identity-coverage gap documented in §6.0.25. The reset is
triggered on confirmed detection, not on motion-gate activity alone (which may be background
noise or a non-person object).

**Interaction with motion gate (§6.0.25):** the adapt-window counter increments only on frames
that passed the motion gate *and* were a scheduled YOLO frame. A motion-gated-out frame does
not count toward the no-detection window — the scene may contain a stationary person not
detectable by frame diff. The interval resets only on confirmed new-person detection.

**Implementation:** a per-`PerCameraTracker` state machine — one counter and one current
interval per camera. No shared state, no cross-camera coupling.

**Config keys (all in `vms/config.py`):**
- `detector_interval_adaptive: bool = False` — master switch; when off, §6.0.25 fixed
  interval is used unchanged.
- `detector_interval_max: int = 4` — ceiling for the adaptive interval; also the upper bound
  for manual per-camera override via `cameras.model_overrides`.
- `detector_adapt_window: int = 5` — consecutive no-new-detection YOLO frames before raising
  interval by one step.

**Gate:** same four metrics as §6.0.25 gate, measured on a clip containing both idle periods
and activity bursts (e.g. a shift-change sequence followed by an empty period). Additionally:
interval distribution histogram (fraction of frames that ran at each interval value) — confirms
the adaptation is firing correctly and not stuck at 1 or pinned at max.

---

### §6.0.5 — Model format normalization to ONNX *(prerequisite for everything below)*
- Build a format-aware export step: each model in the manifest declares its source format
  (`onnx` | `ultralytics_pt` | `torch_pth` | `tf_savedmodel`) and the exporter normalizes it
  to ONNX. `.onnx` models pass through untouched.
- Exporters: Ultralytics `.export(format="onnx")` for YOLO/pose; `torch.onnx.export` for OSNet
  `.pth` (needs the torchreid model definition to load the state-dict into); `tf2onnx` attempt
  for MoViNet (with the documented fallback in §2.5).
- Wire into the existing `vms-models` CLI: `vms-models export <name>` produces the ONNX
  artifact; SHA-256 recorded in the manifest; output gitignored.
- **Validate every export numerically** — exported-ONNX output must match the source model's
  output within tolerance on a fixed input, *before* it feeds the §6.0 baseline. A silently-
  wrong export would poison every downstream accuracy comparison.
- **MoViNet native-TF warm-up (if staying on TF runtime):** if the §6.0.5 evaluation
  determines MoViNet cannot be exported to ONNX and stays on its native TF runtime, it requires
  a startup warm-up pass before the first live frame — analogous to the TensorRT engine
  warm-up in §6.1 but distinct in kind. TF Hub models incur graph-tracing latency on first
  inference; this must not land on a live camera frame. A warm-up pass (one dummy frame per
  camera-state slot, matching the input shape MoViNet expects) must complete before cameras
  attach, logged as `"MoViNet warm-up complete: Nms"`. This is a TF graph-trace cost, not an
  engine-build cost, but the timing constraint is identical: cameras must not be the trigger.
- **Gate:** all accelerable models have a verified ONNX artifact; MoViNet decision recorded
  (exported, or stays native-TF and excluded from §6.1+); if native-TF, warm-up timing
  recorded (must complete in < 10 s to avoid delaying camera attach on startup).

### §6.1 — ONNX Runtime TensorRT EP, FP16 *(the primary win)*
- Add `TensorrtExecutionProvider` to the provider list in `detector.py`, `embedder.py`,
  `ppe.py`, and any other `InferenceSession` construction (grep confirms these three).
- Configure the EP: engine cache directory (so the expensive build happens once, not every
  boot), FP16 enable flag (arch-gated), workspace size, and a **model warm-up pass** on
  startup (first inference triggers the JIT engine build — must happen before cameras attach,
  not on the first live frame).
- **Identity-correctness guard (mandatory):** FP16 changes embedding numerics. Before FP16
  AdaFace ships, run the §6.0 harness to confirm cosine-similarity drift vs FP32 stays within
  tolerance and that `reid_*` / `adaface_min_sim` thresholds still hold. **Per CLAUDE.md §0.5
  this is a MANDATORY /advisor checkpoint** — any threshold change requires it.
- **Cold-cache detection + ops logging (mandatory):** `build_ort_providers()` must detect
  whether the engine cache directory contains `.engine` files. If empty, log at WARNING level:
  `"TRT engine cache cold — first inference will trigger engine build (est. 3-8 min). Cameras
  will not attach until build completes."` A silent multi-minute stall at startup reads as a
  hang to operators unfamiliar with TRT. The ops runbook for every `vms-models swap <name>`
  must include: delete `models/trt_engines/` to force a clean rebuild on next start, and expect
  this build delay. Logging is the only defence against a support ticket at model-swap time.
- **Gate:** ≥2× frames/sec/GPU vs §6.0 baseline, identity accuracy within tolerance, CPU
  fallback still green in CI.

### §6.2 — INT8 quantization *(arch-gated; skipped on Volta)*
- Only runs where `GpuProfile.supports_int8` is true with a meaningful speedup (Turing+).
- Requires a **calibration dataset** (representative plant frames) for post-training
  quantization of YOLO/SCRFD. Detectors tolerate INT8 well; **embedding models (AdaFace,
  OSNet) are the risk** — INT8 can move the similarity manifold enough to break identity
  matching.
- **Hard rule:** INT8 is applied to *detectors first*. INT8 on AdaFace/OSNet is a separate,
  explicitly-gated decision requiring full identity re-validation and **/advisor sign-off**
  (CLAUDE.md §0.5 — changing identity thresholds is non-negotiable). Default: detectors INT8,
  embedders stay FP16.
- **Calibration dataset — use deployment-site frames, not generic CCTV:** PTQ calibration
  with frames from generic CCTV footage produces suboptimal quantization for factory floors
  (different lighting, overhead angles, occlusion patterns). `VMS_GPU_INT8_CALIBRATION_DIR`
  must be populated with representative frames captured *after site go-live* — covering day,
  night, shift-change periods, and the actual camera angles at the specific installation. This
  is a **deployment step, not a build step**. Leave `gpu_tensorrt_int8=false` (the default)
  until a site-specific calibration set exists; mark INT8 enablement as a post-MVP task in the
  Phase 6c plan.
- **Gate:** additional throughput gain measured; identity accuracy unchanged; per-model
  precision recorded in the model manifest.

### §6.3 — NVDEC hardware decode *(ingestion-side; lower priority than §6.4)*

**Priority note (added 2026-06-22, Opus advisor):** §6.3 is explicitly *below* §6.4 (Triton)
in the build order. CPU decode is not the bottleneck at 12–30 cameras; after motion-gate +
detector-interval savings cut idle-frame decode work, additional CPU cores on the hardware spec
are a cheaper lever than a custom NVDEC integration. §6.3 must never gate the 52-cam target.

- Move RTSP H.264/H.265 decode from CPU (OpenCV/FFmpeg software) to the GPU video engine.
- **Windows implementation:** there is no clean Python-accessible NVDEC path on Windows
  equivalent to Linux's `nvv4l2decoder` / GStreamer `nvdec` / DeepStream path. The preferred
  Windows approach, if §6.3 is ever justified by measurement, is **FFmpeg `h264_cuvid` decode
  launched as a subprocess feeding raw frames via shared memory** — lighter than the Video
  Codec SDK ctypes bindings and avoids the CPU→GPU copy (frames decoded to VRAM via cuvid).
  Do NOT plan for Video Codec SDK direct API integration in Python — the engineering cost
  exceeds the benefit at 52 cameras with other levers available.
- Probe `nvdec_units` — consumer cards have 1–2 NVDEC units (a real ceiling for 52 streams);
  data-center cards are effectively unlimited. The probe decides whether NVDEC handles all
  cameras or only a subset, with the rest staying on CPU decode.
- Touches `vms/ingestion/worker.py` (a performance-sensitive path per CLAUDE.md §0.6 — measure
  before/after).
- **Build trigger:** only if the §6.0 harness shows CPU decode is contributing ≥10ms/frame to
  the end-to-end budget *after* §6.0.25 motion-gate savings are applied. Do not build
  speculatively.
- **Gate:** CPU decode load drops materially; no increase in dropped/stale frames.

### §6.4 — Cross-camera dynamic batching via Triton *(52-cam scale lever; deploy topology during MVP)*

**Deployment risk note (added 2026-06-22, Opus advisor):** The code change to enable Triton is
one config line (`VMS_GPU_TRITON_URL`). The *deployment* — WSL2 GPU passthrough on Windows
Server + customer-controlled NVIDIA drivers + rootless Docker + ops runbook — is weeks of work.
**Stand up Triton-in-WSL2 during the 10–12 camera MVP** as a deployment-validation exercise
(not a throughput task). Prove GPU passthrough on representative Windows Server + driver combos,
automate the install, write the runbook, and smoke-test `VMS_GPU_TRITON_URL` against a few
live cameras at MVP. At 52-cam go-live, the topology is then proven and the switch is genuinely
one line. Discovering a WSL2/driver incompatibility at the 52-cam launch is the failure mode to
prevent.

**Windows Triton deployment recipe:**
- Triton ships as a Linux Docker image (no native Windows build). Run inside WSL2 on Windows
  Server 2022 or Windows 11 Pro.
- Prefer **rootless Docker in WSL2** (or `dockerd` directly in WSL2 via systemd) over Docker
  Desktop — Docker Desktop has a commercial license restriction for large enterprises that
  applies to customer hardware.
- WSL2 GPU passthrough requires NVIDIA driver ≥ 535 on the Windows host and the WSL2 kernel
  package `nvidia-utils-xxx`; probe and document the minimum driver version required.
- Set `.wslconfig` `memory` and `swap` limits explicitly — WSL2's default memory ballooning
  can starve the Triton container on a server running VMS + DB + Redis simultaneously.

**Compatibility matrix — the real deliverable of the MVP Triton exercise:**
The exercise is not complete until this table is filled in and committed to the deploy runbook.
"Works" = Triton-in-WSL2 starts cleanly, GPU passthrough confirmed, `VMS_GPU_TRITON_URL`
smoke-test passes against ≥3 live cameras.

| Windows Server / OS | NVIDIA driver branch | WSL2 kernel pkg | Docker engine | Status |
|---|---|---|---|---|
| Windows Server 2022 (21H2) | 535.x | nvidia-utils-535 | 24.x rootless | ○ untested |
| Windows Server 2022 (21H2) | 555.x | nvidia-utils-555 | 24.x rootless | ○ untested |
| Windows 11 Pro 23H2 | 555.x | nvidia-utils-555 | 24.x rootless | ○ untested |

Fill "Status" during MVP (○ untested / ✓ confirmed / ✗ incompatible + reason). Add the minimum
confirmed row as a customer pre-requisite in the deployment guide. **Do not ship Triton as a
supported configuration without at least one ✓ row.**

**Scale trigger:** in-process TRT EP suffices through ~20–30 cameras on a 32 GB Ada/Ampere-class
GPU with FP16 + motion-gate + detector-interval engaged. Triton's cross-camera batching becomes
the marginal lever in the 30→52 band, where un-batched per-camera dispatch stops amortizing
kernel launches. The §6.0 harness (GPU utilization crossing ~70% sustained) is the precise
trigger point — do not hard-commit a camera number before it is measured.

- Stand up **Triton Inference Server** hosting the TensorRT engines; the `InferenceEngine`
  becomes a Triton client. Triton batches frames *across cameras* into one GPU pass — the
  single biggest throughput multiplier at 52 cameras.
- Preserves the Redis-Streams bus (CLAUDE.md §17 invariant): ingestion → inference still flows
  through `frames:groupN`; only the model-execution call inside the engine changes.
- `VMS_GPU_TRITON_URL=""` (empty) = current in-process EP; set to `http://localhost:8001` =
  Triton client mode. This is the only code change in `engine.py`.
- **Gate:** sustained 52-camera real-time at ≤50 ms/frame end-to-end (CLAUDE.md §0.6 target),
  with batching latency within budget.

### §6.5 — Multi-GPU sharding *(the second 32 GB card)*
- With two GPUs: shard cameras across them via the existing `cameras.worker_group` mechanism
  (already used for ingestion partitioning — no new concept). Each GPU runs its own TensorRT
  engines / Triton instance consuming its partition of `frames:groupN`.
- `IdentityService` stays single (not GPU-bound) and receives detections from both — exactly
  the two-node topology in §G.2 of the v2 spec, collapsed onto one host with two cards.
- FAISS remains a single derived cache (CLAUDE.md §17 invariant) rebuilt from `person_embeddings`.
- **Gate:** ~2× aggregate camera capacity vs single-GPU; clean failover if one GPU is lost
  (its cameras degrade, the other GPU's cameras unaffected).

### §6.6 — DeepStream evaluation *(go/no-go; only if still short)*
- **Only built if §6.1–6.5 fail to hit the throughput target.** Spike DeepStream's
  GStreamer NVDEC + nvinfer batched pipeline for a camera subset; compare frames/sec/GPU and
  engineering cost against the Triton path.
- **Windows constraint (hard):** DeepStream is Linux-only. For a Windows-first on-prem SaaS
  product, adopting DeepStream requires every customer deployment to run a Linux VM or container
  (WSL2 with GStreamer + NVDEC passthrough), which adds a mandatory infrastructure dependency
  the operator must install and maintain per site. This cost must be quantified in the go/no-go
  evaluation — it is not just an engineering trade-off, it is a customer-ops burden.
- Explicit decision record: adopt, partially adopt (decode only), or reject. DeepStream's
  CUDA lock-in and rewrite cost must be justified by measured headroom the Triton path cannot
  reach.
- **Gate:** a written recommendation with numbers, not a rewrite. Adoption is unlikely given the
  Windows-first deployment model — the Triton path (§6.4) provides ~80% of DeepStream's
  inference benefit without the rewrite or Linux dependency.

### §6.7 — Dual-stream analytics substream *(ingestion-side; immediate win)*

IP cameras with dual-stream support expose:
- **Main stream:** full resolution (2MP–4K), H.265 — stored for playback and forensic clips.
- **Sub-stream / analytics stream:** reduced resolution (720p–1080p), H.264 — for analytics.

For the VMS inference pipeline, **only the analytics substream should be ingested.** Running
SCRFD/YOLO on 4K frames wastes decode CPU and GPU resize cycles — all models resize internally
to 640×640 or smaller. At 52 cameras this is a meaningful idle-CPU reduction that requires no
NVDEC and no model changes.

**Implementation:** `cameras.analytics_rtsp_url` (nullable `String(500)`). When set, the
ingestion worker opens this URL instead of `rtsp_url`. `rtsp_url` remains the primary/storage
stream URL (used by recording/clip features). When `analytics_rtsp_url` is null the worker
falls back to `rtsp_url` — backwards-compatible with all existing deployments.

```python
# vms/ingestion/worker.py — _capture_loop
_stream_url = self._camera.analytics_rtsp_url or self._camera.rtsp_url
cap = cv2.VideoCapture(_stream_url)
```

**Ops note:** when configuring a new camera with dual-stream support, set
`analytics_rtsp_url` to the sub-stream URL (typically `rtsp://.../stream2` or `/ch0/sub`)
and leave `rtsp_url` pointing at the main stream. **Never log `analytics_rtsp_url` at INFO
level** — it contains RTSP credentials (CLAUDE.md §7.2).

**Gate:** no throughput benchmark required (purely additive); confirm the analytics stream
resolution is ≥ 640px on the shorter side before setting — sub-streams at 320×240 are not
acceptable (YOLO accuracy degrades below 640px input). Log the stream resolution at worker
startup so operators can verify.

---

## §4. Re-modeled capacity target

§G.2 of the v2 spec estimates ~200–300 ms GPU-time/sec/camera under plain CUDA-EP, i.e.
~25–30% utilisation/camera → roughly one A4000-class GPU for 52 cams. Phase 6 targets:

| Lever | Expected effect (to be confirmed by §6.0 harness) |
|---|---|
| Motion gate pre-filter (§6.0.25) | Eliminates YOLO entirely on quiescent frames; savings proportional to idle fraction per camera. High for back-corridor cameras (may be 30–60% of frames); near-zero for entrance gates. Stacks additively with fixed interval. No TensorRT needed. |
| Detector interval (§6.0.25) | Cuts primary-detector passes by the interval factor (e.g. interval=2 ≈ −50% detector GPU-time); cascade stages unchanged. No TensorRT needed. |
| Adaptive interval (§6.0.3) | Captures the motion-gate savings automatically without operator tuning; same ceiling as fixed interval but self-adjusting per camera. Incremental over §6.0.25. |
| TensorRT FP16 (§6.1) | 2–3× inference throughput per GPU |
| INT8 detectors (§6.2, arch-permitting) | +30–50% on detector stages |
| Dynamic batching (§6.4) | Large multiplier at high camera counts (amortizes kernel launch) |
| NVDEC (§6.3) | Frees CPU cores; removes the §G.1 decode ceiling |

**Hard target:** sustained 52 cameras at ≤50 ms/frame end-to-end on a **single** 32 GB GPU
(CLAUDE.md §0.6), with the second GPU providing headroom-to-~100+ cameras and redundancy, not
a requirement for the base 52. All numbers in this table are hypotheses until §6.0 measures
them on the real card — **no capacity claim ships without a benchmark behind it** (CLAUDE.md
production-readiness discipline).

---

## §5. Config additions (`vms/config.py`)

All tunables go through settings per CLAUDE.md §12 — no hard-coded GPU constants.

```python
# gpu acceleration (Phase 6)
detector_interval_frames: int = 1             # 1 = detect every frame (current). N>1 = §6.0.25 track-to-bridge; per-camera override via cameras.model_overrides
gpu_tensorrt_enabled: bool = False            # master switch; False = current CUDA/CPU path
gpu_tensorrt_fp16: bool = True                # arch-gated at runtime by GpuProfile
gpu_tensorrt_int8: bool = False               # detectors only; never embedders without /advisor
gpu_tensorrt_engine_cache_dir: str = "models/trt_engines"
gpu_tensorrt_workspace_mb: int = 4096
gpu_nvdec_enabled: bool = False               # ingestion-side hardware decode
gpu_triton_url: str = ""                      # empty = in-process EP; set = Triton client mode
gpu_int8_calibration_dir: str = ""            # representative frames for PTQ
gpu_onnx_export_dir: str = "models/onnx_exported"   # normalized ONNX artifacts (§6.0.5)

# motion gate and ROI cropping (§6.0.25)
motion_gate_enabled: bool = False             # pre-filter YOLO with lightweight frame-diff/MOG2 gate
motion_gate_method: str = "frame_diff"        # "frame_diff" | "mog2"; mog2 more stable across lighting
motion_gate_min_pixel_diff_pct: float = 0.5  # fraction of pixels that must change; tune per deployment
motion_gate_roi_crop_enabled: bool = False    # crop YOLO input to motion-region bounding box + margin
motion_gate_roi_margin_px: int = 32          # expand motion ROI by this many pixels before crop

# adaptive detector interval (§6.0.3)
detector_interval_adaptive: bool = False      # enable feedback-loop interval; off = §6.0.25 fixed interval
detector_interval_max: int = 4               # ceiling for adaptive interval (also per-camera override cap)
detector_adapt_window: int = 5               # consecutive no-new-detection YOLO frames before raising interval
```

Per-model source format and exporter hint live in the **model manifest** (`models/manifest.json`),
not in `config.py` — they are per-model facts, not global tunables. The manifest already keys
models by name with SHA-256 (CLAUDE.md §8); §6.0.5 adds a `source_format` /`exporter` field.

`VMS_GPU_*` env vars. The master switch defaults **off** so existing deployments and CI are
unaffected until a deployment opts in.

---

## §6. Risks & gotchas

| Risk | Mitigation |
|---|---|
| **FP16/INT8 shifts embedding numerics → identity matching degrades** | §6.0 accuracy harness vs FP32 baseline; embedders stay FP16-min; INT8-on-embedders gated behind /advisor (CLAUDE.md §0.5). Identity correctness is operational-priority #2 (CLAUDE.md §4.4) — above throughput (#4). |
| **Detector-interval skipping (§6.0.25) misses fast events or accumulates cascade error** | Interval applies to the primary detector only; cascade (face/body embedding) is exempt and keeps gate-based sampling. Interval bounded per-tier; §6.0 harness checks ID-switch rate + recall vs every-frame before the value ships. A high-priority event-driven camera can stay at interval=1. |
| **Motion gate false-negative: person enters on a frame below the diff threshold** | Slow-moving entry on a static background may not generate enough frame diff on the first frame. `mog2` mode more robust than `frame_diff` for slow entry. Calibration target < 1% false-negative rate; measured in §6.0.25 gate. `motion_gate_min_pixel_diff_pct` tunable per deployment. |
| **ROI crop + fixed-size resize degrades small/distant persons** | Resizing a small motion-region crop to canonical YOLO input size may drop sub-pixel persons in the background. Validated in §6.0.25 gate before enabling; `motion_gate_roi_crop_enabled` defaults off and can be disabled independently of the motion gate. If accuracy loss is unacceptable, only the motion gate pre-filter is retained. |
| **Adaptive interval (§6.0.3) stuck at max during genuine low-activity period, misses burst** | Interval resets to 1 immediately on any new-person detection — one missed detection at max interval is the worst case (160 ms at interval=4 / 25 fps). `detector_interval_max` capped at 4 by default; entrance-gate cameras can set `detector_interval_max=1` per-camera to disable adaptation for that camera. |
| **Mixed model formats (`.pt`/`.pth`/SavedModel) silently mis-export to ONNX** | §6.0.5 validates every export numerically vs the source model on a fixed input before it feeds the baseline; format declared per-model in the manifest; never infer from extension alone. |
| **Re-downloaded model arrives in a different format than last time** | Loader dispatches on actual file inspection + manifest exporter hint, not a hard-coded extension; a format change is a manifest edit, not a code change. |
| **MoViNet stateful streaming graph won't export to ONNX** | Documented fallback: stays on native TF runtime, excluded from TensorRT (smallest GPU slice, already trigger-gated). Decision recorded in §6.0.5. |
| TensorRT engine build is slow (minutes) and runs on first inference | Engine cache dir + startup warm-up pass before cameras attach; cache keyed by model hash + GPU arch + precision. |
| Engine cache invalid after model swap or driver upgrade | Cache key includes model SHA-256 (already in manifest) and compute-cap; mismatch triggers rebuild, logged. |
| Non-determinism breaks tests that assert exact detection coords | Tests assert tolerances, not bit-exact values; CPU/CUDA path remains the deterministic CI reference. |
| Consumer-card NVDEC unit limit silently caps decode | Probe `nvdec_units`; log the cap explicitly; fall the overflow back to CPU decode (no silent truncation — CLAUDE.md discipline). |
| DeepStream scope-creep | Hard go/no-go gate in §6.6; not built unless §6.1–6.5 measurably fall short. |
| Performance-sensitive paths regress | `worker.py`, `engine.py` changes measured before/after per CLAUDE.md §0.6. |
| Dual-stream sub-stream resolution below YOLO minimum | Log stream resolution at worker startup; reject sub-streams with shorter side < 640px with a clear ERROR and fall back to `rtsp_url`. Prevents silent accuracy degradation from a misconfigured `analytics_rtsp_url`. |
| Body-only identification at face-limited cameras (e.g. overhead/angle cameras like CAM110) | `resolved_via='body'` in `tracking_events` IS the body_only signal — no separate column needed. Future `tracking_events` API routes must include `resolved_via` in responses. Guard view must show a visual indicator when `resolved_via='body'` so operators apply appropriate skepticism. This is an accuracy-disclosure obligation: at calibrated thresholds body Re-ID is reliable, but operators need to know face confirmation was unavailable. |

---

## §7. Definition of done (per sub-phase)

Each sub-phase, before its plan checkbox is marked complete:
- Benchmark numbers recorded (§6.0 harness) — before vs after, on the real GPU.
- Identity-accuracy delta vs FP32 baseline within tolerance (any threshold change → /advisor).
- CPU fallback path still green in CI (the no-GPU dev/CI contract is never broken).
- All new tunables in `config.py`; no hard-coded GPU literals.
- Redis-Streams bus and FAISS-derived-cache invariants (CLAUDE.md §17) intact.
- `black` / `ruff` / `mypy --strict` clean; coverage at target.

---

## §8. Out of scope

- On-camera (smart-camera) edge inference offload — already deferred to v2.x in the v2 spec.
- Replacing PostgreSQL / Redis / FAISS roles (architectural invariants, CLAUDE.md §17).
- Model architecture changes (this spec is about *executing the existing models faster*, not
  swapping SCRFD/AdaFace/YOLO/OSNet for different networks).
- FP8 (Hopper) — noted as future; not specced until an H100-class deployment exists.
- Kafka migration (§G.3 step 3 of the v2 spec — separate scaling concern, >200 cameras).

---

## §9. Sequencing note

This is a **Draft spec** — per CLAUDE.md §4.1 no implementation begins until it is reviewed
and approved, and each sub-phase then gets its own plan file in `docs/superpowers/plans/`
before code. Recommended order: **§6.0 (harness) → §6.0.25 (detector interval + motion gate + ROI crop,
the cheap wins, no TensorRT) → §6.0.3 (adaptive interval, optional; only if §6.0.25
measurements show per-camera manual tuning is burdensome) → §6.0.5 (ONNX normalization,
prerequisite for §6.1+) → §6.1 (TensorRT FP16, the bulk of the win)** — each is measured on
the harness before the next. Only then decide how far up §6.2–6.6 to climb; §6.6 (DeepStream)
is a last-resort rewrite, not a default — the opposite of how the source post frames it,
because TensorRT EP preserves our pipeline structure and gets most of the win without the
CUDA-lock-in rewrite. Phase 6 does not start until Phase 4 (frontend) and Phase 5 (security)
priorities are weighed by the user — it is an optimization phase, not a correctness gap.
