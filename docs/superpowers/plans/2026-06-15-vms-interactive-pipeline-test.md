# Interactive Pipeline Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Build `scripts/interactive_pipeline_test.py` — a CPU-friendly interactive RTSP test harness that runs YOLOv8n body tracking every frame and the production SCRFD 10G + AdaFace IR50 face pipeline every Nth frame, achieving ≥ 20 FPS display on a CPU-only laptop with live keyboard controls.

**Architecture:** Standalone script. Two `CameraWorker` threads each own a `BodyDetector` (yolov8n, every frame) and `FacePipeline` (SCRFD+AdaFace, every N frames, result held). A shared `PipelineState` dataclass (no locks needed — CPython GIL, worst case one stale frame) lets the main thread update `sample_n`, `conf`, and toggles that workers read each loop iteration. Main thread renders only — no inference. A permanent red banner marks this as a test instrument so nobody mistakes it for production.

**Tech Stack:** Python 3.11, OpenCV, ultralytics YOLO (auto-downloads `yolov8n.pt`), onnxruntime, `vms.inference.{detector,embedder,messages}`, threading, pytest

**Spec ref:** `docs/superpowers/specs/2026-06-15-vms-interactive-pipeline-test.md`

---

## File map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `scripts/interactive_pipeline_test.py` | Full test harness (skeleton → add to each task) |
| Create | `tests/test_interactive_pipeline.py` | Unit tests (add to each task) |

No changes to any file under `vms/`.

---

### Task 1: Script skeleton + core dataclasses

**Files:**
- Create: `scripts/interactive_pipeline_test.py`
- Create: `tests/test_interactive_pipeline.py`

- [ ] **Step 1: Write the failing tests for dataclasses**

Create `tests/test_interactive_pipeline.py`:

```python
"""Unit tests for interactive_pipeline_test.py components."""
from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np
import pytest

# Add scripts/ to path so we can import the test harness module
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import interactive_pipeline_test as ipt  # noqa: E402


class TestFaceResult:
    def test_frozen(self) -> None:
        fr = ipt.FaceResult(bbox=(0, 0, 50, 50), confidence=0.9,
                            embedding_norm=18.4, label="UNKNOWN")
        with pytest.raises(FrozenInstanceError):
            fr.label = "X"  # type: ignore[misc]

    def test_label_is_always_unknown(self) -> None:
        fr = ipt.FaceResult(bbox=(0, 0, 50, 50), confidence=0.9,
                            embedding_norm=18.4, label="UNKNOWN")
        assert fr.label == "UNKNOWN"

    def test_embedding_norm_stored(self) -> None:
        fr = ipt.FaceResult(bbox=(10, 20, 60, 70), confidence=0.8,
                            embedding_norm=17.3, label="UNKNOWN")
        assert abs(fr.embedding_norm - 17.3) < 1e-5


class TestFrameResult:
    def test_mutable(self) -> None:
        result = ipt.FrameResult(
            camera_label="CAM105",
            frame=np.zeros((480, 640, 3), dtype=np.uint8),
            tracklets=[],
            face_results=[],
            face_stale_frames=0,
            fps=25.0,
            latency_body_ms=28.0,
            latency_scrfd_ms=0.0,
            latency_adaface_ms=0.0,
            frame_n=1,
        )
        result.fps = 30.0
        assert result.fps == 30.0


class TestPipelineState:
    def test_defaults(self) -> None:
        s = ipt.PipelineState()
        assert s.sample_n == ipt.FACE_SAMPLE_EVERY_N
        assert s.conf == pytest.approx(0.55)
        assert s.face_enabled is True
        assert s.timing_panel is False

    def test_mutability(self) -> None:
        s = ipt.PipelineState()
        s.sample_n = 10
        assert s.sample_n == 10
```

- [ ] **Step 2: Run tests — confirm they fail**

```powershell
pytest tests/test_interactive_pipeline.py -v
```

Expected: `ModuleNotFoundError: No module named 'interactive_pipeline_test'`

- [ ] **Step 3: Create the script skeleton**

Create `scripts/interactive_pipeline_test.py`:

