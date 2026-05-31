from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import torch

from vms.inference.tracker import PerCameraTracker


def _make_result(
    track_id: int,
    bbox: tuple[int, int, int, int],
    conf: float = 0.85,
    kpts_conf: float = 0.9,
    has_keypoints: bool = True,
) -> MagicMock:
    """Build a minimal ultralytics pose-result mock for one person."""
    result = MagicMock()
    result.boxes.xyxy = [torch.tensor(list(bbox), dtype=torch.float32)]
    result.boxes.id = [torch.tensor(float(track_id))]
    result.boxes.conf = [torch.tensor(conf)]
    if has_keypoints:
        kd = torch.zeros(1, 17, 3)
        kd[0, 0] = torch.tensor([50.0, 30.0, kpts_conf])  # nose
        kd[0, 1] = torch.tensor([45.0, 28.0, kpts_conf])  # left_eye
        kd[0, 2] = torch.tensor([55.0, 28.0, kpts_conf])  # right_eye
        result.keypoints = MagicMock()
        result.keypoints.data = kd
    else:
        result.keypoints = None
    return result


# ------------------------------------------------------------------
# Backward-compat: original shape tests
# ------------------------------------------------------------------

def test_tracker_returns_tracklets_for_detected_persons() -> None:
    mock_model = MagicMock()
    mock_model.track.return_value = [
        _make_result(track_id=5, bbox=(10, 20, 100, 200), conf=0.85)
    ]
    tracker = PerCameraTracker(camera_id=1, model=mock_model)
    tracklets = tracker.update(np.zeros((480, 640, 3), dtype=np.uint8))

    assert len(tracklets) == 1
    t = tracklets[0]
    assert t.local_track_id == 5
    assert t.camera_id == 1
    assert t.bbox == (10, 20, 100, 200)
    assert abs(t.confidence - 0.85) < 1e-4


def test_tracker_returns_empty_when_no_persons() -> None:
    mock_model = MagicMock()
    result = MagicMock()
    result.boxes.id = None
    mock_model.track.return_value = [result]
    tracker = PerCameraTracker(camera_id=1, model=mock_model)
    assert tracker.update(np.zeros((100, 100, 3), dtype=np.uint8)) == []


def test_tracker_returns_empty_when_track_ids_none() -> None:
    mock_model = MagicMock()
    result = MagicMock()
    result.boxes.id = None
    mock_model.track.return_value = [result]
    tracker = PerCameraTracker(camera_id=1, model=mock_model)
    assert tracker.update(np.zeros((100, 100, 3), dtype=np.uint8)) == []


# ------------------------------------------------------------------
# New: keypoints + face_visible
# ------------------------------------------------------------------

def test_tracker_populates_keypoints() -> None:
    mock_model = MagicMock()
    mock_model.track.return_value = [_make_result(1, (10, 20, 60, 120), kpts_conf=0.9)]
    tracker = PerCameraTracker(camera_id=1, model=mock_model)
    tracklets = tracker.update(np.zeros((480, 640, 3), dtype=np.uint8))

    assert len(tracklets[0].keypoints) == 17
    assert tracklets[0].face_visible is True   # nose + eye conf=0.9 >= 0.5


def test_tracker_face_not_visible_when_keypoints_low_conf() -> None:
    mock_model = MagicMock()
    mock_model.track.return_value = [_make_result(2, (10, 20, 60, 120), kpts_conf=0.1)]
    tracker = PerCameraTracker(camera_id=1, model=mock_model)
    tracklets = tracker.update(np.zeros((480, 640, 3), dtype=np.uint8))

    assert tracklets[0].face_visible is False


def test_tracker_no_keypoints_model_falls_back_gracefully() -> None:
    """Tracker works with non-pose model (no keypoints attribute)."""
    mock_model = MagicMock()
    mock_model.track.return_value = [_make_result(3, (0, 0, 50, 100), has_keypoints=False)]
    tracker = PerCameraTracker(camera_id=1, model=mock_model)
    tracklets = tracker.update(np.zeros((480, 640, 3), dtype=np.uint8))

    assert len(tracklets) == 1
    assert tracklets[0].keypoints == ()
    assert tracklets[0].face_visible is False


def test_tracker_uses_botsort_config(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """PerCameraTracker passes botsort_config (not bytetrack_config) to model.track."""
    from vms.config import Settings
    monkeypatch.setattr(
        "vms.inference.tracker.get_settings",
        lambda: Settings(db_url="x", jwt_secret="x"),  # type: ignore[call-arg]
    )
    mock_model = MagicMock()
    mock_model.track.return_value = []
    tracker = PerCameraTracker(camera_id=1, model=mock_model)
    tracker.update(np.zeros((100, 100, 3), dtype=np.uint8))

    call_kwargs = mock_model.track.call_args[1]
    assert call_kwargs["tracker"] == "botsort_custom.yaml"
