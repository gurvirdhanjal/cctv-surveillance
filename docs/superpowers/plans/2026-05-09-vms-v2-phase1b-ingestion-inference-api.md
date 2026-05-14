# VMS v2 Phase 1B — Ingestion, Inference, and Base API

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE** (Tasks 1–10 done, 96 tests passing, commit `019e45e`)

**Goal:** Wire the RTSP/webcam frame pipeline end-to-end — camera capture through shared memory and Redis Streams to SCRFD + AdaFace + YOLOv8n + ByteTrack inference — and expose a minimal FastAPI surface (health + person enrollment + JWT auth).

**Architecture:** Four process types communicate over Redis Streams. Ingestion workers decode RTSP/webcam frames into POSIX shared memory and publish 24-byte pointer events to `frames:group{N}` streams. The GPU inference engine reads pointer events, runs the model stack (SCRFD face detect → AdaFace embed → YOLO+ByteTrack person track), and publishes `DetectionFrame` events serialised as JSON to the `detections` stream. The DB writer batch-inserts `tracking_events` from that stream. A FastAPI process serves health, enrollment, and JWT auth. Every process reads config from `vms.config.get_settings()`.

**Tech Stack:** Python 3.10.11 · SQLAlchemy 2.x · FastAPI 0.111 · redis-py 5.0 (asyncio) · fakeredis 2.x (tests only) · onnxruntime-gpu 1.18 · ultralytics 8.2 (YOLOv8n + ByteTrack) · OpenCV 4.9 · numpy 1.26 · python-jose 3.3 · bcrypt 4.1 · pytest 8.x · httpx 0.27

**Spec refs:**
- v1 §3 Architecture · §4 Shared Memory Safety · §5 Backpressure · §6 Inference Pipeline · §11 API Design
- v2 §C Anomaly framework trigger-gated model pools
- `vms/config.py` — all thresholds and paths pre-defined

---

## File Map

```
vms/
├── redis_client.py              # get_redis(), stream_add(), stream_read(), stream_ack()
├── ingestion/
│   ├── __init__.py
│   ├── messages.py              # FramePointer frozen dataclass + to/from Redis fields
│   ├── shm.py                   # SHMSlot: 16-byte header + BGR frame bytes; staleness guard
│   └── worker.py                # IngestionWorker: camera → SHM → stream_add
├── inference/
│   ├── __init__.py
│   ├── messages.py              # Tracklet, FaceWithEmbedding, DetectionFrame + JSON serde
│   ├── detector.py              # SCRFDDetector: ONNX 2.5g face detection + NMS
│   ├── embedder.py              # AdaFaceEmbedder: ONNX IR50 → 512-dim float32
│   ├── tracker.py               # PerCameraTracker: ultralytics YOLO + ByteTrack
│   └── engine.py                # InferenceEngine: reads frames stream → publishes detections
├── writer/
│   ├── __init__.py
│   └── db_writer.py             # DBWriter: reads detections → batch upsert tracking_events
└── api/
    ├── __init__.py
    ├── main.py                  # FastAPI app + lifespan
    ├── deps.py                  # get_db, get_current_user (JWT), create_access_token
    ├── schemas.py               # Pydantic request/response models
    └── routes/
        ├── __init__.py
        ├── health.py            # GET /api/health
        └── persons.py           # POST /api/persons · POST /api/persons/{id}/embeddings · GET /api/persons/search

tests/
├── test_redis_client.py         # stream helpers — fakeredis
├── test_ingestion_shm.py        # SHMSlot write/read/stale
├── test_ingestion_messages.py   # FramePointer round-trip
├── test_ingestion_worker.py     # IngestionWorker — mock camera + fakeredis
├── test_inference_messages.py   # DetectionFrame JSON round-trip
├── test_inference_detector.py   # SCRFDDetector — mock ort.InferenceSession
├── test_inference_embedder.py   # AdaFaceEmbedder — mock ort.InferenceSession
├── test_inference_tracker.py    # PerCameraTracker — mock YOLO model
├── test_inference_engine.py     # InferenceEngine — all models mocked + fakeredis
├── test_writer_db_writer.py     # DBWriter — real test PostgreSQL
├── test_api_health.py           # GET /api/health
├── test_api_deps.py             # JWT create/validate
└── test_api_persons.py          # Enrollment endpoints — real test PostgreSQL
```

**Existing files unchanged:** `vms/config.py`, `vms/db/`, `alembic/`, `tests/conftest.py`

---

## Pre-flight checks

- [ ] **Step 0.1: Add fakeredis to dev dependencies**

Append to `requirements-dev.txt`:
```
fakeredis[aioredis]==2.23.2
```

Install:
```powershell
pip install fakeredis[aioredis]==2.23.2
```

- [ ] **Step 0.2: Confirm test PostgreSQL is still running**
```powershell
docker exec vms-test-db pg_isready -U vms -d vms_test
```
Expected: `/var/run/postgresql:5432 - accepting connections`

- [ ] **Step 0.3: Confirm 57 existing tests still pass**
```powershell
python -m pytest tests/ -q
```
Expected: `57 passed`

---

## Task 1: Redis Stream Client

**Files:**
- Create: `vms/redis_client.py`
- Create: `tests/test_redis_client.py`

- [ ] **Step 1.1: Write failing tests**

```python
# tests/test_redis_client.py
from __future__ import annotations

import pytest
import fakeredis.aioredis as fake_aioredis

from vms.redis_client import stream_add, stream_read, stream_ack


@pytest.fixture
def fake_redis() -> fake_aioredis.FakeRedis:
    return fake_aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_stream_add_returns_string_id(fake_redis: fake_aioredis.FakeRedis) -> None:
    msg_id = await stream_add(fake_redis, "test:s", {"k": "v"})
    assert isinstance(msg_id, str)
    assert "-" in msg_id  # Redis stream ID format: <ms>-<seq>


@pytest.mark.asyncio
async def test_stream_read_returns_added_message(fake_redis: fake_aioredis.FakeRedis) -> None:
    await stream_add(fake_redis, "test:s", {"data": "hello"})
    messages = await stream_read(fake_redis, "test:s", last_id="0-0")
    assert len(messages) == 1
    _msg_id, fields = messages[0]
    assert fields["data"] == "hello"


@pytest.mark.asyncio
async def test_stream_read_empty_stream_returns_empty_list(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    messages = await stream_read(fake_redis, "empty:s", last_id="0-0", block_ms=10)
    assert messages == []


@pytest.mark.asyncio
async def test_stream_ack_succeeds_for_valid_group(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    await fake_redis.xgroup_create("ack:s", "grp", id="0", mkstream=True)
    msg_id = await stream_add(fake_redis, "ack:s", {"k": "v"})
    # Should not raise
    await stream_ack(fake_redis, "ack:s", "grp", msg_id)
```

- [ ] **Step 1.2: Run tests — expect ImportError**
```powershell
python -m pytest tests/test_redis_client.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.redis_client'`

- [ ] **Step 1.3: Implement `vms/redis_client.py`**

```python
"""Redis connection and Stream helpers."""

from __future__ import annotations

import redis.asyncio as aioredis

from vms.config import get_settings


def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    """Return a Redis client using VMS_REDIS_URL."""
    return aioredis.from_url(get_settings().redis_url, decode_responses=True)


async def stream_add(
    client: aioredis.Redis,  # type: ignore[type-arg]
    stream: str,
    fields: dict[str, str],
    maxlen: int | None = None,
) -> str:
    """XADD with MAXLEN cap. Returns the new message ID."""
    if maxlen is None:
        maxlen = get_settings().redis_stream_maxlen
    result: str = await client.xadd(stream, fields, maxlen=maxlen)
    return result


async def stream_read(
    client: aioredis.Redis,  # type: ignore[type-arg]
    stream: str,
    last_id: str = "$",
    count: int = 100,
    block_ms: int = 100,
) -> list[tuple[str, dict[str, str]]]:
    """Blocking XREAD. Returns list of (message_id, fields) pairs."""
    raw = await client.xread({stream: last_id}, count=count, block=block_ms)
    if not raw:
        return []
    _, messages = raw[0]
    return [(msg_id, dict(fields)) for msg_id, fields in messages]


async def stream_ack(
    client: aioredis.Redis,  # type: ignore[type-arg]
    stream: str,
    group: str,
    msg_id: str,
) -> None:
    """XACK a processed message in the given consumer group."""
    await client.xack(stream, group, msg_id)
```

- [ ] **Step 1.4: Run tests — expect 4 passed**
```powershell
python -m pytest tests/test_redis_client.py -v
```
Expected: `4 passed`