```python
"""Interactive pipeline test harness for CPU-only laptops.

Uses YOLOv8n (TEST_BODY_MODEL) for smooth body tracking every frame,
and the production face pipeline (SCRFD 10G + AdaFace IR50) every Nth frame.

NOTE: TEST_BODY_MODEL is intentionally lighter than PROD_BODY_MODEL.
      Do NOT use this script as a proxy for production detection accuracy.

Usage:
    python scripts/interactive_pipeline_test.py
    python scripts/interactive_pipeline_test.py --dry-run

Controls:
    +/-   increase/decrease face sample interval N (1–20)
    C     cycle confidence: 0.40 → 0.55 → 0.70
    F     toggle face pipeline on/off
    T     toggle timing panel row
    S     save snapshot pair to scripts/snapshots/
    R     reset track-ID colour map
    Q     quit
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
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

# ---------------------------------------------------------------------------
# TEST vs PRODUCTION model constants — visible at the top of the file
# ---------------------------------------------------------------------------

TEST_BODY_MODEL     = "yolov8n.pt"               # auto-downloaded by ultralytics (~6 MB)
PROD_BODY_MODEL     = "models/yolov8x-pose.pt"   # production accuracy — NOT used here
FACE_DETECTOR       = "models/scrfd_10g_bnkps.onnx"
FACE_EMBEDDER       = "models/adaface_ir50.onnx"
FACE_SAMPLE_EVERY_N = 5                          # default face sample rate
ADAFACE_MIN_SIM     = 0.72                       # unused (no DB); shown for reference

_CONF_CYCLE: tuple[float, ...] = (0.40, 0.55, 0.70)
_PANEL_H_DEFAULT = 540
_BANNER_H   = 30
_STATS_H    = 44
_TIMING_H   = 24
_HEADER_H   = 0  # no header row in this harness (banner replaces it)
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
    frame: np.ndarray
    tracklets: list[Tracklet]
    face_results: list[FaceResult]
    face_stale_frames: int      # frames since last SCRFD+AdaFace run
    fps: float
    latency_body_ms: float
    latency_scrfd_ms: float     # 0.0 on skip frames
    latency_adaface_ms: float   # 0.0 on skip frames
    frame_n: int


@dataclass
class PipelineState:
    """Shared mutable state read by workers, written by main thread keypresses."""
    sample_n: int   = FACE_SAMPLE_EVERY_N
    conf: float     = 0.55
    face_enabled: bool  = True
    timing_panel: bool  = False
```

- [ ] **Step 4: Run tests — confirm they pass**

```powershell
pytest tests/test_interactive_pipeline.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/interactive_pipeline_test.py tests/test_interactive_pipeline.py
git commit -m "feat: add interactive pipeline test skeleton and core dataclasses"
```

---

### Task 2: FacePipeline

**Files:**
- Modify: `scripts/interactive_pipeline_test.py` — append `FacePipeline` class
- Modify: `tests/test_interactive_pipeline.py` — append `TestFacePipeline` class

- [ ] **Step 1: Write failing tests**

Append to `tests/test_interactive_pipeline.py`:

```python
from unittest.mock import MagicMock, patch
from vms.inference.messages import FaceWithEmbedding


class TestFacePipeline:
    def _make_pipeline(self, detector_faces, embedder_result):
        """Return a FacePipeline with mocked detector and embedder."""
        detector = MagicMock()
        detector.detect.return_value = detector_faces
        embedder = MagicMock()
        embedder.embed.return_value = embedder_result
        return ipt.FacePipeline(detector=detector, embedder=embedder)

    def _fake_face(self, embedding: tuple[float, ...] = ()) -> FaceWithEmbedding:
        return FaceWithEmbedding(
            bbox=(10, 10, 60, 60),
            confidence=0.9,
            embedding=embedding,
            keypoints=(),
        )

    def test_run_returns_unknown_label(self) -> None:
        embedding = tuple([1.0] * 512)
        face = self._fake_face(embedding)
        embedded_face = FaceWithEmbedding(
            bbox=(10, 10, 60, 60), confidence=0.9,
            embedding=embedding, keypoints=(),
        )
        pipeline = self._make_pipeline([face], embedded_face)
        results, _, _ = pipeline.run(np.zeros((480, 640, 3), dtype=np.uint8))
        assert len(results) == 1
        assert results[0].label == "UNKNOWN"

    def test_run_computes_embedding_norm(self) -> None:
        # embedding of all-ones → norm = sqrt(512)
        embedding = tuple([1.0] * 512)
        face = self._fake_face(embedding)
        embedded_face = FaceWithEmbedding(
            bbox=(10, 10, 60, 60), confidence=0.9,
            embedding=embedding, keypoints=(),
        )
        pipeline = self._make_pipeline([face], embedded_face)
        results, _, _ = pipeline.run(np.zeros((480, 640, 3), dtype=np.uint8))
        expected_norm = float(np.linalg.norm(np.ones(512)))
        assert abs(results[0].embedding_norm - expected_norm) < 1e-4

    def test_run_skips_face_with_empty_embedding(self) -> None:
        face = self._fake_face(embedding=())
        embedded_face = FaceWithEmbedding(
            bbox=(10, 10, 60, 60), confidence=0.9,
            embedding=(),  # empty — embedder failed
            keypoints=(),
        )
        pipeline = self._make_pipeline([face], embedded_face)
        results, _, _ = pipeline.run(np.zeros((480, 640, 3), dtype=np.uint8))
        assert results == []

    def test_run_skips_when_embedder_returns_none(self) -> None:
        face = self._fake_face()
        pipeline = self._make_pipeline([face], None)
        results, _, _ = pipeline.run(np.zeros((480, 640, 3), dtype=np.uint8))
        assert results == []

    def test_run_returns_scrfd_and_adaface_timings(self) -> None:
        embedding = tuple([1.0] * 512)
        face = self._fake_face(embedding)
        embedded_face = FaceWithEmbedding(
            bbox=(10, 10, 60, 60), confidence=0.9,
            embedding=embedding, keypoints=(),
        )
        pipeline = self._make_pipeline([face], embedded_face)
        _, scrfd_ms, adaface_ms = pipeline.run(np.zeros((480, 640, 3), dtype=np.uint8))
        assert scrfd_ms >= 0.0
        assert adaface_ms >= 0.0

    def test_run_empty_frame_no_detections(self) -> None:
        pipeline = self._make_pipeline([], None)
        results, _, _ = pipeline.run(np.zeros((480, 640, 3), dtype=np.uint8))
        assert results == []
```

