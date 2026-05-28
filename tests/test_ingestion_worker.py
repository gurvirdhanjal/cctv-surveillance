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


@pytest.mark.asyncio
async def test_ingestion_worker_backoff_delays_increase_with_failures(
    camera_cfg: CameraConfig, fake_redis: AsyncMock
) -> None:
    backoff_delays_ms = (500, 1000, 2000, 4000)
    expected_delays_s = [d / 1000.0 for d in backoff_delays_ms]
    stop_after = len(backoff_delays_ms)

    sleep_calls: list[float] = []

    mock_cap = MagicMock()
    mock_cap.read.return_value = (False, None)
    mock_cap.release = MagicMock()

    worker = IngestionWorker(camera_cfg, fake_redis)

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        if len(sleep_calls) >= stop_after:
            worker._running = False

    with (
        patch("vms.ingestion.worker.cv2.VideoCapture", return_value=mock_cap),
        patch("asyncio.sleep", side_effect=fake_sleep),
        patch("vms.ingestion.worker.get_settings") as mock_cfg,
        patch("vms.ingestion.worker.SHMSlot.create") as mock_create,
    ):
        mock_cfg.return_value.rtsp_failure_threshold = 20
        mock_cfg.return_value.rtsp_backoff_delays_ms = backoff_delays_ms
        mock_create.return_value = MagicMock()
        await worker.start()

    assert sleep_calls[:stop_after] == expected_delays_s


@pytest.mark.asyncio
async def test_rtsp_threshold_reads_from_config(
    camera_cfg: CameraConfig, fake_redis: AsyncMock
) -> None:
    """rtsp_failure_threshold and rtsp_backoff_delays_ms are config-driven."""
    fail_count = 0

    mock_cap = MagicMock()
    mock_cap.release = MagicMock()

    worker = IngestionWorker(camera_cfg, fake_redis)

    def mock_read() -> tuple[bool, None]:
        nonlocal fail_count
        fail_count += 1
        return (False, None)

    mock_cap.read.side_effect = mock_read

    mock_cam = MagicMock()
    mock_cam.is_active = True
    mock_session = MagicMock()
    mock_session.get.return_value = mock_cam
    session_factory = MagicMock(return_value=mock_session)
    worker._session_factory = session_factory

    with (
        patch("vms.ingestion.worker.cv2.VideoCapture", return_value=mock_cap),
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch("vms.ingestion.worker.get_settings") as mock_cfg,
        patch("vms.ingestion.worker.SHMSlot.create") as mock_create,
    ):
        mock_cfg.return_value.rtsp_failure_threshold = 2
        mock_cfg.return_value.rtsp_backoff_delays_ms = (100, 200)
        mock_create.return_value = MagicMock()
        await worker.start()

    assert fail_count >= 2
    assert mock_cam.is_active is False


@pytest.mark.asyncio
async def test_ingestion_worker_marks_camera_inactive_after_failure_threshold(
    camera_cfg: CameraConfig, fake_redis: AsyncMock
) -> None:
    mock_cap = MagicMock()
    mock_cap.read.return_value = (False, None)
    mock_cap.release = MagicMock()

    mock_cam = MagicMock()
    mock_cam.is_active = True
    mock_session = MagicMock()
    mock_session.get.return_value = mock_cam
    session_factory = MagicMock(return_value=mock_session)

    worker = IngestionWorker(camera_cfg, fake_redis, session_factory=session_factory)

    with (
        patch("vms.ingestion.worker.cv2.VideoCapture", return_value=mock_cap),
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch("vms.ingestion.worker.get_settings") as mock_cfg,
        patch("vms.ingestion.worker.SHMSlot.create") as mock_create,
    ):
        mock_cfg.return_value.rtsp_failure_threshold = 3
        mock_cfg.return_value.rtsp_backoff_delays_ms = (100, 200, 400)
        mock_create.return_value = MagicMock()
        await worker.start()

    assert mock_cam.is_active is False
    mock_session.commit.assert_called()
