"""Tests for the ingestion worker camera capture loop."""

from __future__ import annotations

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


@pytest.mark.asyncio
async def test_ingestion_worker_publishes_frame_pointer(
    camera_cfg: CameraConfig, fake_redis: AsyncMock
) -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    mock_cap = MagicMock()
    mock_cap.read.return_value = (True, frame)
    mock_cap.release = MagicMock()

    published: list[FramePointer] = []

    async def capture_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        published.append(FramePointer.from_redis_fields(fields))
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
    assert published[0].seq_id == 0
    assert published[0].timestamp_ms == 1000


@pytest.mark.asyncio
async def test_ingestion_worker_skips_failed_read(
    camera_cfg: CameraConfig, fake_redis: AsyncMock
) -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    call_count = 0

    async def capture_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        worker._running = False
        return "1-0"

    def mock_read():  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (False, frame)  # first read fails
        return (True, frame)

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