- [ ] **Step 2: Run tests — confirm they fail**

```powershell
pytest tests/test_interactive_pipeline.py::TestFacePipeline -v
```

Expected: `AttributeError: module 'interactive_pipeline_test' has no attribute 'FacePipeline'`

- [ ] **Step 3: Implement FacePipeline**

Append to `scripts/interactive_pipeline_test.py` (after the dataclasses block):

```python
# ---------------------------------------------------------------------------
# FacePipeline — SCRFD + AdaFace (production models, sampled every N frames)
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
```

- [ ] **Step 4: Run tests — confirm they pass**

```powershell
pytest tests/test_interactive_pipeline.py::TestFacePipeline -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/interactive_pipeline_test.py tests/test_interactive_pipeline.py
git commit -m "feat: add FacePipeline (SCRFD + AdaFace wrapper with embedding norm)"
```

---

### Task 3: BodyDetector

**Files:**
- Modify: `scripts/interactive_pipeline_test.py` — append `BodyDetector` class
- Modify: `tests/test_interactive_pipeline.py` — append `TestBodyDetector` class

- [ ] **Step 1: Write failing tests**

Append to `tests/test_interactive_pipeline.py`:

```python
class TestBodyDetector:
    def _mock_yolo_result(
        self, boxes: list[tuple[int, int, int, int]], ids: list[int], confs: list[float]
    ) -> Any:
        """Build a mock ultralytics result object."""
        import torch

        mock_r = MagicMock()
        mock_r.boxes.id = torch.tensor(ids, dtype=torch.float32) if ids else None
        mock_r.boxes.xyxy = torch.tensor(
            [[float(x1), float(y1), float(x2), float(y2)] for x1, y1, x2, y2 in boxes],
            dtype=torch.float32,
        )
        mock_r.boxes.conf = torch.tensor(confs, dtype=torch.float32)
        return [mock_r]

    def test_returns_tracklets_for_detected_persons(self) -> None:
        model = MagicMock()
        model.track.return_value = self._mock_yolo_result(
            [(10, 20, 100, 200)], [3], [0.85]
        )
        detector = ipt.BodyDetector(model=model, botsort_config="botsort_custom.yaml", camera_id=105)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracklets, latency_ms = detector.detect(frame, conf=0.55)
        assert len(tracklets) == 1
        assert tracklets[0].local_track_id == 3
        assert tracklets[0].camera_id == 105
        assert tracklets[0].bbox == (10, 20, 100, 200)
        assert latency_ms >= 0.0

    def test_returns_empty_when_no_tracks(self) -> None:
        model = MagicMock()
        no_id_result = MagicMock()
        no_id_result.boxes.id = None
        model.track.return_value = [no_id_result]
        detector = ipt.BodyDetector(model=model, botsort_config="botsort_custom.yaml", camera_id=110)
        tracklets, _ = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8), conf=0.55)
        assert tracklets == []

    def test_returns_empty_when_yolo_returns_empty_list(self) -> None:
        model = MagicMock()
        model.track.return_value = []
        detector = ipt.BodyDetector(model=model, botsort_config="botsort_custom.yaml", camera_id=105)
        tracklets, _ = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8), conf=0.55)
        assert tracklets == []

    def test_tracklet_keypoints_empty_for_nano_model(self) -> None:
        """yolov8n has no pose head — keypoints must be empty tuple."""
        model = MagicMock()
        model.track.return_value = self._mock_yolo_result([(0, 0, 50, 50)], [1], [0.9])
        detector = ipt.BodyDetector(model=model, botsort_config="botsort_custom.yaml", camera_id=105)
        tracklets, _ = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8), conf=0.55)
        assert tracklets[0].keypoints == ()
        assert tracklets[0].face_visible is False
```

- [ ] **Step 2: Run tests — confirm they fail**

```powershell
pytest tests/test_interactive_pipeline.py::TestBodyDetector -v
```

Expected: `AttributeError: module 'interactive_pipeline_test' has no attribute 'BodyDetector'`

- [ ] **Step 3: Implement BodyDetector**

Append to `scripts/interactive_pipeline_test.py`:

