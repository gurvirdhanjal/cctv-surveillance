"""OSNet body Re-ID embedder -- ONNX inference wrapper.

Model: osnet_x1_0 trained on Market-1501, 512-dim L2-normalized output.
Input tensor: [1, 3, 256, 128] float32 RGB, ImageNet mean/std normalized.
Minimum crop size: 16h x 8w pixels; returns () for smaller crops.
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_H = 256
_W = 128
_MIN_H = 16
_MIN_W = 8
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)


class BodyEmbedder:
    """Wraps OSNet ONNX model for 512-dim body appearance embeddings."""

    def __init__(self, model_path: str) -> None:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        self._session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self._input_name: str = self._session.get_inputs()[0].name

    def embed(self, crop_bgr: np.ndarray[Any, Any]) -> tuple[float, ...]:
        """Return 512-dim L2-normalized embedding, or () if crop is too small."""
        h, w = crop_bgr.shape[:2]
        if h < _MIN_H or w < _MIN_W:
            return ()
        resized = cv2.resize(crop_bgr, (_W, _H), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        chw = np.transpose(rgb, (2, 0, 1))
        chw = (chw - _MEAN) / _STD
        tensor = chw[np.newaxis]  # (1, 3, 256, 128)
        output: list[np.ndarray[Any, Any]] = self._session.run(
            None, {self._input_name: tensor}
        )
        vec = output[0][0].astype(np.float32)
        vec /= np.linalg.norm(vec) + 1e-8
        return tuple(float(x) for x in vec)
