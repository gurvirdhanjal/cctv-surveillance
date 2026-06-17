"""Two-camera gate entry pipeline smoke test.

Runs SCRFD face detection + YOLOv8x-pose / BoT-SORT tracking against two
live Hikvision IP cameras and renders a side-by-side display window.

No DB writes. No Redis writes. No identity enrolment — observation only.

Usage:
    python scripts/gate_smoke_test.py
    python scripts/gate_smoke_test.py --dry-run     # 5 frames, no display, exit

Controls:
    Q    quit cleanly
    S    save snapshot pair to scripts/snapshots/
    R    reset track-ID colour map
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import argparse
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make 'vms' importable from any CWD
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Load .env before Settings import (python-dotenv is a project dependency)
try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass  # rely on env vars being pre-set

# Required by pydantic Settings; not used in this script
os.environ.setdefault("VMS_DB_URL", "postgresql://localhost/vms_unused")
os.environ.setdefault("VMS_JWT_SECRET", "smoke-test-dummy-secret")

# CCTV-tuned thresholds: lower conf catches more distant/smaller faces
os.environ.setdefault("VMS_SCRFD_CONF", "0.55")
os.environ.setdefault("VMS_MIN_FACE_PX", "30")

# Suppress TF / ONNX startup noise
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import cv2
import numpy as np

# Fail fast if running under a headless OpenCV (e.g. system Python where ultralytics
# monkey-patches cv2.imshow with opencv-python-headless).
# Fix: use the project venv — .\venv\Scripts\python.exe scripts\gate_smoke_test.py
_cv2_has_gui = hasattr(cv2, "imshow") and "highgui" in cv2.getBuildInformation().lower()
if "headless" in cv2.__file__.lower() or not _cv2_has_gui:
    print(
        f"ERROR: headless OpenCV detected ({cv2.__file__}).\n"
        "Run the script with the project venv Python:\n"
        r"  .\venv\Scripts\python.exe scripts\gate_smoke_test.py",
        file=sys.stderr,
    )
    sys.exit(1)

from vms.config import get_settings
from vms.inference.detector import SCRFDDetector
from vms.inference.messages import FaceWithEmbedding, Tracklet
from vms.inference.tracker import PerCameraTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gate_smoke")

_PANEL_H_DEFAULT = 540
_STATS_BAR_H = 32
_HEADER_H = 28
_SNAPSHOTS_DIR = Path(__file__).resolve().parent / "snapshots"

# Shared track-ID → BGR colour map (cleared on R keypress)
_TRACK_COLORS: dict[int, tuple[int, int, int]] = {}


# ---------------------------------------------------------------------------
# Data transfer object
# ---------------------------------------------------------------------------


@dataclass
class FrameResult:
    camera_label: str
    frame: np.ndarray  # original-resolution BGR
    tracklets: list[Tracklet]
    faces: list[FaceWithEmbedding]
    fps: float
    latency_ms: float
    frame_n: int


# ---------------------------------------------------------------------------
# Camera worker — one thread per camera
# ---------------------------------------------------------------------------


class CameraWorker:
    """Reads RTSP frames, runs inference, publishes FrameResult to a bounded queue."""

    def __init__(
        self,
        camera_id: int,
        camera_label: str,
        rtsp_url: str,
        detector: Any,  # SCRFDDetector | _YoloFaceBackend | _NullDetector
        tracker: PerCameraTracker,
    ) -> None:
        self._camera_id = camera_id
        self._camera_label = camera_label
        self._rtsp_url = rtsp_url
        self._detector = detector
        self._tracker = tracker
        self._result_queue: queue.Queue[FrameResult] = queue.Queue(maxsize=2)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._first_detected = False

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
        """Drain queue and return the most recent result (discards stale frames)."""
        result: FrameResult | None = None
        while True:
            try:
                result = self._result_queue.get_nowait()
            except queue.Empty:
                break
        return result

    def _open_stream(self) -> cv2.VideoCapture | None:
        urls = [self._rtsp_url, self._rtsp_url.replace("/101", "/102")]
        for attempt, url in enumerate(urls):
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if cap.isOpened():
                if attempt == 1:
                    logger.warning(
                        "%s: main stream failed, using substream fallback", self._camera_label
                    )
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                logger.info(
                    "%s: connected  %dx%d @ %.1ffps",
                    self._camera_label,
                    w,
                    h,
                    fps,
                )
                return cap
            cap.release()
        logger.error(
            "%s: unreachable on both main and substream — check network/credentials",
            self._camera_label,
        )
        return None

    def _run(self) -> None:
        cap = self._open_stream()
        if cap is None:
            return

        fps_times: deque[float] = deque(maxlen=30)
        consecutive_failures = 0
        frame_n = 0
        fps = 0.0

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

            # Skip inference when main thread hasn't consumed the previous result
            if self._result_queue.full():
                continue

            t0 = time.perf_counter()
            try:
                tracklets = self._tracker.update(frame)
                faces = self._detector.detect(frame)
            except Exception:
                logger.exception("%s: inference error on frame %d", self._camera_label, frame_n)
                continue
            latency_ms = (time.perf_counter() - t0) * 1000

            if tracklets and not self._first_detected:
                self._first_detected = True
                logger.info(
                    "First person detected on %s, track T:%d",
                    self._camera_label,
                    tracklets[0].local_track_id,
                )

            result = FrameResult(
                camera_label=self._camera_label,
                frame=frame,
                tracklets=list(tracklets),
                faces=list(faces),
                fps=fps,
                latency_ms=latency_ms,
                frame_n=frame_n,
            )
            try:
                self._result_queue.put_nowait(result)
            except queue.Full:
                pass

        cap.release()
        logger.info("%s: worker stopped", self._camera_label)


# ---------------------------------------------------------------------------
# Rendering helpers (main thread only)
# ---------------------------------------------------------------------------


def _track_color(track_id: int) -> tuple[int, int, int]:
    if track_id not in _TRACK_COLORS:
        hue = (track_id * 47 + 30) % 180
        hsv = np.array([[[hue, 210, 220]]], dtype=np.uint8)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
        _TRACK_COLORS[track_id] = (int(bgr[0]), int(bgr[1]), int(bgr[2]))
    return _TRACK_COLORS[track_id]


def _labeled_box(
    img: np.ndarray,
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


def _render_panel(result: FrameResult, panel_h: int) -> tuple[np.ndarray, int]:
    """Scale frame to panel_h, draw overlays. Returns (panel_bgr, person_count)."""
    h0, w0 = result.frame.shape[:2]
    panel_w = int(w0 * (panel_h / h0))
    panel = cv2.resize(result.frame, (panel_w, panel_h))
    sx = panel_w / w0
    sy = panel_h / h0

    # SCRFD face boxes (blue, thin) + confidence label
    scaled_face_centres: list[tuple[int, int, int, int]] = []
    for face in result.faces:
        fx1 = int(face.bbox[0] * sx)
        fy1 = int(face.bbox[1] * sy)
        fx2 = int(face.bbox[2] * sx)
        fy2 = int(face.bbox[3] * sy)
        scaled_face_centres.append((fx1, fy1, fx2, fy2))
        cv2.rectangle(panel, (fx1, fy1), (fx2, fy2), (255, 80, 0), 1)
        cv2.putText(
            panel,
            f"F:{face.confidence:.2f}",
            (fx1, max(fy1 - 3, 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 120, 0),
            1,
        )

    # Person boxes (per-track colour) + inner face box where face falls inside person
    for t in result.tracklets:
        px1 = int(t.bbox[0] * sx)
        py1 = int(t.bbox[1] * sy)
        px2 = int(t.bbox[2] * sx)
        py2 = int(t.bbox[3] * sy)
        _labeled_box(
            panel, px1, py1, px2, py2, f"T:{t.local_track_id}", _track_color(t.local_track_id)
        )

        # Blue inner box if face centre lies inside person bbox
        for fx1, fy1, fx2, fy2 in scaled_face_centres:
            fc_x = (fx1 + fx2) // 2
            fc_y = (fy1 + fy2) // 2
            if px1 <= fc_x <= px2 and py1 <= fc_y <= py2:
                cv2.rectangle(panel, (fx1, fy1), (fx2, fy2), (255, 180, 0), 2)

    # Semi-transparent head count overlay (top-left)
    count = len(result.tracklets)
    hud = f"{result.camera_label}  Persons: {count}"
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
) -> np.ndarray:
    bar = np.full((_STATS_BAR_H, total_w, 3), 30, dtype=np.uint8)

    def _text(r: FrameResult | None, prefix: str) -> str:
        if r is None:
            return f"{prefix}  waiting..."
        return f"{prefix}  {r.fps:.1f}fps  inf:{r.latency_ms:.0f}ms  frame:{r.frame_n}"

    cv2.putText(
        bar, _text(front, "CAM105"), (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1
    )
    cv2.putText(
        bar,
        _text(back, "CAM110"),
        (total_w // 2 + 8, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (180, 180, 180),
        1,
    )
    return bar


def _render_header(total_w: int, total_count: int) -> np.ndarray:
    header = np.full((_HEADER_H, total_w, 3), 20, dtype=np.uint8)
    text = f"PLANT TOTAL  Persons: {total_count}"
    (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
    x = max(0, (total_w - tw) // 2)
    cv2.putText(header, text, (x, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
    return header


def _save_snapshots(front: FrameResult | None, back: FrameResult | None) -> None:
    _SNAPSHOTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")
    for label, result in [("front", front), ("back", back)]:
        if result is not None:
            path = _SNAPSHOTS_DIR / f"gate_smoke_{ts}_{label}.jpg"
            cv2.imwrite(str(path), result.frame)
            logger.info("Snapshot saved: %s", path.name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="VMS two-camera gate entry smoke test")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Open streams, log info, process 5 frames, then exit without display",
    )
    parser.add_argument(
        "--panel-height",
        type=int,
        default=_PANEL_H_DEFAULT,
        metavar="PX",
        help="Display height per camera panel in pixels (default: 540)",
    )
    args = parser.parse_args()

    settings = get_settings()

    front_url = os.environ.get("VMS_CAM_GATE_FRONT_URL", "")
    back_url = os.environ.get("VMS_CAM_GATE_BACK_URL", "")
    if not front_url or not back_url:
        logger.error("VMS_CAM_GATE_FRONT_URL or VMS_CAM_GATE_BACK_URL not set — check .env")
        sys.exit(1)

    logger.info("Loading models (may take a few seconds)...")
    # Two separate detector instances so each worker thread owns its own ONNX session
    front_detector = SCRFDDetector.from_path(settings.scrfd_model)
    back_detector = SCRFDDetector.from_path(settings.scrfd_model)
    # Separate PerCameraTracker instances required: persist=True tracking state is per-instance
    front_tracker = PerCameraTracker.from_path(105, settings.yolov8x_pose_model)
    back_tracker = PerCameraTracker.from_path(110, settings.yolov8x_pose_model)
    logger.info("Models loaded.")

    front_worker = CameraWorker(105, "Front Gate", front_url, front_detector, front_tracker)
    back_worker = CameraWorker(110, "Back Gate", back_url, back_detector, back_tracker)

    front_worker.start()
    back_worker.start()

    front_result: FrameResult | None = None
    back_result: FrameResult | None = None
    dry_run_count = 0
    win_title = "VMS Gate Entry  [Q=quit  S=snapshot  R=reset colours]"

    try:
        while True:
            fr = front_worker.latest()
            br = back_worker.latest()
            if fr is not None:
                front_result = fr
            if br is not None:
                back_result = br

            # --- Dry-run mode: log frames, no display ---
            if args.dry_run:
                if fr is not None or br is not None:
                    dry_run_count += 1
                    logger.info(
                        "dry-run %d/5  front_frame=%s  back_frame=%s",
                        dry_run_count,
                        front_result.frame_n if front_result else "-",
                        back_result.frame_n if back_result else "-",
                    )
                if dry_run_count >= 5:
                    logger.info("dry-run complete — 5 frames processed, exiting")
                    break
                time.sleep(0.05)
                continue

            # --- Display mode ---
            if front_result is None and back_result is None:
                time.sleep(0.02)
                continue

            panel_h = args.panel_height
            placeholder_w = int(panel_h * 16 / 9)

            if front_result is not None:
                front_panel, front_count = _render_panel(front_result, panel_h)
            else:
                front_panel = np.zeros((panel_h, placeholder_w, 3), dtype=np.uint8)
                cv2.putText(
                    front_panel,
                    "Front Gate: waiting...",
                    (20, panel_h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (70, 70, 70),
                    1,
                )
                front_count = 0

            if back_result is not None:
                back_panel, back_count = _render_panel(back_result, panel_h)
            else:
                back_panel = np.zeros((panel_h, placeholder_w, 3), dtype=np.uint8)
                cv2.putText(
                    back_panel,
                    "Back Gate: waiting...",
                    (20, panel_h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (70, 70, 70),
                    1,
                )
                back_count = 0

            # Equalise panel widths if cameras have different aspect ratios
            fw, bw = front_panel.shape[1], back_panel.shape[1]
            if fw != bw:
                target_w = max(fw, bw)
                if fw < target_w:
                    pad = np.zeros((panel_h, target_w - fw, 3), dtype=np.uint8)
                    front_panel = np.hstack([front_panel, pad])
                else:
                    pad = np.zeros((panel_h, target_w - bw, 3), dtype=np.uint8)
                    back_panel = np.hstack([back_panel, pad])

            side_by_side = np.hstack([front_panel, back_panel])
            total_w = side_by_side.shape[1]

            header = _render_header(total_w, front_count + back_count)
            stats = _render_stats_bar(front_result, back_result, total_w)
            display = np.vstack([header, side_by_side, stats])

            # Vertical divider between panels
            mid_x = front_panel.shape[1]
            cv2.line(display, (mid_x, 0), (mid_x, display.shape[0]), (70, 70, 70), 1)

            cv2.imshow(win_title, display)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                logger.info("Quit key pressed")
                break
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
