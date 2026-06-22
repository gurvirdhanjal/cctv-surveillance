"""Tests for PerCameraTracker adaptive detector interval (§6.0.3).

State-machine tests call _update_adaptive_interval directly to avoid frame-counter
phase interactions when the interval changes mid-sequence.
Integration tests exercise the full update() path.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from vms.inference.messages import Tracklet
from vms.inference.tracker import PerCameraTracker


def _make_tracker() -> tuple[PerCameraTracker, MagicMock]:
    model = MagicMock()
    model.track.return_value = []
    return PerCameraTracker(camera_id=1, model=model), model


def _frame() -> np.ndarray:  # type: ignore[type-arg]
    return np.zeros((480, 640, 3), dtype=np.uint8)


def _tracklet(tid: int) -> Tracklet:
    return Tracklet(local_track_id=tid, camera_id=1, bbox=(0, 0, 10, 10), confidence=0.9)


_BASE_ENV = {
    "VMS_DB_URL": "postgresql://x/y",
    "VMS_JWT_SECRET": "s",
    "VMS_DETECTOR_INTERVAL_ADAPTIVE": "true",
    "VMS_DETECTOR_INTERVAL_MAX": "4",
    "VMS_DETECTOR_ADAPT_WINDOW": "3",
    "VMS_DETECTOR_INTERVAL_FRAMES": "1",
}


@patch.dict("os.environ", _BASE_ENV)
def test_adaptive_interval_starts_at_1() -> None:
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, _ = _make_tracker()
    assert tracker._adapt_interval == 1
    get_settings.cache_clear()


@patch.dict("os.environ", _BASE_ENV)
def test_adaptive_interval_raises_after_empty_window() -> None:
    """adapt_window=3 YOLO runs with no new tracks → interval raises to 2."""
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, _ = _make_tracker()
    for _ in range(3):
        tracker._update_adaptive_interval([])
    assert tracker._adapt_interval == 2
    get_settings.cache_clear()


@patch.dict("os.environ", _BASE_ENV)
def test_adaptive_interval_resets_on_new_track_id() -> None:
    """New track ID entering FOV resets interval to 1 regardless of current value."""
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, _ = _make_tracker()
    # Raise to 3 via 6 direct state-machine calls (2 windows x window=3)
    for _ in range(6):
        tracker._update_adaptive_interval([])
    assert tracker._adapt_interval == 3

    # New person (ID 99) — not in _prev_track_ids → resets interval
    tracker._update_adaptive_interval([_tracklet(99)])
    assert tracker._adapt_interval == 1
    get_settings.cache_clear()


@patch.dict("os.environ", _BASE_ENV)
def test_adaptive_interval_respects_max_cap() -> None:
    """Interval never exceeds detector_interval_max=4."""
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, _ = _make_tracker()
    # Drive 15 direct calls: 3 per window x 5 windows = interval 2->3->4->stays 4
    for _ in range(15):
        tracker._update_adaptive_interval([])
    assert tracker._adapt_interval == 4
    get_settings.cache_clear()


@patch.dict(
    "os.environ",
    {**_BASE_ENV, "VMS_DETECTOR_INTERVAL_ADAPTIVE": "false", "VMS_DETECTOR_INTERVAL_FRAMES": "2"},
)
def test_adaptive_interval_disabled_uses_fixed_interval() -> None:
    """When adaptive=False, the fixed detector_interval_frames governs scheduling."""
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, model = _make_tracker()
    for _ in range(4):
        tracker.update(_frame())
    assert model.track.call_count == 2  # interval=2 → 4 frames → 2 YOLO runs
    assert tracker._adapt_interval == 1  # adaptive never ran
    get_settings.cache_clear()


@patch.dict("os.environ", _BASE_ENV)
def test_adaptive_no_detect_count_resets_after_window() -> None:
    """_no_new_detect_count resets to 0 after raising the interval."""
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, _ = _make_tracker()
    for _ in range(3):
        tracker._update_adaptive_interval([])
    assert tracker._no_new_detect_count == 0
    assert tracker._adapt_interval == 2
    get_settings.cache_clear()


@patch.dict("os.environ", _BASE_ENV)
def test_adaptive_continuing_track_does_not_reset_interval() -> None:
    """A continuing track (same ID) does NOT reset the interval; only new entries do."""
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, _ = _make_tracker()
    # Raise to 2
    for _ in range(3):
        tracker._update_adaptive_interval([])
    assert tracker._adapt_interval == 2

    # ID 42 appears for the first time → new → resets interval
    tracker._update_adaptive_interval([_tracklet(42)])
    assert tracker._adapt_interval == 1

    # ID 42 continues (same ID each call) → not new → window fills → raises back to 2
    for _ in range(3):
        tracker._update_adaptive_interval([_tracklet(42)])
    assert tracker._adapt_interval == 2
    get_settings.cache_clear()


@patch.dict("os.environ", _BASE_ENV)
def test_adaptive_interval_applied_in_update_loop() -> None:
    """When adaptive=True and interval raises to 2, YOLO skips every other frame."""
    from vms.config import get_settings

    get_settings.cache_clear()
    tracker, model = _make_tracker()
    # Raise interval to 2 via state machine
    for _ in range(3):
        tracker._update_adaptive_interval([])
    assert tracker._adapt_interval == 2

    # Reset frame counter to a known even value so YOLO is scheduled
    tracker._frame_counter = 0
    model.track.reset_mock()

    # 4 frames with interval=2 → 2 YOLO calls (frames 0, 2)
    for _ in range(4):
        tracker.update(_frame())
    assert model.track.call_count == 2
    get_settings.cache_clear()
