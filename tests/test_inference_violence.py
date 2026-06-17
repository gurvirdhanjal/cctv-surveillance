"""Tests for the R(2+1)D-18 violence detection wrapper."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from vms.inference.violence import ViolenceModel


def test_empty_path_model_is_unavailable() -> None:
    """Empty path disables violence detection gracefully."""
    model = ViolenceModel("")
    assert not model.is_available


def test_pt_file_not_found_model_is_unavailable(tmp_path: Path) -> None:
    """A .pt path that does not exist disables violence detection."""
    model = ViolenceModel(str(tmp_path / "no_such.pt"))
    assert not model.is_available


def test_score_frame_returns_none_when_unavailable() -> None:
    """score_frame() returns None when model not loaded."""
    model = ViolenceModel("")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    assert model.score_frame(camera_id=1, frame_bgr=frame) is None


def test_evict_camera_is_noop_when_unavailable() -> None:
    """evict_camera() does not raise when model is disabled."""
    model = ViolenceModel("")
    model.evict_camera(camera_id=99)  # must not raise
