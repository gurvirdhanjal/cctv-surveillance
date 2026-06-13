"""CameraProfiler tests -- cv2.VideoCapture is mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vms.profiler.probe import CameraProfiler


def _make_cap_mock(
    *,
    opened: bool = True,
    width: float = 1920.0,
    height: float = 1080.0,
    fps: float = 25.0,
    fourcc: float = 0.0,
    frame_brightness: int = 128,
) -> MagicMock:
    """Build a mock cv2.VideoCapture that returns textured frames."""
    cap = MagicMock()
    cap.isOpened.return_value = opened
    cap.get.side_effect = lambda prop: {
        3: width,  # CAP_PROP_FRAME_WIDTH
        4: height,  # CAP_PROP_FRAME_HEIGHT
        5: fps,  # CAP_PROP_FPS
        6: fourcc,  # CAP_PROP_FOURCC
    }.get(prop, 0.0)
    rng = np.random.default_rng(42)
    frame = rng.integers(50, 200, (int(height), int(width), 3), dtype=np.uint8)
    cap.read.return_value = (True, frame)
    return cap


@patch("vms.profiler.probe.cv2.VideoCapture")
def test_probe_returns_full_tier_on_1080p_stream(mock_cap_cls: MagicMock) -> None:
    mock_cap_cls.return_value = _make_cap_mock()
    profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
    result = profiler.probe("rtsp://fake/stream")
    assert result.resolution_h == 1080
    assert result.fps_measured is not None
    assert result.suggested_tier == "FULL"


@patch("vms.profiler.probe.cv2.VideoCapture")
def test_probe_detects_low_tier_on_480p_stream(mock_cap_cls: MagicMock) -> None:
    mock_cap_cls.return_value = _make_cap_mock(height=480.0, fps=15.0)
    profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
    result = profiler.probe("rtsp://fake/stream")
    assert result.suggested_tier == "LOW"
    assert result.resolution_h == 480


@patch("vms.profiler.probe.cv2.VideoCapture")
def test_probe_raises_on_unopened_capture(mock_cap_cls: MagicMock) -> None:
    mock_cap_cls.return_value = _make_cap_mock(opened=False)
    profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
    with pytest.raises(RuntimeError, match="Cannot open RTSP stream"):
        profiler.probe("rtsp://fake/unreachable")


@patch("vms.profiler.probe.cv2.VideoCapture")
def test_probe_computes_focus_score(mock_cap_cls: MagicMock) -> None:
    mock_cap_cls.return_value = _make_cap_mock()
    profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
    result = profiler.probe("rtsp://fake/stream")
    assert result.focus_score is not None
    assert result.focus_score >= 0.0


@patch("vms.profiler.probe.cv2.VideoCapture")
def test_probe_codec_string_populated(mock_cap_cls: MagicMock) -> None:
    mock_cap_cls.return_value = _make_cap_mock()
    profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
    result = profiler.probe("rtsp://fake/stream")
    assert result.codec is not None


@patch("vms.profiler.probe.cv2.VideoCapture")
def test_probe_frame_drop_rate_zero_on_clean_stream(mock_cap_cls: MagicMock) -> None:
    mock_cap_cls.return_value = _make_cap_mock()
    profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
    result = profiler.probe("rtsp://fake/stream")
    assert result.frame_drop_rate == 0.0


@patch("vms.profiler.probe.cv2.VideoCapture")
def test_probe_detects_analog_combing_via_alternating_rows(
    mock_cap_cls: MagicMock,
) -> None:
    """Frame with strong alternating-row intensity pattern -> analog-via-encoder=True."""
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.get.side_effect = lambda p: {3: 1920.0, 4: 1080.0, 5: 25.0, 6: 0.0}.get(p, 0.0)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[::2] = 200  # even rows bright
    frame[1::2] = 50  # odd rows dark
    cap.read.return_value = (True, frame)
    mock_cap_cls.return_value = cap

    profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
    result = profiler.probe("rtsp://fake/analog")
    assert result.is_analog_via_encoder is True