- [ ] **Step 1.5: Lint + type-check**
```powershell
ruff check vms/redis_client.py tests/test_redis_client.py
mypy vms/redis_client.py
```

- [ ] **Step 1.6: Commit**
```powershell
git add vms/redis_client.py tests/test_redis_client.py requirements-dev.txt
git commit -m "feat(redis): add stream_add/stream_read/stream_ack helpers"
```

---

## Task 2: SHM Slot + FramePointer Message

**Files:**
- Create: `vms/ingestion/__init__.py`
- Create: `vms/ingestion/messages.py`
- Create: `vms/ingestion/shm.py`
- Create: `tests/test_ingestion_shm.py`
- Create: `tests/test_ingestion_messages.py`

- [ ] **Step 2.1: Write failing tests for FramePointer**

```python
# tests/test_ingestion_messages.py
from __future__ import annotations

from vms.ingestion.messages import FramePointer


def test_frame_pointer_round_trips_through_redis_fields() -> None:
    fp = FramePointer(cam_id=3, shm_name="vms_cam_3", seq_id=99, timestamp_ms=12345, width=1920, height=1080)
    fields = fp.to_redis_fields()
    recovered = FramePointer.from_redis_fields(fields)
    assert recovered == fp


def test_frame_pointer_is_immutable() -> None:
    fp = FramePointer(cam_id=1, shm_name="x", seq_id=0, timestamp_ms=0, width=640, height=480)
    try:
        fp.cam_id = 99  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except Exception:
        pass
```

- [ ] **Step 2.2: Write failing tests for SHMSlot**

```python
# tests/test_ingestion_shm.py
from __future__ import annotations

import struct
import time
from unittest.mock import patch

import numpy as np
import pytest

from vms.ingestion.shm import SHMSlot, _HEADER_FMT, _HEADER_SIZE


@pytest.fixture
def slot() -> SHMSlot:
    s = SHMSlot.create("vms_test_slot_task2", width=64, height=48)
    yield s
    try:
        s.close()
        s.unlink()
    except Exception:
        pass


def test_shm_slot_write_then_read_returns_frame(slot: SHMSlot) -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    frame[10, 20] = [100, 150, 200]
    slot.write(frame, seq_id=1)
    result = slot.read()
    assert result is not None
    out_frame, seq_id, _ts = result
    assert out_frame.shape == (48, 64, 3)
    assert list(out_frame[10, 20]) == [100, 150, 200]
    assert seq_id == 1


def test_shm_slot_read_returns_none_when_stale(slot: SHMSlot) -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    slot.write(frame, seq_id=1)
    real_now = time.monotonic()
    # Simulate time advancing 1 second past write — well beyond 200ms threshold
    with patch("vms.ingestion.shm.time") as mock_time:
        mock_time.monotonic.return_value = real_now + 1.0
        result = slot.read()
    assert result is None


def test_shm_slot_seq_id_is_preserved(slot: SHMSlot) -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    slot.write(frame, seq_id=42)
    result = slot.read()
    assert result is not None
    _, seq_id, _ = result
    assert seq_id == 42
```

- [ ] **Step 2.3: Run tests — expect ImportError**
```powershell
python -m pytest tests/test_ingestion_messages.py tests/test_ingestion_shm.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.ingestion'`

- [ ] **Step 2.4: Create `vms/ingestion/__init__.py`**
```python
"""Ingestion layer: camera capture, shared memory, Redis Stream publishing."""
```

- [ ] **Step 2.5: Implement `vms/ingestion/messages.py`**

```python
"""Inter-process message types for the ingestion layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FramePointer:
    """Lightweight Redis Stream payload pointing to a frame in shared memory."""

    cam_id: int
    shm_name: str
    seq_id: int
    timestamp_ms: int
    width: int
    height: int

    def to_redis_fields(self) -> dict[str, str]:
        return {
            "cam_id": str(self.cam_id),
            "shm_name": self.shm_name,
            "seq_id": str(self.seq_id),
            "timestamp_ms": str(self.timestamp_ms),
            "width": str(self.width),
            "height": str(self.height),
        }

    @classmethod
    def from_redis_fields(cls, fields: dict[str, str]) -> FramePointer:
        return cls(
            cam_id=int(fields["cam_id"]),
            shm_name=fields["shm_name"],
            seq_id=int(fields["seq_id"]),
            timestamp_ms=int(fields["timestamp_ms"]),
            width=int(fields["width"]),
            height=int(fields["height"]),
        )
```

- [ ] **Step 2.6: Implement `vms/ingestion/shm.py`**

```python
"""Shared memory slot for single-camera frame exchange between processes.

Layout: first 16 bytes = header (seq_id: uint64 LE, timestamp_ms: uint64 LE),
followed by raw BGR frame bytes (height * width * 3).
"""

from __future__ import annotations

import struct
import time
from multiprocessing.shared_memory import SharedMemory

import numpy as np

from vms.config import get_settings

_HEADER_SIZE = 16
_HEADER_FMT = "<QQ"  # little-endian: seq_id (uint64) + timestamp_ms (uint64)


class SHMSlot:
    """One shared memory region for one camera frame."""

    def __init__(self, name: str, width: int, height: int) -> None:
        self.name = name
        self.width = width
        self.height = height
        self._frame_bytes = width * height * 3
        self._shm = SharedMemory(name=name, create=False)

    @classmethod
    def create(cls, name: str, width: int, height: int) -> SHMSlot:
        """Allocate a new SHM segment. Caller owns cleanup via close() + unlink()."""
        total = _HEADER_SIZE + width * height * 3
        shm = SharedMemory(name=name, create=True, size=total)
        shm.close()
        return cls(name, width, height)

    def write(self, frame: np.ndarray, seq_id: int) -> int:
        """Write BGR frame and header. Returns the timestamp_ms recorded."""
        ts_ms = int(time.monotonic() * 1000)
        self._shm.buf[:_HEADER_SIZE] = struct.pack(_HEADER_FMT, seq_id, ts_ms)
        raw = frame.tobytes()
        self._shm.buf[_HEADER_SIZE : _HEADER_SIZE + len(raw)] = raw
        return ts_ms

    def read(self) -> tuple[np.ndarray, int, int] | None:
        """Read frame. Returns (frame_bgr, seq_id, timestamp_ms) or None if stale."""
        seq_id, timestamp_ms = struct.unpack(_HEADER_FMT, bytes(self._shm.buf[:_HEADER_SIZE]))
        now_ms = int(time.monotonic() * 1000)
        if now_ms - timestamp_ms > get_settings().stale_threshold_ms:
            return None
        raw = bytes(self._shm.buf[_HEADER_SIZE : _HEADER_SIZE + self._frame_bytes])
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(self.height, self.width, 3).copy()
        return frame, seq_id, timestamp_ms

    def close(self) -> None:
        self._shm.close()

    def unlink(self) -> None:
        self._shm.unlink()
```

- [ ] **Step 2.7: Run tests — expect 5 passed**
```powershell
python -m pytest tests/test_ingestion_messages.py tests/test_ingestion_shm.py -v
```
Expected: `5 passed`

- [ ] **Step 2.8: Lint + type-check**
```powershell
ruff check vms/ingestion/ tests/test_ingestion_messages.py tests/test_ingestion_shm.py
mypy vms/ingestion/messages.py vms/ingestion/shm.py
```

- [ ] **Step 2.9: Commit**
```powershell
git add vms/ingestion/ tests/test_ingestion_messages.py tests/test_ingestion_shm.py
git commit -m "feat(ingestion): add SHMSlot and FramePointer message"
```

---

## Task 3: Ingestion Worker

**Files:**
- Create: `vms/ingestion/worker.py`
- Create: `tests/test_ingestion_worker.py`

- [ ] **Step 3.1: Write failing tests**

