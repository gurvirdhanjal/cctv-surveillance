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

import argparse  # noqa: F401
import contextlib
import logging
import os
import queue
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field  # noqa: F401
from datetime import datetime, timezone  # noqa: F401
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
