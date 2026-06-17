"""Multi-camera live pipeline test — visual validation on CPU or GPU.

Reads 2-4 Hikvision RTSP cameras from .env, runs the full inference stack
(face detection + embedding, body tracking + ReID), and renders a tiled HUD
with per-camera stats and a global head count.

No DB writes. No Redis. No identity enrolment. Observation only.

Usage:
    venv/Scripts/python.exe scripts/multi_cam_pipeline_test.py
    venv/Scripts/python.exe scripts/multi_cam_pipeline_test.py --cameras 105 110
    venv/Scripts/python.exe scripts/multi_cam_pipeline_test.py --dry-run

Camera env vars (set in .env):
    VMS_CAM_GATE_BACK_URL    camera_id=105
    VMS_CAM_GATE_FRONT_URL   camera_id=110
    VMS_CAM_GATE_4_URL       camera_id=141
    VMS_CAM_ANPR_URL         camera_id=200

Model toggle env vars (set empty to disable):
    VMS_TRANSREID_BODY_MODEL   body Re-ID (ONNX, preferred on CPU)
    VMS_OSNET_AIN_MODEL        body Re-ID (torchreid, heavier)
    VMS_YOLOV8X_POSE_MODEL     pose keypoints (disable for CPU)
    VMS_VIOLENCE_MODEL         violence detection (disable for CPU)
    VMS_PPE_MODEL              PPE compliance (off by default)

Keyboard controls:
    F        toggle face pipeline (SCRFD + AdaFace)
    B        toggle body Re-ID (TransReID / OSNet)
    +/-      increase/decrease face sample rate (every N frames)
    C        cycle SCRFD face confidence: 0.40 -> 0.55 -> 0.70
    Y        cycle YOLO person confidence: 0.40 -> 0.50 -> 0.60 -> 0.70
    T        cycle YOLO frame-skip: every 1 -> 2 -> 3 -> 5 frames
    1-5      go fullscreen on camera 1-5
    0 / G    return to grid view
    S        save snapshot of current frame
    Q        quit

CPU tips — add to .env or export before running:
    VMS_YOLOV8X_POSE_MODEL=        # disables pose (~150ms/frame)
    VMS_VIOLENCE_MODEL=            # disables MoViNet TF (~300ms/frame)
    VMS_OSNET_AIN_MODEL=           # prefer TransReID ONNX over OSNet
"""

from __future__ import annotations

import argparse
import logging
import os
import queue
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

