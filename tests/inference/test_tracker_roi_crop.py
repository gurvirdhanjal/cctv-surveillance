"""Tests for ROI cropping in PerCameraTracker.update() (Phase 6c Task 6).

When motion_gate_roi_crop_enabled=True and the motion gate passes on a real YOLO
frame, the tracker crops to the changed-pixel bounding box, resizes to a fixed
640x640, runs YOLO on the crop, then maps bboxes/keypoints back to full-frame
coordinates.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np

from vms.inference.tracker import PerCameraTracker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings(**overrides: Any) -> MagicMock:
    s = MagicMock()
    s.motion_gate_enabled = True
    s.motion_gate_method = "frame_diff"
    s.motion_gate_min_pixel_diff_pct = 1.0
    s.motion_gate_roi_crop_enabled = False
    s.motion_gate_roi_margin_px = 0
    s.detector_interval_frames = 1
    s.detector_interval_adaptive = False
    s.tracker_buffer_frames = 30
    s.yolo_person_conf = 0.5
    s.face_kpt_min_conf = 0.5
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _make_tracker() -> tuple[PerCameraTracker, MagicMock]:
    mock_model = MagicMock()
    mock_model.track.return_value = []
    tracker = PerCameraTracker(camera_id=1, model=mock_model)
    return tracker, mock_model


def _make_yolo_result(
    bboxes: list[tuple[float, float, float, float]],
    track_ids: list[int],
    confidences: list[float],
) -> list[Any]:
    """Create a minimal mock YOLO result list with given detections."""
    r = MagicMock()
    boxes = MagicMock()
    boxes.xyxy = [np.array(b, dtype=np.float32) for b in bboxes]
    boxes.id = [np.array(t, dtype=np.float32) for t in track_ids]
    boxes.conf = [np.array(c, dtype=np.float32) for c in confidences]
    r.boxes = boxes
    r.keypoints = None  # disables keypoint extraction path
    return [r]


def _prime_baseline(
    tracker: PerCameraTracker,
    mock_model: MagicMock,
    frame: np.ndarray[Any, Any],
    settings: MagicMock,
) -> None:
    """Run one update to establish the frame_diff baseline without ROI crop."""
    with (
        patch("vms.inference.tracker.get_settings", return_value=settings),
        patch("vms.inference.tracker.resolve_tracker_config", return_value="dummy.yaml"),
    ):
        tracker.update(frame)
    mock_model.track.reset_mock()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_roi_crop_disabled_passes_full_frame() -> None:
    """When motion_gate_roi_crop_enabled=False YOLO receives the full-resolution frame."""
    tracker, mock_model = _make_tracker()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    settings = _mock_settings(motion_gate_roi_crop_enabled=False)

    # First update: motion gate returns True immediately (no baseline).
    with (
        patch("vms.inference.tracker.get_settings", return_value=settings),
        patch("vms.inference.tracker.resolve_tracker_config", return_value="dummy.yaml"),
    ):
        tracker.update(frame)

    mock_model.track.assert_called_once()
    call_frame = mock_model.track.call_args[0][0]
    assert call_frame.shape == frame.shape


def test_roi_crop_enabled_resizes_to_640() -> None:
    """When ROI crop is enabled and motion is localized, YOLO receives a 640x640 input."""
    tracker, mock_model = _make_tracker()
    frame1 = np.zeros((480, 640, 3), dtype=np.uint8)
    settings = _mock_settings(motion_gate_roi_crop_enabled=True, motion_gate_roi_margin_px=0)

    # Establish baseline with frame1 (all zeros).
    _prime_baseline(tracker, mock_model, frame1, settings)

    # Frame2: localized 100x100 motion patch — enough to pass the motion gate.
    frame2 = np.zeros((480, 640, 3), dtype=np.uint8)
    frame2[50:150, 100:200] = 200  # bright patch

    with (
        patch("vms.inference.tracker.get_settings", return_value=settings),
        patch("vms.inference.tracker.resolve_tracker_config", return_value="dummy.yaml"),
    ):
        tracker.update(frame2)

    mock_model.track.assert_called_once()
    call_frame = mock_model.track.call_args[0][0]
    # ROI crop + resize must produce exactly 640x640
    assert call_frame.shape == (640, 640, 3)


def test_roi_crop_maps_bbox_back_to_full_frame() -> None:
    """A detection (0,0,640,640) in the 640x640 crop maps back to the full ROI rect."""
    tracker, mock_model = _make_tracker()
    frame1 = np.zeros((480, 640, 3), dtype=np.uint8)
    settings = _mock_settings(motion_gate_roi_crop_enabled=True, motion_gate_roi_margin_px=0)

    _prime_baseline(tracker, mock_model, frame1, settings)

    # Motion in region x=[100,300), y=[100,400) of the 640x480 frame.
    frame2 = np.zeros((480, 640, 3), dtype=np.uint8)
    frame2[100:400, 100:300] = 200  # (y, x) slice

    # Detection (0,0,640,640) in crop space covers the full crop.
    # roi = (100,100,300,400); roi_w=200, roi_h=300
    # x_full = int(0 * 200/640) + 100 = 100, int(640 * 200/640) + 100 = 300
    # y_full = int(0 * 300/640) + 100 = 100, int(640 * 300/640) + 100 = 400
    mock_model.track.return_value = _make_yolo_result(
        bboxes=[(0.0, 0.0, 640.0, 640.0)],
        track_ids=[7],
        confidences=[0.85],
    )

    with (
        patch("vms.inference.tracker.get_settings", return_value=settings),
        patch("vms.inference.tracker.resolve_tracker_config", return_value="dummy.yaml"),
    ):
        result = tracker.update(frame2)

    assert len(result) == 1
    x1, y1, x2, y2 = result[0].bbox
    assert x1 == 100
    assert y1 == 100
    assert x2 == 300
    assert y2 == 400


def test_roi_crop_no_effect_on_coasting_frame() -> None:
    """Interval-skipped frames return cached tracklets unchanged, ignoring ROI flag."""
    tracker, mock_model = _make_tracker()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    settings = _mock_settings(
        motion_gate_roi_crop_enabled=True,
        motion_gate_roi_margin_px=0,
        detector_interval_frames=5,  # run YOLO every 5th frame
    )

    # First update: frame_counter=0, interval=5, should_run=(0%5==0) -> True (runs YOLO)
    with (
        patch("vms.inference.tracker.get_settings", return_value=settings),
        patch("vms.inference.tracker.resolve_tracker_config", return_value="dummy.yaml"),
    ):
        tracker.update(frame)
    mock_model.track.reset_mock()

    # Second update: frame_counter=1, should_run=(1%5==0) -> False (coasting)
    with (
        patch("vms.inference.tracker.get_settings", return_value=settings),
        patch("vms.inference.tracker.resolve_tracker_config", return_value="dummy.yaml"),
    ):
        result = tracker.update(frame)

    # YOLO never called on coasting frame
    mock_model.track.assert_not_called()
    # Returns cached tracklets (empty from first run)
    assert result == []
