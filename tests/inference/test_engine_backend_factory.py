"""Tests for InferenceEngine backend factory (Phase 6c Task 5).

Verifies that _build_inference_backend selects ORT vs Triton based on
VMS_GPU_TRITON_URL, and that _process_one_message routes detect/embed
through self._backend instead of self._detector/self._embedder directly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import fakeredis.aioredis as fake_aioredis
import numpy as np
import pytest

from vms.inference.engine import InferenceEngine
from vms.inference.messages import DetectionFrame
from vms.ingestion.messages import FramePointer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(
    fake_redis: fake_aioredis.FakeRedis,
    *,
    triton_url: str = "",
) -> InferenceEngine:
    detector = MagicMock()
    detector.detect.return_value = []
    embedder = MagicMock()
    embedder.embed.return_value = None
    tracker = MagicMock()
    tracker.update.return_value = []

    with patch("vms.inference.engine.get_settings") as mock_settings:
        s = MagicMock()
        s.gpu_triton_url = triton_url
        s.scrfd_conf = 0.5
        s.min_face_px = 40
        s.min_blur = 25.0
        s.min_body_bbox_px = 32
        s.torso_kp_conf_threshold = 0.3
        s.torso_crop_pad_fraction = 0.1
        mock_settings.return_value = s

        return InferenceEngine(
            camera_ids=[1],
            worker_group=1,
            detector=detector,
            embedder=embedder,
            trackers={1: tracker},
            redis_client=fake_redis,
        )


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


def test_engine_factory_returns_ort_backend_when_triton_url_empty(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    """When VMS_GPU_TRITON_URL is empty, _build_inference_backend must return OrtInferenceBackend."""
    from vms.inference.backend import OrtInferenceBackend

    engine = _make_engine(fake_redis, triton_url="")
    assert isinstance(engine._backend, OrtInferenceBackend)  # type: ignore[attr-defined]


def test_engine_factory_returns_triton_backend_when_triton_url_set(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    """When VMS_GPU_TRITON_URL is set, _build_inference_backend must construct TritonInferenceBackend."""
    from vms.inference.backend import TritonInferenceBackend

    mock_triton = MagicMock(spec=TritonInferenceBackend)

    detector = MagicMock()
    detector.detect.return_value = []
    embedder = MagicMock()
    tracker = MagicMock()
    tracker.update.return_value = []

    with (
        patch("vms.inference.engine.get_settings") as mock_settings,
        patch("vms.inference.engine.TritonInferenceBackend", return_value=mock_triton) as mock_cls,
    ):
        s = MagicMock()
        s.gpu_triton_url = "localhost:8001"
        mock_settings.return_value = s

        engine = InferenceEngine(
            camera_ids=[1],
            worker_group=1,
            detector=detector,
            embedder=embedder,
            trackers={1: tracker},
            redis_client=fake_redis,
        )

    mock_cls.assert_called_once_with(url="localhost:8001")
    assert engine._backend is mock_triton  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Message processing routes through backend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_process_message_uses_backend_detect(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    """_process_one_message must call self._backend.detect() not self._detector.detect()."""
    engine = _make_engine(fake_redis, triton_url="")

    mock_backend = MagicMock()
    mock_backend.detect.return_value = ()
    mock_backend.embed.return_value = None
    mock_backend.embed_body.return_value = ((), 0.0)
    mock_backend.score_ppe.return_value = None
    engine._backend = mock_backend  # type: ignore[attr-defined]

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    pointer = FramePointer(
        cam_id=1, shm_name="vms_cam_1", seq_id=0, timestamp_ms=1000, width=640, height=480
    )

    mock_slot = MagicMock()
    mock_slot.read.return_value = (frame, 0, 1000)

    # Tracker returns a tracklet with face_visible=True so detect() is exercised.
    from vms.inference.messages import Tracklet

    mock_tracklet = Tracklet(
        local_track_id=1, camera_id=1, bbox=(10, 10, 100, 200), confidence=0.9, face_visible=True
    )
    engine._trackers[1].update.return_value = [mock_tracklet]

    with (
        patch("vms.inference.engine.SHMSlot.open", return_value=mock_slot),
        patch("vms.inference.engine.stream_add", return_value="1-0"),
    ):
        await engine._process_one_message("1-0", pointer.to_redis_fields())

    mock_backend.detect.assert_called_once_with(frame)


@pytest.mark.asyncio
async def test_engine_existing_ort_path_publishes_detection_frame(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    """Regression: ORT default path still publishes a DetectionFrame (backward-compat check)."""
    engine = _make_engine(fake_redis, triton_url="")

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    pointer = FramePointer(
        cam_id=1, shm_name="vms_cam_1", seq_id=0, timestamp_ms=1000, width=640, height=480
    )

    mock_slot = MagicMock()
    mock_slot.read.return_value = (frame, 0, 1000)

    published: list[dict[str, str]] = []

    async def fake_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        published.append({"stream": stream, **fields})
        return "1-0"

    with (
        patch("vms.inference.engine.SHMSlot.open", return_value=mock_slot),
        patch("vms.inference.engine.stream_add", side_effect=fake_stream_add),
    ):
        await engine._process_one_message("1-0", pointer.to_redis_fields())

    assert len(published) == 1
    assert published[0]["stream"] == "detections"
    frame_data = DetectionFrame.from_redis_fields(published[0])
    assert frame_data.camera_id == 1


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis() -> fake_aioredis.FakeRedis:
    return fake_aioredis.FakeRedis(decode_responses=True)
