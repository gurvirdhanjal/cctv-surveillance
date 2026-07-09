"""Tests for the DecodeBackend protocol + OpenCvDecoder (Phase 6d Task 1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from vms.ingestion.decoder import DecodeBackend, OpenCvDecoder
from vms.ingestion.worker import CameraConfig, IngestionWorker


class _FakeDecoder:
    """Minimal structural DecodeBackend used to drive the worker loop."""

    def __init__(self, frames: int, width: int = 64, height: int = 48) -> None:
        self._remaining = frames
        self._shape = (height, width, 3)
        self.released = False

    def read(self) -> tuple[bool, np.ndarray | None]:  # type: ignore[type-arg]
        if self._remaining <= 0:
            return False, None
        self._remaining -= 1
        return True, np.zeros(self._shape, dtype=np.uint8)

    def get_resolution(self) -> tuple[int, int]:
        return self._shape[1], self._shape[0]

    def release(self) -> None:
        self.released = True


def test_fake_and_opencv_decoders_satisfy_protocol() -> None:
    assert isinstance(_FakeDecoder(1), DecodeBackend)
    with patch("vms.ingestion.decoder.cv2.VideoCapture", return_value=MagicMock()):
        assert isinstance(OpenCvDecoder("rtsp://x"), DecodeBackend)


def test_opencv_decoder_limits_rtsp_buffer_to_one_frame() -> None:
    import cv2

    mock_cap = MagicMock()
    with patch("vms.ingestion.decoder.cv2.VideoCapture", return_value=mock_cap):
        OpenCvDecoder("rtsp://x")
    mock_cap.set.assert_called_once_with(cv2.CAP_PROP_BUFFERSIZE, 1)


def test_opencv_decoder_reports_resolution_from_capture() -> None:
    import cv2

    mock_cap = MagicMock()
    mock_cap.get.side_effect = lambda prop: {
        cv2.CAP_PROP_FRAME_WIDTH: 1280.0,
        cv2.CAP_PROP_FRAME_HEIGHT: 720.0,
    }[prop]
    with patch("vms.ingestion.decoder.cv2.VideoCapture", return_value=mock_cap):
        decoder = OpenCvDecoder("rtsp://x")
    assert decoder.get_resolution() == (1280, 720)
    decoder.release()
    mock_cap.release.assert_called_once()


@pytest.mark.asyncio
async def test_worker_uses_injected_decoder_factory() -> None:
    cfg = CameraConfig(camera_id=7, rtsp_url="rtsp://x", worker_group=1, width=64, height=48)
    decoder = _FakeDecoder(frames=1)
    factory_urls: list[str] = []

    def factory(url: str) -> _FakeDecoder:
        factory_urls.append(url)
        return decoder

    published: list[dict[str, str]] = []

    async def capture_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        published.append(fields)
        worker._running = False
        return "1-0"

    worker = IngestionWorker(cfg, AsyncMock(), decoder_factory=factory)

    with (
        patch("vms.ingestion.worker.stream_add", side_effect=capture_stream_add),
        patch("vms.ingestion.worker.SHMSlot.create") as mock_create,
    ):
        mock_slot = MagicMock()
        mock_slot.name = "vms_cam_7"
        mock_slot.write.return_value = 1000
        mock_create.return_value = mock_slot
        await worker.start()

    assert factory_urls == ["rtsp://x"]
    assert len(published) == 1
    assert decoder.released is True