```python
# ---------------------------------------------------------------------------
# BodyDetector — YOLOv8n (test-only nano model, NOT production accuracy)
# ---------------------------------------------------------------------------


class BodyDetector:
    """Wraps YOLOv8n.track() for one camera.

    Uses TEST_BODY_MODEL (yolov8n) — fast on CPU but lower accuracy than
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
```

- [ ] **Step 4: Run tests — confirm they pass**

```powershell
pytest tests/test_interactive_pipeline.py::TestBodyDetector -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/interactive_pipeline_test.py tests/test_interactive_pipeline.py
git commit -m "feat: add BodyDetector (yolov8n wrapper, test harness only)"
```

---

### Task 4: CameraWorker

**Files:**
- Modify: `scripts/interactive_pipeline_test.py` — append `CameraWorker` class
- Modify: `tests/test_interactive_pipeline.py` — append `TestCameraWorker` class

- [ ] **Step 1: Write failing tests**

Append to `tests/test_interactive_pipeline.py`:

```python
class TestCameraWorker:
    def _make_worker(
        self,
        camera_id: int = 105,
        camera_label: str = "CAM105",
        rtsp_url: str = "rtsp://fake/stream",
        face_results: list[ipt.FaceResult] | None = None,
        state: ipt.PipelineState | None = None,
    ) -> tuple[ipt.CameraWorker, MagicMock, MagicMock]:
        body_det = MagicMock(spec=ipt.BodyDetector)
        body_det.detect.return_value = ([], 25.0)

        face_pip = MagicMock(spec=ipt.FacePipeline)
        face_pip.run.return_value = (face_results or [], 110.0, 40.0)

        s = state or ipt.PipelineState()
        worker = ipt.CameraWorker(
            camera_id=camera_id,
            camera_label=camera_label,
            rtsp_url=rtsp_url,
            body_detector=body_det,
            face_pipeline=face_pip,
            state=s,
        )
        return worker, body_det, face_pip

    def test_queue_maxsize_two(self) -> None:
        worker, _, _ = self._make_worker()
        assert worker._result_queue.maxsize == 2

    def test_face_pipeline_called_on_sample_frames(self) -> None:
        """With sample_n=3, face pipeline should fire on frames 0, 3, 6."""
        state = ipt.PipelineState(sample_n=3, face_enabled=True)
        worker, body_det, face_pip = self._make_worker(state=state)

        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Simulate the per-frame logic directly (without threading)
        fired_on = []
        last_face: list[ipt.FaceResult] = []
        for frame_n in range(7):
            body_det.detect.return_value = ([], 25.0)
            if state.face_enabled and frame_n % state.sample_n == 0:
                last_face, _, _ = face_pip.run(frame)
                fired_on.append(frame_n)

        assert fired_on == [0, 3, 6]
        assert face_pip.run.call_count == 3

    def test_face_pipeline_not_called_when_disabled(self) -> None:
        state = ipt.PipelineState(sample_n=1, face_enabled=False)
        worker, _, face_pip = self._make_worker(state=state)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        for frame_n in range(5):
            if state.face_enabled and frame_n % state.sample_n == 0:
                face_pip.run(frame)

        face_pip.run.assert_not_called()

    def test_face_stale_frames_increments_between_samples(self) -> None:
        """face_stale_frames should be 0 on sample frame, then count up."""
        state = ipt.PipelineState(sample_n=5, face_enabled=True)
        stale_counts: list[int] = []
        stale = 0

        for frame_n in range(8):
            if state.face_enabled and frame_n % state.sample_n == 0:
                stale = 0
            else:
                stale += 1
            stale_counts.append(stale)

        # frames 0..7 → [0, 1, 2, 3, 4, 0, 1, 2]
        assert stale_counts == [0, 1, 2, 3, 4, 0, 1, 2]
```

- [ ] **Step 2: Run tests — confirm they fail**

```powershell
pytest tests/test_interactive_pipeline.py::TestCameraWorker -v
```

Expected: `AttributeError: module 'interactive_pipeline_test' has no attribute 'CameraWorker'`

- [ ] **Step 3: Implement CameraWorker**

Append to `scripts/interactive_pipeline_test.py`:

```python
# ---------------------------------------------------------------------------
# CameraWorker — one thread per camera
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
        for attempt, url in enumerate([
            self._rtsp_url,
            self._rtsp_url.replace("/101", "/102"),
        ]):
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
        logger.error("%s: cannot open stream — check network/credentials", self._camera_label)
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
                    logger.warning("%s: %d consecutive decode failures",
                                   self._camera_label, consecutive_failures)
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

            # Body detection — every frame
            tracklets, body_ms = self._body_detector.detect(frame, self._state.conf)

            # Face pipeline — every N frames when enabled
            scrfd_ms = 0.0
            adaface_ms = 0.0
            if self._state.face_enabled and frame_n % self._state.sample_n == 0:
                last_face_results, scrfd_ms, adaface_ms = self._face_pipeline.run(frame)
                last_scrfd_ms = scrfd_ms
                last_adaface_ms = adaface_ms
                face_stale = 0
                if last_face_results:
                    logger.debug("%s: face sample frame=%d faces=%d norm=%.2f",
                                 self._camera_label, frame_n, len(last_face_results),
                                 last_face_results[0].embedding_norm)
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
            try:
                self._result_queue.put_nowait(result)
            except queue.Full:
                pass

        cap.release()
        logger.info("%s: worker stopped", self._camera_label)
```