```python
# tests/test_ingestion_worker.py
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from vms.ingestion.messages import FramePointer
from vms.ingestion.worker import CameraConfig, IngestionWorker


@pytest.fixture
def camera_cfg() -> CameraConfig:
    return CameraConfig(camera_id=1, rtsp_url="0", worker_group=1, width=64, height=48)


@pytest.fixture
def fake_redis() -> AsyncMock:
    return AsyncMock()


def _make_mock_cap(frame: np.ndarray, read_ok: bool = True) -> MagicMock:
    cap = MagicMock()
    cap.read.return_value = (read_ok, frame)
    cap.release = MagicMock()
    return cap


@pytest.mark.asyncio
async def test_ingestion_worker_publishes_frame_pointer(
    camera_cfg: CameraConfig, fake_redis: AsyncMock
) -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    mock_cap = _make_mock_cap(frame)

    published: list[FramePointer] = []

    async def capture_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        published.append(FramePointer.from_redis_fields(fields))
        # Stop after first successful publish
        worker._running = False
        return "1-0"

    worker = IngestionWorker(camera_cfg, fake_redis)

    with (
        patch("vms.ingestion.worker.cv2.VideoCapture", return_value=mock_cap),
        patch("vms.ingestion.worker.stream_add", side_effect=capture_stream_add),
        patch("vms.ingestion.worker.SHMSlot.create") as mock_create,
    ):
        mock_slot = MagicMock()
        mock_slot.name = "vms_cam_1"
        mock_slot.write.return_value = 1000
        mock_create.return_value = mock_slot
        await worker.start()

    assert len(published) == 1
    assert published[0].cam_id == 1
    assert published[0].shm_name == "vms_cam_1"
    assert published[0].width == 64
    assert published[0].height == 48


@pytest.mark.asyncio
async def test_ingestion_worker_skips_failed_read(
    camera_cfg: CameraConfig, fake_redis: AsyncMock
) -> None:
    bad_frame = np.zeros((48, 64, 3), dtype=np.uint8)
    call_count = 0

    async def capture_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        worker._running = False
        return "1-0"

    def mock_read():  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (False, bad_frame)  # first read fails
        return (True, bad_frame)

    mock_cap = MagicMock()
    mock_cap.read.side_effect = mock_read
    mock_cap.release = MagicMock()

    worker = IngestionWorker(camera_cfg, fake_redis)

    with (
        patch("vms.ingestion.worker.cv2.VideoCapture", return_value=mock_cap),
        patch("vms.ingestion.worker.stream_add", side_effect=capture_stream_add),
        patch("vms.ingestion.worker.SHMSlot.create") as mock_create,
    ):
        mock_slot = MagicMock()
        mock_slot.name = "vms_cam_1"
        mock_slot.write.return_value = 1000
        mock_create.return_value = mock_slot
        await worker.start()

    assert call_count >= 2  # retried after failed read
```

- [ ] **Step 3.2: Run tests — expect ImportError**
```powershell
python -m pytest tests/test_ingestion_worker.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.ingestion.worker'`

- [ ] **Step 3.3: Implement `vms/ingestion/worker.py`**

```python
"""Ingestion worker: camera → shared memory → Redis Stream."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import cv2
import redis.asyncio as aioredis

from vms.ingestion.messages import FramePointer
from vms.ingestion.shm import SHMSlot
from vms.redis_client import stream_add

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    camera_id: int
    rtsp_url: str
    worker_group: int
    width: int = 1920
    height: int = 1080


class IngestionWorker:
    """Reads frames from one camera, writes to SHM, publishes FramePointer to Redis."""

    def __init__(self, camera: CameraConfig, redis_client: aioredis.Redis) -> None:  # type: ignore[type-arg]
        self._camera = camera
        self._redis = redis_client
        self._seq_id = 0
        self._running = False
        self._slot: SHMSlot | None = None

    async def start(self) -> None:
        shm_name = f"vms_cam_{self._camera.camera_id}"
        self._slot = SHMSlot.create(shm_name, self._camera.width, self._camera.height)
        self._running = True
        try:
            await self._capture_loop()
        finally:
            if self._slot:
                self._slot.close()
                self._slot.unlink()

    async def stop(self) -> None:
        self._running = False

    async def _capture_loop(self) -> None:
        cap = cv2.VideoCapture(self._camera.rtsp_url)
        stream_name = f"frames:group{self._camera.worker_group}"
        try:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    logger.warning("camera_id=%d frame read failed", self._camera.camera_id)
                    await asyncio.sleep(0.1)
                    continue
                if frame.shape[:2] != (self._camera.height, self._camera.width):
                    frame = cv2.resize(frame, (self._camera.width, self._camera.height))
                assert self._slot is not None
                ts_ms = self._slot.write(frame, self._seq_id)
                pointer = FramePointer(
                    cam_id=self._camera.camera_id,
                    shm_name=self._slot.name,
                    seq_id=self._seq_id,
                    timestamp_ms=ts_ms,
                    width=self._camera.width,
                    height=self._camera.height,
                )
                await stream_add(self._redis, stream_name, pointer.to_redis_fields())
                self._seq_id += 1
                await asyncio.sleep(0)  # yield to event loop
        finally:
            cap.release()
```

- [ ] **Step 3.4: Run tests — expect 2 passed**
```powershell
python -m pytest tests/test_ingestion_worker.py -v
```
Expected: `2 passed`

- [ ] **Step 3.5: Lint + type-check**
```powershell
ruff check vms/ingestion/worker.py tests/test_ingestion_worker.py
mypy vms/ingestion/worker.py
```

- [ ] **Step 3.6: Commit**
```powershell
git add vms/ingestion/worker.py tests/test_ingestion_worker.py
git commit -m "feat(ingestion): add IngestionWorker camera capture loop"
```

---

## Task 4: Inference DTOs

**Files:**
- Create: `vms/inference/__init__.py`
- Create: `vms/inference/messages.py`
- Create: `tests/test_inference_messages.py`

- [ ] **Step 4.1: Write failing tests**

```python
# tests/test_inference_messages.py
from __future__ import annotations

import json

import numpy as np

from vms.inference.messages import DetectionFrame, FaceWithEmbedding, Tracklet


def test_tracklet_is_immutable() -> None:
    t = Tracklet(local_track_id=1, camera_id=2, bbox=(0, 0, 100, 200), confidence=0.9)
    try:
        t.local_track_id = 99  # type: ignore[misc]
        assert False, "FrozenInstanceError expected"
    except Exception:
        pass


def test_face_with_embedding_stores_512_floats() -> None:
    emb = tuple(float(x) for x in np.random.randn(512).astype(np.float32))
    face = FaceWithEmbedding(bbox=(10, 20, 50, 80), confidence=0.75, embedding=emb)
    assert len(face.embedding) == 512


def test_detection_frame_json_round_trip() -> None:
    emb = tuple(0.1 for _ in range(512))
    frame = DetectionFrame(
        camera_id=5,
        seq_id=100,
        timestamp_ms=999000,
        tracklets=(Tracklet(local_track_id=1, camera_id=5, bbox=(0, 0, 100, 200), confidence=0.8),),
        face_embeddings=(FaceWithEmbedding(bbox=(10, 10, 50, 60), confidence=0.9, embedding=emb),),
    )
    payload = frame.to_redis_fields()
    assert payload["camera_id"] == "5"
    recovered = DetectionFrame.from_redis_fields(payload)
    assert recovered.camera_id == 5
    assert recovered.seq_id == 100
    assert len(recovered.tracklets) == 1
    assert recovered.tracklets[0].local_track_id == 1
    assert len(recovered.face_embeddings) == 1
    assert len(recovered.face_embeddings[0].embedding) == 512


def test_detection_frame_with_no_detections() -> None:
    frame = DetectionFrame(
        camera_id=1, seq_id=0, timestamp_ms=0, tracklets=(), face_embeddings=()
    )
    recovered = DetectionFrame.from_redis_fields(frame.to_redis_fields())
    assert recovered.tracklets == ()
    assert recovered.face_embeddings == ()
```

- [ ] **Step 4.2: Run tests — expect ImportError**
```powershell
python -m pytest tests/test_inference_messages.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.inference'`

- [ ] **Step 4.3: Create `vms/inference/__init__.py`**
```python
"""Inference layer: SCRFD face detection, AdaFace embedding, YOLO+ByteTrack tracking."""
```

- [ ] **Step 4.4: Implement `vms/inference/messages.py`**

