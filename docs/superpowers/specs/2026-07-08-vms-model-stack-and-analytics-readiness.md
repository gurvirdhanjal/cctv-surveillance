# VMS Model Stack & Analytics Readiness
**Design Specification** · 2026-07-08
**Status:** Approved (open questions resolved by user 2026-07-08 — see §12)

---

## 1. Purpose

This spec is the single authoritative description of every ML model the VMS runs, how each
is served on the GPU, how detections are bound to persons frame-by-frame, and how that
identity data flows (or is supposed to flow) into plant-wide analytics and the frontend.

It also answers a direct product question against the day-one requirement:

> *"Make existing IP cameras AI-powered. Host any model on our GPU server. Do proper
> plant/site-wide analytics. Facial recognition so we can answer: where was Brijesh
> at 2 PM?"*

Section 2 traces that requirement against the live codebase. Section 7 assesses whether
each model is optimised and accurate enough, and what remains to extract full value.
Section 10 is the gap register with a proposed remediation order.

**Relationship to other specs.** This spec does not supersede anything. It consolidates:
`2026-06-13-vms-gpu-acceleration.md` (serving architecture), `2026-05-01-vms-v2-hardened-design.md`
(pipeline + anomaly framework), `2026-07-08-vms-frontend-premium-polish.md` Part V /
Phase 4P plan (analytics endpoints), and the Phase 6b/6c plans and notes (measured numbers).
Where those disagree with this document, they win; this spec's new content is §8–§10
(homography calibration API, person timeline API, gap register).

---

## 2. Day-one requirement traceability

| Requirement | Status | Evidence / Gap |
|---|---|---|
| **Existing IP cameras become AI-powered** | ✅ Working | `scripts/multi_cam_pipeline_test.py` runs 2–5 Hikvision RTSP cameras through the full production model stack (SCRFD + AdaFace + YOLO-pose/BoT-SORT + TransReID + PPE + violence) at 30 fps display with per-camera stats. Ingestion → inference → writer services do the same in production mode. |
| **GPU server hosts any model** | ✅ Architecture in place | Two serving paths, switchable by config only: in-process ONNX Runtime with TensorRT FP16 EP (Phase 6b, active) and Triton Inference Server gRPC (Phase 6c, complete, smoke-tested 2026-06-26). `scripts/build_triton_repo.py` generates a Triton model repo from any ONNX file — adding a new model is an export + config.pbtxt, zero pipeline code. |
| **Optimised GPU inference** | ✅ Measured, one gate open | 27× serial speedup vs CPU (15.4 ms vs 413 ms for SCRFD+AdaFace+TransReID+PPE), VRAM 1,125 MB of 16 GB at 5 cameras, GPU util 97%. **Open gate:** FP16 cosine-drift check on real crops (Phase 6b Task 5 first step) has not run yet — TRT FP16 accuracy is unvalidated on plant footage. |
| **Frames accurately bound to persons** | ✅ Per-camera / ⚠️ cross-camera partial | BoT-SORT `local_track_id` → `assign_and_identify()` → `(global_track_id, person_id, resolved_via)` persisted to `tracking_events` with bbox, timestamps, and floor coordinates. Cross-camera merge is gated by `CameraTopology` transit windows + margin gate. Body-anchor propagation across cameras is minimal (see §6.3). |
| **Known persons tracked once enrolled** | ✅ Backend / ⚠️ frontend wiring | Enrolment → `person_embeddings` → FAISS incremental add via dirty queue → every future face match resolves `person_id`. EnrolmentWizard's final embedding push is flagged as not fully wired (Phase 4P Task 15). No "alert when person X seen" follow feature. |
| **Plant/site-wide analytics** | ❌ Biggest gap | Frontend pages exist (AnalyticsDashboard, Heatmap, TimeScrubber) but call endpoints that return 404: `/api/analytics/kpi`, `/api/analytics/head-count`. All planned in Phase 4P — **not started**. |
| **"Where was Brijesh at 2 PM?"** | ❌ Data exists, no API | `tracking_events` has `person_id` (indexed), `event_ts` (indexed), `camera_id`, `zone_id`, `floor_x/floor_y` — the query is a single indexed SELECT. **No endpoint exposes it.** Phase 4P adds only `last_seen_at` on person detail; a full timeline/sightings endpoint is not planned anywhere. §9.2 of this spec defines it. |
| **Homography / floor-plan analytics** | ⚠️ Half-built | `cameras.homography_matrix` storage, `project_to_floor()` foot-point projection, and `floor_x/floor_y` persistence all work. Frontend `HomographyCalibrator.tsx` exists. **Missing:** the API endpoint to save a calibrated matrix, and any endpoint that reads floor coordinates back out (heatmap, live floor-plan positions). |

