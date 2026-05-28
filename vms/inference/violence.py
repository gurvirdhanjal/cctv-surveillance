"""MoViNet-A0 violence-detection ONNX wrapper.

If the ONNX file is absent at construction time, score() permanently returns
None — the pipeline continues without violence detection. This keeps the
deployment installable on a fresh checkout before models are downloaded.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    import onnxruntime as ort  # type: ignore[import-untyped]  # lazy
except ImportError:
    ort = None


class ViolenceModel:
    def __init__(self, path: str) -> None:
        self._path = path
        self._session: Any = None
        if not os.path.exists(path):
            logger.warning("violence model %s not found; violence detection disabled", path)
            return
        if ort is None:
            logger.warning("onnxruntime not available; violence detection disabled")
            return
        try:
            self._session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        except Exception as exc:
            logger.warning("violence model load failed (%s); detection disabled", exc)
            self._session = None

    def score(self, clip: np.ndarray[Any, Any]) -> float | None:
        if self._session is None:
            return None
        if clip.shape[0] != 16:
            return None
        x = (clip.astype(np.float32) / 255.0).transpose(0, 3, 1, 2)[np.newaxis, ...]
        name = self._session.get_inputs()[0].name
        out = self._session.run(None, {name: x})
        return float(out[0].ravel()[0])
