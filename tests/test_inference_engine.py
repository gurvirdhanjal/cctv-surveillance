from __future__ import annotations

from unittest.mock import MagicMock, patch

import fakeredis.aioredis as fake_aioredis
import numpy as np
import pytest

from vms.inference.engine import InferenceEngine
from vms.inference.messages import DetectionFrame
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
    pointer = FramePointer(
        cam_id=1, shm_name="vms_cam_1", seq_id=0, timestamp_ms=1000, width=640, height=480
    )

    mock_slot = MagicMock()
    mock_slot.read.return_value = (frame, 0, 1000)

    published: list[dict[str, str]] = []

    async def fake_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        published.append({"stream": stream, **fields})
        engine._running = False
        return "1-0"

    with (
        patch("vms.inference.engine.SHMSlot.open", return_value=mock_slot),
        patch("vms.inference.engine.stream_add", side_effect=fake_stream_add),
        patch(
            "vms.inference.engine.stream_read", return_value=[("1-0", pointer.to_redis_fields())]
        ),
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
    pointer = FramePointer(
        cam_id=1, shm_name="vms_cam_1", seq_id=0, timestamp_ms=1000, width=640, height=480
    )

    mock_slot = MagicMock()
    mock_slot.read.return_value = None  # stale

    published: list[dict[str, str]] = []

    async def fake_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        published.append(fields)
        return "1-0"

    with (
        patch("vms.inference.engine.SHMSlot.open", return_value=mock_slot),
        patch("vms.inference.engine.stream_add", side_effect=fake_stream_add),
    ):
        await engine._process_one_message("1-0", pointer.to_redis_fields())

    assert published == []  # nothing published for stale frame
