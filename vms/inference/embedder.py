"""AdaFace IR101/WebFace12M face embedder (ONNX or InsightFace fallback).

Input:  (1, 3, 112, 112) float32, normalised (pixel - 127.5) / 127.5, RGB
Output: (1, 512) float32 L2-normalised embedding

CVLFace models (IR101/WebFace12M and newer) expect RGB input.
OpenCV frames are BGR — _preprocess converts before normalising.

When the detector provides 5-point keypoints (scrfd_10g_bnkps.onnx), the embedder
performs an affine warp to the AdaFace canonical 112×112 pose before embedding.
Without keypoints (fallback detectors) it falls back to bbox crop + resize.

Model loading strategy (tried in order):
  1. ONNX file at model_path — fastest, recommended for production.
  2. InsightFace FaceAnalysis w/ recognition module — auto-downloads buffalo_l.
     Install with: pip install insightface onnxruntime
  3. Null embedder (graceful degradation) — embed() always returns None,
     so tracklets carry empty embeddings → FAISS never matches → UNKNOWN_PERSON.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import cv2
import numpy as np

from vms.config import get_settings
from vms.inference.messages import FaceWithEmbedding

# Standard AdaFace/ArcFace 5-point reference landmarks for 112×112 canonical crop.
# Order: left-eye, right-eye, nose-tip, left-mouth, right-mouth.
_ALIGN_DST = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def _align_face(
    img_bgr: np.ndarray[Any, np.dtype[Any]],
    keypoints: tuple[tuple[float, float], ...],
) -> np.ndarray[Any, np.dtype[Any]] | None:
    """Affine-warp face crop to 112×112 using 5-point landmarks.

    Returns None when estimateAffinePartial2D fails (degenerate keypoints).
    """
    src = np.array(keypoints, dtype=np.float32)
    M, _ = cv2.estimateAffinePartial2D(src, _ALIGN_DST, method=cv2.LMEDS)
    if M is None:
        return None
    return cv2.warpAffine(img_bgr, M, (_EMBED_INPUT_SIZE, _EMBED_INPUT_SIZE), flags=cv2.INTER_LINEAR)

logger = logging.getLogger(__name__)

_EMBED_INPUT_SIZE = 112


class _InsightFaceEmbedder:
    """Uses InsightFace ArcFace recognition model for 512-dim embeddings."""

    def __init__(self, app: Any, min_face_px: int) -> None:
        self._app = app
        self._min_face_px = min_face_px

    def embed(
        self, face: FaceWithEmbedding, frame_bgr: np.ndarray[Any, np.dtype[Any]]
    ) -> FaceWithEmbedding | None:
        x1, y1, x2, y2 = face.bbox
        if (x2 - x1) < self._min_face_px or (y2 - y1) < self._min_face_px:
            return None
        faces = self._app.get(frame_bgr)
        # Find the InsightFace detection whose bbox best overlaps our bbox
        best: Any = None
        best_iou = 0.0
        for f in faces:
            fx1, fy1, fx2, fy2 = (int(v) for v in f.bbox)
            ix1, iy1 = max(x1, fx1), max(y1, fy1)
            ix2, iy2 = min(x2, fx2), min(y2, fy2)
            inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            if inter == 0:
                continue
            union = (x2 - x1) * (y2 - y1) + (fx2 - fx1) * (fy2 - fy1) - inter
            iou = inter / union if union else 0.0
            if iou > best_iou:
                best_iou = iou
                best = f
        if best is None or best.embedding is None:
            return None
        emb = best.embedding.astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return FaceWithEmbedding(
            bbox=face.bbox,
            confidence=face.confidence,
            embedding=tuple(float(v) for v in emb),
        )


class _NullEmbedder:
    """No-op embedder — returns None for every face (no identity matching)."""

    def embed(
        self, face: FaceWithEmbedding, frame_bgr: np.ndarray[Any, np.dtype[Any]]
    ) -> FaceWithEmbedding | None:
        return None


class AdaFaceEmbedder:
    """Wraps AdaFace IR50 ONNX model for 512-dim face embedding.

    When model file is absent, falls back to InsightFace auto-download.
    When neither is available, embed() returns None (graceful degradation).
    """

    def __init__(
        self,
        session: Any,  # ort.InferenceSession -- stubs are incomplete; MagicMock in tests
        min_face_px: int | None = None,
    ) -> None:
        self._sess = session
        self._input_name: str = session.get_inputs()[0].name
        self._min_face_px = min_face_px if min_face_px is not None else get_settings().min_face_px
        self._min_blur: float = get_settings().min_blur

    @classmethod
    def from_path(cls, model_path: str) -> AdaFaceEmbedder | _InsightFaceEmbedder | _NullEmbedder:
        """Load from ONNX file, InsightFace fallback, or null embedder."""
        settings = get_settings()
        min_px = settings.min_face_px

        if os.path.exists(model_path):
            try:
                import onnxruntime as ort  # type: ignore[import-untyped]  # lazy

                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                sess: Any = ort.InferenceSession(model_path, providers=providers)
                logger.info("AdaFaceEmbedder loaded from %s", model_path)
                return cls(session=sess, min_face_px=min_px)
            except Exception as exc:
                logger.warning("ONNX load failed (%s); trying InsightFace fallback", exc)

        try:
            from insightface.app import FaceAnalysis  # type: ignore[import-not-found]

            logger.info("AdaFace ONNX not found; loading InsightFace buffalo_l for embedding")
            app = FaceAnalysis(
                name="buffalo_l",
                allowed_modules=["detection", "recognition"],
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            app.prepare(ctx_id=0, det_size=(_EMBED_INPUT_SIZE * 4, _EMBED_INPUT_SIZE * 4))
            return _InsightFaceEmbedder(app, min_px)
        except Exception:
            pass

        logger.warning(
            "Face embedder unavailable — ONNX file %s not found and InsightFace not installed. "
            "Persons will not be identified (all UNKNOWN). "
            "Fix: pip install insightface  OR  download %s",
            model_path,
            model_path,
        )
        return _NullEmbedder()

    def embed(
        self, face: FaceWithEmbedding, frame_bgr: np.ndarray[Any, np.dtype[Any]]
    ) -> FaceWithEmbedding | None:
        """Crop/align the face from frame and compute its embedding.

        Uses 5-point affine alignment when keypoints are present (scrfd_10g_bnkps).
        Falls back to bbox crop+resize when keypoints are absent.
        Returns None if the crop is empty or below min_face_px.
        """
        x1, y1, x2, y2 = face.bbox
        if (x2 - x1) < self._min_face_px or (y2 - y1) < self._min_face_px:
            return None

        if face.keypoints:
            aligned = _align_face(frame_bgr, face.keypoints)
            if aligned is not None:
                crop: np.ndarray[Any, np.dtype[Any]] = aligned
            else:
                crop = frame_bgr[y1:y2, x1:x2]
        else:
            crop = frame_bgr[y1:y2, x1:x2]

        if crop.size == 0:
            return None

        blob = self._preprocess(crop)
        raw: list[Any] = self._sess.run(None, {self._input_name: blob})
        emb_array: np.ndarray[Any, np.dtype[Any]] = raw[0][0].astype(np.float32)
        # CVLFace IR101 backbone does not L2-normalise internally — normalise here.
        # FAISS cosine search and adaface_min_sim both assume unit-norm embeddings.
        norm = np.linalg.norm(emb_array)
        if norm > 0:
            emb_array = emb_array / norm
        embedding = tuple(float(v) for v in emb_array)
        return FaceWithEmbedding(
            bbox=face.bbox,
            confidence=face.confidence,
            embedding=embedding,
        )

    def _preprocess(
        self, face_bgr: np.ndarray[Any, np.dtype[Any]]
    ) -> np.ndarray[Any, np.dtype[Any]]:
        # CVLFace models (IR101/WebFace12M) expect RGB input.
        # OpenCV is BGR-native, so we convert before normalising.
        # Normalisation: (pixel - 127.5) / 127.5  matches CVLFace to_input() exactly.
        face = cv2.resize(
            face_bgr, (_EMBED_INPUT_SIZE, _EMBED_INPUT_SIZE), interpolation=cv2.INTER_LANCZOS4
        )
        face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
        face = face.astype(np.float32)
        face = (face - 127.5) / 127.5
        return np.transpose(face, (2, 0, 1))[None]
