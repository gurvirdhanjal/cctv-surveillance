from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from vms.inference.tracker import PerCameraTracker


def _make_mock_yolo_result(
    boxes_xyxy: list[list[float]], track_ids: list[int], confs: list[float]
) -> MagicMock:
    result = MagicMock()
    if track_ids:
        result.boxes.id = np.array(track_ids, dtype=np.float32)
        result.boxes.xyxy = np.array(boxes_xyxy, dtype=np.float32)
        result.boxes.conf = np.array(confs, dtype=np.float32)
    else:
        result.boxes.id = None
        result.boxes.xyxy = np.empty((0, 4))
        result.boxes.conf = np.empty((0,))
    return result


@pytest.fixture
def tracker() -> PerCameraTracker:
    mock_model = MagicMock()
    return PerCameraTracker(camera_id=1, model=mock_model)


def test_tracker_returns_tracklets_for_detected_persons(
    tracker: PerCameraTracker,
) -> None:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_result = _make_mock_yolo_result(
        boxes_xyxy=[[10.0, 20.0, 100.0, 200.0]],
        track_ids=[5],
        confs=[0.85],
    )
    tracker._model.track.return_value = [mock_result]

    tracklets = tracker.update(frame)
    assert len(tracklets) == 1
    assert tracklets[0].local_track_id == 5
    assert tracklets[0].camera_id == 1
    assert tracklets[0].bbox == (10, 20, 100, 200)
    assert abs(tracklets[0].confidence - 0.85) < 1e-4


def test_tracker_returns_empty_when_no_persons(tracker: PerCameraTracker) -> None:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_result = _make_mock_yolo_result([], [], [])
    tracker._model.track.return_value = [mock_result]
    assert tracker.update(frame) == []


def test_tracker_returns_empty_when_track_ids_none(tracker: PerCameraTracker) -> None:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = MagicMock()
    result.boxes.id = None
    tracker._model.track.return_value = [result]
    assert tracker.update(frame) == []
