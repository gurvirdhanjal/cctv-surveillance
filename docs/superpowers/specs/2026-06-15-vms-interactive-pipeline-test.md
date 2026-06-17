# VMS Interactive Pipeline Test
**Design Specification** · 2026-06-15
**Status:** Approved

---

## 1. Purpose

A standalone interactive test harness for verifying the face detection and embedding
pipeline against live RTSP cameras on a CPU-only laptop. The primary goal is smooth
real-time display (≥ 20 FPS) while confirming that SCRFD face detection and AdaFace
embedding extraction fire correctly and label unenrolled persons as UNKNOWN.

This script is a **test instrument only**. It intentionally uses a lighter body
detector (`yolov8n.pt`) to free CPU headroom for the production face pipeline.
The production body detector (`yolov8x-pose.pt`) is declared as a constant but
not loaded, so the distinction is explicit to any future reader.

---

## 2. Scope

- **In scope:** body tracking, face detection, face embedding extraction, UNKNOWN
  labelling, live display with per-component timing, interactive keyboard controls.
- **Out of scope:** DB writes, Redis writes, identity enrolment, cross-camera
  topology, alert dispatch, PPE compliance, audit log.

---

## 3. Constants (top of file, never buried)

```python
TEST_BODY_MODEL     = "yolov8n.pt"                  # auto-downloaded by ultralytics
PROD_BODY_MODEL     = "models/yolov8x-pose.pt"       # production — not used here
FACE_DETECTOR       = "models/scrfd_10g_bnkps.onnx"
FACE_EMBEDDER       = "models/adaface_ir50.onnx"
FACE_SAMPLE_EVERY_N = 5                              # default; tunable at runtime
ADAFACE_MIN_SIM     = 0.72                           # below this → UNKNOWN
```

---

## 4. Components

### 4.1 BodyDetector
Wraps `ultralytics.YOLO(TEST_BODY_MODEL).track(frame, persist=True,
tracker=botsort_custom.yaml, verbose=False)`. Returns `list[Tracklet]`
(same frozen dataclass as production). Runs on every frame.

### 4.2 FacePipeline
Wraps `SCRFDDetector` (from `vms.inference.detector`) + `AdaFaceEmbedder`
(from `vms.inference.embedder`). Runs only on frame indices where
`frame_n % N == 0`. Returns `list[FaceResult]`:

```python
@dataclass(frozen=True)
class FaceResult:
    bbox: tuple[int, int, int, int]
    confidence: float
    embedding_norm: float   # L2 norm of 512-d AdaFace vector
    label: str              # always "UNKNOWN" in this harness (no DB)
```

Between sample frames, the previous `list[FaceResult]` is carried forward
unchanged on the `FrameResult` dataclass. This means face boxes stay on screen
between samples — they do not disappear.

### 4.3 CameraWorker
One thread per camera. Owns a `BodyDetector` + `FacePipeline` instance.
Publishes to a bounded `Queue(maxsize=2)` — drops current result if queue
is full (never blocks inference). Main thread drains with `get_nowait()`.

```python
@dataclass
class FrameResult:
    camera_label: str
    frame: np.ndarray           # BGR, original resolution
    tracklets: list[Tracklet]
    face_results: list[FaceResult]
    face_stale_frames: int      # frames since last SCRFD+AdaFace run
    fps: float
    latency_body_ms: float
    latency_scrfd_ms: float     # 0.0 on skip frames
    latency_adaface_ms: float   # 0.0 on skip frames
    frame_n: int
```

### 4.4 Renderer (main thread only)
Scales frame to `panel_h`, draws:
- **Green boxes** — body tracklets, colour per track ID, label `T:{id}`
- **Blue boxes** — face detections, label `UNKNOWN (n={norm:.2f})`
- **Red banner** — `MODE: DEMO FAST BODY DETECTOR, PRODUCTION FACE PIPELINE`
  pinned to top of the composite window, always visible
