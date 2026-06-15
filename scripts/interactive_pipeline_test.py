"""Interactive pipeline test harness for CPU-only laptops.

Uses YOLOv8n (TEST_BODY_MODEL) for smooth body tracking every frame,
and the production face pipeline (SCRFD 10G + AdaFace IR50) every Nth frame.

NOTE: TEST_BODY_MODEL is intentionally lighter than PROD_BODY_MODEL.
      Do NOT use this script as a proxy for production detection accuracy.

Usage:
    python scripts/interactive_pipeline_test.py
    python scripts/interactive_pipeline_test.py --dry-run

Controls:
    +/-   increase/decrease face sample interval N (1-20)
    C     cycle confidence: 0.40 -> 0.55 -> 0.70
    F     toggle face pipeline on/off
    T     toggle timing panel row
    S     save snapshot pair to scripts/snapshots/
    R     reset track-ID colour map
    Q     quit
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import queue
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
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
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

# ---------------------------------------------------------------------------
# TEST vs PRODUCTION model constants -- visible at the top of the file
# ---------------------------------------------------------------------------

TEST_BODY_MODEL = "yolov8n.pt"  # auto-downloaded by ultralytics (~6 MB)
PROD_BODY_MODEL = "models/yolov8x-pose.pt"  # production accuracy -- NOT used here
FACE_DETECTOR = "models/scrfd_10g_bnkps.onnx"
FACE_EMBEDDER = "models/adaface_ir50.onnx"
FACE_SAMPLE_EVERY_N = 5  # default face sample rate
ADAFACE_MIN_SIM = 0.72  # unused (no DB); shown for reference

_CONF_CYCLE: tuple[float, ...] = (0.40, 0.55, 0.70)
_PANEL_H_DEFAULT = 540
_BANNER_H = 30
_STATS_H = 44
_TIMING_H = 24
_HEADER_H = 0  # no header row in this harness (banner replaces it)
_SNAPSHOTS_DIR = Path(__file__).resolve().parent / "snapshots"

_TRACK_COLORS: dict[int, tuple[int, int, int]] = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline_test")

import cv2
import numpy as np

from vms.config import get_settings
from vms.inference.messages import FaceWithEmbedding, Tracklet


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FaceResult:
    """One detected face with embedding norm. Label is always UNKNOWN (no DB)."""

    bbox: tuple[int, int, int, int]
    confidence: float
    embedding_norm: float
    label: str  # always "UNKNOWN" in this harness


@dataclass
class FrameResult:
    """Snapshot of one camera frame after body + face inference."""

    camera_label: str
    frame: np.ndarray  # type: ignore[type-arg]
    tracklets: list[Tracklet]
    face_results: list[FaceResult]
    face_stale_frames: int  # frames since last SCRFD+AdaFace run
    fps: float
    latency_body_ms: float
    latency_scrfd_ms: float  # 0.0 on skip frames
    latency_adaface_ms: float  # 0.0 on skip frames
    frame_n: int


@dataclass
class PipelineState:
    """Shared mutable state read by workers, written by main thread keypresses."""

    sample_n: int = FACE_SAMPLE_EVERY_N
    conf: float = 0.55
    face_enabled: bool = True
    timing_panel: bool = False


# ---------------------------------------------------------------------------
# FacePipeline -- SCRFD + AdaFace (production models, sampled every N frames)
# ---------------------------------------------------------------------------

from vms.inference.detector import SCRFDDetector
from vms.inference.embedder import AdaFaceEmbedder


class FacePipeline:
    """Runs SCRFD face detection + AdaFace embedding on a single frame.

    Caller decides the sampling schedule. This class just runs when called.
    """

    def __init__(self, detector: Any, embedder: Any) -> None:
        self._detector = detector
        self._embedder = embedder

    @classmethod
    def from_paths(cls, detector_path: str, embedder_path: str) -> FacePipeline:
        return cls(
            detector=SCRFDDetector.from_path(detector_path),
            embedder=AdaFaceEmbedder.from_path(embedder_path),
        )

    def run(self, frame: np.ndarray[Any, np.dtype[Any]]) -> tuple[list[FaceResult], float, float]:
        """Detect faces + compute embeddings. Returns (results, scrfd_ms, adaface_ms)."""
        t0 = time.perf_counter()
        faces: list[FaceWithEmbedding] = self._detector.detect(frame)
        scrfd_ms = (time.perf_counter() - t0) * 1000

        results: list[FaceResult] = []
        adaface_total = 0.0
        for face in faces:
            t1 = time.perf_counter()
            embedded: FaceWithEmbedding | None = self._embedder.embed(face, frame)
            adaface_total += (time.perf_counter() - t1) * 1000
            if embedded is None or not embedded.embedding:
                continue
            norm = float(np.linalg.norm(embedded.embedding))
            results.append(
                FaceResult(
                    bbox=embedded.bbox,
                    confidence=embedded.confidence,
                    embedding_norm=norm,
                    label="UNKNOWN",
                )
            )
        return results, scrfd_ms, adaface_total


# ---------------------------------------------------------------------------
# BodyDetector -- YOLOv8n (test-only nano model, NOT production accuracy)
# ---------------------------------------------------------------------------


class BodyDetector:
    """Wraps YOLOv8n.track() for one camera.

    Uses TEST_BODY_MODEL (yolov8n) -- fast on CPU but lower accuracy than
    PROD_BODY_MODEL (yolov8x-pose). Do not use in production.
    """

    def __init__(self, model: Any, botsort_config: str, camera_id: int) -> None:
        self._model = model
        self._botsort_config = botsort_config
        self._camera_id = camera_id

    @classmethod
    def from_config(cls, camera_id: int) -> BodyDetector:
        from ultralytics import YOLO  # type: ignore[attr-defined]

        settings = get_settings()
        logger.info("Loading test body model: %s (not production accuracy)", TEST_BODY_MODEL)
        return cls(
            model=YOLO(TEST_BODY_MODEL),
            botsort_config=settings.botsort_config,
            camera_id=camera_id,
        )

    def detect(
        self, frame: np.ndarray[Any, np.dtype[Any]], conf: float
    ) -> tuple[list[Tracklet], float]:
        """Run tracking. Returns (tracklets, latency_ms). keypoints always empty (no pose head)."""
        t0 = time.perf_counter()
        results: Any = self._model.track(
            frame,
            conf=conf,
            persist=True,
            tracker=self._botsort_config,
            verbose=False,
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        if not results:
            return [], latency_ms
        r = results[0]
        if r.boxes.id is None:
            return [], latency_ms

        tracklets: list[Tracklet] = []
        for bbox_arr, tid, conf_val in zip(r.boxes.xyxy, r.boxes.id, r.boxes.conf, strict=False):
            x1, y1, x2, y2 = (int(v) for v in bbox_arr)
            tracklets.append(
                Tracklet(
                    local_track_id=int(tid),
                    camera_id=self._camera_id,
                    bbox=(x1, y1, x2, y2),
                    confidence=float(conf_val),
                    keypoints=(),
                    face_visible=False,
                )
            )
        return tracklets, latency_ms


# ---------------------------------------------------------------------------
# CameraWorker -- one thread per camera
# ---------------------------------------------------------------------------


class CameraWorker:
    """Reads RTSP frames, runs BodyDetector every frame + FacePipeline every N frames."""

    def __init__(
        self,
        camera_id: int,
        camera_label: str,
        rtsp_url: str,
        body_detector: BodyDetector,
        face_pipeline: FacePipeline,
        state: PipelineState,
    ) -> None:
        self._camera_id = camera_id
        self._camera_label = camera_label
        self._rtsp_url = rtsp_url
        self._body_detector = body_detector
        self._face_pipeline = face_pipeline
        self._state = state
        self._result_queue: queue.Queue[FrameResult] = queue.Queue(maxsize=2)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name=f"worker-{self._camera_label}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=4.0)

    def latest(self) -> FrameResult | None:
        result: FrameResult | None = None
        while True:
            try:
                result = self._result_queue.get_nowait()
            except queue.Empty:
                break
        return result

    def _open_stream(self) -> cv2.VideoCapture | None:
        if self._rtsp_url.isdigit():
            cap = cv2.VideoCapture(int(self._rtsp_url))
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                logger.info("%s: webcam %s opened %dx%d @ %.1ffps", self._camera_label, self._rtsp_url, w, h, fps)
                return cap
            cap.release()
            logger.warning("%s: webcam index %s not available", self._camera_label, self._rtsp_url)
            return None

        for attempt, url in enumerate(
            [
                self._rtsp_url,
                self._rtsp_url.replace("/101", "/102"),
            ]
        ):
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if cap.isOpened():
                if attempt == 1:
                    logger.warning("%s: using substream fallback /102", self._camera_label)
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                logger.info("%s: connected %dx%d @ %.1ffps", self._camera_label, w, h, fps)
                return cap
            cap.release()
        logger.error("%s: cannot open stream -- check network/credentials", self._camera_label)
        return None

    def _run(self) -> None:
        cap = self._open_stream()
        if cap is None:
            return

        fps_times: deque[float] = deque(maxlen=30)
        consecutive_failures = 0
        frame_n = 0
        fps = 0.0
        last_face_results: list[FaceResult] = []
        last_scrfd_ms = 0.0
        last_adaface_ms = 0.0
        face_stale = 0

        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                consecutive_failures += 1
                if consecutive_failures % 5 == 0:
                    logger.warning(
                        "%s: %d consecutive decode failures",
                        self._camera_label,
                        consecutive_failures,
                    )
                time.sleep(0.05)
                continue

            consecutive_failures = 0
            frame_n += 1
            t_now = time.perf_counter()
            fps_times.append(t_now)
            if len(fps_times) >= 2:
                fps = (len(fps_times) - 1) / (fps_times[-1] - fps_times[0])

            if self._result_queue.full():
                continue

            tracklets, body_ms = self._body_detector.detect(frame, self._state.conf)

            scrfd_ms = 0.0
            adaface_ms = 0.0
            if self._state.face_enabled and frame_n % self._state.sample_n == 0:
                last_face_results, scrfd_ms, adaface_ms = self._face_pipeline.run(frame)
                last_scrfd_ms = scrfd_ms
                last_adaface_ms = adaface_ms
                face_stale = 0
                if last_face_results:
                    logger.debug(
                        "%s: face sample frame=%d faces=%d norm=%.2f",
                        self._camera_label,
                        frame_n,
                        len(last_face_results),
                        last_face_results[0].embedding_norm,
                    )
            else:
                face_stale += 1

            result = FrameResult(
                camera_label=self._camera_label,
                frame=frame,
                tracklets=tracklets,
                face_results=last_face_results,
                face_stale_frames=face_stale,
                fps=fps,
                latency_body_ms=body_ms,
                latency_scrfd_ms=last_scrfd_ms,
                latency_adaface_ms=last_adaface_ms,
                frame_n=frame_n,
            )
            with contextlib.suppress(queue.Full):
                self._result_queue.put_nowait(result)

        cap.release()
        logger.info("%s: worker stopped", self._camera_label)


# ---------------------------------------------------------------------------
# Rendering helpers (main thread only -- never call from worker threads)
# ---------------------------------------------------------------------------


def _track_color(track_id: int) -> tuple[int, int, int]:
    if track_id not in _TRACK_COLORS:
        hue = (track_id * 47 + 30) % 180
        hsv = np.array([[[hue, 210, 220]]], dtype=np.uint8)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
        _TRACK_COLORS[track_id] = (int(bgr[0]), int(bgr[1]), int(bgr[2]))
    return _TRACK_COLORS[track_id]


def _labeled_box(
    img: np.ndarray[Any, np.dtype[Any]],
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    label: str,
    color: tuple[int, int, int],
    thickness: int = 2,
) -> None:
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    label_y = max(y1 - 4, th + 4)
    cv2.rectangle(img, (x1, label_y - th - 4), (x1 + tw + 6, label_y + 2), color, -1)
    cv2.putText(img, label, (x1 + 3, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)


def _render_banner(total_w: int) -> np.ndarray[Any, np.dtype[Any]]:
    banner: np.ndarray[Any, np.dtype[Any]] = np.full((_BANNER_H, total_w, 3), 25, dtype=np.uint8)
    text = "MODE: DEMO FAST BODY DETECTOR, PRODUCTION FACE PIPELINE"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    x = max(0, (total_w - tw) // 2)
    cv2.putText(banner, text, (x, th + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 220), 1)
    return banner


def _render_panel(result: FrameResult, panel_h: int) -> tuple[np.ndarray[Any, np.dtype[Any]], int]:
    """Scale frame, draw body + face overlays. Returns (panel, person_count)."""
    h0, w0 = result.frame.shape[:2]
    panel_w = int(w0 * (panel_h / h0))
    panel: np.ndarray[Any, np.dtype[Any]] = cv2.resize(result.frame, (panel_w, panel_h))
    sx = panel_w / w0
    sy = panel_h / h0

    for t in result.tracklets:
        px1 = int(t.bbox[0] * sx)
        py1 = int(t.bbox[1] * sy)
        px2 = int(t.bbox[2] * sx)
        py2 = int(t.bbox[3] * sy)
        _labeled_box(
            panel, px1, py1, px2, py2, f"T:{t.local_track_id}", _track_color(t.local_track_id)
        )

    stale_tag = f" s:{result.face_stale_frames}" if result.face_stale_frames > 0 else ""
    for face in result.face_results:
        fx1 = int(face.bbox[0] * sx)
        fy1 = int(face.bbox[1] * sy)
        fx2 = int(face.bbox[2] * sx)
        fy2 = int(face.bbox[3] * sy)
        cv2.rectangle(panel, (fx1, fy1), (fx2, fy2), (255, 80, 0), 2)
        label = f"UNKNOWN n:{face.embedding_norm:.2f}{stale_tag}"
        cv2.putText(
            panel, label, (fx1, max(fy1 - 3, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 140, 0), 1
        )

    count = len(result.tracklets)
    hud = f"{result.camera_label}  P:{count}  F:{len(result.face_results)}"
    (tw, th), _ = cv2.getTextSize(hud, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
    overlay = panel.copy()
    cv2.rectangle(overlay, (4, 2), (tw + 14, th + 14), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, panel, 0.45, 0, panel)
    cv2.putText(panel, hud, (8, th + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    return panel, count


def _render_stats_bar(
    front: FrameResult | None,
    back: FrameResult | None,
    total_w: int,
    state: PipelineState,
) -> np.ndarray[Any, np.dtype[Any]]:
    bar: np.ndarray[Any, np.dtype[Any]] = np.full((_STATS_H, total_w, 3), 30, dtype=np.uint8)

    def _fmt(r: FrameResult | None, cam: str) -> tuple[str, tuple[int, int, int]]:
        if r is None:
            return f"{cam}: waiting...", (140, 140, 140)
        face_str = (
            "face:OFF"
            if not state.face_enabled
            else f"scrfd:{r.latency_scrfd_ms:.0f}ms ada:{r.latency_adaface_ms:.0f}ms"
        )
        text = (
            f"{cam}: {r.fps:.1f}fps  body:{r.latency_body_ms:.0f}ms  "
            f"{face_str}  N={state.sample_n}  stale:{r.face_stale_frames}"
        )
        color: tuple[int, int, int] = (0, 0, 220) if r.fps < 15.0 else (180, 180, 180)
        return text, color

    front_text, front_color = _fmt(front, front.camera_label if front else "CAM1")
    back_text, back_color = _fmt(back, back.camera_label if back else "CAM2")
    cv2.putText(bar, front_text, (8, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, front_color, 1)
    cv2.putText(bar, back_text, (8, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.42, back_color, 1)
    return bar


def _render_timing_panel(
    front: FrameResult | None,
    back: FrameResult | None,
    total_w: int,
) -> np.ndarray[Any, np.dtype[Any]]:
    row: np.ndarray[Any, np.dtype[Any]] = np.full((_TIMING_H, total_w, 3), 15, dtype=np.uint8)

    def _fmt(r: FrameResult | None, cam: str) -> str:
        if r is None:
            return f"{cam}:-"
        norm = r.face_results[0].embedding_norm if r.face_results else 0.0
        return (
            f"{cam} yolo:{r.latency_body_ms:.0f}  "
            f"scrfd:{r.latency_scrfd_ms:.0f}  "
            f"ada:{r.latency_adaface_ms:.0f}  "
            f"norm:{norm:.2f}"
        )

    text = _fmt(front, front.camera_label if front else "CAM1") + "   |   " + _fmt(back, back.camera_label if back else "CAM2")
    cv2.putText(row, text, (8, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (100, 220, 100), 1)
    return row


def _save_snapshots(front: FrameResult | None, back: FrameResult | None) -> None:
    _SNAPSHOTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")
    for label, result in [("front", front), ("back", back)]:
        if result is not None:
            path = _SNAPSHOTS_DIR / f"pipeline_test_{ts}_{label}.jpg"
            cv2.imwrite(str(path), result.frame)
            logger.info("Snapshot saved: %s", path.name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="VMS interactive pipeline test -- CPU-friendly, production face models"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process 10 frames per camera, log timings, exit without display",
    )
    parser.add_argument("--panel-height", type=int, default=_PANEL_H_DEFAULT, metavar="PX")
    parser.add_argument(
        "--webcam",
        action="store_true",
        help="Use laptop webcam instead of RTSP (index 0). Add --webcam2 for a second webcam.",
    )
    parser.add_argument(
        "--webcam2",
        type=int,
        default=1,
        metavar="INDEX",
        help="Second webcam device index (default 1). Ignored unless --webcam is set.",
    )
    args = parser.parse_args()

    if args.webcam:
        front_url = "0"
        back_url = str(args.webcam2)
        front_label = "WEBCAM"
        back_label = f"WEBCAM{args.webcam2}"
        logger.info("Webcam mode: front=index 0, back=index %d", args.webcam2)
    else:
        front_url = os.environ.get("VMS_CAM_GATE_FRONT_URL", "")
        back_url = os.environ.get("VMS_CAM_GATE_BACK_URL", "")
        if not front_url or not back_url:
            logger.error("VMS_CAM_GATE_FRONT_URL or VMS_CAM_GATE_BACK_URL not set -- check .env")
            sys.exit(1)
        front_label = "CAM105"
        back_label = "CAM110"

    logger.info("TEST_BODY_MODEL : %s  (NOT production accuracy)", TEST_BODY_MODEL)
    logger.info("PROD_BODY_MODEL : %s  (not loaded in this harness)", PROD_BODY_MODEL)
    logger.info("FACE_DETECTOR   : %s", FACE_DETECTOR)
    logger.info("FACE_EMBEDDER   : %s", FACE_EMBEDDER)
    logger.info("Loading models...")

    state = PipelineState()

    front_cam_id = 0 if args.webcam else 105
    back_cam_id = args.webcam2 if args.webcam else 110
    front_body = BodyDetector.from_config(camera_id=front_cam_id)
    back_body = BodyDetector.from_config(camera_id=back_cam_id)
    front_face = FacePipeline.from_paths(FACE_DETECTOR, FACE_EMBEDDER)
    back_face = FacePipeline.from_paths(FACE_DETECTOR, FACE_EMBEDDER)

    logger.info("Models loaded. Starting workers...")

    front_worker = CameraWorker(front_cam_id, front_label, front_url, front_body, front_face, state)
    back_worker = CameraWorker(back_cam_id, back_label, back_url, back_body, back_face, state)
    front_worker.start()
    back_worker.start()

    front_result: FrameResult | None = None
    back_result: FrameResult | None = None
    dry_run_seen = 0
    dry_run_face_fired = 0
    win_title = "VMS Pipeline Test  [+/-=N  C=conf  F=face  T=timing  S=snap  R=reset  Q=quit]"

    try:
        while True:
            fr = front_worker.latest()
            br = back_worker.latest()
            if fr is not None:
                front_result = fr
            if br is not None:
                back_result = br

            if args.dry_run:
                if fr is not None or br is not None:
                    dry_run_seen += 1
                    if front_result and front_result.face_results:
                        dry_run_face_fired += 1
                    if back_result and back_result.face_results:
                        dry_run_face_fired += 1
                    logger.info(
                        "dry-run %d/10  %s fps=%.1f body_ms=%.0f faces=%d"
                        "  %s fps=%.1f body_ms=%.0f faces=%d",
                        dry_run_seen,
                        front_label,
                        front_result.fps if front_result else 0.0,
                        front_result.latency_body_ms if front_result else 0.0,
                        len(front_result.face_results) if front_result else 0,
                        back_label,
                        back_result.fps if back_result else 0.0,
                        back_result.latency_body_ms if back_result else 0.0,
                        len(back_result.face_results) if back_result else 0,
                    )
                if dry_run_seen >= 10:
                    if front_result is None:
                        logger.error("dry-run FAIL: %s never delivered a frame", front_label)
                        sys.exit(1)
                    if not args.webcam and back_result is None:
                        logger.error("dry-run FAIL: %s never delivered a frame", back_label)
                        sys.exit(1)
                    logger.info(
                        "dry-run PASS: 10 frames received, face pipeline fired %d times",
                        dry_run_face_fired,
                    )
                    break
                time.sleep(0.05)
                continue

            if front_result is None and back_result is None:
                time.sleep(0.02)
                continue

            panel_h = args.panel_height
            placeholder_w = int(panel_h * 16 / 9)

            if front_result is not None:
                front_panel, _ = _render_panel(front_result, panel_h)
            else:
                front_panel = np.zeros((panel_h, placeholder_w, 3), dtype=np.uint8)
                cv2.putText(
                    front_panel,
                    f"{front_label}: waiting...",
                    (20, panel_h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (60, 60, 60),
                    1,
                )

            if back_result is not None:
                back_panel, _ = _render_panel(back_result, panel_h)
            else:
                back_panel = np.zeros((panel_h, placeholder_w, 3), dtype=np.uint8)
                cv2.putText(
                    back_panel,
                    "CAM110: waiting...",
                    (20, panel_h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (60, 60, 60),
                    1,
                )

            fw, bw = front_panel.shape[1], back_panel.shape[1]
            if fw != bw:
                target_w = max(fw, bw)
                pad_w = target_w - fw if fw < target_w else target_w - bw
                pad = np.zeros((panel_h, pad_w, 3), dtype=np.uint8)
                if fw < target_w:
                    front_panel = np.hstack([front_panel, pad])
                else:
                    back_panel = np.hstack([back_panel, pad])

            side_by_side: np.ndarray[Any, np.dtype[Any]] = np.hstack([front_panel, back_panel])
            total_w = side_by_side.shape[1]

            banner = _render_banner(total_w)
            stats = _render_stats_bar(front_result, back_result, total_w, state)

            layers: list[np.ndarray[Any, np.dtype[Any]]] = [banner, side_by_side, stats]
            if state.timing_panel:
                layers.append(_render_timing_panel(front_result, back_result, total_w))

            display: np.ndarray[Any, np.dtype[Any]] = np.vstack(layers)
            mid_x = front_panel.shape[1]
            cv2.line(display, (mid_x, 0), (mid_x, display.shape[0]), (60, 60, 60), 1)

            cv2.imshow(win_title, display)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            elif key == ord("+") or key == ord("="):
                state.sample_n = min(20, state.sample_n + 1)
                logger.info("Face sample N -> %d", state.sample_n)
            elif key == ord("-"):
                state.sample_n = max(1, state.sample_n - 1)
                logger.info("Face sample N -> %d", state.sample_n)
            elif key == ord("c"):
                idx = _CONF_CYCLE.index(state.conf) if state.conf in _CONF_CYCLE else 1
                state.conf = _CONF_CYCLE[(idx + 1) % len(_CONF_CYCLE)]
                logger.info("Confidence -> %.2f", state.conf)
            elif key == ord("f"):
                state.face_enabled = not state.face_enabled
                logger.info("Face pipeline %s", "ON" if state.face_enabled else "OFF")
            elif key == ord("t"):
                state.timing_panel = not state.timing_panel
            elif key == ord("s"):
                _save_snapshots(front_result, back_result)
            elif key == ord("r"):
                _TRACK_COLORS.clear()
                logger.info("Track colour palette reset")

    finally:
        front_worker.stop()
        back_worker.stop()
        cv2.destroyAllWindows()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
