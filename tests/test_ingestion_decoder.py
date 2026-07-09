"""Tests for the DecodeBackend protocol + decode probes (Phase 6d Tasks 1-2)."""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from vms.ingestion.decoder import (
    DecodeBackend,
    OpenCvDecoder,
    _mask_url,
    nvdec_available,
    probe_codec,
)
from vms.ingestion.worker import CameraConfig, IngestionWorker

_SECRET_URL = "rtsp://admin:secret123@10.0.0.5:554/Streaming/Channels/101"


@pytest.fixture(autouse=True)
def _clear_probe_caches() -> Any:
    nvdec_available.cache_clear()
    yield
    nvdec_available.cache_clear()


def _gpu_profile(nvdec_units: int = 1) -> Any:
    from vms.inference.gpu_profile import GpuProfile

    return GpuProfile(
        arch="Ada",
        compute_cap=8.9,
        vram_gb=16.0,
        nvdec_units=nvdec_units,
        supports_fp16=True,
        supports_int8=True,
    )


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


# -- capability probe (Task 2) --------------------------------------------------


def test_nvdec_available_true_when_gpu_and_cuvid_present() -> None:
    run_result = MagicMock(stdout="V..... h264_cuvid  Nvidia CUVID H264 decoder", returncode=0)
    with (
        patch("vms.ingestion.decoder.detect_gpu_profile", return_value=_gpu_profile()),
        patch("vms.ingestion.decoder.subprocess.run", return_value=run_result) as mock_run,
    ):
        assert nvdec_available() is True
        # lru-cached: a second call must not re-run ffmpeg
        assert nvdec_available() is True
    assert mock_run.call_count == 1


def test_nvdec_available_false_without_gpu_skips_ffmpeg() -> None:
    with (
        patch("vms.ingestion.decoder.detect_gpu_profile", return_value=None),
        patch("vms.ingestion.decoder.subprocess.run") as mock_run,
    ):
        assert nvdec_available() is False
    mock_run.assert_not_called()


def test_nvdec_available_false_when_ffmpeg_missing_logs_warning(caplog: Any) -> None:
    with (
        patch("vms.ingestion.decoder.detect_gpu_profile", return_value=_gpu_profile()),
        patch("vms.ingestion.decoder.subprocess.run", side_effect=FileNotFoundError),
        caplog.at_level("WARNING"),
    ):
        assert nvdec_available() is False
    assert any("ffmpeg" in r.getMessage().lower() for r in caplog.records)


def test_nvdec_available_false_when_build_lacks_cuvid() -> None:
    run_result = MagicMock(stdout="V..... h264  plain decoder", returncode=0)
    with (
        patch("vms.ingestion.decoder.detect_gpu_profile", return_value=_gpu_profile()),
        patch("vms.ingestion.decoder.subprocess.run", return_value=run_result),
    ):
        assert nvdec_available() is False


# -- codec probe (Task 2) --------------------------------------------------------


def test_probe_codec_returns_h264_and_hevc() -> None:
    for codec in ("h264", "hevc"):
        run_result = MagicMock(stdout=f"{codec}\n", returncode=0)
        with patch("vms.ingestion.decoder.subprocess.run", return_value=run_result):
            assert probe_codec(_SECRET_URL) == codec


def test_probe_codec_none_on_failure_timeout_or_unknown() -> None:
    fail = MagicMock(stdout="", returncode=1)
    with patch("vms.ingestion.decoder.subprocess.run", return_value=fail):
        assert probe_codec(_SECRET_URL) is None
    with patch(
        "vms.ingestion.decoder.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=10),
    ):
        assert probe_codec(_SECRET_URL) is None
    unknown = MagicMock(stdout="mjpeg\n", returncode=0)
    with patch("vms.ingestion.decoder.subprocess.run", return_value=unknown):
        assert probe_codec(_SECRET_URL) is None


def test_probe_failures_never_log_credentials(caplog: Any) -> None:
    fail = MagicMock(stdout="", returncode=1)
    with (
        patch("vms.ingestion.decoder.subprocess.run", return_value=fail),
        caplog.at_level("DEBUG"),
    ):
        probe_codec(_SECRET_URL)
    with (
        patch("vms.ingestion.decoder.detect_gpu_profile", return_value=_gpu_profile()),
        patch("vms.ingestion.decoder.subprocess.run", side_effect=FileNotFoundError),
        caplog.at_level("DEBUG"),
    ):
        nvdec_available()
    for record in caplog.records:
        assert "secret123" not in record.getMessage()
        assert "admin:" not in record.getMessage()


def test_mask_url_strips_credentials() -> None:
    assert _mask_url(_SECRET_URL) == "rtsp://***@10.0.0.5:554/Streaming/Channels/101"
    assert _mask_url("rtsp://10.0.0.5/ch1") == "rtsp://10.0.0.5/ch1"
    assert _mask_url("file.mp4") == "file.mp4"
