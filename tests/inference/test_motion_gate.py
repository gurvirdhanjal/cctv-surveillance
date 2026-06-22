"""Tests for PerCameraTracker motion gate (§6.0.25)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from vms.inference.messages import Tracklet
from vms.inference.tracker import PerCameraTracker


def _make_tracker() -> tuple[PerCameraTracker, MagicMock]:
    model = MagicMock()
    model.track.return_value = []
    return PerCameraTracker(camera_id=1, model=model), model


def _static_frame() -> np.ndarray:  # type: ignore[type-arg]
    return np.full((480, 640, 3), 128, dtype=np.uint8)


def _active_frame() -> np.ndarray:  # type: ignore[type-arg]
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[100:200, 100:200] = 255  # bright patch
    return frame


def _tracklet(tid: int = 1) -> Tracklet:
    return Tracklet(local_track_id=tid, camera_id=1, bbox=(0, 0, 10, 10), confidence=0.9)


@patch.dict(
    "os.environ",
    {"VMS_DB_URL": "postgresql://x/y", "VMS_JWT_SECRET": "s", "VMS_MOTION_GATE_ENABLED": "false"},
)
def test_motion_gate_disabled_always_calls_yolo() -> None:
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, model = _make_tracker()
    frame = _static_frame()
    for _ in range(5):
        tracker.update(frame)
    assert model.track.call_count == 5
    get_settings.cache_clear()


@patch.dict(
    "os.environ",
    {
        "VMS_DB_URL": "postgresql://x/y",
        "VMS_JWT_SECRET": "s",
        "VMS_MOTION_GATE_ENABLED": "true",
        "VMS_MOTION_GATE_MIN_PIXEL_DIFF_PCT": "1.0",
    },
)
def test_motion_gate_first_frame_always_runs_yolo() -> None:
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, model = _make_tracker()
    tracker.update(_static_frame())
    assert model.track.call_count == 1
    get_settings.cache_clear()


@patch.dict(
    "os.environ",
    {
        "VMS_DB_URL": "postgresql://x/y",
        "VMS_JWT_SECRET": "s",
        "VMS_MOTION_GATE_ENABLED": "true",
        "VMS_MOTION_GATE_MIN_PIXEL_DIFF_PCT": "1.0",
    },
)
def test_motion_gate_static_scene_skips_yolo() -> None:
    """Identical frames → 0% diff → gate blocks after the first frame."""
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, model = _make_tracker()
    frame = _static_frame()
    tracker.update(frame)  # frame 1: no baseline → runs
    model.track.reset_mock()
    tracker.update(frame)  # frame 2: identical → gate blocks
    tracker.update(frame)  # frame 3: identical → gate blocks
    assert model.track.call_count == 0
    get_settings.cache_clear()


@patch.dict(
    "os.environ",
    {
        "VMS_DB_URL": "postgresql://x/y",
        "VMS_JWT_SECRET": "s",
        "VMS_MOTION_GATE_ENABLED": "true",
        "VMS_MOTION_GATE_MIN_PIXEL_DIFF_PCT": "0.5",
    },
)
def test_motion_gate_active_scene_calls_yolo() -> None:
    """Large pixel change → gate passes → YOLO called."""
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, model = _make_tracker()
    tracker.update(_static_frame())  # frame 1: baseline
    model.track.reset_mock()
    # Second frame is very different (bright vs dark)
    tracker.update(_active_frame())
    assert model.track.call_count == 1
    get_settings.cache_clear()


@patch.dict(
    "os.environ",
    {
        "VMS_DB_URL": "postgresql://x/y",
        "VMS_JWT_SECRET": "s",
        "VMS_MOTION_GATE_ENABLED": "true",
        "VMS_MOTION_GATE_MIN_PIXEL_DIFF_PCT": "1.0",
        "VMS_TRACKER_BUFFER_FRAMES": "3",
    },
)
def test_motion_gate_expires_tracks_after_long_static() -> None:
    """After tracker_buffer_frames static frames, _last_tracklets must be cleared."""
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, model = _make_tracker()
    # Seed a tracklet via the first (baseline) frame
    model.track.return_value = [
        MagicMock(
            boxes=MagicMock(
                id=MagicMock(__iter__=MagicMock(return_value=iter([MagicMock(item=lambda: 1)]))),
                xyxy=[MagicMock(__iter__=MagicMock(return_value=iter([0, 0, 10, 10])))],
                conf=[MagicMock(item=lambda: 0.9)],
            ),
            keypoints=None,
        )
    ]
    # Manually set last_tracklets so we can observe expiry
    tracker._last_tracklets = [_tracklet()]
    frame = _static_frame()
    # Pre-populate prev_frame_gray to simulate an already-running tracker that has
    # established a baseline — otherwise the first update() call sets the baseline
    # (returns True) and doesn't count toward the static_count.
    tracker._prev_frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # Send 3 consecutive static frames (tracker_buffer_frames=3)
    for _ in range(3):
        tracker.update(frame)
    assert tracker._last_tracklets == []
    get_settings.cache_clear()


@patch.dict(
    "os.environ",
    {
        "VMS_DB_URL": "postgresql://x/y",
        "VMS_JWT_SECRET": "s",
        "VMS_MOTION_GATE_ENABLED": "true",
        "VMS_MOTION_GATE_METHOD": "mog2",
        "VMS_MOTION_GATE_MIN_PIXEL_DIFF_PCT": "0.5",
    },
)
def test_motion_gate_mog2_mode_initialised_lazily() -> None:
    """MOG2 background subtractor created on first call, not in __init__."""
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, _ = _make_tracker()
    assert tracker._mog2 is None
    tracker.update(_static_frame())
    assert tracker._mog2 is not None
    get_settings.cache_clear()