---

## 3. Model inventory

All model binaries live in `models/` (gitignored), tracked by `models/manifest.json`.
Every threshold below is a `VMS_*` env var in `vms/config.py` — never hard-coded.

### 3.1 Person detection + pose + tracking — YOLO26m-pose + BoT-SORT

| | |
|---|---|
| Weights | `models/yolo26m-pose.pt` / `models/yolo26m-pose.engine` (TRT 10.9, 48.6 MB) |
| Wrapper | `vms/inference/tracker.py` — `PerCameraTracker` |
| Output | Person bbox + 17 COCO keypoints per detection; BoT-SORT assigns `local_track_id` |
| Serving | Ultralytics native; TRT via pre-built `.engine` (`VMS_YOLOV8X_POSE_MODEL=models/yolo26m-pose.engine`) — independent switch from the ORT TRT flag |
| Thresholds | `yolo_person_conf=0.50` (raise to 0.60–0.70 on overhead views); `tracker_buffer_frames=90` |
| Role in binding | This is the **anchor model**: every downstream identity signal (face, body, PPE) attaches to its tracklets. Keypoints also drive the face-visibility gate and pose-normalised torso crops. |

BoT-SORT was chosen over ByteTrack for camera-motion compensation (sparse optical flow) —
robust to factory vibration. Config rendered at runtime from `botsort_custom.yaml`.

### 3.2 Face detection — SCRFD-10G-KPS

| | |
|---|---|
| Weights | `models/scrfd_10g_bnkps.onnx` (WiderFace Hard 82.8% — SOTA-class for its size) |
| Wrapper | `vms/inference/detector.py` |
| Input | 640×640 letterbox, `(px−127.5)/128`, RGB CHW |
| Output | 9 tensors (cls/bbox/kps × strides 8/16/32), **pre-sigmoid**, 5-point landmarks |
| Thresholds | `scrfd_conf=0.60`, `min_face_px=40`, NMS IoU 0.35 |
| Latency | 2.3 ms TRT FP16 (CPU: 20.5 ms) |
| Gating | Only runs when a tracklet's nose+eye keypoint confidence ≥ `face_kpt_min_conf=0.5` (~30% GPU saved on ceiling cameras) |

### 3.3 Face embedding — AdaFace IR-101 / WebFace12M

| | |
|---|---|
| Weights | `models/adaface_ir101_webface12m.onnx` (CVLFace) |
| Wrapper | `vms/inference/embedder.py` |
| Input | 112×112, **RGB** (CVLFace convention), `(px−127.5)/127.5`, 5-point affine alignment from SCRFD landmarks (LMEDS), Lanczos fallback crop |
| Output | 512-d L2-normalised; pre-norm L2 kept as quality signal |
| Thresholds | `adaface_min_sim=0.72` ⚠️ **stale — set for old IR50/MS1MV2; re-calibration on real footage is a mandatory `/advisor` gate**; `min_blur=25.0` Laplacian |
| Latency | 2.2 ms TRT FP16 (CPU: 230.9 ms — the single biggest TRT win, 105×) |
| Role | Primary identity signal. FAISS `IndexIDMap2(IndexFlatIP(512))` over `person_embeddings`. |

### 3.4 Body re-identification — TransReID-SSL ViT-B/16+ICS (MSMT17)

