"""Tests for ViolenceModel warm-up on load (Phase 6c Task 8).

Verifies that _warm_up_model runs a dummy forward pass on the loaded model
to pre-compile CUDA kernels, preventing first-frame stalls in production.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np


def test_warm_up_model_calls_model_with_correct_shape() -> None:
    """_warm_up_model calls model(dummy) with shape (1,3,clip_frames,H,W)."""
    from vms.inference.violence import _INPUT_H, _INPUT_W, _warm_up_model

    mock_model = MagicMock()
    _warm_up_model(mock_model, device="cpu", clip_frames=16, h=_INPUT_H, w=_INPUT_W)

    mock_model.assert_called_once()
    call_tensor = mock_model.call_args[0][0]
    assert tuple(call_tensor.shape) == (1, 3, 16, _INPUT_H, _INPUT_W)


def test_warm_up_model_different_clip_frames() -> None:
    """_warm_up_model uses the configured clip_frames, not a hardcoded value."""
    from vms.inference.violence import _INPUT_H, _INPUT_W, _warm_up_model

    mock_model = MagicMock()
    _warm_up_model(mock_model, device="cpu", clip_frames=8, h=_INPUT_H, w=_INPUT_W)

    call_tensor = mock_model.call_args[0][0]
    assert tuple(call_tensor.shape) == (1, 3, 8, _INPUT_H, _INPUT_W)


def test_violence_model_disabled_when_no_path() -> None:
    """When path is empty, model is unavailable and no warm-up occurs."""
    from vms.inference.violence import ViolenceModel

    vm = ViolenceModel("")
    assert not vm.is_available
    assert vm.score_frame(camera_id=1, frame_bgr=np.zeros((112, 112, 3), dtype=np.uint8)) is None
