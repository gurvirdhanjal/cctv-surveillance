"""AdaFace IR50 face embedder (ONNX).

Input:  (1, 3, 112, 112) float32, normalised (pixel - 127.5) / 128.0, RGB
Output: (1, 512) float32 L2-normalised embedding
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from vms.config import get_settings
from vms.inference.messages import FaceWithEmbedding

logger = logging.getLogger(__name__)

_EMBED_INPUT_SIZE = 112


class AdaFaceEmbedder:
    """Wraps AdaFace IR50 ONNX model for 512-dim face embedding."""

    def __init__(
        self,
        session: Any,  # ort.InferenceSession -- stubs are incomplete; MagicMock in tests
        min_face_px: int | None = None,
    ) -> None:
        self._sess = session
        self._input_name: str = session.get_inputs()[0].name
        self._min_face_px = min_face_px if min_face_px is not None else get_settings().min_face_px

    @classmethod
    def from_path(cls, model_path: str) -> AdaFaceEmbedder:
        import onnxruntime as ort  # type: ignore[import-untyped]  # lazy: not available in test env

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        sess: Any = ort.InferenceSession(model_path, providers=providers)
        return cls(session=sess)

    def embed(
        self, face: FaceWithEmbedding, frame_bgr: np.ndarray[Any, np.dtype[Any]]
    ) -> FaceWithEmbedding | None:
        """Crop the face from frame and compute its embedding.

        Returns updated FaceWithEmbedding with embedding filled in,
        or None if the crop is empty or below min_face_px.
        """
        x1, y1, x2, y2 = face.bbox
        if (x2 - x1) < self._min_face_px or (y2 - y1) < self._min_face_px:
            return None
        crop: np.ndarray[Any, np.dtype[Any]] = frame_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        blob = self._preprocess(crop)
        raw: list[Any] = self._sess.run(None, {self._input_name: blob})
        emb_array: np.ndarray[Any, np.dtype[Any]] = raw[0][0].astype(np.float32)
        embedding = tuple(float(v) for v in emb_array)
        return FaceWithEmbedding(
            bbox=face.bbox,
            confidence=face.confidence,
            embedding=embedding,
        )

    def _preprocess(
        self, face_bgr: np.ndarray[Any, np.dtype[Any]]
    ) -> np.ndarray[Any, np.dtype[Any]]:
        face = cv2.resize(face_bgr, (_EMBED_INPUT_SIZE, _EMBED_INPUT_SIZE))
        face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB).astype(np.float32)
        face = (face - 127.5) / 128.0
        return np.transpose(face, (2, 0, 1))[None]