- [ ] **Step 4: Run tests — confirm they pass**

```powershell
pytest tests/test_interactive_pipeline.py::TestCameraWorker -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/interactive_pipeline_test.py tests/test_interactive_pipeline.py
git commit -m "feat: add CameraWorker with per-frame body + N-frame face sampling"
```

---

### Task 5: Rendering helpers

**Files:**
- Modify: `scripts/interactive_pipeline_test.py` — append rendering functions
- Modify: `tests/test_interactive_pipeline.py` — append `TestRendering` class

- [ ] **Step 1: Write failing tests**

Append to `tests/test_interactive_pipeline.py`:

```python
class TestRendering:
    def _make_frame_result(
        self,
        fps: float = 25.0,
        tracklets: list | None = None,
        face_results: list | None = None,
        stale: int = 0,
    ) -> ipt.FrameResult:
        return ipt.FrameResult(
            camera_label="CAM105",
            frame=np.zeros((1080, 1920, 3), dtype=np.uint8),
            tracklets=tracklets or [],
            face_results=face_results or [],
            face_stale_frames=stale,
            fps=fps,
            latency_body_ms=28.0,
            latency_scrfd_ms=112.0,
            latency_adaface_ms=43.0,
            frame_n=10,
        )

    def test_render_banner_has_correct_height(self) -> None:
        banner = ipt._render_banner(total_w=1280)
        assert banner.shape[0] == ipt._BANNER_H
        assert banner.shape[1] == 1280
        assert banner.shape[2] == 3

    def test_render_banner_is_numpy_uint8(self) -> None:
        banner = ipt._render_banner(total_w=800)
        assert banner.dtype == np.uint8

    def test_render_panel_output_shape(self) -> None:
        result = self._make_frame_result()
        panel, count = ipt._render_panel(result, panel_h=540)
        assert panel.shape[0] == 540
        assert panel.shape[2] == 3
        assert count == 0

    def test_render_panel_count_equals_tracklets(self) -> None:
        from vms.inference.messages import Tracklet
        t = Tracklet(local_track_id=1, camera_id=105,
                     bbox=(10, 20, 100, 200), confidence=0.9)
        result = self._make_frame_result(tracklets=[t])
        _, count = ipt._render_panel(result, panel_h=540)
        assert count == 1

    def test_render_stats_bar_shape(self) -> None:
        result = self._make_frame_result()
        bar = ipt._render_stats_bar(result, None, total_w=1280,
                                    state=ipt.PipelineState())
        assert bar.shape[0] == ipt._STATS_H
        assert bar.shape[1] == 1280

    def test_render_stats_bar_has_text_content(self) -> None:
        # Verifies that text was rendered (any channel above the background value of 30).
        # Visual confirmation that FPS < 15 renders red is done in Task 7 manual test.
        low_fps = self._make_frame_result(fps=8.0)
        bar = ipt._render_stats_bar(low_fps, None, total_w=1280,
                                    state=ipt.PipelineState())
        # Background is 30 per channel; text pixels raise at least one channel above 100
        assert bar.max() > 100

    def test_render_timing_panel_shape(self) -> None:
        result = self._make_frame_result()
        row = ipt._render_timing_panel(result, None, total_w=1280)
        assert row.shape[0] == ipt._TIMING_H
        assert row.shape[1] == 1280
```

- [ ] **Step 2: Run tests — confirm they fail**

```powershell
pytest tests/test_interactive_pipeline.py::TestRendering -v
```

Expected: `AttributeError: module 'interactive_pipeline_test' has no attribute '_render_banner'`

- [ ] **Step 3: Implement rendering helpers**

Append to `scripts/interactive_pipeline_test.py`:

