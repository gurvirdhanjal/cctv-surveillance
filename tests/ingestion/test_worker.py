"""Ingestion worker — CameraConfig and analytics substream selection (§6.7)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import cv2
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


def _fake_capture_factory(
    *,
    width: int = 0,
    height: int = 0,
) -> tuple[list[str], object]:
    """Return (opened_urls, factory) that builds mock VideoCapture objects."""
    opened: list[str] = []

    def _factory(url: str) -> MagicMock:
        opened.append(url)
        mock_cap = MagicMock()
        mock_cap.read.return_value = (False, None)
        mock_cap.get.side_effect = lambda prop: (
            float(width) if prop == cv2.CAP_PROP_FRAME_WIDTH else float(height)
        )
        return mock_cap

    return opened, _factory


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

    opened, factory = _fake_capture_factory(width=1280, height=720)
    with patch("vms.ingestion.worker.cv2.VideoCapture", side_effect=factory):
        await worker._capture_loop()

    assert opened == ["rtsp://cam/sub"]


@pytest.mark.asyncio
async def test_capture_loop_falls_back_to_rtsp_url_when_analytics_not_set() -> None:
    """Worker must use rtsp_url when analytics_rtsp_url is None."""
    cam = _make_camera(rtsp_url="rtsp://cam/main", analytics_rtsp_url=None)
    worker = IngestionWorker(camera=cam, redis_client=MagicMock())
    worker._running = False

    opened, factory = _fake_capture_factory(width=1920, height=1080)
    with patch("vms.ingestion.worker.cv2.VideoCapture", side_effect=factory):
        await worker._capture_loop()

    assert opened == ["rtsp://cam/main"]


@pytest.mark.asyncio
async def test_capture_loop_falls_back_when_analytics_resolution_too_small() -> None:
    """Worker must fall back to rtsp_url when analytics substream shorter side < 640px."""
    cam = _make_camera(rtsp_url="rtsp://cam/main", analytics_rtsp_url="rtsp://cam/sub")
    worker = IngestionWorker(camera=cam, redis_client=MagicMock())
    worker._running = False

    opened, factory = _fake_capture_factory(width=320, height=240)
    with patch("vms.ingestion.worker.cv2.VideoCapture", side_effect=factory):
        await worker._capture_loop()

    assert opened == ["rtsp://cam/sub", "rtsp://cam/main"]


@pytest.mark.asyncio
async def test_capture_loop_no_fallback_when_resolution_unknown() -> None:
    """When CAP_PROP_FRAME_WIDTH returns 0 (RTSP not reporting), no fallback — best-effort."""
    cam = _make_camera(rtsp_url="rtsp://cam/main", analytics_rtsp_url="rtsp://cam/sub")
    worker = IngestionWorker(camera=cam, redis_client=MagicMock())
    worker._running = False

    opened, factory = _fake_capture_factory(width=0, height=0)
    with patch("vms.ingestion.worker.cv2.VideoCapture", side_effect=factory):
        await worker._capture_loop()

    assert opened == ["rtsp://cam/sub"]
