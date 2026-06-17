"""Tests for PPEModel — YOLOv8 SH17 detection wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from vms.inference.ppe import PPEModel

# SH17 class indices (confirmed from notebook)
_HELMET = 10
_VEST = 16
_GLOVES = 9
_MASK = 5
_NUM_CLASSES = 17
_NUM_ANCHORS = 8400


def _make_output(detections: list[tuple[int, float]]) -> np.ndarray:
    """Build a fake (1, 21, 8400) ONNX output with specific class detections.

    detections: list of (class_idx, confidence) placed into distinct anchors.
    All other anchors have zero scores.
    """
    output = np.zeros((1, 4 + _NUM_CLASSES, _NUM_ANCHORS), dtype=np.float32)
    for i, (cls_idx, conf) in enumerate(detections):
        # Set box coords to a valid non-degenerate box (cx=0.5, cy=0.5, w=0.3, h=0.5)
        output[0, 0, i] = 0.5  # cx
        output[0, 1, i] = 0.5  # cy
        output[0, 2, i] = 0.3  # w
        output[0, 3, i] = 0.5  # h
        output[0, 4 + cls_idx, i] = conf
    return output


def _make_model_with_output(output: np.ndarray, monkeypatch: pytest.MonkeyPatch) -> PPEModel:
    """Return an already-loaded PPEModel whose session returns the given output."""
    from vms.inference.ppe import _TARGET

    mock_session = MagicMock()
    mock_session.run.return_value = [output]
    mock_session.get_inputs.return_value = [MagicMock(name="images")]

    model = PPEModel.__new__(PPEModel)
    model._path = "fake.onnx"
    model._session = mock_session
    model._input_name = "images"
    model._conf_threshold = 0.25
    model._nms_iou_threshold = 0.45
    model._target = dict(_TARGET)
    return model


# ------------------------------------------------------------------
# Availability
# ------------------------------------------------------------------


def test_ppe_model_unavailable_when_path_missing() -> None:
    assert PPEModel("").is_available is False
    assert PPEModel("nonexistent.onnx").is_available is False


def test_ppe_model_is_available_false_when_session_none() -> None:
    m = PPEModel.__new__(PPEModel)
    m._session = None
    assert m.is_available is False


# ------------------------------------------------------------------
# score_crop output shape and keys
# ------------------------------------------------------------------


def test_ppe_model_score_crop_returns_dict_with_all_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """score_crop always returns a dict with all 4 keys when model is available."""
    output = _make_output([(_HELMET, 0.8)])
    model = _make_model_with_output(output, monkeypatch)
    crop = np.zeros((128, 64, 3), dtype=np.uint8)
    result = model.score_crop(crop)
    assert result is not None
    assert set(result.keys()) == {"helmet", "vest", "gloves", "mask"}


def test_ppe_model_score_crop_returns_zeros_when_no_detections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no class exceeds conf_threshold, all values are 0.0."""
    output = np.zeros((1, 4 + _NUM_CLASSES, _NUM_ANCHORS), dtype=np.float32)
    model = _make_model_with_output(output, monkeypatch)
    result = model.score_crop(np.zeros((128, 64, 3), dtype=np.uint8))
    assert result is not None
    assert result["helmet"] == 0.0
    assert result["vest"] == 0.0
    assert result["gloves"] == 0.0
    assert result["mask"] == 0.0


def test_ppe_model_score_crop_picks_max_confidence_for_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Max score among all surviving helmet detections is returned."""
    output = _make_output([(_HELMET, 0.9), (_HELMET, 0.6), (_VEST, 0.7)])
    model = _make_model_with_output(output, monkeypatch)
    result = model.score_crop(np.zeros((128, 64, 3), dtype=np.uint8))
    assert result is not None
    assert abs(result["helmet"] - 0.9) < 1e-4
    assert abs(result["vest"] - 0.7) < 1e-4
    assert result["gloves"] == 0.0
    assert result["mask"] == 0.0


def test_ppe_model_score_crop_returns_none_on_tiny_crop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Crops smaller than 32x32 pixels return None."""
    output = _make_output([(_HELMET, 0.9)])
    model = _make_model_with_output(output, monkeypatch)
    assert model.score_crop(np.zeros((31, 31, 3), dtype=np.uint8)) is None
    assert model.score_crop(np.zeros((10, 50, 3), dtype=np.uint8)) is None


def test_ppe_model_score_crop_returns_none_when_unavailable() -> None:
    model = PPEModel("")
    assert model.score_crop(np.zeros((128, 64, 3), dtype=np.uint8)) is None


def test_ppe_model_all_four_target_classes_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _make_output(
        [
            (_HELMET, 0.88),
            (_VEST, 0.75),
            (_GLOVES, 0.60),
            (_MASK, 0.55),
        ]
    )
    model = _make_model_with_output(output, monkeypatch)
    result = model.score_crop(np.zeros((200, 100, 3), dtype=np.uint8))
    assert result is not None
    assert abs(result["helmet"] - 0.88) < 1e-4
    assert abs(result["vest"] - 0.75) < 1e-4
    assert abs(result["gloves"] - 0.60) < 1e-4
    assert abs(result["mask"] - 0.55) < 1e-4