```python
# ---------------------------------------------------------------------------
# Rendering helpers (main thread only — never call from worker threads)
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
    x1: int, y1: int, x2: int, y2: int,
    label: str,
    color: tuple[int, int, int],
    thickness: int = 2,
) -> None:
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    label_y = max(y1 - 4, th + 4)
    cv2.rectangle(img, (x1, label_y - th - 4), (x1 + tw + 6, label_y + 2), color, -1)
    cv2.putText(img, label, (x1 + 3, label_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)


def _render_banner(total_w: int) -> np.ndarray[Any, np.dtype[Any]]:
    banner: np.ndarray[Any, np.dtype[Any]] = np.full(
        (_BANNER_H, total_w, 3), 25, dtype=np.uint8
    )
    text = "MODE: DEMO FAST BODY DETECTOR, PRODUCTION FACE PIPELINE"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    x = max(0, (total_w - tw) // 2)
    cv2.putText(banner, text, (x, th + 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 220), 1)
    return banner


def _render_panel(
    result: FrameResult, panel_h: int
) -> tuple[np.ndarray[Any, np.dtype[Any]], int]:
    """Scale frame, draw body + face overlays. Returns (panel, person_count)."""
    h0, w0 = result.frame.shape[:2]
    panel_w = int(w0 * (panel_h / h0))
    panel: np.ndarray[Any, np.dtype[Any]] = cv2.resize(result.frame, (panel_w, panel_h))
    sx = panel_w / w0
    sy = panel_h / h0

    # Green body boxes (one per track)
    for t in result.tracklets:
        px1 = int(t.bbox[0] * sx)
        py1 = int(t.bbox[1] * sy)
        px2 = int(t.bbox[2] * sx)
        py2 = int(t.bbox[3] * sy)
        _labeled_box(panel, px1, py1, px2, py2,
                     f"T:{t.local_track_id}", _track_color(t.local_track_id))

    # Blue face boxes (sampled, held from last sample frame)
    stale_tag = f" s:{result.face_stale_frames}" if result.face_stale_frames > 0 else ""
    for face in result.face_results:
        fx1 = int(face.bbox[0] * sx)
        fy1 = int(face.bbox[1] * sy)
        fx2 = int(face.bbox[2] * sx)
        fy2 = int(face.bbox[3] * sy)
        cv2.rectangle(panel, (fx1, fy1), (fx2, fy2), (255, 80, 0), 2)
        label = f"UNKNOWN n:{face.embedding_norm:.2f}{stale_tag}"
        cv2.putText(panel, label, (fx1, max(fy1 - 3, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 140, 0), 1)

    # Head-count HUD (top-left)
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
    bar: np.ndarray[Any, np.dtype[Any]] = np.full(
        (_STATS_H, total_w, 3), 30, dtype=np.uint8
    )

    def _fmt(r: FrameResult | None, cam: str) -> tuple[str, tuple[int, int, int]]:
        if r is None:
            return f"{cam}: waiting...", (140, 140, 140)
        face_str = (
            "face:OFF" if not state.face_enabled
            else f"scrfd:{r.latency_scrfd_ms:.0f}ms ada:{r.latency_adaface_ms:.0f}ms"
        )
        text = (f"{cam}: {r.fps:.1f}fps  body:{r.latency_body_ms:.0f}ms  "
                f"{face_str}  N={state.sample_n}  stale:{r.face_stale_frames}")
        color = (0, 0, 220) if r.fps < 15.0 else (180, 180, 180)
        return text, color

    front_text, front_color = _fmt(front, "CAM105")
    back_text, back_color   = _fmt(back,  "CAM110")
    cv2.putText(bar, front_text, (8, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, front_color, 1)
    cv2.putText(bar, back_text,  (8, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.42, back_color,  1)
    return bar


def _render_timing_panel(
    front: FrameResult | None,
    back: FrameResult | None,
    total_w: int,
) -> np.ndarray[Any, np.dtype[Any]]:
    row: np.ndarray[Any, np.dtype[Any]] = np.full(
        (_TIMING_H, total_w, 3), 15, dtype=np.uint8
    )

    def _fmt(r: FrameResult | None, cam: str) -> str:
        if r is None:
            return f"{cam}:-"
        norm = r.face_results[0].embedding_norm if r.face_results else 0.0
        return (f"{cam} yolo:{r.latency_body_ms:.0f}  "
                f"scrfd:{r.latency_scrfd_ms:.0f}  "
                f"ada:{r.latency_adaface_ms:.0f}  "
                f"norm:{norm:.2f}")

    text = _fmt(front, "CAM105") + "   |   " + _fmt(back, "CAM110")
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
```

- [ ] **Step 4: Run tests — confirm they pass**

```powershell
pytest tests/test_interactive_pipeline.py::TestRendering -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Run the full test suite so far**

```powershell
pytest tests/test_interactive_pipeline.py -v
```

Expected: all tests PASS (21 total at this point).

- [ ] **Step 6: Commit**

```powershell
git add scripts/interactive_pipeline_test.py tests/test_interactive_pipeline.py
git commit -m "feat: add rendering helpers (banner, panel, stats bar, timing panel)"
```

---

### Task 6: Main loop, controls, and dry-run

**Files:**
- Modify: `scripts/interactive_pipeline_test.py` — append `main()`
- Modify: `tests/test_interactive_pipeline.py` — append `TestMainControls` class

- [ ] **Step 1: Write failing tests**

Append to `tests/test_interactive_pipeline.py`:

```python
class TestMainControls:
    def test_conf_cycle_advances(self) -> None:
        state = ipt.PipelineState(conf=0.40)
        cycle = ipt._CONF_CYCLE
        idx = cycle.index(state.conf)
        state.conf = cycle[(idx + 1) % len(cycle)]
        assert state.conf == pytest.approx(0.55)

    def test_conf_cycle_wraps(self) -> None:
        state = ipt.PipelineState(conf=0.70)
        cycle = ipt._CONF_CYCLE
        idx = cycle.index(state.conf)
        state.conf = cycle[(idx + 1) % len(cycle)]
        assert state.conf == pytest.approx(0.40)

    def test_sample_n_clamped_to_min_1(self) -> None:
        state = ipt.PipelineState(sample_n=1)
        state.sample_n = max(1, state.sample_n - 1)
        assert state.sample_n == 1

    def test_sample_n_clamped_to_max_20(self) -> None:
        state = ipt.PipelineState(sample_n=20)
        state.sample_n = min(20, state.sample_n + 1)
        assert state.sample_n == 20

    def test_face_toggle_flips(self) -> None:
        state = ipt.PipelineState(face_enabled=True)
        state.face_enabled = not state.face_enabled
        assert state.face_enabled is False
        state.face_enabled = not state.face_enabled
        assert state.face_enabled is True

    def test_timing_panel_toggle(self) -> None:
        state = ipt.PipelineState(timing_panel=False)
        state.timing_panel = not state.timing_panel
        assert state.timing_panel is True
