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
import logging
import os
import queue  # noqa: F401
import sys
import threading  # noqa: F401
import time
from collections import deque  # noqa: F401
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

import cv2  # noqa: F401
import numpy as np

from vms.config import get_settings  # noqa: F401
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

    def run(
        self, frame: np.ndarray[Any, np.dtype[Any]]
    ) -> tuple[list[FaceResult], float, float]:
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
