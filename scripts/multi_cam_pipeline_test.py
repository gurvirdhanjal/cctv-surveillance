"""Multi-camera live pipeline test — visual validation on CPU or GPU.

Reads 2-5 Hikvision RTSP cameras from .env, runs the full inference stack
(face detection + embedding, body tracking + ReID), and renders an adaptive
grid HUD with per-camera stats and a global head count.

No DB writes. No Redis. No identity enrolment. Observation only.

Usage:
    venv/Scripts/python.exe scripts/multi_cam_pipeline_test.py
    venv/Scripts/python.exe scripts/multi_cam_pipeline_test.py --cameras 105 110
    venv/Scripts/python.exe scripts/multi_cam_pipeline_test.py --dry-run

Camera env vars (set in .env):
    VMS_CAM_GATE_BACK_URL    camera_id=105
    VMS_CAM_GATE_FRONT_URL   camera_id=110
    VMS_CAM_GATE_4_URL       camera_id=141
    VMS_CAM_INDOOR_2_URL     camera_id=144
    VMS_CAM_ANPR_URL         camera_id=200

Model toggle env vars (set empty to disable):
    VMS_TRANSREID_BODY_MODEL   body Re-ID (TransReID ONNX, 768-dim)
    VMS_YOLOV8X_POSE_MODEL     pose keypoints (disable for CPU)
    VMS_VIOLENCE_MODEL         violence detection (disable for CPU)
    VMS_PPE_MODEL              PPE compliance (off by default)

Keyboard controls:
    F        toggle face pipeline (SCRFD + AdaFace)
    B        toggle body Re-ID (TransReID / OSNet)
    V        toggle violence detection (R(2+1)D-18)
    P        toggle PPE compliance (YOLOv8l SH17)
    +/-      increase/decrease face sample rate (every N frames)
    C        cycle SCRFD face confidence: 0.40 -> 0.55 -> 0.70
    Y        cycle YOLO person confidence: 0.40 -> 0.50 -> 0.60 -> 0.70
    T        cycle YOLO frame-skip: every 1 -> 2 -> 3 -> 5 frames
    S        save snapshot of current frame
    1-9      fullscreen camera N (letterboxed; press same key or G to return to grid)
    G        return to grid view
    Q        quit

CPU tips — add to .env or export before running:
    VMS_YOLOV8X_POSE_MODEL=        # disables pose (~150ms/frame)
    VMS_VIOLENCE_MODEL=            # disables R(2+1)D-18 (~300ms/frame)
"""

from __future__ import annotations

import argparse
import logging
import math
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

# Prepend PyTorch's bundled CUDA DLLs so onnxruntime-gpu can find cublasLt64_12.dll
# without requiring a system CUDA installation.
_torch_lib = _PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "torch" / "lib"
if _torch_lib.is_dir():
    import os as _os

    _os.environ["PATH"] = str(_torch_lib) + _os.pathsep + _os.environ.get("PATH", "")

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