```python
"""Inter-process message types for the inference layer."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Tracklet:
    """One ByteTrack-confirmed person tracklet from a single camera."""

    local_track_id: int
    camera_id: int
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float


@dataclass(frozen=True)
class FaceWithEmbedding:
    """Face detection with 512-dim AdaFace embedding."""

    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in original frame coords
    confidence: float
    embedding: tuple[float, ...]  # 512 float32 values


@dataclass(frozen=True)
class DetectionFrame:
    """All detections for one camera frame, published to the 'detections' Redis stream."""

    camera_id: int
    seq_id: int
    timestamp_ms: int
    tracklets: tuple[Tracklet, ...]
    face_embeddings: tuple[FaceWithEmbedding, ...]

    def to_redis_fields(self) -> dict[str, str]:
        tracklets_json = json.dumps(
            [
                {
                    "local_track_id": t.local_track_id,
                    "camera_id": t.camera_id,
                    "bbox": list(t.bbox),
                    "confidence": t.confidence,
                }
                for t in self.tracklets
            ]
        )
        faces_json = json.dumps(
            [
                {
                    "bbox": list(f.bbox),
                    "confidence": f.confidence,
                    "embedding": list(f.embedding),
                }
                for f in self.face_embeddings
            ]
        )
        return {
            "camera_id": str(self.camera_id),
            "seq_id": str(self.seq_id),
            "timestamp_ms": str(self.timestamp_ms),
            "tracklets": tracklets_json,
            "face_embeddings": faces_json,
        }

    @classmethod
    def from_redis_fields(cls, fields: dict[str, str]) -> DetectionFrame:
        raw_tracklets: list[dict[str, object]] = json.loads(fields["tracklets"])
        raw_faces: list[dict[str, object]] = json.loads(fields["face_embeddings"])

        tracklets = tuple(
            Tracklet(
                local_track_id=int(t["local_track_id"]),  # type: ignore[arg-type]
                camera_id=int(t["camera_id"]),  # type: ignore[arg-type]
                bbox=tuple(int(v) for v in t["bbox"]),  # type: ignore[arg-type]
                confidence=float(t["confidence"]),  # type: ignore[arg-type]
            )
            for t in raw_tracklets
        )
        face_embeddings = tuple(
            FaceWithEmbedding(
                bbox=tuple(int(v) for v in f["bbox"]),  # type: ignore[arg-type]
                confidence=float(f["confidence"]),  # type: ignore[arg-type]
                embedding=tuple(float(v) for v in f["embedding"]),  # type: ignore[arg-type]
            )
            for f in raw_faces
        )
        return cls(
            camera_id=int(fields["camera_id"]),
            seq_id=int(fields["seq_id"]),
            timestamp_ms=int(fields["timestamp_ms"]),
            tracklets=tracklets,
            face_embeddings=face_embeddings,
        )
```

- [ ] **Step 4.5: Run tests — expect 4 passed**
```powershell
python -m pytest tests/test_inference_messages.py -v
```
Expected: `4 passed`

- [ ] **Step 4.6: Lint + type-check**
```powershell
ruff check vms/inference/ tests/test_inference_messages.py
mypy vms/inference/messages.py
```

- [ ] **Step 4.7: Commit**
```powershell
git add vms/inference/ tests/test_inference_messages.py
git commit -m "feat(inference): add Tracklet, FaceWithEmbedding, DetectionFrame DTOs"
```

---

## Task 5: SCRFD Face Detector

**Files:**
- Create: `vms/inference/detector.py`
- Create: `tests/test_inference_detector.py`

SCRFD 2.5g ONNX produces 6 outputs for a 640×640 input:
- `outputs[0..2]`: class confidence tensors for strides 8, 16, 32 — shapes `(12800,1)`, `(3200,1)`, `(800,1)`
- `outputs[3..5]`: bbox regression tensors for strides 8, 16, 32 — shapes `(12800,4)`, `(3200,4)`, `(800,4)`

Preprocessing: resize to 640×640, convert BGR→RGB, normalise `(pixel − 127.5) / 128.0`, transpose to `(1,3,640,640)`.

- [ ] **Step 5.1: Write failing tests**

```python
# tests/test_inference_detector.py
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from vms.inference.detector import SCRFDDetector


def _make_mock_session(
    conf_value: float = 0.9, n_stride8: int = 12800
) -> MagicMock:
    """Build a mock ort.InferenceSession that returns one high-confidence detection."""
    sess = MagicMock()
    sess.get_inputs.return_value = [MagicMock(name="input.1")]
    # stride-8 output: one anchor at grid cell (40,40) has high confidence
    cls8 = np.zeros((n_stride8, 1), dtype=np.float32)
    # anchor index for cell (40,40) with 2 anchors/cell = (40*80 + 40)*2 = 6480
    cls8[6480, 0] = 4.0  # sigmoid(4.0) ≈ 0.98, well above 0.6 threshold
    bbox8 = np.zeros((n_stride8, 4), dtype=np.float32)
    bbox8[6480] = [5.0, 5.0, 5.0, 5.0]  # 40px box in stride-8 space

    cls16 = np.zeros((3200, 1), dtype=np.float32)
    bbox16 = np.zeros((3200, 4), dtype=np.float32)
    cls32 = np.zeros((800, 1), dtype=np.float32)
    bbox32 = np.zeros((800, 4), dtype=np.float32)

    sess.run.return_value = [cls8, cls16, cls32, bbox8, bbox16, bbox32]
    return sess


def test_scrfd_detector_returns_face_detections() -> None:
    sess = _make_mock_session()
    detector = SCRFDDetector(session=sess)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    detections = detector.detect(frame)
    assert len(detections) >= 1
    x1, y1, x2, y2 = detections[0].bbox
    assert x2 > x1 and y2 > y1
    assert 0.0 < detections[0].confidence <= 1.0


def test_scrfd_detector_returns_empty_for_blank_output() -> None:
    sess = MagicMock()
    sess.get_inputs.return_value = [MagicMock(name="input.1")]
    # All zeros — no detections above threshold
    sess.run.return_value = [
        np.zeros((12800, 1), dtype=np.float32),
        np.zeros((3200, 1), dtype=np.float32),
        np.zeros((800, 1), dtype=np.float32),
        np.zeros((12800, 4), dtype=np.float32),
        np.zeros((3200, 4), dtype=np.float32),
        np.zeros((800, 4), dtype=np.float32),
    ]
    detector = SCRFDDetector(session=sess)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    assert detector.detect(frame) == []


def test_scrfd_detector_filters_below_min_face_px() -> None:
    sess = _make_mock_session()
    detector = SCRFDDetector(session=sess, min_face_px=1000)  # impossibly large
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert detector.detect(frame) == []
```

- [ ] **Step 5.2: Run tests — expect ImportError**
```powershell
python -m pytest tests/test_inference_detector.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.inference.detector'`

- [ ] **Step 5.3: Implement `vms/inference/detector.py`**

```python
"""SCRFD 2.5g face detector (ONNX).

Input:  (1, 3, 640, 640) float32, normalised (pixel - 127.5) / 128.0
Outputs: [cls_s8, cls_s16, cls_s32, bbox_s8, bbox_s16, bbox_s32]
         cls shapes: (N, 1)  where N = H/stride * W/stride * 2 anchors
         bbox shapes: (N, 4) ltrb in stride units
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort

from vms.config import get_settings
from vms.inference.messages import FaceWithEmbedding

logger = logging.getLogger(__name__)

_INPUT_SIZE = 640
_STRIDES = [8, 16, 32]
_ANCHORS_PER_CELL = 2


class SCRFDDetector:
    """Wraps SCRFD 2.5g ONNX model for face detection."""

    def __init__(
        self,
        session: ort.InferenceSession,
        conf_thres: float | None = None,
        nms_thres: float = 0.35,
        min_face_px: int | None = None,
    ) -> None:
        self._sess = session
        self._input_name: str = session.get_inputs()[0].name
        self._conf_thres = conf_thres if conf_thres is not None else get_settings().scrfd_conf
        self._nms_thres = nms_thres
        self._min_face_px = min_face_px if min_face_px is not None else get_settings().min_face_px

    @classmethod
    def from_path(cls, model_path: str) -> SCRFDDetector:
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        sess = ort.InferenceSession(model_path, providers=providers)
        return cls(session=sess)

    def detect(self, frame_bgr: np.ndarray) -> list[FaceWithEmbedding]:
        """Run detection on a BGR frame. Returns list of FaceWithEmbedding (no embedding set)."""
        h0, w0 = frame_bgr.shape[:2]
        blob = self._preprocess(frame_bgr)
        outputs: list[Any] = self._sess.run(None, {self._input_name: blob})
        return self._decode(outputs, h0, w0)

    def _preprocess(self, img: np.ndarray) -> np.ndarray:
        resized = cv2.resize(img, (_INPUT_SIZE, _INPUT_SIZE))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
        rgb = (rgb - 127.5) / 128.0
        return np.transpose(rgb, (2, 0, 1))[None]

    def _decode(
        self, outputs: list[Any], h0: int, w0: int
    ) -> list[FaceWithEmbedding]:
        cls_outputs = outputs[0:3]
        bbox_outputs = outputs[3:6]

        boxes_all: list[np.ndarray] = []
        scores_all: list[np.ndarray] = []

        for cls_out, bbox_out, stride in zip(cls_outputs, bbox_outputs, _STRIDES):
            n = cls_out.shape[0]
            side = _INPUT_SIZE // stride
            hw = side * side
            if n != hw * _ANCHORS_PER_CELL:
                continue

            scores: np.ndarray = 1.0 / (1.0 + np.exp(-cls_out[:, 0]))
            keep = scores > self._conf_thres
            if not np.any(keep):
                continue

            scores = scores[keep]
            bbox = bbox_out[keep]

            ys, xs = np.meshgrid(np.arange(side), np.arange(side), indexing="ij")
            centers = np.stack([xs.ravel(), ys.ravel()], axis=1)
            centers = np.repeat(centers, _ANCHORS_PER_CELL, axis=0)
            centers = centers[keep] * stride

            x1 = centers[:, 0] - bbox[:, 0] * stride
            y1 = centers[:, 1] - bbox[:, 1] * stride
            x2 = centers[:, 0] + bbox[:, 2] * stride
            y2 = centers[:, 1] + bbox[:, 3] * stride

            boxes_all.append(np.stack([x1, y1, x2, y2], axis=1))
            scores_all.append(scores)

        if not boxes_all:
            return []

        boxes = np.concatenate(boxes_all)
        scores_arr = np.concatenate(scores_all)

        boxes[:, [0, 2]] *= w0 / _INPUT_SIZE
        boxes[:, [1, 3]] *= h0 / _INPUT_SIZE

        boxes_xywh = [
            [float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])]
            for b in boxes
        ]
        idxs = cv2.dnn.NMSBoxes(boxes_xywh, scores_arr.tolist(), self._conf_thres, self._nms_thres)
        if len(idxs) == 0:
            return []

        results: list[FaceWithEmbedding] = []
        for i in idxs.flatten():
            x1, y1, x2, y2 = int(boxes[i, 0]), int(boxes[i, 1]), int(boxes[i, 2]), int(boxes[i, 3])
            if (x2 - x1) < self._min_face_px or (y2 - y1) < self._min_face_px:
                continue
            results.append(
                FaceWithEmbedding(
                    bbox=(x1, y1, x2, y2),
                    confidence=float(scores_arr[i]),
                    embedding=(),  # filled in by AdaFaceEmbedder
                )
            )
        return results
```

