"""Detector interval: PerCameraTracker coasts between YOLO frames (§6.0.25)."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from vms.config import get_settings
from vms.inference.tracker import PerCameraTracker


def _make_tracker_with_mock(returns_tracklet: bool = False) -> tuple[PerCameraTracker, MagicMock]:
    """Build a PerCameraTracker backed by a mocked YOLO model."""
    mock_model = MagicMock()
    mock_result = MagicMock()

    if returns_tracklet:
        # Simulate one confirmed person track so _last_tracklets is non-empty.
        mock_result.boxes.id = [42]
        mock_result.boxes.xyxy = [[10.0, 20.0, 50.0, 80.0]]
        mock_result.boxes.conf = [0.9]
        mock_result.keypoints = None
    else:
        mock_result.boxes.id = None  # no tracks — early return path

    mock_model.track.return_value = [mock_result]
    tracker = PerCameraTracker(camera_id=1, model=mock_model)
    return tracker, mock_model


def _frame() -> np.ndarray:  # type: ignore[type-arg]
    return np.zeros((640, 640, 3), dtype=np.uint8)


def test_interval_1_calls_yolo_every_frame(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("VMS_DETECTOR_INTERVAL_FRAMES", "1")
    get_settings.cache_clear()

    tracker, mock_model = _make_tracker_with_mock()
    for _ in range(5):
        tracker.update(_frame())

    assert mock_model.track.call_count == 5
    get_settings.cache_clear()


def test_interval_2_halves_yolo_calls(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("VMS_DETECTOR_INTERVAL_FRAMES", "2")
    get_settings.cache_clear()

    tracker, mock_model = _make_tracker_with_mock()
    for _ in range(4):
        tracker.update(_frame())

    assert mock_model.track.call_count == 2
    get_settings.cache_clear()


def test_interval_3_runs_every_third_frame(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("VMS_DETECTOR_INTERVAL_FRAMES", "3")
    get_settings.cache_clear()

    tracker, mock_model = _make_tracker_with_mock()
    for _ in range(9):
        tracker.update(_frame())

    assert mock_model.track.call_count == 3
    get_settings.cache_clear()


def test_skip_returns_last_tracklets(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Skip frame must return the tracklets from the last real YOLO run, not empty."""
    monkeypatch.setenv("VMS_DETECTOR_INTERVAL_FRAMES", "2")
    get_settings.cache_clear()

    tracker, mock_model = _make_tracker_with_mock(returns_tracklet=True)
    result_yolo = tracker.update(_frame())  # frame 0: YOLO runs
    result_skip = tracker.update(_frame())  # frame 1: coasts

    assert mock_model.track.call_count == 1
    assert len(result_skip) == len(result_yolo)
    assert result_skip is result_yolo  # exact same list object from _last_tracklets
    get_settings.cache_clear()


def test_interval_first_frame_always_runs_yolo(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Frame 0 must always trigger YOLO regardless of interval value."""
    monkeypatch.setenv("VMS_DETECTOR_INTERVAL_FRAMES", "5")
    get_settings.cache_clear()

    tracker, mock_model = _make_tracker_with_mock()
    tracker.update(_frame())

    assert mock_model.track.call_count == 1
    get_settings.cache_clear()