os.environ.setdefault("VMS_DB_URL", "postgresql://localhost/vms_unused")
os.environ.setdefault("VMS_JWT_SECRET", "smoke-test-dummy-secret")
os.environ.setdefault("VMS_SCRFD_CONF", "0.50")
os.environ.setdefault("VMS_MIN_FACE_PX", "28")
# Lower blur gate for live validation — gate cameras capture moving workers.
# Production default (25.0) rejects slightly-blurred faces from motion; 8.0 keeps them.
os.environ.setdefault("VMS_MIN_BLUR", "8.0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
# Force RTSP over TCP — prevents HEVC bitstream corruption from UDP packet loss
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

# Face pipeline runs every N body frames — keep CPU load manageable.
_FACE_SAMPLE_DEFAULT = 3
_BODY_REID_SAMPLE_DEFAULT = 5   # body ReID every N frames (TransReID ~60ms on CPU)
_YOLO_SAMPLE_DEFAULT = 3        # YOLO inference every N frames; last boxes reused in between
_RECONNECT_AFTER = 8            # consecutive read fails before reconnect attempt
_PANEL_H = 540
_STATS_H = 60
_SNAPSHOTS_DIR = Path(__file__).resolve().parent / "snapshots"
_CONF_CYCLE: tuple[float, ...] = (0.40, 0.55, 0.70)
_YOLO_CONF_CYCLE: tuple[float, ...] = (0.40, 0.50, 0.60, 0.70)
_YOLO_SAMPLE_CYCLE: tuple[int, ...] = (1, 2, 3, 5)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mcam")

import cv2
import numpy as np

from vms.config import get_settings
from vms.inference.body_embedder import create_body_embedder
from vms.inference.detector import SCRFDDetector
from vms.inference.embedder import AdaFaceEmbedder
from vms.inference.messages import FaceWithEmbedding, Tracklet
from vms.inference.tracker import PerCameraTracker

# ---------------------------------------------------------------------------
# Shared mutable state (toggled by keypress in main thread)
# ---------------------------------------------------------------------------


@dataclass
class PipelineState:
    face_enabled: bool = True
    body_reid_enabled: bool = True
    face_sample_n: int = _FACE_SAMPLE_DEFAULT
    reid_sample_n: int = _BODY_REID_SAMPLE_DEFAULT
    yolo_sample_n: int = _YOLO_SAMPLE_DEFAULT  # run YOLO every N frames; reuse boxes between
    conf: float = 0.55            # SCRFD face detection confidence
    yolo_conf: float = 0.55       # YOLO person class confidence (overrides yolo_person_conf)
    fullscreen_cam: int | None = None  # None = grid; 0-based index = fullscreen that camera


# ---------------------------------------------------------------------------
# Per-frame result DTO
# ---------------------------------------------------------------------------


@dataclass
class FrameResult:
    camera_id: int
    camera_label: str
    frame: np.ndarray  # type: ignore[type-arg]
    tracklets: list[Tracklet]
    faces: list[FaceWithEmbedding]
    body_reid_active: bool
    fps: float
    latency_ms: float
    frame_n: int
    face_fps: float = 0.0  # rolling face-embedding rate (embedded frames with ≥1 face)


# ---------------------------------------------------------------------------
# Camera worker thread
# ---------------------------------------------------------------------------

_TRACK_COLORS: dict[int, tuple[int, int, int]] = {}


def _track_color(tid: int) -> tuple[int, int, int]:
    if tid not in _TRACK_COLORS:
        import random
        rng = random.Random(tid * 2654435761)
        _TRACK_COLORS[tid] = (rng.randint(60, 255), rng.randint(60, 255), rng.randint(60, 255))
    return _TRACK_COLORS[tid]


class CameraWorker:
    def __init__(
        self,
        camera_id: int,
        label: str,
        rtsp_url: str,
        detector: Any,
        embedder: Any,
        tracker: PerCameraTracker,
        body_embedder: Any,
        state: PipelineState,
    ) -> None:
        self._id = camera_id
        self._label = label
        self._url = rtsp_url
        self._detector = detector
        self._embedder = embedder
        self._tracker = tracker
        self._body_embedder = body_embedder
        self._state = state
        self._q: queue.Queue[FrameResult] = queue.Queue(maxsize=2)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._reader_thread: threading.Thread | None = None
        self._last_tracklets: list[Tracklet] = []  # reused on YOLO-skipped frames
        # Dedicated reader thread writes here; inference thread reads the latest frame.
        # Reader drains the RTSP buffer continuously so inference never blocks on cap.read().
        self._frame_lock = threading.Lock()
        self._latest_raw_frame: np.ndarray | None = None  # type: ignore[type-arg]

    def start(self) -> None:
        self._reader_thread = threading.Thread(
            target=self._read_frames, name=f"reader-{self._id}", daemon=True
        )
        self._reader_thread.start()
        self._thread = threading.Thread(target=self._run, name=f"cam-{self._id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=4.0)
        if self._reader_thread:
            self._reader_thread.join(timeout=4.0)

    def latest(self) -> FrameResult | None:
        result: FrameResult | None = None
        while True:
            try:
                result = self._q.get_nowait()
            except queue.Empty:
                break
        return result

    def _open(self) -> cv2.VideoCapture | None:
        for url in [self._url, self._url.replace("/101", "/102")]:
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                logger.info("%s: connected %dx%d @ %.1f fps", self._label, w, h, fps)
                return cap
            cap.release()
        logger.error("%s: cannot connect — check network/credentials", self._label)
        return None

    def _read_frames(self) -> None:
        """Dedicated reader thread: drain RTSP buffer at full camera speed.

        Continuously calls cap.read() and stores only the latest frame.
        The inference thread reads from _latest_raw_frame without blocking on I/O.
        This prevents H.265 keyframe-interval stalls (2+ seconds) from blocking inference.
        """
        cap = self._open()
        if cap is None:
            return
        consecutive_fails = 0
        while not self._stop.is_set():
            ret, frame = cap.read()
            if not ret:
                consecutive_fails += 1
                if consecutive_fails == 1:
                    logger.warning("%s: frame read failed", self._label)
                if consecutive_fails >= _RECONNECT_AFTER:
                    logger.warning(
                        "%s: %d consecutive failures — reconnecting", self._label, consecutive_fails
                    )
                    cap.release()
                    time.sleep(2.0)
                    new_cap = self._open()
                    if new_cap is not None:
                        cap = new_cap
                        consecutive_fails = 0
                    else:
                        logger.error("%s: reconnect failed — retry in 10s", self._label)
                        time.sleep(10.0)
                        consecutive_fails = _RECONNECT_AFTER
                else:
                    time.sleep(0.05)
                continue
            consecutive_fails = 0
            with self._frame_lock:
                self._latest_raw_frame = frame
        cap.release()
        logger.info("%s: reader stopped", self._label)

    def _run(self) -> None:
        fps_deque: deque[float] = deque(maxlen=30)
        face_fps_deque: deque[float] = deque(maxlen=10)
        frame_n = 0
        t_prev = time.monotonic()
        t_last_face_emb = time.monotonic()

        while not self._stop.is_set():
            with self._frame_lock:
                frame = self._latest_raw_frame

            if frame is None:
                time.sleep(0.02)  # wait for reader thread to get first frame
                continue

            t0 = time.monotonic()
            frame_n += 1

            try:
                # Body tracking — every yolo_sample_n frames; reuse last boxes in between.
                # BoT-SORT with persist=True handles gaps gracefully.
                if frame_n % self._state.yolo_sample_n == 0:
                    self._last_tracklets = self._tracker.update(
                        frame, conf=self._state.yolo_conf
                    )
                tracklets = self._last_tracklets

                # Face pipeline — every N frames when enabled
                faces: list[FaceWithEmbedding] = []
                if self._state.face_enabled and frame_n % self._state.face_sample_n == 0:
                    raw_faces = self._detector.detect(frame)
                    for f in raw_faces:
                        if f.confidence < self._state.conf:
                            continue
                        emb = self._embedder.embed(f, frame)
                        faces.append(emb if emb is not None else f)

                # Body Re-ID — every N frames when enabled
                reid_active = False
                if (
                    self._state.body_reid_enabled
                    and self._body_embedder is not None
                    and frame_n % self._state.reid_sample_n == 0
                ):
                    reid_active = True
                    h_f, w_f = frame.shape[:2]
                    enriched: list[Tracklet] = []
                    for t in tracklets:
                        x1, y1, x2, y2 = t.bbox
                        x1c, y1c = max(0, x1), max(0, y1)
                        x2c, y2c = min(w_f, x2), min(h_f, y2)
                        crop = frame[y1c:y2c, x1c:x2c]
                        if crop.size > 0 and crop.shape[0] >= 16 and crop.shape[1] >= 8:
                            emb_tuple, quality = self._body_embedder.embed(crop)
                            enriched.append(
                                Tracklet(
                                    local_track_id=t.local_track_id,
                                    camera_id=t.camera_id,
                                    bbox=t.bbox,
                                    confidence=t.confidence,
                                    embedding=t.embedding,
                                    body_embedding=emb_tuple,
                                    body_quality_norm=quality,
                                )
                            )
                        else:
                            enriched.append(t)
                    tracklets = tuple(enriched)

            except Exception:
                logger.exception("%s: inference error frame %d", self._label, frame_n)
                continue

            t1 = time.monotonic()
            fps_deque.append(1.0 / max(t1 - t_prev, 1e-6))
            t_prev = t1
            latency_ms = (t1 - t0) * 1000

            # Track face embedding rate (faces with a real embedding, not just SCRFD detections)
            embedded_faces = [f for f in faces if f.embedding]
            if embedded_faces:
                now = time.monotonic()
                face_fps_deque.append(1.0 / max(now - t_last_face_emb, 1e-6))
                t_last_face_emb = now
            face_fps = sum(face_fps_deque) / len(face_fps_deque) if face_fps_deque else 0.0

            result = FrameResult(
                camera_id=self._id,
                camera_label=self._label,
                frame=frame,
                tracklets=list(tracklets),
                faces=faces,
                body_reid_active=reid_active,
                fps=sum(fps_deque) / len(fps_deque),
                latency_ms=latency_ms,
                frame_n=frame_n,
                face_fps=face_fps,
            )
            try:
                self._q.put_nowait(result)
            except queue.Full:
                try:
                    self._q.get_nowait()
                    self._q.put_nowait(result)
                except queue.Empty:
                    pass

        logger.info("%s: inference stopped", self._label)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_panel(result: FrameResult, target_h: int, show_reid_dim: bool) -> np.ndarray:  # type: ignore[type-arg]
    frame = result.frame.copy()
    h_orig, w_orig = frame.shape[:2]
    scale = target_h / h_orig
    w_scaled = int(w_orig * scale)
    panel = cv2.resize(frame, (w_scaled, target_h), interpolation=cv2.INTER_AREA)

    # Person bounding boxes + track IDs
    for t in result.tracklets:
        x1, y1, x2, y2 = [int(v * scale) for v in t.bbox]
        color = _track_color(t.local_track_id)
        cv2.rectangle(panel, (x1, y1), (x2, y2), color, 2)

        label = f"T{t.local_track_id} {t.confidence:.2f}"
        if t.body_embedding and show_reid_dim:
            q = t.body_quality_norm
            label += f" q={q:.2f}"

        cv2.putText(panel, label, (x1, max(y1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    # Face boxes
    for f in result.faces:
        x1, y1, x2, y2 = [int(v * scale) for v in f.bbox]
        cv2.rectangle(panel, (x1, y1), (x2, y2), (0, 200, 255), 1)
        norm_str = f"n={f.face_quality_norm:.2f}" if f.face_quality_norm != 1.0 else ""
        cv2.putText(panel, f"F{norm_str}", (x1, max(y1 - 4, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)

    # Stats bar
    person_count = len(result.tracklets)
    reid_tag = " ReID" if result.body_reid_active else ""
    face_rate = f" Face~{result.face_fps:.1f}/s" if result.face_fps > 0 else ""
    hud = (
        f"{result.camera_label}  "
        f"P:{person_count}  "
        f"F:{int(result.fps)}fps  "
        f"{result.latency_ms:.0f}ms{reid_tag}{face_rate}"
    )
    bar = np.zeros((32, w_scaled, 3), dtype=np.uint8)
    cv2.putText(bar, hud, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1)
    return np.vstack([bar, panel])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _camera_spec(camera_id: int) -> tuple[str, str] | None:
    """Return (label, rtsp_url) for a given camera_id, or None if not configured."""
    mapping = {
        105: ("Back Gate",  os.environ.get("VMS_CAM_GATE_BACK_URL", "")),
        110: ("Front Gate", os.environ.get("VMS_CAM_GATE_FRONT_URL", "")),
        141: ("Gate 4",     os.environ.get("VMS_CAM_GATE_4_URL", "")),
        200: ("ANPR",       os.environ.get("VMS_CAM_ANPR_URL", "")),
    }
    entry = mapping.get(camera_id)
    if entry and entry[1]:
        return entry
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-camera pipeline visual test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--cameras", nargs="+", type=int, default=[105, 110],
        help="Camera IDs to activate (default: 105 110). Available: 105 110 141 200",
    )
    parser.add_argument("--panel-h", type=int, default=_PANEL_H, help="Panel height per camera")
    parser.add_argument(
        "--yolo-every", type=int, default=_YOLO_SAMPLE_DEFAULT, metavar="N",
        help=f"Run YOLO every N frames (default {_YOLO_SAMPLE_DEFAULT}); reuses last boxes between runs",
    )
    parser.add_argument(
        "--device", default=None, choices=["cpu", "cuda"],
        help="Inference device (default: cuda if available, else cpu)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Process 10 frames and exit")
    args = parser.parse_args()

    settings = get_settings()

    # Resolve inference device
    if args.device:
        _device = args.device
    else:
        try:
            import torch as _torch
            _device = "cuda" if _torch.cuda.is_available() else "cpu"
        except ImportError:
            _device = "cpu"
    logger.info("Inference device: %s", _device)

    # Build camera list
    cameras: list[tuple[int, str, str]] = []  # (id, label, url)
    for cid in args.cameras:
        spec = _camera_spec(cid)
        if spec is None:
            logger.warning("Camera %d: no URL configured in .env — skipping", cid)
            continue
        cameras.append((cid, spec[0], spec[1]))

    if not cameras:
        logger.error("No cameras configured. Set VMS_CAM_* vars in .env and retry.")
        sys.exit(1)

    logger.info("Cameras: %s", ", ".join(f"{label}(cam{cid})" for cid, label, _ in cameras))

    # Load models
    logger.info("Loading models...")
    detector = SCRFDDetector.from_path(settings.scrfd_model)
    embedder = AdaFaceEmbedder.from_path(settings.adaface_model)
    body_embedder = create_body_embedder(
        transreid_path=settings.transreid_body_model,
        osnet_path=settings.osnet_ain_model,
        device=_device,
    )

    if body_embedder is not None:
        kind = type(body_embedder).__name__
        logger.info("Body Re-ID: %s", kind)
    else:
        logger.info("Body Re-ID: DISABLED (no model path configured)")

    state = PipelineState(
        conf=settings.scrfd_conf,
        yolo_conf=settings.yolo_person_conf,
        yolo_sample_n=args.yolo_every,
    )

    # Tracker model: use configured pose model or fall back to yolov8n (CPU-safe, ~15ms/frame).
    # To force the light model: set VMS_YOLOV8X_POSE_MODEL= (empty) in .env.
    _tracker_model = settings.yolov8x_pose_model or "yolov8n.pt"
    if not settings.yolov8x_pose_model:
        logger.info("Pose model disabled — using yolov8n.pt (CPU-safe fallback)")

    # Start workers
    workers: list[CameraWorker] = []
    for cid, label, url in cameras:
        tracker = PerCameraTracker.from_path(cid, _tracker_model)
        w = CameraWorker(cid, label, url, detector, embedder, tracker, body_embedder, state)
        w.start()
        workers.append(w)

    logger.info(
        "Controls: F=face  B=body_reid  +/-=face_rate  C=confidence  S=snapshot  Q=quit"
    )

    show_reid_dim = body_embedder is not None
    frame_counter = 0

    try:
        while True:
            panels: list[np.ndarray] = []  # type: ignore[type-arg]
            current_results: list[FrameResult | None] = []
            for w in workers:
                r = w.latest()
                current_results.append(r)
                if r is not None:
                    panels.append(_render_panel(r, args.panel_h, show_reid_dim))

            if panels:
                # Equalise heights before hstack
                target_h = max(p.shape[0] for p in panels)
                padded = []
                for p in panels:
                    if p.shape[0] < target_h:
                        pad = np.zeros((target_h - p.shape[0], p.shape[1], 3), dtype=np.uint8)
                        p = np.vstack([p, pad])
                    padded.append(p)

                grid = np.hstack(padded)

                # Global head count — use cached results, never call w.latest() twice
                total_persons = sum(len(r.tracklets) for r in current_results if r is not None)
                face_tag = f"Face:{'ON' if state.face_enabled else 'OFF'} N={state.face_sample_n}"
                reid_tag = f"ReID:{'ON' if state.body_reid_enabled else 'OFF'}"
                fconf_tag = f"FConf:{state.conf:.2f}"
                yolo_tag = f"YConf:{state.yolo_conf:.2f} Ev:{state.yolo_sample_n}"
                footer_text = (
                    f"  HEAD COUNT: {total_persons}   {face_tag}   {reid_tag}"
                    f"   {fconf_tag}   {yolo_tag}"
                )
                footer = np.zeros((36, grid.shape[1], 3), dtype=np.uint8)
                cv2.putText(footer, footer_text, (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 200), 2)

                display = np.vstack([grid, footer])
                cv2.imshow("VMS Pipeline Test", display)

            key = cv2.waitKey(1) & 0xFF
            if args.dry_run:
                frame_counter += 1
                if frame_counter >= 10:
                    logger.info("Dry run complete.")
                    break

            if key == ord("q"):
                break
            elif key == ord("f"):
                state.face_enabled = not state.face_enabled
                logger.info("Face pipeline: %s", "ON" if state.face_enabled else "OFF")
            elif key == ord("b"):
                state.body_reid_enabled = not state.body_reid_enabled
                logger.info("Body ReID: %s", "ON" if state.body_reid_enabled else "OFF")
            elif key == ord("+") or key == ord("="):
                state.face_sample_n = max(1, state.face_sample_n - 1)
                logger.info("Face sample every %d frames", state.face_sample_n)
            elif key == ord("-"):
                state.face_sample_n = min(20, state.face_sample_n + 1)
                logger.info("Face sample every %d frames", state.face_sample_n)
            elif key == ord("c"):
                idx = (_CONF_CYCLE.index(state.conf) + 1) % len(_CONF_CYCLE) if state.conf in _CONF_CYCLE else 0
                state.conf = _CONF_CYCLE[idx]
                logger.info("Face (SCRFD) confidence: %.2f", state.conf)
            elif key == ord("y"):
                idx = (_YOLO_CONF_CYCLE.index(state.yolo_conf) + 1) % len(_YOLO_CONF_CYCLE) if state.yolo_conf in _YOLO_CONF_CYCLE else 1
                state.yolo_conf = _YOLO_CONF_CYCLE[idx]
                logger.info("YOLO person confidence: %.2f", state.yolo_conf)
            elif key == ord("t"):
                idx = (_YOLO_SAMPLE_CYCLE.index(state.yolo_sample_n) + 1) % len(_YOLO_SAMPLE_CYCLE) if state.yolo_sample_n in _YOLO_SAMPLE_CYCLE else 0
                state.yolo_sample_n = _YOLO_SAMPLE_CYCLE[idx]
                logger.info("YOLO runs every %d frames", state.yolo_sample_n)
            elif key == ord("s"):
                _SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                if panels:
                    path = _SNAPSHOTS_DIR / f"snapshot_{ts}.jpg"
                    cv2.imwrite(str(path), display)
                    logger.info("Snapshot saved: %s", path)

    finally:
        for w in workers:
            w.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