- [ ] **Step 5.4: Run tests — expect 3 passed**
```powershell
python -m pytest tests/test_inference_detector.py -v
```
Expected: `3 passed`

- [ ] **Step 5.5: Lint + type-check**
```powershell
ruff check vms/inference/detector.py tests/test_inference_detector.py
mypy vms/inference/detector.py
```

- [ ] **Step 5.6: Commit**
```powershell
git add vms/inference/detector.py tests/test_inference_detector.py
git commit -m "feat(inference): add SCRFDDetector ONNX wrapper"
```

---

## Task 6: AdaFace Embedder

**Files:**
- Create: `vms/inference/embedder.py`
- Create: `tests/test_inference_embedder.py`

AdaFace IR50: input `(1,3,112,112)` float32 normalised `(pixel-127.5)/128`, output `(1,512)` float32.

- [ ] **Step 6.1: Write failing tests**

```python
# tests/test_inference_embedder.py
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from vms.inference.embedder import AdaFaceEmbedder
from vms.inference.messages import FaceWithEmbedding


def _make_mock_session() -> MagicMock:
    sess = MagicMock()
    embedding = np.random.randn(1, 512).astype(np.float32)
    sess.run.return_value = [embedding]
    return sess


def test_adaface_embedder_returns_512_dim_embedding() -> None:
    sess = _make_mock_session()
    embedder = AdaFaceEmbedder(session=sess)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    face = FaceWithEmbedding(bbox=(10, 10, 100, 100), confidence=0.9, embedding=())
    result = embedder.embed(face, frame)
    assert len(result.embedding) == 512
    assert result.bbox == face.bbox
    assert result.confidence == face.confidence


def test_adaface_embedder_returns_none_for_empty_crop() -> None:
    sess = _make_mock_session()
    embedder = AdaFaceEmbedder(session=sess)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # bbox outside frame bounds → empty crop
    face = FaceWithEmbedding(bbox=(200, 200, 300, 300), confidence=0.9, embedding=())
    result = embedder.embed(face, frame)
    assert result is None


def test_adaface_embedder_skips_small_face() -> None:
    sess = _make_mock_session()
    embedder = AdaFaceEmbedder(session=sess, min_face_px=100)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    face = FaceWithEmbedding(bbox=(10, 10, 50, 50), confidence=0.9, embedding=())  # 40px face
    result = embedder.embed(face, frame)
    assert result is None
    sess.run.assert_not_called()
```

- [ ] **Step 6.2: Run tests — expect ImportError**
```powershell
python -m pytest tests/test_inference_embedder.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.inference.embedder'`

- [ ] **Step 6.3: Implement `vms/inference/embedder.py`**

```python
"""AdaFace IR50 face embedder (ONNX).

Input:  (1, 3, 112, 112) float32, normalised (pixel - 127.5) / 128.0, RGB
Output: (1, 512) float32 L2-normalised embedding
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort

from vms.config import get_settings
from vms.inference.messages import FaceWithEmbedding

logger = logging.getLogger(__name__)

_EMBED_INPUT_NAME = "input"


class AdaFaceEmbedder:
    """Wraps AdaFace IR50 ONNX model for 512-dim face embedding."""

    def __init__(
        self,
        session: ort.InferenceSession,
        min_face_px: int | None = None,
    ) -> None:
        self._sess = session
        self._min_face_px = min_face_px if min_face_px is not None else get_settings().min_face_px

    @classmethod
    def from_path(cls, model_path: str) -> AdaFaceEmbedder:
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        sess = ort.InferenceSession(model_path, providers=providers)
        return cls(session=sess)

    def embed(
        self, face: FaceWithEmbedding, frame_bgr: np.ndarray
    ) -> FaceWithEmbedding | None:
        """Crop the face from frame and compute its embedding.

        Returns updated FaceWithEmbedding with embedding filled in,
        or None if the crop is empty or below min_face_px.
        """
        x1, y1, x2, y2 = face.bbox
        crop = frame_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        if (x2 - x1) < self._min_face_px or (y2 - y1) < self._min_face_px:
            return None

        blob = self._preprocess(crop)
        raw: list[Any] = self._sess.run(None, {_EMBED_INPUT_NAME: blob})
        emb_array: np.ndarray = raw[0][0].astype(np.float32)
        embedding = tuple(float(v) for v in emb_array)
        return FaceWithEmbedding(
            bbox=face.bbox,
            confidence=face.confidence,
            embedding=embedding,
        )

    def _preprocess(self, face_bgr: np.ndarray) -> np.ndarray:
        face = cv2.resize(face_bgr, (112, 112))
        face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB).astype(np.float32)
        face = (face - 127.5) / 128.0
        return np.transpose(face, (2, 0, 1))[None]
```

- [ ] **Step 6.4: Run tests — expect 3 passed**
```powershell
python -m pytest tests/test_inference_embedder.py -v
```
Expected: `3 passed`

- [ ] **Step 6.5: Lint + type-check**
```powershell
ruff check vms/inference/embedder.py tests/test_inference_embedder.py
mypy vms/inference/embedder.py
```

- [ ] **Step 6.6: Commit**
```powershell
git add vms/inference/embedder.py tests/test_inference_embedder.py
git commit -m "feat(inference): add AdaFaceEmbedder ONNX wrapper"
```

---

## Task 7: YOLO + ByteTrack Person Tracker

**Files:**
- Create: `vms/inference/tracker.py`
- Create: `tests/test_inference_tracker.py`

`PerCameraTracker` wraps `ultralytics.YOLO.track()` — this performs both YOLOv8n person detection and ByteTrack tracking in one call, matching the legacy `scrfd_face.py` pattern.

- [ ] **Step 7.1: Write failing tests**

