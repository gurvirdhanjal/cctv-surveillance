"""Tests for the MoViNet A2 Stream violence wrapper."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from vms.inference.violence import ViolenceModel


def test_empty_path_model_is_unavailable() -> None:
    """Empty path disables violence detection gracefully."""
    model = ViolenceModel("")
    assert not model.is_available


def test_missing_dir_model_is_unavailable(tmp_path: Path) -> None:
    """Non-existent directory disables violence detection gracefully."""
    model = ViolenceModel(str(tmp_path / "no_such_dir"))
    assert not model.is_available


def test_score_frame_returns_none_when_unavailable() -> None:
    """score_frame() returns None when model not loaded."""
    model = ViolenceModel("")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    assert model.score_frame(camera_id=1, frame_bgr=frame) is None


def test_saved_model_dir_detection(tmp_path: Path) -> None:
    """_is_saved_model_dir recognises a directory with saved_model.pb."""
    from vms.inference.violence import _is_saved_model_dir

    assert not _is_saved_model_dir(str(tmp_path / "nonexistent"))
    assert not _is_saved_model_dir(str(tmp_path))  # empty dir

    (tmp_path / "saved_model.pb").touch()
    assert _is_saved_model_dir(str(tmp_path))
