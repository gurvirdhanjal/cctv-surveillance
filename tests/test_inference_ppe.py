"""Tests for PPEModel ONNX wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from vms.inference.ppe import PPEModel


def test_ppe_model_unavailable_when_model_path_missing() -> None:
    model = PPEModel("")
    assert model.is_available is False


def test_ppe_model_unavailable_when_path_not_onnx() -> None:
    model = PPEModel("nonexistent/path/model.onnx")
    assert model.is_available is False


def test_ppe_model_score_crop_returns_none_when_unavailable() -> None:
    model = PPEModel("")
    crop = np.zeros((64, 32, 3), dtype=np.uint8)
    assert model.score_crop(crop) is None


def test_ppe_model_score_crop_returns_none_on_tiny_crop() -> None:
    """Crops smaller than 32x32 are too small for reliable PPE classification."""
    model = PPEModel("")
    assert model.score_crop(np.zeros((31, 31, 3), dtype=np.uint8)) is None
    assert model.score_crop(np.zeros((10, 50, 3), dtype=np.uint8)) is None


def test_ppe_model_score_crop_returns_tuple_with_mocked_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a mocked ONNX session, score_crop returns (helmet_conf, vest_conf)."""
    # softmax([2.0, 1.0]) ≈ [0.731, 0.269] → helmet_conf ≈ 0.269 (no_helmet wins)
    # softmax([0.5, 3.0]) ≈ [0.076, 0.924] → vest_conf ≈ 0.924 (vest wins)
    fake_output = np.array([[2.0, 1.0, 0.5, 3.0]], dtype=np.float32)  # shape (1, 4)

    mock_session = MagicMock()
    mock_session.run.return_value = [fake_output]
    mock_session.get_inputs.return_value = [MagicMock(name="input")]

    def fake_inference_session(path: str, **kwargs: object) -> MagicMock:
        return mock_session

    import onnxruntime as ort  # type: ignore[import-untyped]

    monkeypatch.setattr(ort, "InferenceSession", fake_inference_session)

    # Point to a fake path but bypass the file-existence check
    model = PPEModel.__new__(PPEModel)
    model._path = "fake.onnx"
    model._session = mock_session
    model._input_name = "input"

    crop = np.zeros((128, 64, 3), dtype=np.uint8)
    result = model.score_crop(crop)

    assert result is not None
    helmet_conf, vest_conf = result
    # helmet_conf = softmax([2.0,1.0])[1] ≈ 0.269 (no_helmet logit is higher)
    assert 0.0 < helmet_conf < 0.5
    # vest_conf = softmax([0.5,3.0])[1] ≈ 0.924 (vest logit is higher)
    assert vest_conf > 0.8


def test_ppe_model_is_available_false_when_session_none() -> None:
    model = PPEModel.__new__(PPEModel)
    model._session = None
    assert model.is_available is False