```python
# tests/test_inference_tracker.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vms.inference.messages import Tracklet
from vms.inference.tracker import PerCameraTracker


def _make_mock_yolo_result(
    boxes_xyxy: list[list[float]], track_ids: list[int], confs: list[float]
) -> MagicMock:
    result = MagicMock()
    if track_ids:
        result.boxes.id = np.array(track_ids, dtype=np.float32)
        result.boxes.xyxy = np.array(boxes_xyxy, dtype=np.float32)
        result.boxes.conf = np.array(confs, dtype=np.float32)
    else:
        result.boxes.id = None
        result.boxes.xyxy = np.empty((0, 4))
        result.boxes.conf = np.empty((0,))
    return result


@pytest.fixture
def tracker() -> PerCameraTracker:
    mock_model = MagicMock()
    return PerCameraTracker(camera_id=1, model=mock_model)


def test_tracker_returns_tracklets_for_detected_persons(
    tracker: PerCameraTracker,
) -> None:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_result = _make_mock_yolo_result(
        boxes_xyxy=[[10.0, 20.0, 100.0, 200.0]],
        track_ids=[5],
        confs=[0.85],
    )
    tracker._model.track.return_value = [mock_result]

    tracklets = tracker.update(frame)
    assert len(tracklets) == 1
    assert tracklets[0].local_track_id == 5
    assert tracklets[0].camera_id == 1
    assert tracklets[0].bbox == (10, 20, 100, 200)
    assert abs(tracklets[0].confidence - 0.85) < 1e-4


def test_tracker_returns_empty_when_no_persons(tracker: PerCameraTracker) -> None:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_result = _make_mock_yolo_result([], [], [])
    tracker._model.track.return_value = [mock_result]
    assert tracker.update(frame) == []


def test_tracker_returns_empty_when_track_ids_none(tracker: PerCameraTracker) -> None:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = MagicMock()
    result.boxes.id = None
    tracker._model.track.return_value = [result]
    assert tracker.update(frame) == []
```

- [ ] **Step 7.2: Run tests — expect ImportError**
```powershell
python -m pytest tests/test_inference_tracker.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.inference.tracker'`

- [ ] **Step 7.3: Implement `vms/inference/tracker.py`**

```python
"""Per-camera person tracker using ultralytics YOLOv8n + ByteTrack."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from vms.config import get_settings
from vms.inference.messages import Tracklet

logger = logging.getLogger(__name__)


class PerCameraTracker:
    """Wraps ultralytics YOLO.track() for one camera, yielding stable local_track_id values."""

    def __init__(self, camera_id: int, model: Any) -> None:
        self.camera_id = camera_id
        self._model = model

    @classmethod
    def from_path(cls, camera_id: int, model_path: str) -> PerCameraTracker:
        from ultralytics import YOLO  # imported lazily — not available in test env without GPU
        return cls(camera_id=camera_id, model=YOLO(model_path))

    def update(self, frame_bgr: np.ndarray) -> list[Tracklet]:
        """Run detection + tracking on one frame. Returns confirmed tracklets."""
        settings = get_settings()
        results = self._model.track(
            frame_bgr,
            conf=settings.scrfd_conf,
            persist=True,
            tracker=settings.bytetrack_config,
            verbose=False,
        )
        if not results:
            return []
        boxes = results[0].boxes
        if boxes.id is None:
            return []

        tracklets: list[Tracklet] = []
        for bbox_arr, tid, conf in zip(boxes.xyxy, boxes.id, boxes.conf):
            x1, y1, x2, y2 = (int(v) for v in bbox_arr)
            tracklets.append(
                Tracklet(
                    local_track_id=int(tid),
                    camera_id=self.camera_id,
                    bbox=(x1, y1, x2, y2),
                    confidence=float(conf),
                )
            )
        return tracklets
```

- [ ] **Step 7.4: Run tests — expect 3 passed**
```powershell
python -m pytest tests/test_inference_tracker.py -v
```
Expected: `3 passed`

- [ ] **Step 7.5: Lint + type-check**
```powershell
ruff check vms/inference/tracker.py tests/test_inference_tracker.py
mypy vms/inference/tracker.py
```

- [ ] **Step 7.6: Commit**
```powershell
git add vms/inference/tracker.py tests/test_inference_tracker.py
git commit -m "feat(inference): add PerCameraTracker YOLO+ByteTrack wrapper"
```

---

## Task 8: Inference Engine

**Files:**
- Create: `vms/inference/engine.py`
- Create: `tests/test_inference_engine.py`

The engine reads from `frames:group{N}` streams, reads the SHM slot, runs SCRFD + AdaFace + Tracker, and publishes a `DetectionFrame` to the `detections` stream. Stale frames and frames below `min_blur` are skipped.

- [ ] **Step 8.1: Write failing tests**

```python
# tests/test_inference_engine.py
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import fakeredis.aioredis as fake_aioredis

from vms.inference.engine import InferenceEngine
from vms.inference.messages import DetectionFrame, FaceWithEmbedding, Tracklet
from vms.ingestion.messages import FramePointer


@pytest.fixture
def fake_redis() -> fake_aioredis.FakeRedis:
    return fake_aioredis.FakeRedis(decode_responses=True)


def _make_engine(fake_redis: fake_aioredis.FakeRedis) -> InferenceEngine:
    detector = MagicMock()
    detector.detect.return_value = []
    embedder = MagicMock()
    tracker = MagicMock()
    tracker.update.return_value = []
    return InferenceEngine(
        camera_ids=[1],
        worker_group=1,
        detector=detector,
        embedder=embedder,
        trackers={1: tracker},
        redis_client=fake_redis,
    )


@pytest.mark.asyncio
async def test_engine_publishes_detection_frame_to_detections_stream(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    engine = _make_engine(fake_redis)

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    pointer = FramePointer(cam_id=1, shm_name="vms_cam_1", seq_id=0, timestamp_ms=1000, width=640, height=480)

    mock_slot = MagicMock()
    mock_slot.read.return_value = (frame, 0, 1000)

    published: list[dict[str, str]] = []

    async def fake_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        published.append({"stream": stream, **fields})
        engine._running = False
        return "1-0"

    with (
        patch("vms.inference.engine.SHMSlot", return_value=mock_slot),
        patch("vms.inference.engine.stream_add", side_effect=fake_stream_add),
        patch("vms.inference.engine.stream_read", return_value=[("1-0", pointer.to_redis_fields())]),
    ):
        await engine._process_one_message("1-0", pointer.to_redis_fields())

    assert len(published) == 1
    assert published[0]["stream"] == "detections"
    frame_data = DetectionFrame.from_redis_fields(published[0])
    assert frame_data.camera_id == 1
    assert frame_data.seq_id == 0


@pytest.mark.asyncio
async def test_engine_skips_stale_frame(fake_redis: fake_aioredis.FakeRedis) -> None:
    engine = _make_engine(fake_redis)
    pointer = FramePointer(cam_id=1, shm_name="vms_cam_1", seq_id=0, timestamp_ms=1000, width=640, height=480)

    mock_slot = MagicMock()
    mock_slot.read.return_value = None  # stale

    published: list[dict[str, str]] = []

    async def fake_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        published.append(fields)
        return "1-0"

    with (
        patch("vms.inference.engine.SHMSlot", return_value=mock_slot),
        patch("vms.inference.engine.stream_add", side_effect=fake_stream_add),
    ):
        await engine._process_one_message("1-0", pointer.to_redis_fields())

    assert published == []  # nothing published for stale frame
```

- [ ] **Step 8.2: Run tests — expect ImportError**
```powershell
python -m pytest tests/test_inference_engine.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.inference.engine'`

- [ ] **Step 8.3: Implement `vms/inference/engine.py`**