os.environ.setdefault("VMS_DB_URL", "postgresql://localhost/vms_unused")
os.environ.setdefault("VMS_JWT_SECRET", "smoke-test-dummy-secret")
os.environ.setdefault(
    "VMS_SCRFD_CONF", "0.30"
)  # test default: lower than prod (0.50) per /advisor 2026-06-17
os.environ.setdefault("VMS_MIN_FACE_PX", "20")  # 20px catches workers at distance
# Lower blur gate for live validation — gate cameras capture moving workers.
# Production default (25.0) rejects slightly-blurred faces from motion; 8.0 keeps them.
os.environ.setdefault("VMS_MIN_BLUR", "8.0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
# Force RTSP over TCP — prevents HEVC bitstream corruption from UDP packet loss
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

# Face pipeline runs every N body frames — keep CPU load manageable.
_FACE_SAMPLE_DEFAULT = 3
_BODY_REID_SAMPLE_DEFAULT = 5  # body ReID every N frames (TransReID ~60ms on CPU)
_YOLO_SAMPLE_DEFAULT = 3  # YOLO inference every N frames; last boxes reused in between
_RECONNECT_AFTER = 8  # consecutive read fails before reconnect attempt
_MAX_DELIVER_FPS = 30  # reader caps delivery to this rate regardless of GOP bursts
_PANEL_H = 540
_STATS_H = 60
_SNAPSHOTS_DIR = Path(__file__).resolve().parent / "snapshots"
_CONF_CYCLE: tuple[float, ...] = (0.30, 0.40, 0.55, 0.70)
_YOLO_CONF_CYCLE: tuple[float, ...] = (0.40, 0.50, 0.60, 0.70)
_YOLO_SAMPLE_CYCLE: tuple[int, ...] = (1, 2, 3, 5)
# Grid display target window size (pixels). Override with --width / --height.
_GRID_W = 1280
_GRID_H = 620
_FOOTER_H = 28

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mcam")

import cv2
import numpy as np

from vms.config import get_settings
from vms.inference.body_embedder import create_body_embedder, extract_torso_crop
from vms.inference.detector import SCRFDDetector
from vms.inference.embedder import AdaFaceEmbedder
from vms.inference.messages import FaceWithEmbedding, Tracklet
from vms.inference.ppe import PPEModel
from vms.inference.tracker import PerCameraTracker
from vms.inference.violence import ViolenceModel

# ---------------------------------------------------------------------------
# Shared mutable state (toggled by keypress in main thread)
# ---------------------------------------------------------------------------


@dataclass
class PipelineState:
    face_enabled: bool = True
    body_reid_enabled: bool = True
    violence_enabled: bool = True
    ppe_enabled: bool = True
    face_sample_n: int = _FACE_SAMPLE_DEFAULT
    reid_sample_n: int = _BODY_REID_SAMPLE_DEFAULT
    yolo_sample_n: int = _YOLO_SAMPLE_DEFAULT  # run YOLO every N frames; reuse boxes between
    conf: float = 0.55  # SCRFD face detection confidence
    yolo_conf: float = 0.55  # YOLO person class confidence (overrides yolo_person_conf)
    focus_idx: int | None = None  # None = grid view; 0-based index = fullscreen that camera


# ---------------------------------------------------------------------------
# Per-camera calibration statistics accumulator
# ---------------------------------------------------------------------------


class CameraStats:
    """Rolling calibration counters for accuracy hardening and threshold tuning.

    Designed for concurrent read/write: all mutations must hold self.lock.
    Reads in _print_calibration_stats snapshot-copy under the lock then release.
    """

    def __init__(self, camera_id: int, label: str) -> None:
        self.camera_id = camera_id
        self.label = label
        self.lock = threading.Lock()
        # cumulative totals (since start; never reset)
        self.total_frames: int = 0
        self.total_faces_detected: int = 0   # SCRFD detections that passed conf filter
        self.total_faces_embedded: int = 0   # embed() returned non-None result
        self.total_faces_rejected: int = 0   # embed() returned None (blur / size gate)
        self.total_body_attempts: int = 0    # tracklets that met the size gate
        self.total_kp_available: int = 0     # of those, tracklets with 17 COCO keypoints
        # rolling windows (last 200 samples) for live quality distribution
        self.body_quality_norms: deque[float] = deque(maxlen=200)
        self.face_quality_norms: deque[float] = deque(maxlen=200)
        self.person_counts: deque[int] = deque(maxlen=60)


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
    face_fps: float = 0.0
    violence_score: float | None = None
    ppe_results: list[dict[str, float] | None] = field(default_factory=list)


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
        violence_model: Any = None,
        ppe_model: Any = None,
        stats: "CameraStats | None" = None,
    ) -> None:
        self._id = camera_id
        self._label = label
        self._url = rtsp_url
        self._detector = detector
        self._embedder = embedder
        self._tracker = tracker
        self._body_embedder = body_embedder
        self._state = state
        self._violence_model = violence_model
        self._ppe_model = ppe_model
        self._q: queue.Queue[FrameResult] = queue.Queue(maxsize=2)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._reader_thread: threading.Thread | None = None
        self._last_tracklets: list[Tracklet] = []  # reused on YOLO-skipped frames
        # Dedicated reader thread writes here; inference thread reads the latest frame.
        # Reader drains the RTSP buffer continuously so inference never blocks on cap.read().
        self._frame_lock = threading.Lock()
        self._latest_raw_frame: np.ndarray | None = None  # type: ignore[type-arg]
        self._frame_seq: int = 0  # incremented by reader; inference skips unchanged frames
        self._stats: CameraStats = stats if stats is not None else CameraStats(camera_id, label)

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
        # Build candidate URLs: main stream path, legacy single-channel path, substream
        candidates = [self._url]
        if "/Streaming/Channels/101" in self._url:
            candidates.append(self._url.replace("/Streaming/Channels/101", "/Streaming/Channels/1"))
            candidates.append(
                self._url.replace("/Streaming/Channels/101", "/Streaming/Channels/102")
            )
        elif "/101" in self._url:
            candidates.append(self._url.replace("/101", "/102"))

        for url in candidates:
            import re as _re

            safe = _re.sub(r"(rtsp://[^:]+:)[^@]+(@)", r"\1***\2", url)
            logger.info("%s: trying %s", self._label, safe)
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                logger.info("%s: connected %dx%d @ %.1f fps", self._label, w, h, fps)
                return cap
            cap.release()
        import re as _re

        safe_base = _re.sub(r"(rtsp://[^:]+:)[^@]+(@)", r"\1***\2", self._url)
        logger.error(
            "%s: cannot connect (%s) — 401 usually means wrong credentials. "
            "Hikvision username is 'admin' (lowercase) by default. "
            "Verify in VLC: Media > Open Network Stream.",
            self._label,
            safe_base,
        )
        return None

    def _read_frames(self) -> None:
        """Dedicated reader thread: drain RTSP buffer at full camera speed.

        Continuously calls cap.read() and stores only the latest frame.
        The inference thread reads from _latest_raw_frame without blocking on I/O.
        This prevents H.265 keyframe-interval stalls (2+ seconds) from blocking inference.
        Delivery rate is capped at _MAX_DELIVER_FPS to prevent GOP-burst frame floods.
        """
        cap = self._open()
        if cap is None:
            return
        consecutive_fails = 0
        _min_interval = 1.0 / _MAX_DELIVER_FPS
        _last_deliver = 0.0
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
            now = time.monotonic()
            if now - _last_deliver >= _min_interval:
                with self._frame_lock:
                    self._latest_raw_frame = frame
                    self._frame_seq += 1
                _last_deliver = now
        cap.release()
        logger.info("%s: reader stopped", self._label)

    def _run(self) -> None:
        fps_deque: deque[float] = deque(maxlen=30)
        face_fps_deque: deque[float] = deque(maxlen=10)
        frame_n = 0
        t_prev = time.monotonic()
        t_last_face_emb = time.monotonic()
        last_frame_seq = -1

        while not self._stop.is_set():
            with self._frame_lock:
                frame = self._latest_raw_frame
                frame_seq = self._frame_seq

            if frame is None or frame_seq == last_frame_seq:
                time.sleep(0.005)  # wait for a new frame from the reader thread
                continue
            last_frame_seq = frame_seq

            t0 = time.monotonic()
            fps_deque.append(1.0 / max(t0 - t_prev, 1e-6))
            t_prev = t0  # measure delivery interval, not post-inference time
            frame_n += 1

            # Per-frame calibration counters — updated inside try, committed to stats after
            _face_detected = 0
            _face_embedded = 0
            _face_rejected = 0
            _face_q_batch: list[float] = []
            _body_attempts = 0
            _kp_available = 0
            _body_q_batch: list[float] = []

            try:
                # Body tracking — every yolo_sample_n frames; reuse last boxes in between.
                # BoT-SORT with persist=True handles gaps gracefully.
                if frame_n % self._state.yolo_sample_n == 0:
                    self._last_tracklets = self._tracker.update(frame, conf=self._state.yolo_conf)
                tracklets = self._last_tracklets

                # Face pipeline — every N frames when enabled
                faces: list[FaceWithEmbedding] = []
                if self._state.face_enabled and frame_n % self._state.face_sample_n == 0:
                    raw_faces = self._detector.detect(frame)
                    for f in raw_faces:
                        if f.confidence < self._state.conf:
                            continue
                        _face_detected += 1
                        emb = self._embedder.embed(f, frame)
                        if emb is not None:
                            _face_embedded += 1
                            if emb.face_quality_norm != 1.0:
                                _face_q_batch.append(emb.face_quality_norm)
                            faces.append(emb)
                        else:
                            _face_rejected += 1
                            faces.append(f)  # still render box without embedding

                # Body Re-ID — every N frames when enabled
                # Uses extract_torso_crop (pose-normalized) to match production engine.py.
                reid_active = False
                if (
                    self._state.body_reid_enabled
                    and self._body_embedder is not None
                    and frame_n % self._state.reid_sample_n == 0
                ):
                    reid_active = True
                    _reid_settings = get_settings()
                    h_f, w_f = frame.shape[:2]
                    enriched: list[Tracklet] = []
                    for t in tracklets:
                        x1, y1, x2, y2 = t.bbox
                        x1c, y1c = max(0, x1), max(0, y1)
                        x2c, y2c = min(w_f, x2), min(h_f, y2)
                        crop = frame[y1c:y2c, x1c:x2c]
                        if crop.size > 0 and crop.shape[0] >= 16 and crop.shape[1] >= 8:
                            _body_attempts += 1
                            if len(t.keypoints) == 17:
                                _kp_available += 1
                            torso = extract_torso_crop(
                                frame,
                                t.bbox,
                                t.keypoints,
                                _reid_settings.torso_kp_conf_threshold,
                                _reid_settings.torso_crop_pad_fraction,
                            )
                            emb_tuple, quality = self._body_embedder.embed(torso)
                            if emb_tuple:
                                _body_q_batch.append(quality)
                            enriched.append(
                                Tracklet(
                                    local_track_id=t.local_track_id,
                                    camera_id=t.camera_id,
                                    bbox=t.bbox,
                                    confidence=t.confidence,
                                    embedding=t.embedding,
                                    body_embedding=emb_tuple,
                                    body_quality_norm=quality,
                                    keypoints=t.keypoints,
                                    face_visible=t.face_visible,
                                )
                            )
                        else:
                            enriched.append(t)
                    tracklets = tuple(enriched)

                # Violence scoring — streaming model, runs every frame when ≥2 persons
                violence_score: float | None = None
                if (
                    self._state.violence_enabled
                    and self._violence_model is not None
                    and self._violence_model.is_available
                    and len(tracklets) >= 2
                ):
                    violence_score = self._violence_model.score_frame(self._id, frame)

                # PPE detection — per-person crop, same cadence as body ReID
                ppe_results: list[dict[str, float] | None] = []
                if (
                    self._state.ppe_enabled
                    and self._ppe_model is not None
                    and self._ppe_model.is_available
                    and frame_n % self._state.reid_sample_n == 0
                ):
                    h_f, w_f = frame.shape[:2]
                    for t in tracklets:
                        x1, y1, x2, y2 = t.bbox
                        crop = frame[max(0, y1) : min(h_f, y2), max(0, x1) : min(w_f, x2)]
                        if crop.size > 0 and crop.shape[0] >= 32 and crop.shape[1] >= 32:
                            ppe_results.append(self._ppe_model.score_crop(crop))
                        else:
                            ppe_results.append(None)

            except Exception:
                logger.exception("%s: inference error frame %d", self._label, frame_n)
                continue

            t1 = time.monotonic()
            latency_ms = (t1 - t0) * 1000

            # Commit per-frame counts to the shared calibration stats object
            with self._stats.lock:
                self._stats.total_frames += 1
                self._stats.total_faces_detected += _face_detected
                self._stats.total_faces_embedded += _face_embedded
                self._stats.total_faces_rejected += _face_rejected
                self._stats.total_body_attempts += _body_attempts
                self._stats.total_kp_available += _kp_available
                self._stats.body_quality_norms.extend(_body_q_batch)
                self._stats.face_quality_norms.extend(_face_q_batch)
                self._stats.person_counts.append(len(tracklets))

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
                violence_score=violence_score,
                ppe_results=ppe_results,
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