| | |
|---|---|
| Weights | `models/transreid_body_msmt17.onnx` (75.1 mAP / 89.6 R1 on MSMT17) |
| Wrapper | `vms/inference/body_embedder.py` — `TransReIDBodyEmbedder` |
| Input | 384×128, ImageNet-normalised RGB; **pose-normalised torso crop** (shoulders+hips keypoints, `torso_kp_conf_threshold=0.3`, 20% pad) with full-bbox fallback |
| Output | 768-d L2-normalised + Laplacian-variance quality |
| Thresholds | `reid_body_confirmed_sim=0.65`, `reid_body_cross_cam_sim=0.70` — calibrated 2026-06-16 **on webcam footage** (same-person p5 0.843, diff-person p99 0.450). Expected real-camera degradation: same p5 ~0.70–0.75. Re-calibration on plant cameras is a mandatory `/advisor` gate. |
| Latency | 4.2 ms TRT FP16 (CPU: 34.8 ms) |
| Role | Secondary identity signal; **first pass** in cross-camera matching (angle-invariant), face as fallback. Carries identity when the face is occluded/blurred (CAM105/CAM200-class cameras). |

**Alternative:** `models/osnet_ain_x1_0_msmt17.onnx` (512-d, dynamic batch, opset 17) is
exported and Triton-validated (cosine ≥ 0.9999 vs PyTorch) — the batching-friendly option
for 30+ camera Triton deployments. Not active by default.

### 3.5 PPE compliance — YOLOv8l SH17

| | |
|---|---|
| Weights | `models/sh17_ppe_yolov8l.onnx`; enabled by setting `VMS_PPE_MODEL` |
| Wrapper | `vms/inference/ppe.py` |
| Classes | helmet=10, vest=16, gloves=9, mask=5 (SH17 indices — do not change) |
| Thresholds | per-class 0.5; pre-NMS conf 0.25; NMS IoU 0.45; `ppe_gate_min_persons=1` |
| Latency | 6.7 ms TRT FP16 (CPU: 127.1 ms) — the slowest ONNX model; runs per-person-crop |

### 3.6 Violence — R(2+1)D-18 (Kinetics-400)

| | |
|---|---|
| Weights | torchvision KINETICS400_V1 (native PyTorch, **not** ONNX/Triton — 16-frame clip buffering doesn't fit Triton's stateless batching) |
| Wrapper | `vms/inference/violence.py`; replaced MoViNet A2 (Phase 6c Task 8 verdict: no ONNX export needed) |
| Method | sigmoid(max logit over 9 violence-adjacent K400 classes: wrestling, slapping, headbutting, kicks, …) on 16-frame 112×112 clips, stride 8 |
| Thresholds | `violence_threshold=0.65`, gated on ≥2 persons (`violence_gate_min_persons`) |
| ⚠️ Accuracy note | This is a **zero-shot proxy**, not a trained violence classifier. K400 action classes correlate with, but do not equal, plant-floor violence. Expect false positives on vigorous manual labour and false negatives on shoving/grappling that resembles no K400 class. See §7.4. |

### 3.7 Not yet deployed

| Model | Purpose | Status |
|---|---|---|
| CLIP-ViT-B/32 text encoder | Natural-language forensic search (`GET /api/forensic/search`) | Endpoint returns 501; blocked on `VMS_CLIP_MODEL` pipeline (recording/analytics spec Phase 3) |
| Fine-tuned violence classifier | Replace K400 proxy | No spec yet — see §10 |

---

## 4. Serving & GPU optimisation architecture

### 4.1 Two switchable serving paths (zero code change between them)

```
                     ┌── VMS_GPU_TRITON_URL=""  ──────► in-process ONNX Runtime
frame ─► pre-process─┤                                   └ TensorRT EP (FP16) ► CUDA EP ► CPU EP
                     └── VMS_GPU_TRITON_URL=host:8001 ─► tritonclient.grpc.infer()
                                                          └ Triton ORT backend, dynamic batching
```