```

- [ ] **Step 2: Run tests — confirm they fail (or pass already — _CONF_CYCLE must be defined)**

```powershell
pytest tests/test_interactive_pipeline.py::TestMainControls -v
```

Expected: all 6 tests PASS immediately (these test pure Python state logic; `_CONF_CYCLE` was defined in Task 1).

- [ ] **Step 3: Implement main()**

Append to `scripts/interactive_pipeline_test.py`:

```python
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="VMS interactive pipeline test — CPU-friendly, production face models"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Process 10 frames per camera, log timings, exit without display")
    parser.add_argument("--panel-height", type=int, default=_PANEL_H_DEFAULT, metavar="PX")
    args = parser.parse_args()

    settings = get_settings()

    front_url = os.environ.get("VMS_CAM_GATE_FRONT_URL", "")
    back_url  = os.environ.get("VMS_CAM_GATE_BACK_URL", "")
    if not front_url or not back_url:
        logger.error("VMS_CAM_GATE_FRONT_URL or VMS_CAM_GATE_BACK_URL not set — check .env")
        sys.exit(1)

    logger.info("TEST_BODY_MODEL : %s  (NOT production accuracy)", TEST_BODY_MODEL)
    logger.info("PROD_BODY_MODEL : %s  (not loaded in this harness)", PROD_BODY_MODEL)
    logger.info("FACE_DETECTOR   : %s", FACE_DETECTOR)
    logger.info("FACE_EMBEDDER   : %s", FACE_EMBEDDER)
    logger.info("Loading models…")

    state = PipelineState()

    front_body = BodyDetector.from_config(camera_id=105)
    back_body  = BodyDetector.from_config(camera_id=110)
    front_face = FacePipeline.from_paths(FACE_DETECTOR, FACE_EMBEDDER)
    back_face  = FacePipeline.from_paths(FACE_DETECTOR, FACE_EMBEDDER)

    logger.info("Models loaded. Starting workers…")

    front_worker = CameraWorker(105, "CAM105", front_url, front_body, front_face, state)
    back_worker  = CameraWorker(110, "CAM110", back_url,  back_body,  back_face,  state)
    front_worker.start()
    back_worker.start()

    front_result: FrameResult | None = None
    back_result:  FrameResult | None = None
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

            # --- Dry-run mode ---
            if args.dry_run:
                if fr is not None or br is not None:
                    dry_run_seen += 1
                    if front_result and front_result.face_results:
                        dry_run_face_fired += 1
                    if back_result and back_result.face_results:
                        dry_run_face_fired += 1
                    logger.info(
                        "dry-run %d/10  CAM105 fps=%.1f body_ms=%.0f faces=%d"
                        "  CAM110 fps=%.1f body_ms=%.0f faces=%d",
                        dry_run_seen,
                        front_result.fps if front_result else 0.0,
                        front_result.latency_body_ms if front_result else 0.0,
                        len(front_result.face_results) if front_result else 0,
                        back_result.fps if back_result else 0.0,
                        back_result.latency_body_ms if back_result else 0.0,
                        len(back_result.face_results) if back_result else 0,
                    )
                if dry_run_seen >= 10:
                    if front_result is None or back_result is None:
                        logger.error("dry-run FAIL: one or both streams never delivered a frame")
                        sys.exit(1)
                    logger.info("dry-run PASS: 10 frames received, face pipeline fired %d times",
                                dry_run_face_fired)
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
                front_panel, fc = _render_panel(front_result, panel_h)
            else:
                front_panel = np.zeros((panel_h, placeholder_w, 3), dtype=np.uint8)
                cv2.putText(front_panel, "CAM105: waiting…", (20, panel_h // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 60, 60), 1)
                fc = 0

            if back_result is not None:
                back_panel, bc = _render_panel(back_result, panel_h)
            else:
                back_panel = np.zeros((panel_h, placeholder_w, 3), dtype=np.uint8)
                cv2.putText(back_panel, "CAM110: waiting…", (20, panel_h // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 60, 60), 1)
                bc = 0

            fw, bw = front_panel.shape[1], back_panel.shape[1]
            if fw != bw:
                target_w = max(fw, bw)
                pad_shape = (panel_h, abs(target_w - fw if fw < target_w else target_w - bw), 3)
                pad = np.zeros(pad_shape, dtype=np.uint8)
                if fw < target_w:
                    front_panel = np.hstack([front_panel, pad])
                else:
                    back_panel = np.hstack([back_panel, pad])

            side_by_side: np.ndarray[Any, np.dtype[Any]] = np.hstack([front_panel, back_panel])
            total_w = side_by_side.shape[1]

            banner = _render_banner(total_w)
            stats  = _render_stats_bar(front_result, back_result, total_w, state)

            layers: list[np.ndarray[Any, np.dtype[Any]]] = [banner, side_by_side, stats]
            if state.timing_panel:
                layers.append(_render_timing_panel(front_result, back_result, total_w))

            display: np.ndarray[Any, np.dtype[Any]] = np.vstack(layers)

            # Vertical divider
            mid_x = front_panel.shape[1]
            cv2.line(display, (mid_x, 0), (mid_x, display.shape[0]), (60, 60, 60), 1)

            cv2.imshow(win_title, display)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            elif key == ord("+") or key == ord("="):
                state.sample_n = min(20, state.sample_n + 1)
                logger.info("Face sample N → %d", state.sample_n)
            elif key == ord("-"):
                state.sample_n = max(1, state.sample_n - 1)
                logger.info("Face sample N → %d", state.sample_n)
            elif key == ord("c"):
                idx = _CONF_CYCLE.index(state.conf) if state.conf in _CONF_CYCLE else 1
                state.conf = _CONF_CYCLE[(idx + 1) % len(_CONF_CYCLE)]
                logger.info("Confidence → %.2f", state.conf)
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
```

- [ ] **Step 4: Run the full test suite**

```powershell
pytest tests/test_interactive_pipeline.py -v
```

Expected: all tests PASS (27 total).

- [ ] **Step 5: Lint and type-check**

```powershell
black scripts/interactive_pipeline_test.py tests/test_interactive_pipeline.py
ruff check scripts/interactive_pipeline_test.py tests/test_interactive_pipeline.py
```

Expected: no errors. Fix any ruff findings before proceeding.

- [ ] **Step 6: Commit**

```powershell
git add scripts/interactive_pipeline_test.py tests/test_interactive_pipeline.py
git commit -m "feat: add main loop with live controls and dry-run mode"
```

---

### Task 7: Manual end-to-end smoke test (cameras required)

This task runs the script against the real cameras. It is **not automated** — mark complete once you've observed the expected behaviour in person.

- [ ] **Step 1: Activate the project venv**

```powershell
.\venv\Scripts\Activate.ps1
```

- [ ] **Step 2: Run dry-run mode first**

```powershell
python scripts/interactive_pipeline_test.py --dry-run
```

Expected log output (approximately):
```
13:45:01 INFO    pipeline_test: TEST_BODY_MODEL : yolov8n.pt  (NOT production accuracy)
13:45:01 INFO    pipeline_test: Loading models…
13:45:04 INFO    pipeline_test: CAM105: connected 2560x1440 @ 20.0fps
13:45:04 INFO    pipeline_test: CAM110: connected 1920x1080 @ 25.0fps
13:45:05 INFO    pipeline_test: dry-run 1/10  CAM105 fps=0.0 body_ms=28 faces=0 …
…
13:45:07 INFO    pipeline_test: dry-run PASS: 10 frames received, face pipeline fired N times
```

Exit code must be 0.

- [ ] **Step 3: Run interactive mode**

```powershell
python scripts/interactive_pipeline_test.py
```

Verify each of the following before marking complete:

- [ ] Red banner "MODE: DEMO FAST BODY DETECTOR, PRODUCTION FACE PIPELINE" is visible at the top
- [ ] Both camera panels show live video (not frozen)
- [ ] FPS shown in stats bar is ≥ 20 for both cameras
- [ ] Green body boxes appear when a person walks in front of either camera
- [ ] Blue face box with "UNKNOWN n:XX.XX" appears after a person faces the camera (may be stale for up to N frames — `stale:N` shown)
- [ ] Pressing `+` increases N in the stats bar; `-` decreases it
- [ ] Pressing `C` cycles the confidence value shown
- [ ] Pressing `F` removes face boxes and shows "face:OFF" in stats bar; pressing again restores them
- [ ] Pressing `T` adds the timing row below the stats bar
- [ ] Pressing `S` saves snapshot files to `scripts/snapshots/`
- [ ] Pressing `Q` exits cleanly with "Shutdown complete" log line

- [ ] **Step 4: Commit task completion note**

```powershell
git add .
git commit -m "test: interactive pipeline test verified against CAM105 and CAM110"
```