- **Stats bar** — per-camera: `fps / body_ms / scrfd_ms / adaface_ms / sample:N`
- **Timing panel** (toggle) — second stats row with raw component latencies
  and `embed_norm` of most recent face

---

## 5. Display Layout

```
┌──────────────────────────────────────────────────────────────┐
│  ⚠  MODE: DEMO FAST BODY DETECTOR, PRODUCTION FACE PIPELINE  │  red, full width
├────────────────────────┬─────────────────────────────────────┤
│  CAM105 panel          │  CAM110 panel                       │
│  green body boxes      │  green body boxes                   │
│  blue face box         │  blue face box                      │
│  UNKNOWN (n=0.41)      │  UNKNOWN (n=0.38)                   │
├────────────────────────┴─────────────────────────────────────┤
│ CAM105: 24fps  body:28ms  face:145ms  sample:5  stale:3       │
│ CAM110: 22fps  body:26ms  face:139ms  sample:5  stale:1       │  stats bar
├──────────────────────────────────────────────────────────────┤
│ [T] yolo:28ms  scrfd:112ms  adaface:43ms  norm:18.4  (CAM105)│  timing panel (toggle)
└──────────────────────────────────────────────────────────────┘
```

`stale:N` shows how many frames have elapsed since the last face sample — gives
the operator a live sense of how stale the face overlay is.

---

## 6. Live Controls

| Key | Action |
|-----|--------|
| `+` | Increase face sample interval N by 1 (max 20) |
| `-` | Decrease face sample interval N by 1 (min 1) |
| `C` | Cycle body confidence threshold: 0.40 → 0.55 → 0.70 → 0.40 |
| `F` | Toggle face pipeline on/off (body tracking continues unaffected) |
| `T` | Toggle per-component timing row |
| `S` | Save snapshot pair to `scripts/snapshots/` |
| `R` | Reset track-ID colour map |
| `Q` | Quit cleanly (stops both workers, destroys window) |

---

## 7. Camera Configuration

Reads same env vars as `gate_smoke_test.py`:

```
VMS_CAM_GATE_FRONT_URL   rtsp://admin:sss12345@172.16.2.105:554/Streaming/Channels/101
VMS_CAM_GATE_BACK_URL    rtsp://admin:sss12345@172.16.2.110:554/Streaming/Channels/101
```

Both workers attempt the main stream first, fall back to `/102` (Hikvision
substream) automatically if the main stream fails. Substream fallback is
logged at WARNING level.

`--panel-height PX` CLI arg (default 540) controls display scale. Reducing
to 360 further cuts render cost on low-res displays.

`--dry-run` processes 10 frames per camera, logs timing per component, exits
without opening a window — useful for CI / headless benchmarking.

---

## 8. Performance Contract

| Metric | Target |
|--------|--------|
| Display FPS | ≥ 20 FPS on a dual-core CPU laptop |
| Body inference (yolov8n) | ≤ 35 ms/frame |
| Face pipeline (SCRFD + AdaFace) | ≤ 180 ms per sample, amortised ≤ 36 ms at N=5 |
| End-to-end display latency | ≤ 150 ms from capture to screen |

If display FPS drops below 15, the stats bar renders the FPS value in red
as a visual alert to the operator.

---

## 9. File Location

```
scripts/interactive_pipeline_test.py   ← new file
scripts/snapshots/                     ← auto-created on first S keypress
```

No changes to any file under `vms/`. This script imports from `vms/` but
never mutates production code.

---

## 10. Testing

A `--dry-run` flag is the automated test path:

```powershell
python scripts/interactive_pipeline_test.py --dry-run
```

Exits 0 if:
- Both RTSP streams open successfully
- Body detector fires on ≥ 1 frame per camera
- Face pipeline fires on ≥ 1 frame per camera
- No exceptions thrown

Exits 1 with a descriptive error if any of the above fail.