def _grid_dims(n: int) -> tuple[int, int]:
    """Return (cols, rows) for an adaptive grid of n panels."""
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return cols, rows


def _letterbox_cell(img: np.ndarray, cell_w: int, cell_h: int) -> np.ndarray:  # type: ignore[type-arg]
    """Fit img into (cell_w × cell_h) preserving aspect ratio; fill unused space with black."""
    h, w = img.shape[:2]
    scale = min(cell_w / w, cell_h / h)
    nw, nh = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((cell_h, cell_w, 3), dtype=np.uint8)
    y_off = (cell_h - nh) // 2
    x_off = (cell_w - nw) // 2
    canvas[y_off : y_off + nh, x_off : x_off + nw] = resized
    return canvas


def _compose_grid(panels: list[np.ndarray], n_cols: int, n_rows: int, cell_w: int, cell_h: int) -> np.ndarray:  # type: ignore[type-arg]
    """Resize each panel to (cell_w, cell_h) and arrange into a filled grid image.
    Panels are pre-rendered at 16:9 aspect ratio so cell dimensions match — no letterbox bars."""
    cells: list[np.ndarray] = []  # type: ignore[type-arg]
    for p in panels:
        ph, pw = p.shape[:2]
        if pw != cell_w or ph != cell_h:
            p = cv2.resize(p, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
        cells.append(p)
    # Pad with black cells to fill the grid rectangle
    blank = np.zeros((cell_h, cell_w, 3), dtype=np.uint8)
    while len(cells) < n_cols * n_rows:
        cells.append(blank)
    rows_list = []
    for r in range(n_rows):
        row_cells = cells[r * n_cols : r * n_cols + n_cols]
        rows_list.append(np.hstack(row_cells))
    return np.vstack(rows_list)


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

        cv2.putText(panel, label, (x1, max(y1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    # Face boxes
    for f in result.faces:
        x1, y1, x2, y2 = [int(v * scale) for v in f.bbox]
        cv2.rectangle(panel, (x1, y1), (x2, y2), (0, 200, 255), 1)
        norm_str = f"n={f.face_quality_norm:.2f}" if f.face_quality_norm != 1.0 else ""
        cv2.putText(
            panel,
            f"F{norm_str}",
            (x1, max(y1 - 4, 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 200, 255),
            1,
        )

    # PPE badges — per-tracklet (only when ppe_results has data for this frame)
    for t, ppe in zip(result.tracklets, result.ppe_results):
        if ppe is None:
            continue
        x1, y1 = int(t.bbox[0] * scale), int(t.bbox[3] * scale)
        missing = [k[0].upper() for k, v in ppe.items() if v < 0.4]
        if missing:
            badge = "NO:" + "".join(missing)
            cv2.putText(
                panel,
                badge,
                (x1, min(y1 + 14, target_h - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (0, 60, 255),
                1,
            )

    # Violence alert — red border + text when score exceeds threshold
    v_score = result.violence_score
    if v_score is not None and v_score >= 0.60:
        cv2.rectangle(panel, (0, 0), (w_scaled, target_h), (0, 0, 220), 4)
        cv2.putText(
            panel,
            f"VIOLENCE {v_score:.2f}",
            (8, target_h - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (0, 0, 255),
            2,
        )

    # Stats bar
    person_count = len(result.tracklets)
    face_count = len(result.faces)
    face_embedded = sum(1 for f in result.faces if f.embedding)
    reid_tag = " B" if result.body_reid_active else ""
    fps_val = min(int(result.fps), 999)  # cap display at 999 to avoid 5-digit numbers
    # Fe:embedded/detected — shows quality-gate effectiveness at a glance
    embed_tag = f"Fe:{face_embedded}/{face_count}" if face_count > 0 else "Fe:-"
    hud = (
        f"{result.camera_label}  "
        f"P:{person_count} {embed_tag}  "
        f"{fps_val}fps {result.latency_ms:.0f}ms{reid_tag}"
    )
    bar = np.zeros((28, w_scaled, 3), dtype=np.uint8)
    cv2.putText(bar, hud, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (220, 220, 220), 1)
    return np.vstack([bar, panel])


# ---------------------------------------------------------------------------
# Calibration stats printer
# ---------------------------------------------------------------------------


def _print_calibration_stats(
    all_stats: list[CameraStats],
    state: PipelineState,
    settings: Any,
) -> None:
    """Print per-camera accuracy/quality stats to stdout for threshold calibration."""
    ts = datetime.now().strftime("%H:%M:%S")
    sep = "-" * 80
    print(f"\n{sep}")
    print(f"  VMS Calibration Stats @ {ts}")
    print(sep)
    for s in all_stats:
        with s.lock:
            f_det = s.total_faces_detected
            f_emb = s.total_faces_embedded
            f_rej = s.total_faces_rejected
            b_att = s.total_body_attempts
            kp_av = s.total_kp_available
            bq = list(s.body_quality_norms)
            fq = list(s.face_quality_norms)
            pc = list(s.person_counts)
            frms = s.total_frames

        emb_pct = f_emb * 100 / f_det if f_det > 0 else 0.0
        kp_pct = kp_av * 100 / b_att if b_att > 0 else 0.0
        p_avg = sum(pc) / len(pc) if pc else 0.0
        p_peak = max(pc) if pc else 0

        bq_str = (
            f"avg={sum(bq)/len(bq):.3f}  min={min(bq):.3f}  max={max(bq):.3f}  n={len(bq)}"
            if bq
            else "no data yet"
        )
        fq_str = (
            f"avg={sum(fq)/len(fq):.3f}  min={min(fq):.3f}  max={max(fq):.3f}  n={len(fq)}"
            if fq
            else "no data yet"
        )

        print(f"  CAM{s.camera_id}  {s.label}  ({frms} frames processed)")
        print(f"    Persons  : avg={p_avg:.1f}  peak={p_peak}  (rolling {len(pc)} frames)")
        print(
            f"    Faces    : detected={f_det}  embedded={f_emb} ({emb_pct:.1f}%)"
            f"  quality-rejected={f_rej}"
        )
        print(
            f"    Body     : crops={b_att}  pose-kpts={kp_pct:.1f}%"
            f"  (kpts available={kp_av})"
        )
        print(f"    Body  Bq : {bq_str}")
        print(f"    Face  Fq : {fq_str}")

    print(sep)
    print("  Active thresholds:")
    print(f"    scrfd_conf              = {state.conf:.2f}")
    print(f"    min_blur                = {settings.min_blur:.1f}")
    print(f"    reid_quality_norm_floor = {settings.reid_quality_norm_floor:.2f}")
    print(f"    torso_kp_conf_threshold = {settings.torso_kp_conf_threshold:.2f}")
    print(f"    torso_crop_pad_fraction = {settings.torso_crop_pad_fraction:.2f}")
    print(f"    reid_body_confirmed_sim = {settings.reid_body_confirmed_sim:.2f}")
    print(f"    reid_body_cross_cam_sim = {settings.reid_body_cross_cam_sim:.2f}")
    print(f"    reid_enroll_dedup_sim   = {settings.reid_enroll_dedup_sim:.2f}")

    # Tuning hints derived from observed distributions
    hints: list[str] = []
    for s in all_stats:
        with s.lock:
            bq = list(s.body_quality_norms)
            f_det = s.total_faces_detected
            f_rej = s.total_faces_rejected
        if bq and min(bq) < 0.40:
            hints.append(
                f"CAM{s.camera_id}: body_q min={min(bq):.3f} -- very low-norm crops in gallery;"
                f" consider raising reid_quality_norm_floor above {min(bq):.2f}"
            )
        if f_det > 20 and f_rej / f_det > 0.35:
            hints.append(
                f"CAM{s.camera_id}: {f_rej/f_det*100:.0f}% face embed rejection --"
                f" consider lowering min_blur (currently {settings.min_blur:.1f})"
            )
        if f_det > 20 and f_rej / f_det < 0.03:
            hints.append(
                f"CAM{s.camera_id}: only {f_rej/f_det*100:.1f}% face quality rejection --"
                f" min_blur={settings.min_blur:.1f} may be too permissive for production"
            )
    if hints:
        print(sep)
        print("  Tuning hints:")
        for h in hints:
            print(f"    [!] {h}")
    print(sep)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _camera_spec(camera_id: int) -> tuple[str, str] | None:
    """Return (label, rtsp_url) for a given camera_id, or None if not configured."""
    mapping = {
        105: ("Back Gate", os.environ.get("VMS_CAM_GATE_BACK_URL", "")),
        110: ("Front Gate", os.environ.get("VMS_CAM_GATE_FRONT_URL", "")),
        141: ("Gate 4", os.environ.get("VMS_CAM_GATE_4_URL", "")),
        144: ("Indoor 2", os.environ.get("VMS_CAM_INDOOR_2_URL", "")),
        200: ("ANPR", os.environ.get("VMS_CAM_ANPR_URL", "")),
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
        "--cameras",
        nargs="+",
        type=int,
        default=[105, 110, 141, 144, 200],
        help="Camera IDs to activate (default: all). Available: 105 110 141 144 200",
    )
    parser.add_argument(
        "--width", type=int, default=_GRID_W, help=f"Display window width  (default {_GRID_W})"
    )
    parser.add_argument(
        "--height", type=int, default=_GRID_H, help=f"Display window height (default {_GRID_H})"
    )
    parser.add_argument(
        "--yolo-every",
        type=int,
        default=_YOLO_SAMPLE_DEFAULT,
        metavar="N",
        help=f"Run YOLO every N frames (default {_YOLO_SAMPLE_DEFAULT}); reuses last boxes between runs",
    )
    parser.add_argument(
        "--device",
        default=None,
        choices=["cpu", "cuda"],
        help="Inference device (default: cuda if available, else cpu)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Process 10 frames and exit")
    parser.add_argument(
        "--stats-interval",
        type=float,
        default=5.0,
        metavar="N",
        dest="stats_interval",
        help="Print calibration stats to console every N seconds (default 5.0; 0 = disable)",
    )
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

    # Display dimensions (may be overridden by --width / --height)
    grid_w: int = args.width
    grid_h: int = args.height

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
    body_embedder = create_body_embedder(transreid_path=settings.transreid_body_model)

    if body_embedder is not None:
        kind = type(body_embedder).__name__
        logger.info("Body Re-ID: %s", kind)
    else:
        logger.info("Body Re-ID: DISABLED (no model path configured)")

    violence_model = ViolenceModel(
        settings.violence_model,
        clip_frames=settings.violence_clip_frames,
        clip_stride=settings.violence_clip_stride,
    )
    ppe_model = PPEModel(settings.ppe_model)
    if violence_model.is_available:
        logger.info("Violence detection: ENABLED (R(2+1)D-18)")
    else:
        logger.info("Violence detection: DISABLED (set VMS_VIOLENCE_MODEL=models/movinet_a2)")
    if ppe_model.is_available:
        logger.info("PPE detection: ENABLED (YOLOv8l SH17)")
    else:
        logger.info("PPE detection: DISABLED (set VMS_PPE_MODEL=models/sh17_ppe_yolov8l.onnx)")

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
    all_stats: list[CameraStats] = []
    for cid, label, url in cameras:
        tracker = PerCameraTracker.from_path(cid, _tracker_model)
        cam_stats = CameraStats(cid, label)
        all_stats.append(cam_stats)
        w = CameraWorker(
            cid,
            label,
            url,
            detector,
            embedder,
            tracker,
            body_embedder,
            state,
            violence_model,
            ppe_model,
            stats=cam_stats,
        )
        w.start()
        workers.append(w)

    logger.info(
        "Controls: F=face  B=body_reid  V=violence  P=ppe  +/-=face_rate  C=confidence  "
        "Y=yolo_conf  T=yolo_skip  S=snapshot  1-N=fullscreen  G=grid  Q=quit"
    )

    show_reid_dim = body_embedder is not None
    frame_counter = 0
    _last_stats_print = time.monotonic()
    # Per-slot result cache: keeps last-good FrameResult per camera so the grid never
    # collapses (changes dimensions) when a camera temporarily returns None.
    cached_results: list[FrameResult | None] = [None] * len(workers)
    display: np.ndarray | None = None  # type: ignore[type-arg]
    live_results: list[FrameResult] = []

    try:
        while True:
            current_results: list[FrameResult | None] = []
            for i, w in enumerate(workers):
                r = w.latest()
                current_results.append(r)
                if r is not None:
                    cached_results[i] = r

            live_results = [r for r in cached_results if r is not None]

            if live_results:
                n = len(live_results)
                total_persons = sum(len(r.tracklets) for r in current_results if r is not None)
                face_tag = f"F:{'ON' if state.face_enabled else 'OFF'}"
                reid_tag = f"B:{'ON' if state.body_reid_enabled else 'OFF'}"
                vio_tag = f"V:{'ON' if state.violence_enabled else 'OFF'}"
                ppe_tag = f"P:{'ON' if state.ppe_enabled else 'OFF'}"
                conf_tag = f"FC:{state.conf:.2f} YC:{state.yolo_conf:.2f}"
                focus_tag = (
                    f" [CAM{state.focus_idx + 1}|G=grid]" if state.focus_idx is not None else ""
                )
                # Cumulative face embed rate across all cameras (shown in footer for live feedback)
                _tot_det = sum(s.total_faces_detected for s in all_stats)
                _tot_emb = sum(s.total_faces_embedded for s in all_stats)
                _emb_rate = f"{_tot_emb*100//_tot_det}%" if _tot_det > 0 else "--%"
                footer_text = (
                    f"  HEAD:{total_persons}  {face_tag} {reid_tag} {vio_tag} {ppe_tag}"
                    f"  {conf_tag}  Ev:{state.yolo_sample_n}"
                    f"  EmB:{_tot_emb}/{_tot_det}({_emb_rate}){focus_tag}"
                )

                if state.focus_idx is not None and state.focus_idx < n:
                    # Fullscreen: render at max content height that fits the window
                    fs_content_h = grid_h - _FOOTER_H - 28
                    panel = _render_panel(
                        live_results[state.focus_idx], fs_content_h, show_reid_dim
                    )
                    grid = _letterbox_cell(panel, grid_w, grid_h - _FOOTER_H)
                else:
                    # Adaptive grid: 16:9 cell height, capped so we never overflow the window
                    n_cols, n_rows = _grid_dims(n)
                    cell_w = grid_w // n_cols
                    max_content_h = (grid_h - _FOOTER_H) // n_rows - 28
                    content_h = min(cell_w * 9 // 16, max_content_h)
                    cell_h = content_h + 28
                    panels = [_render_panel(r, content_h, show_reid_dim) for r in live_results]
                    grid = _compose_grid(panels, n_cols, n_rows, cell_w, cell_h)

                footer = np.zeros((_FOOTER_H, grid.shape[1], 3), dtype=np.uint8)
                cv2.putText(
                    footer, footer_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 255, 200), 2
                )

                display = np.vstack([grid, footer])
                cv2.imshow("VMS Pipeline Test", display)

            # Periodic calibration stats to console (stats_interval=0 disables)
            if args.stats_interval > 0 and time.monotonic() - _last_stats_print >= args.stats_interval:
                _print_calibration_stats(all_stats, state, settings)
                _last_stats_print = time.monotonic()

            key = cv2.waitKey(33) & 0xFF
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
            elif key == ord("v"):
                state.violence_enabled = not state.violence_enabled
                logger.info("Violence detection: %s", "ON" if state.violence_enabled else "OFF")
            elif key == ord("p"):
                state.ppe_enabled = not state.ppe_enabled
                logger.info("PPE detection: %s", "ON" if state.ppe_enabled else "OFF")
            elif key == ord("+") or key == ord("="):
                state.face_sample_n = max(1, state.face_sample_n - 1)
                logger.info("Face sample every %d frames", state.face_sample_n)
            elif key == ord("-"):
                state.face_sample_n = min(20, state.face_sample_n + 1)
                logger.info("Face sample every %d frames", state.face_sample_n)
            elif key == ord("c"):
                idx = (
                    (_CONF_CYCLE.index(state.conf) + 1) % len(_CONF_CYCLE)
                    if state.conf in _CONF_CYCLE
                    else 0
                )
                state.conf = _CONF_CYCLE[idx]
                logger.info("Face (SCRFD) confidence: %.2f", state.conf)
            elif key == ord("y"):
                idx = (
                    (_YOLO_CONF_CYCLE.index(state.yolo_conf) + 1) % len(_YOLO_CONF_CYCLE)
                    if state.yolo_conf in _YOLO_CONF_CYCLE
                    else 1
                )
                state.yolo_conf = _YOLO_CONF_CYCLE[idx]
                logger.info("YOLO person confidence: %.2f", state.yolo_conf)
            elif key == ord("t"):
                idx = (
                    (_YOLO_SAMPLE_CYCLE.index(state.yolo_sample_n) + 1) % len(_YOLO_SAMPLE_CYCLE)
                    if state.yolo_sample_n in _YOLO_SAMPLE_CYCLE
                    else 0
                )
                state.yolo_sample_n = _YOLO_SAMPLE_CYCLE[idx]
                logger.info("YOLO runs every %d frames", state.yolo_sample_n)
            elif key == ord("s"):
                _SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                if live_results and display is not None:
                    path = _SNAPSHOTS_DIR / f"snapshot_{ts}.jpg"
                    cv2.imwrite(str(path), display)
                    logger.info("Snapshot saved: %s", path)
            elif ord("1") <= key <= ord("9"):
                idx = key - ord("1")
                if live_results and idx < len(live_results):
                    state.focus_idx = None if state.focus_idx == idx else idx
                    mode = "grid" if state.focus_idx is None else f"camera {idx + 1} fullscreen"
                    logger.info("Display: %s", mode)
            elif key == ord("g") or key == ord("0"):
                state.focus_idx = None
                logger.info("Display: grid")

    finally:
        for w in workers:
            w.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