```python
"""Inference engine: reads frames stream → SCRFD + AdaFace + Tracker → detections stream."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np
import redis.asyncio as aioredis

from vms.inference.detector import SCRFDDetector
from vms.inference.embedder import AdaFaceEmbedder
from vms.inference.messages import DetectionFrame
from vms.inference.tracker import PerCameraTracker
from vms.ingestion.messages import FramePointer
from vms.ingestion.shm import SHMSlot
from vms.redis_client import stream_add, stream_read

logger = logging.getLogger(__name__)

_DETECTIONS_STREAM = "detections"


class InferenceEngine:
    """Reads from frames:group{N} streams, runs model stack, publishes DetectionFrame."""

    def __init__(
        self,
        camera_ids: list[int],
        worker_group: int,
        detector: SCRFDDetector,
        embedder: AdaFaceEmbedder,
        trackers: dict[int, PerCameraTracker],
        redis_client: aioredis.Redis,  # type: ignore[type-arg]
    ) -> None:
        self._camera_ids = camera_ids
        self._stream_name = f"frames:group{worker_group}"
        self._detector = detector
        self._embedder = embedder
        self._trackers = trackers
        self._redis = redis_client
        self._running = False
        self._last_id = "0-0"

    async def run(self) -> None:
        self._running = True
        while self._running:
            messages = await stream_read(
                self._redis, self._stream_name, last_id=self._last_id, count=10
            )
            for msg_id, fields in messages:
                await self._process_one_message(msg_id, fields)
                self._last_id = msg_id
            if not messages:
                await asyncio.sleep(0.01)

    async def stop(self) -> None:
        self._running = False

    async def _process_one_message(self, msg_id: str, fields: dict[str, str]) -> None:
        pointer = FramePointer.from_redis_fields(fields)
        slot = SHMSlot(name=pointer.shm_name, width=pointer.width, height=pointer.height)
        frame_result = slot.read()
        if frame_result is None:
            logger.debug("camera_id=%d seq=%d stale — skipped", pointer.cam_id, pointer.seq_id)
            return

        frame_bgr, seq_id, timestamp_ms = frame_result

        # Face detection + embedding (gated pool — only on faces above min_blur)
        raw_faces = self._detector.detect(frame_bgr)
        face_embeddings = []
        for face in raw_faces:
            with_emb = self._embedder.embed(face, frame_bgr)
            if with_emb is not None:
                face_embeddings.append(with_emb)

        # Person tracking
        tracker = self._trackers.get(pointer.cam_id)
        tracklets = tracker.update(frame_bgr) if tracker else []

        detection_frame = DetectionFrame(
            camera_id=pointer.cam_id,
            seq_id=seq_id,
            timestamp_ms=timestamp_ms,
            tracklets=tuple(tracklets),
            face_embeddings=tuple(face_embeddings),
        )
        await stream_add(self._redis, _DETECTIONS_STREAM, detection_frame.to_redis_fields())
```

- [ ] **Step 8.4: Run tests — expect 2 passed**
```powershell
python -m pytest tests/test_inference_engine.py -v
```
Expected: `2 passed`

- [ ] **Step 8.5: Lint + type-check**
```powershell
ruff check vms/inference/engine.py tests/test_inference_engine.py
mypy vms/inference/engine.py
```

- [ ] **Step 8.6: Commit**
```powershell
git add vms/inference/engine.py tests/test_inference_engine.py
git commit -m "feat(inference): add InferenceEngine stream reader + model orchestration"
```

---

## Task 9: FastAPI App, Health, Auth, and Person Enrollment

**Files:**
- Create: `vms/api/__init__.py`
- Create: `vms/api/main.py`
- Create: `vms/api/deps.py`
- Create: `vms/api/schemas.py`
- Create: `vms/api/routes/__init__.py`
- Create: `vms/api/routes/health.py`
- Create: `vms/api/routes/persons.py`
- Create: `tests/test_api_health.py`
- Create: `tests/test_api_deps.py`
- Create: `tests/test_api_persons.py`

- [ ] **Step 9.1: Write failing tests for health**

```python
# tests/test_api_health.py
from __future__ import annotations

import pytest
from httpx import AsyncClient

from vms.api.main import app


@pytest.mark.asyncio
async def test_health_returns_200() -> None:
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_has_status_ok() -> None:
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/health")
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
```

- [ ] **Step 9.2: Write failing tests for JWT auth**

```python
# tests/test_api_deps.py
from __future__ import annotations

import pytest

from vms.api.deps import create_access_token, decode_access_token


def test_create_and_decode_token_round_trip() -> None:
    token = create_access_token(user_id=42, role="guard")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "guard"


def test_decode_invalid_token_raises() -> None:
    with pytest.raises(Exception):
        decode_access_token("not.a.valid.token")
```

- [ ] **Step 9.3: Write failing tests for person enrollment**

```python
# tests/test_api_persons.py
from __future__ import annotations

import numpy as np
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token
from vms.api.main import app


def _auth_headers(role: str = "admin") -> dict[str, str]:
    token = create_access_token(user_id=1, role=role)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_person_returns_201(db_session: Session) -> None:
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/persons",
            json={"full_name": "Alice Tester", "person_type": "employee", "employee_id": "E001"},
            headers=_auth_headers(),
        )
    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Alice Tester"
    assert "person_id" in body


@pytest.mark.asyncio
async def test_create_person_requires_auth() -> None:
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/persons",
            json={"full_name": "No Auth", "person_type": "employee"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_search_persons_returns_matching_results(db_session: Session) -> None:
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create a person first
        await client.post(
            "/api/persons",
            json={"full_name": "Bob Search", "person_type": "visitor"},
            headers=_auth_headers(),
        )
        response = await client.get(
            "/api/persons/search?q=Bob",
            headers=_auth_headers(),
        )
    assert response.status_code == 200
    results = response.json()
    assert any("Bob" in p["full_name"] for p in results)


@pytest.mark.asyncio
async def test_add_embedding_to_existing_person(db_session: Session) -> None:
    embedding = [float(x) for x in np.random.randn(512).astype(np.float32)]
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/persons",
            json={"full_name": "Carol Embed", "person_type": "employee"},
            headers=_auth_headers(),
        )
        person_id = create_resp.json()["person_id"]
        embed_resp = await client.post(
            f"/api/persons/{person_id}/embeddings",
            json={"embedding": embedding, "quality_score": 0.85, "source": "enrollment"},
            headers=_auth_headers(),
        )
    assert embed_resp.status_code == 201
```

- [ ] **Step 9.4: Run all API tests — expect ImportError**
```powershell
python -m pytest tests/test_api_health.py tests/test_api_deps.py tests/test_api_persons.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.api'`

- [ ] **Step 9.5: Create `vms/api/__init__.py`**
```python
"""FastAPI application package."""
```

- [ ] **Step 9.6: Implement `vms/api/schemas.py`**

```python
"""Pydantic request/response schemas for the VMS API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PersonCreate(BaseModel):
    full_name: str = Field(..., max_length=200)
    person_type: str = Field(..., pattern="^(employee|visitor|unknown)$")
    employee_id: str | None = Field(None, max_length=50)
    department: str | None = Field(None, max_length=100)


class PersonResponse(BaseModel):
    person_id: int
    full_name: str
    person_type: str
    employee_id: str | None
    department: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class EmbeddingCreate(BaseModel):
    embedding: list[float] = Field(..., min_length=512, max_length=512)
    quality_score: float = Field(..., ge=0.0, le=1.0)
    source: str = Field("enrollment", pattern="^(enrollment|re_enrollment|auto)$")


class EmbeddingResponse(BaseModel):
    embedding_id: int
    person_id: int
    quality_score: float
    source: str

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str
    version: str
```

- [ ] **Step 9.7: Implement `vms/api/deps.py`**

```python
"""FastAPI dependencies: database session, JWT auth."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from vms.config import get_settings
from vms.db.session import SessionLocal

_bearer = HTTPBearer()


def get_db() -> Generator[Any, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    payload = {"sub": str(user_id), "role": role}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return dict(jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]))


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict[str, Any]:
    try:
        return decode_access_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
```

- [ ] **Step 9.8: Create `vms/api/routes/__init__.py`**
```python
"""API route packages."""
```

- [ ] **Step 9.9: Implement `vms/api/routes/health.py`**

```python
"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from vms.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")
```

- [ ] **Step 9.10: Implement `vms/api/routes/persons.py`**

```python
"""Person enrollment and search endpoints."""

from __future__ import annotations

from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.api.schemas import EmbeddingCreate, EmbeddingResponse, PersonCreate, PersonResponse
from vms.db.models import Person, PersonEmbedding

router = APIRouter()


@router.post("/persons", response_model=PersonResponse, status_code=status.HTTP_201_CREATED)
def create_person(
    body: PersonCreate,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> Person:
    person = Person(
        full_name=body.full_name,
        person_type=body.person_type,
        employee_id=body.employee_id,
        department=body.department,
    )
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.post(
    "/persons/{person_id}/embeddings",
    response_model=EmbeddingResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_embedding(
    person_id: int,
    body: EmbeddingCreate,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> PersonEmbedding:
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    emb_array = np.array(body.embedding, dtype=np.float32)
    record = PersonEmbedding(
        person_id=person_id,
        embedding=emb_array,
        quality_score=body.quality_score,
        source=body.source,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/persons/search", response_model=list[PersonResponse])
def search_persons(
    q: str,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> list[Person]:
    return (
        db.query(Person)
        .filter(
            Person.full_name.ilike(f"%{q}%") | Person.employee_id.ilike(f"%{q}%")
        )
        .limit(50)
        .all()
    )
```

- [ ] **Step 9.11: Implement `vms/api/main.py`**

```python
"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from vms.api.routes import health, persons

app = FastAPI(title="VMS API", version="0.1.0")

app.include_router(health.router, prefix="/api")
app.include_router(persons.router, prefix="/api")
```