- `InferenceBackend` Protocol (`vms/inference/backend.py`): `detect / embed / embed_body / score_ppe`.
  `OrtInferenceBackend` and `TritonInferenceBackend` share **identical Python pre/post-processing**
  (letterbox, NMS, affine alignment, torso crop) — only the kernel call differs. Triton smoke test
  (2026-06-26) proved bit-identical outputs (cosine 0.999998–1.000000) and 0.95× throughput at
  1 camera (batching benefit begins ~30 cameras).
- TRT engine cache: `models/trt_engines/` (gitignored; first build ~5 min total, then <1 s loads).
  Delete on driver upgrade. Workspace on 16 GB cards: `VMS_GPU_TENSORRT_WORKSPACE_MB=2048`.
- FP16 is architecture-gated at runtime (`vms/inference/gpu_profile.py`, Volta+). INT8 is
  config-present but **prohibited for embedders** without `/advisor` (identity correctness).
- Every ONNX wrapper runs a TRT warm-up pass at load (added to body_embedder/PPE in Phase 6b
  Task 2) — without it the first live frame stalls 2–5 min on engine build.

### 4.2 Measured performance (RTX 2000 Ada 16 GB, Phase 6b Task 4)

| Model | CPU | TRT FP16 | Speedup |
|---|---|---|---|
| SCRFD 640² | 20.5 ms | 2.3 ms | 8.9× |
| AdaFace 112² | 230.9 ms | 2.2 ms | 105× |
| TransReID 384×128 | 34.8 ms | 4.2 ms | 8.3× |
| PPE YOLOv8l 640² | 127.1 ms | 6.7 ms | 19× |
| **Serial total** | **413 ms** | **15.4 ms** | **27×** |

VRAM steady-state 1,125 MB / 16,380 MB (6.9%) at 5 cameras; +33 MiB per additional YOLO
camera context; safety ceiling 14 GB. Headroom for 52 cameras is ample on the compute side.

### 4.3 Per-frame cost-control ladder (all off by default at MVP)

1. **Keypoint face gate** (on): SCRFD+AdaFace skipped unless a tracklet's face is visible.
2. **Motion gate** (`motion_gate_enabled=False`): frame-diff or MOG2; skips YOLO on static scenes.
3. **Fixed/adaptive detector interval** (`detector_interval_frames=1`; adaptive off): tracker
   coasts on Kalman prediction between YOLO runs. Held at 1 during Phase 6b by `/advisor` decision —
   do not mix interval tuning with TRT enablement.
4. **ROI crop** (`motion_gate_roi_crop_enabled=False`): YOLO input cropped to motion regions,
   fixed 640² resize to keep the TRT engine cache key stable.

Scale-by-config ladder (from Phase 6c): 1–12 cams = ORT in-process; 12–30 = Triton batch 8 +
motion gate; 30–52 = batch 16 + adaptive interval + ROI; 52–100+ = multi-GPU worker groups.
**No Python changes at any rung.**

### 4.4 Stream decoding — current state and known limit

Decoding is **CPU FFmpeg** (OpenCV `CAP_FFMPEG`, TCP-forced RTSP, dedicated reader thread
per camera draining at camera speed, inference reads latest frame). NVDEC (`gpu_nvdec_enabled`)
is config-present but not implemented.

