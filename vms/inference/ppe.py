"""YOLOv8x-CHV PPE compliance classifier (ONNX).

Classifies whether each person is wearing a helmet and/or safety vest.

Model input:  (1, 3, 640, 640) float32, RGB, normalised to [0, 1], letterboxed.
Model output: (1, 4) float32 logits — [no_helmet, helmet, no_vest, vest].

Returns per-tracklet (helmet_conf, vest_conf) where each is the softmax
probability that the PPE item IS worn.  None when model is unavailable.

Graceful degradation:
    If the ONNX file is absent or onnxruntime fails to load, score_crop()
    returns None and PPEDetector silently disables itself via should_run().
"""

from __future__ import annotations

import logging
import os
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_INPUT_SIZE = 640
_MIN_CROP = 32  # crops smaller than this are too small for reliable classification


def _softmax2(a: float, b: float) -> tuple[float, float]:
    """Numerically-stable softmax for a 2-element pair."""
    m = max(a, b)
    ea, eb = (a - m), (b - m)
    s = ea + eb  # log-space sum
    import math

    denom = math.exp(ea) + math.exp(eb)
    return math.exp(ea) / denom, math.exp(eb) / denom


class PPEModel:
    """YOLOv8x-CHV ONNX PPE classifier.

    Stateless — no per-camera state.  Call score_crop() with any person crop.

    Usage:
        model = PPEModel(get_settings().ppe_model)
        if model.is_available:
            result = model.score_crop(crop_bgr)   # (helmet_conf, vest_conf) | None
    """

    def __init__(self, model_path: str) -> None:
        self._path = model_path
        self._session: Any = None
        self._input_name: str = "input"

        if not model_path:
            logger.info(
                "VMS_PPE_MODEL not set — PPE detection disabled. "
                "Set VMS_PPE_MODEL to an ONNX file path."
            )
            return

        if not os.path.isfile(model_path):
            logger.warning(
                "ppe_model path %r is not a file — PPE detection disabled.",
                model_path,
            )
            return

        self._load(model_path)

    def _load(self, path: str) -> None:
        try:
            import onnxruntime as ort  # type: ignore[import-untyped]

            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            sess = ort.InferenceSession(path, providers=providers)
            self._input_name = sess.get_inputs()[0].name
            self._session = sess
            logger.info("PPEModel loaded from %s", path)
        except Exception as exc:
            logger.warning(
                "PPEModel load failed (%s) — PPE detection disabled. "
                "Install: pip install onnxruntime",
                exc,
            )
            self._session = None

    @property
    def is_available(self) -> bool:
        return self._session is not None

    def score_crop(self, crop_bgr: np.ndarray[Any, Any]) -> tuple[float, float] | None:
        """Score a person crop.  Returns (helmet_conf, vest_conf) or None.

        helmet_conf: probability in [0,1] that a helmet IS worn.
        vest_conf:   probability in [0,1] that a safety vest IS worn.

        Args:
            crop_bgr: Person bounding-box crop, (H, W, 3) uint8 BGR.

        Returns:
            (helmet_conf, vest_conf) or None when unavailable / crop too small.
        """
        if self._session is None:
            return None

        h, w = crop_bgr.shape[:2]
        if h < _MIN_CROP or w < _MIN_CROP:
            return None

        try:
            tensor = self._preprocess(crop_bgr)
            outputs = self._session.run(None, {self._input_name: tensor})
            logits = outputs[0][0]  # shape (4,) — [no_helmet, helmet, no_vest, vest]

            _, helmet_conf = _softmax2(float(logits[0]), float(logits[1]))
            _, vest_conf = _softmax2(float(logits[2]), float(logits[3]))

            return helmet_conf, vest_conf

        except Exception as exc:
            logger.debug("PPEModel.score_crop error: %s", exc)
            return None

    def _preprocess(self, crop_bgr: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        """Letterbox-resize to 640×640, RGB, normalise to [0,1], add batch dim."""
        h, w = crop_bgr.shape[:2]
        scale = _INPUT_SIZE / max(h, w)
        new_h, new_w = int(h * scale), int(w * scale)
        resized = cv2.resize(crop_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        canvas = np.full((_INPUT_SIZE, _INPUT_SIZE, 3), 114, dtype=np.uint8)
        pad_y = (_INPUT_SIZE - new_h) // 2
        pad_x = (_INPUT_SIZE - new_w) // 2
        canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized

        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        return np.transpose(rgb, (2, 0, 1))[np.newaxis]  # (1, 3, 640, 640)