- [ ] **Step 9.12: Run all API tests — expect 7 passed**
```powershell
python -m pytest tests/test_api_health.py tests/test_api_deps.py tests/test_api_persons.py -v
```
Expected: `7 passed`

- [ ] **Step 9.13: Lint + type-check**
```powershell
ruff check vms/api/ tests/test_api_health.py tests/test_api_deps.py tests/test_api_persons.py
mypy vms/api/
```

- [ ] **Step 9.14: Commit**
```powershell
git add vms/api/ tests/test_api_health.py tests/test_api_deps.py tests/test_api_persons.py
git commit -m "feat(api): add FastAPI app, health endpoint, JWT auth, and enrollment routes"
```

---

## Task 10: DB Writer (Batch tracking_events insert)

**Files:**
- Create: `vms/writer/__init__.py`
- Create: `vms/writer/db_writer.py`
- Create: `tests/test_writer_db_writer.py`

The DB writer reads `DetectionFrame` events from the `detections` stream and batch-inserts `tracking_events` using `INSERT ... ON CONFLICT DO NOTHING` for idempotency (spec v1 §10, CLAUDE.md §6.3).

- [ ] **Step 10.1: Write failing tests**

```python
# tests/test_writer_db_writer.py
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from vms.db.models import TrackingEvent
from vms.inference.messages import DetectionFrame, FaceWithEmbedding, Tracklet
from vms.writer.db_writer import flush_detection_frame


def _make_frame(camera_id: int = 1, seq_id: int = 0) -> DetectionFrame:
    return DetectionFrame(
        camera_id=camera_id,
        seq_id=seq_id,
        timestamp_ms=1_000_000,
        tracklets=(
            Tracklet(local_track_id=10, camera_id=camera_id, bbox=(0, 0, 100, 200), confidence=0.9),
        ),
        face_embeddings=(),
    )


@pytest.mark.integration
def test_flush_detection_frame_inserts_tracking_event(db_session: Session) -> None:
    frame = _make_frame(camera_id=1, seq_id=0)
    flush_detection_frame(db_session, frame)
    db_session.flush()

    rows = db_session.query(TrackingEvent).filter_by(camera_id=1, local_track_id=10).all()
    assert len(rows) == 1
    assert rows[0].confidence is not None


@pytest.mark.integration
def test_flush_detection_frame_is_idempotent(db_session: Session) -> None:
    frame = _make_frame(camera_id=2, seq_id=1)
    flush_detection_frame(db_session, frame)
    flush_detection_frame(db_session, frame)  # second call must not raise
    db_session.flush()

    rows = db_session.query(TrackingEvent).filter_by(camera_id=2, local_track_id=10).all()
    assert len(rows) == 1  # deduplicated by unique constraint


@pytest.mark.integration
def test_flush_detection_frame_no_op_for_empty_tracklets(db_session: Session) -> None:
    frame = DetectionFrame(
        camera_id=3, seq_id=0, timestamp_ms=0, tracklets=(), face_embeddings=()
    )
    flush_detection_frame(db_session, frame)  # must not raise
    db_session.flush()
    rows = db_session.query(TrackingEvent).filter_by(camera_id=3).all()
    assert rows == []
```

- [ ] **Step 10.2: Check the TrackingEvent model fields used above**

Verify the ORM model has `camera_id`, `local_track_id`, `confidence`, and the idempotency constraint:
```powershell
python -c "from vms.db.models import TrackingEvent; print([c.name for c in TrackingEvent.__table__.columns])"
```
Expected output includes: `camera_id`, `local_track_id`, `event_ts`, `confidence`, `bbox_x1`, etc.

- [ ] **Step 10.3: Run tests — expect ImportError**
```powershell
python -m pytest tests/test_writer_db_writer.py -v -m integration
```
Expected: `ModuleNotFoundError: No module named 'vms.writer'`

- [ ] **Step 10.4: Create `vms/writer/__init__.py`**
```python
"""DB writer: consumes detections stream and persists to tracking_events."""
```

- [ ] **Step 10.5: Implement `vms/writer/db_writer.py`**

```python
"""Batch inserts DetectionFrame tracklets into tracking_events.

Uses INSERT ... ON CONFLICT DO NOTHING for idempotent replay (spec §6.3).
The unique constraint uq_tracking_idem on (camera_id, local_track_id, event_ts)
is defined in alembic/versions/0001_initial_schema.py.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.orm import Session

from vms.inference.messages import DetectionFrame
from vms.redis_client import stream_read

logger = logging.getLogger(__name__)

_DETECTIONS_STREAM = "detections"
_INSERT_SQL = text(
    """
    INSERT INTO tracking_events
        (camera_id, local_track_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, confidence, event_ts)
    VALUES
        (:camera_id, :local_track_id, :bbox_x1, :bbox_y1, :bbox_x2, :bbox_y2, :confidence, :event_ts)
    ON CONFLICT ON CONSTRAINT uq_tracking_idem DO NOTHING
    """
)


def flush_detection_frame(db: Session, frame: DetectionFrame) -> None:
    """Write all tracklets from one DetectionFrame to tracking_events (idempotent)."""
    if not frame.tracklets:
        return

    event_ts = datetime.fromtimestamp(frame.timestamp_ms / 1000.0, tz=timezone.utc)
    rows = [
        {
            "camera_id": t.camera_id,
            "local_track_id": t.local_track_id,
            "bbox_x1": t.bbox[0],
            "bbox_y1": t.bbox[1],
            "bbox_x2": t.bbox[2],
            "bbox_y2": t.bbox[3],
            "confidence": t.confidence,
            "event_ts": event_ts,
        }
        for t in frame.tracklets
    ]
    db.execute(_INSERT_SQL, rows)


class DBWriter:
    """Consumes the 'detections' Redis stream and batch-writes to tracking_events."""

    def __init__(
        self,
        redis_client: aioredis.Redis,  # type: ignore[type-arg]
        db_factory: type[Session],
    ) -> None:
        self._redis = redis_client
        self._db_factory = db_factory
        self._running = False
        self._last_id = "0-0"

    async def run(self) -> None:
        self._running = True
        while self._running:
            messages = await stream_read(
                self._redis, _DETECTIONS_STREAM, last_id=self._last_id, count=100
            )
            if messages:
                db = self._db_factory()
                try:
                    for msg_id, fields in messages:
                        frame = DetectionFrame.from_redis_fields(fields)
                        flush_detection_frame(db, frame)
                        self._last_id = msg_id
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("DB writer flush failed")
                finally:
                    db.close()
            else:
                await asyncio.sleep(0.05)

    async def stop(self) -> None:
        self._running = False
```

- [ ] **Step 10.6: Run tests — expect 3 passed**
```powershell
python -m pytest tests/test_writer_db_writer.py -v -m integration
```
Expected: `3 passed`

- [ ] **Step 10.7: Run full test suite — expect 57 + new tests all passing**
```powershell
python -m pytest tests/ -q
```
Expect all original tests + all new tests pass with no failures.

- [ ] **Step 10.8: Lint + type-check**
```powershell
black vms/ tests/
ruff check vms/ tests/
mypy vms/
```

- [ ] **Step 10.9: Coverage check**
```powershell
python -m pytest tests/ --cov=vms --cov-report=term-missing -q
```
Target: ≥ 70% across `vms/ingestion/`, `vms/inference/`, `vms/writer/`, `vms/api/`

- [ ] **Step 10.10: Commit**
```powershell
git add vms/writer/ tests/test_writer_db_writer.py
git commit -m "feat(writer): add DBWriter batch insert to tracking_events"
```

---

## Self-Review Checklist

Before declaring this plan complete, verify:

| Check | Status |
|---|---|
| All 10 tasks have failing-test → implement → pass → commit cycle | |
| `mypy vms/ --strict` passes with no errors | |
| `ruff check vms/ tests/` clean | |
| Full suite `pytest tests/ -q` green | |
| No `print()` calls in any `vms/` file | |
| No hardcoded thresholds — all use `get_settings()` | |
| No ONNX model files committed | |
| Phase 1B status in CLAUDE.md updated to IN PROGRESS then COMPLETE | |

---

## Execution Options

Plan saved to `docs/superpowers/plans/2026-05-09-vms-v2-phase1b-ingestion-inference-api.md`.

**Option 1 — Subagent-Driven (recommended):** One subagent per task, diff reviewed between tasks. Use `superpowers:subagent-driven-development`.

**Option 2 — Inline Execution:** Execute tasks in this session with checkpoints. Use `superpowers:executing-plans`.