> **Update 2026-07-08:** the user has confirmed from live multi-camera runs that **CPU decode
> is the observed bottleneck** — the §6.3 build trigger is met. Phase 6d is activated for
> NVDEC decode only (INT8 remains deferred). Plan:
> `docs/superpowers/plans/2026-07-08-vms-phase6d-nvdec-gpu-decode.md`. The plan's Task 0
> still records the quantified before/after baseline, as §6.3 requires ("measure
> before/after" — worker.py is a §0.6 performance-sensitive path).

### 4.5 The interactive test pipeline (`scripts/multi_cam_pipeline_test.py`)

Observation-only harness (no DB/Redis writes) that exercises the **production** wrappers on
live RTSP. It is the tool for Task 5 camera characterization: per-camera face-detect %,
face-embed rate, body/face quality distributions (p5–p95), FPS, latency, with live threshold
cycling (SCRFD 0.30→0.70, YOLO 0.40→0.70) and tuning hints.

⚠️ **Its defaults are deliberately looser than production** (`min_blur=8` vs 25, SCRFD conf
0.30 vs 0.60, face sample every 3 frames, body every 5). Any threshold conclusion drawn from
it must be re-stated at production settings before being written into a per-camera override.

---

## 5. Frame → person binding (the data path that makes analytics possible)

```
RTSP ─► IngestionWorker ─► SHM slot ─► frames stream (Redis)
  ─► InferenceEngine:
        YOLO26m-pose + BoT-SORT      → tracklets (local_track_id, bbox, 17 kps)
        face-visible gate → SCRFD    → face bboxes + 5 landmarks
        AdaFace (aligned crop)       → 512-d face embedding  → bound to tracklet by
                                        face-centre-inside-person-bbox (greedy)
        TransReID (torso crop)       → 768-d body embedding + quality
        PPE / violence (optional)    → per-tracklet scores / per-frame score
  ─► detections stream (Redis)
  ─► IdentityService: assign_and_identify(camera_id, local_track_id, face_emb, body_emb, ble)
        → (global_track_id, person_id, resolved_via)      # all three MUST be persisted
        FusionResolver order: Face ≻ Body ≻ BLE (invariant)
        cross-camera: body-first two-pass match, CameraTopology.transit_ok() gate,
                      margin gate best−second ≥ reid_margin=0.08
  ─► DBWriter.flush_detection_frame (idempotent, uq_tracking_idem)
  ─► tracking_events row:
        camera_id · local_track_id · global_track_id · person_id · zone_id
        event_ts · ingest_ts · bbox · floor_x/floor_y (homography) · resolved_via
```

Everything needed for "who was where when" lands in one table, indexed on `person_id`,
`global_track_id`, `camera_id`, `event_ts`. Durability and idempotency follow the
CLAUDE.md §17 invariants (DB before FAISS, Redis Streams bus, append-only audit).

---

## 6. Known-person lifecycle

### 6.1 Enrolment
1. `POST /api/persons` (manager role) creates the person.
2. `POST /api/persons/{id}/embeddings` stores a normalised AdaFace embedding + quality;
   near-duplicate rejection at `reid_enroll_dedup_sim`; publishes `faiss_dirty` add event.
3. FAISS updates incrementally; full rebuild from `person_embeddings` on service start
   (DB is source of truth — invariant).

### 6.2 Recognition after enrolment
Every face embedding on every camera is FAISS-searched (k=2 for margin). A hit ≥
`adaface_min_sim` sets `person_id` on the tracklet **and anchors it to every registry entry
sharing the same `global_track_id`** — so one good face match on one camera labels the
person's simultaneous/subsequent body-only sightings. `UnknownPersonDetector` fires HIGH
alerts for tracked-but-unmatched persons.

### 6.3 Known weaknesses
- **Cross-camera body-anchor propagation is minimal**: if Brijesh's face is matched on CAM141
  and he walks to face-hostile CAM110, the link survives only if the cross-camera body match
  succeeds within topology + margin gates. There is no persistent "person body gallery"
  spanning the visit. (Phase 2d spec describes it; implementation is a same-GID lookup only.)
- **EnrolmentWizard frontend**: final embedding push flagged unwired (Phase 4P Task 15).
- **No follow/watchlist feature**: nothing lets an operator say "alert me when person X is seen."
  Frontend has `pinnedCameraIds`/followed-person UI affordances but no backend contract.

---

## 7. Are the models optimised and accurate? — assessment

### 7.1 Optimisation: **yes, effectively done for this hardware tier**
27× serial speedup, 15.4 ms model budget inside the 50 ms/frame end-to-end target, 6.9% VRAM,
Triton path proven for horizontal scale. The remaining levers (motion gate, adaptive interval,
ROI crop, NVDEC, INT8 detectors) are deliberately parked until measurements justify them.
**Recommendation: stop optimising kernels; spend effort on §7.2–§7.4 accuracy gates and the
analytics gaps in §9 — that is where value is currently blocked.**

### 7.2 Accuracy: strong model choices, **but three validation gates are still open**

| Gate | Risk if skipped | Owner action |
|---|---|---|
| **FP16 cosine drift check** (`scripts/trt_fp16_drift_check.py`) — ≥50 face + ≥50 body crops from the multi-cam run; HARD STOP if any crop < 0.99 cosine FP32-vs-FP16 | Silent identity degradation on every camera; blocks GA sign-off | **First step of the next Task 5 hardware session.** |
| **`adaface_min_sim=0.72` re-calibration** — threshold predates IR101/WebFace12M + affine alignment | Wrong accept/reject boundary: either misses (Brijesh unrecognised) or false matches (wrong Brijesh) | Collect labelled sighting pairs (Task 5 gathers distributions); Bayesian/Optuna path in v2 §P.3; mandatory `/advisor`. |
| **Body Re-ID thresholds calibrated on webcam, not plant cameras** (0.65/0.70) | Cross-camera merges too loose or too tight → track fragmentation or identity bleed | Same Task 5 collection; mandatory `/advisor` before change. |

Model pedigree itself is not the concern — SCRFD-10G, AdaFace IR101/WebFace12M, and
TransReID MSMT17 are at or near state of the art for their compute class. The concern is
**operating-point calibration on real plant footage**, which is exactly what Task 5 exists for.

### 7.3 Per-camera reality (provisional, single run — Task 5 must confirm)
- CAM141/CAM144: 57–99% face-embed rate → reference cameras; thresholds locked; canary —
  if their face-embed rate changes after any override, STOP.
- CAM105/CAM200: blurry faces (body quality min 2.1–2.9 Laplacian) → **body-primary** cameras.
- CAM110: 0 faces in test run → detection-limited; investigate mounting/optics before software.

Consequence: plant-wide person tracking **cannot rely on face alone**. The body-Re-ID path and
its calibration are load-bearing, not a nice-to-have.

### 7.4 The one genuinely weak model: violence
R(2+1)D-18 with K400 class-max is a proxy, not a violence classifier. Acceptable for MVP
(gated ≥2 persons, 0.65 threshold, CRITICAL alert with human ack), **not acceptable as a GA
safety claim**. Path: collect plant-floor clips flagged by the current proxy → label →
fine-tune R(2+1)D-18 (or evaluate X3D/VideoMAE-small) on a real violence dataset
(RWF-2000-style) — needs its own spec before any work.

### 7.5 Supply-chain hygiene gap
`models/manifest.json` has `sha256: null` for every model. `vms-models verify` is therefore
a no-op. Compute and commit real checksums — one-session task, closes a production-readiness
audit item.

---

## 8. Homography & floor-plane positioning

### 8.1 What exists
- `cameras.homography_matrix` (3×3 row-major JSON) storage.
- `vms/identity/homography.py::project_to_floor()` — foot-point `((x1+x2)/2, y2)` via
  `cv2.perspectiveTransform`, graceful None on missing/malformed matrix.
- `tracking_events.floor_x / floor_y` populated per event when the camera is calibrated.
- `POST /api/cameras/{id}/recalibrate-required` + §H.3 rule: replaced camera ⇒ floor coords
  NULL until re-calibrated.
- Frontend `HomographyCalibrator.tsx` (point-pair picking UI) exists in the admin camera tabs.

### 8.2 What is missing (this spec defines the contract)

**8.2.1 Calibration write API**
```
PUT /api/cameras/{id}/homography          (admin)
  body: { matrix: number[9],              # row-major 3×3
          point_pairs: [{image:[x,y], floor:[x,y]}, ...],   # ≥4, audited
          floor_plan_id: int | null,
          rms_error_px: float }           # from cv2.findHomography reprojection
  effects: writes cameras.homography_matrix, clears recalibrate_required_at,
           audit event CAMERA_CALIBRATED
GET /api/cameras/{id}/homography          (viewer) → matrix + calibration metadata + staleness flag
```
Server recomputes the matrix from `point_pairs` with `cv2.findHomography(RANSAC)` and rejects
if RMS reprojection error exceeds a configurable `VMS_HOMOGRAPHY_MAX_RMS_PX` (default 15).
The client-supplied matrix is advisory only; the server-computed one is stored.

**8.2.2 Floor-plan asset + read APIs** (consumed by heatmap/live map)
```
GET /api/floor-plans                       → registered plan images + scale (m/px)
GET /api/analytics/heatmap?floor_plan_id=&from=&to=&bucket_m=1.0
                                           → binned counts over floor_x/floor_y
GET /api/live/floor-positions?floor_plan_id=    (or WebSocket event floor_positions)
                                           → current tracklets with floor coords + person_id
```
Heatmap aggregation must be a rollup or bounded window query — `tracking_events` is
partition-scale; no unbounded scans (edge-cases spec applies).

---

## 9. Analytics & frontend wiring

### 9.1 Current state
Frontend surfaces already built (Phase 4K/4L/4M): AnalyticsDashboard, HeatmapPage,
TimeScrubber, ForensicSearchPage, live operator console. Backend endpoints they call:

| Frontend call | Backend status |
|---|---|
| `GET /api/analytics/kpi` | **404** — Phase 4P Task 3 |
| `GET /api/analytics/head-count?days=7` | **404** — Phase 4P Task 4 (+ `analytics_head_count_hourly` rollup table + scheduler job) |
| `GET /api/system/metrics` | **404** — Phase 4P Task 5 |
| `GET /api/forensic/search?q=` | **501** — CLIP text encoder not deployed |
| `GET /api/forensic/clips/{gid}` | ✅ works |
| `GET /api/state/snapshot` | ✅ works |

Phase 4P (`docs/superpowers/plans/2026-07-08-vms-phase4p-data-completeness.md`, NOT STARTED)
covers persons detail, KPI, head-count series, system metrics, clip export, users, bookmarks.

### 9.2 The missing centrepiece: person timeline ("Where was Brijesh at 2 PM?")

**Not in Phase 4P or any existing spec.** The data is fully present and indexed; the endpoint
is a straightforward read route. Proposed contract:

```
GET /api/persons/{person_id}/timeline?from=&to=&camera_id=&zone_id=&limit=500
  (role-gated: user must hold camera permission for each returned camera —
   rows from unpermitted cameras are filtered, not 403'd)
  → [ { from_ts, to_ts,                    # contiguous sightings coalesced into visits
        camera_id, camera_name, zone_id, zone_name,
        global_track_id, resolved_via,     # face/body/ble — expose match confidence class
        floor_x, floor_y,                  # when calibrated
        thumbnail_url | null } ]           # best-quality crop for the visit, if stored

GET /api/persons/{person_id}/last-seen     # convenience; also folded into Phase 4P Task 1
```

Implementation notes:
- **Coalescing:** raw `tracking_events` are per-frame; the endpoint must group consecutive
  events on the same `(camera_id, global_track_id)` with gaps < `VMS_TIMELINE_GAP_S`
  (default 10 s) into visit spans. Do this in SQL (window functions), not Python loops.
- **`resolved_via` must be surfaced** — a body-resolved sighting is weaker evidence than a
  face-resolved one; the UI should badge it. (This is why discarding the third tuple element
  is banned.)
- **Audit:** person-timeline queries are surveillance lookups — write an audit event
  (`PERSON_TIMELINE_QUERIED`, actor, target person, range) per request.
- **GDPR:** purged persons have `person_id` SET NULL in `tracking_events` — timeline of a
  purged person naturally returns empty. No extra handling needed; verify with a test.
- Frontend: person detail page timeline strip + floor-plan trace (needs §8.2 read APIs for
  the map view; camera/time list works without homography).

This endpoint, plus Phase 4P Tasks 1/3/4 and the §8.2 heatmap API, closes the day-one
analytics requirement end-to-end.

---

## 10. Gap register & remediation order

| # | Gap | Effort | Blocked by | Priority rationale |
|---|---|---|---|---|
| 1 | FP16 drift check on real crops | Hours (needs camera hardware) | Task 5 session | Identity-correctness gate; blocks GA on TRT FP16; everything downstream trusts embeddings |
| 2 | Task 5 camera characterization (multi-run, day/night) + per-camera `min_blur`/conf overrides | Days | Hardware access | Determines face-vs-body strategy per camera; feeds gaps 3–4 |
| 3 | `adaface_min_sim` + `reid_body_*` re-calibration on plant footage | Days | Gap 2 data; mandatory `/advisor` | Wrong operating point = wrong answers to "who is this" |
| 4 | Person timeline endpoint (§9.2) | Small (1 route + SQL + tests) | **IN PLAN** — Phase 4P Task 1b | **Highest value-per-effort in the codebase**; directly answers the day-one query |
| 5 | Phase 4P analytics endpoints (KPI, head-count rollup, system metrics, persons detail) | Planned, plan written | User review of Phase 4P plan | Frontend pages are dead without them |
| 6 | Homography calibration write API + heatmap/floor read APIs (§8.2) | Medium | **IN PLAN** — Phase 4P Tasks 8b/8c + 14b | Unlocks floor-plan analytics; heatmap page currently has no data source |
| 7 | Enrolment wizard embedding push wiring | Small | Phase 4P Task 15 | Known persons can't be enrolled from the UI today |
| 8 | Manifest SHA-256 checksums | Trivial | Nothing | Production-readiness audit item |
| 9 | Watchlist / "follow person" alerts | Medium | Needs spec (alert type + routing + UI) | Frequently expected VMS feature; not day-one-critical |
| 10 | Violence model fine-tune (replace K400 proxy) | Large | Needs own spec + labelled data | Only weak model in the stack; MVP-acceptable, GA-questionable |
| 11 | CLIP forensic text search | Large | Recording/analytics spec Phase 3 | Deferred by existing spec; unchanged |
| 12 | NVDEC decode | Large | **ACTIVATED 2026-07-08** — CPU decode confirmed as bottleneck by user; plan `2026-07-08-vms-phase6d-nvdec-gpu-decode.md` written | §6.3 build trigger met; decode moves to the GPU video engine per the prescribed FFmpeg `h264_cuvid` subprocess approach |
| 13 | Cross-camera body-anchor gallery (persistent per-visit body gallery) | Medium-large | Needs spec + `/advisor` (touches identity correctness) | Improves track continuity on face-hostile cameras |

Suggested sequencing: **1 → 2 → 3** (the accuracy gates, all one hardware campaign) in
parallel with **4 → 8 → 7** (small backend wins), then **5 → 6** as the planned analytics
phase, with 9/10/13 spec'd afterwards.

---

## 11. Mandatory `/advisor` gates touching this spec

Per CLAUDE.md §0.5, the following require `/advisor` before any change:
- Any new value for `adaface_min_sim`, `reid_body_confirmed_sim`, `reid_body_cross_cam_sim`,
  `scrfd_conf` (gap 3).
- Any FP16 drift result with a crop < 0.99 cosine (gap 1 HARD STOP).
- Cross-camera body-anchor gallery design (gap 13 — topology/gate logic).
- INT8 on any embedder (prohibited outright without it).
- Timeline endpoint does **not** need `/advisor` (read-only, no identity logic), but its
  migration-free nature should be confirmed at implementation (it is — no schema change).

---

## 12. Open questions — RESOLVED 2026-07-08 (user decision: adopt all recommendations)

1. Person timeline (§9.2) → **Phase 4P Task 1b** (shares the persons route file and tests).
2. Floor-plan assets → **minimal `floor_plans` table now** (Phase 4P Task 8b); full upload/
   versioning management deferred to the recording/analytics spec.
3. Watchlist alerts → **deferred; needs its own short spec** before any implementation
   (gap 9 unchanged).
4. Per-camera identity-mode labels → **keep as overrides only for now**; revisit after
   Phase 6b Task 5 characterization output.

Additionally resolved: the user confirmed CPU stream decoding is the current bottleneck,
activating gap 12 (NVDEC) — see §4.4 update and the Phase 6d plan.

---

**End of spec.**
