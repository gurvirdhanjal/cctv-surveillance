"""Ingestion worker — CameraConfig and analytics substream selection (§6.7)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vms.ingestion.worker import CameraConfig, IngestionWorker


def _make_camera(
    *,
    rtsp_url: str = "rtsp://cam/main",
    analytics_rtsp_url: str | None = None,
) -> CameraConfig:
    return CameraConfig(
        camera_id=1,
        rtsp_url=rtsp_url,
        worker_group=0,
        analytics_rtsp_url=analytics_rtsp_url,
    )


def test_camera_config_analytics_url_defaults_none() -> None:
    cam = CameraConfig(camera_id=1, rtsp_url="rtsp://x", worker_group=0)
    assert cam.analytics_rtsp_url is None


def test_camera_config_analytics_url_set() -> None:
    cam = _make_camera(analytics_rtsp_url="rtsp://cam/sub")
    assert cam.analytics_rtsp_url == "rtsp://cam/sub"


@pytest.mark.asyncio
async def test_capture_loop_uses_analytics_url_when_set() -> None:
    """Worker must open analytics_rtsp_url instead of rtsp_url when both are set."""
    cam = _make_camera(rtsp_url="rtsp://cam/main", analytics_rtsp_url="rtsp://cam/sub")
    worker = IngestionWorker(camera=cam, redis_client=MagicMock())
    worker._running = False

    opened_urls: list[str] = []

    def _fake_capture(url: str) -> MagicMock:
        opened_urls.append(url)
        mock_cap = MagicMock()
        mock_cap.read.return_value = (False, None)
        return mock_cap

    with patch("vms.ingestion.worker.cv2.VideoCapture", side_effect=_fake_capture):
        await worker._capture_loop()

    assert opened_urls == ["rtsp://cam/sub"]


@pytest.mark.asyncio
async def test_capture_loop_falls_back_to_rtsp_url_when_analytics_not_set() -> None:
    """Worker must use rtsp_url when analytics_rtsp_url is None."""
    cam = _make_camera(rtsp_url="rtsp://cam/main", analytics_rtsp_url=None)
    worker = IngestionWorker(camera=cam, redis_client=MagicMock())
    worker._running = False

    opened_urls: list[str] = []

    def _fake_capture(url: str) -> MagicMock:
        opened_urls.append(url)
        mock_cap = MagicMock()
        mock_cap.read.return_value = (False, None)
        return mock_cap

    with patch("vms.ingestion.worker.cv2.VideoCapture", side_effect=_fake_capture):
        await worker._capture_loop()

    assert opened_urls == ["rtsp://cam/main"]
