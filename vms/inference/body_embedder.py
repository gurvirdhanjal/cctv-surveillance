"""Body Re-ID embedder: TransReIDBodyEmbedder (ViT-B/16+ICS msmt17 ONNX, 768-dim, 384x128).

Calibrated 2026-06-16; thresholds: reid_body_confirmed_sim=0.65, reid_body_cross_cam_sim=0.70.
Any threshold change requires a mandatory /advisor session (CLAUDE.md §0.5).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_MIN_H = 16
_MIN_W = 8

# TransReID ViT-B/16+ICS input spec (confirmed from pos_embed [1,193,768], 2026-06-15)
_TRANSREID_H = 384
_TRANSREID_W = 128
_TRANSREID_EMBED_DIM = 768
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class TransReIDBodyEmbedder:
    """ViT-B/16+ICS msmt17 ONNX body Re-ID embedder — 768-dim L2-normalised output.

    Input:  BGR numpy crop, any size >= 16h x 8w; resized internally to 384x128.
    Output: 768-dim L2-normalised embedding as tuple[float, ...], or () on failure.

    Activate via config: VMS_TRANSREID_BODY_MODEL=models/transreid_body_msmt17.onnx
    """

    def __init__(self, model_path: str) -> None:
        self._sess: Any = None
        self._input_name: str = "input"
        self._available = False

        if not os.path.exists(model_path):
            logger.warning(
                "TransReIDBodyEmbedder: ONNX file not found at %s — embedder disabled. "
                "Export first: python scripts/export_transreid_onnx.py",
                model_path,
            )
            return

        try:
            import onnxruntime as ort  # type: ignore[import-untyped]

            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            self._sess = ort.InferenceSession(model_path, providers=providers)
            self._input_name = self._sess.get_inputs()[0].name
            self._available = True
            logger.info("TransReIDBodyEmbedder: loaded %s", model_path)
        except ImportError:
            logger.warning(
                "onnxruntime not installed — TransReIDBodyEmbedder disabled. "
                "pip install onnxruntime"
            )
        except Exception as exc:
            logger.warning("TransReIDBodyEmbedder failed to load %s: %s", model_path, exc)

    def embed(self, crop_bgr: np.ndarray[Any, Any]) -> tuple[tuple[float, ...], float]:
        """Return (embedding, quality) tuple.

        embedding: 768-dim L2-normalised vector, or () on failure.
        quality: Laplacian variance of the input crop (higher = sharper).
                 0.0 on failure. Note: semantically different from face_quality_norm
                 (which is AdaFace pre-norm L2). Both feed reid_quality_norm_floor but
                 that floor is 0.0 until separately calibrated per signal type.
        """
        if not self._available or self._sess is None:
            return (), 0.0
        h, w = crop_bgr.shape[:2]
        if h < _MIN_H or w < _MIN_W:
            return (), 0.0
        blob = self._preprocess(crop_bgr)
        raw: list[Any] = self._sess.run(None, {self._input_name: blob})
        emb: np.ndarray[Any, Any] = raw[0][0].astype(np.float32)
        # ONNX model includes F.normalize — re-normalise as a safety guard.
        norm = float(np.linalg.norm(emb))
        emb = emb / norm if norm > 1e-8 else emb
        quality = float(cv2.Laplacian(crop_bgr, cv2.CV_64F).var())
        return tuple(float(x) for x in emb), quality

    def _preprocess(self, crop_bgr: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        # TransReID uses ImageNet normalisation on RGB [0,1] float input.
        # OpenCV is BGR-native; resize first (cheaper on smaller image), then convert.
        resized = cv2.resize(
            crop_bgr, (_TRANSREID_W, _TRANSREID_H), interpolation=cv2.INTER_LANCZOS4
        )
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        rgb = (rgb - _IMAGENET_MEAN) / _IMAGENET_STD  # (H, W, 3)
        chw = np.transpose(rgb, (2, 0, 1))[None]  # (1, 3, H, W)
        return chw


def extract_torso_crop(
    frame_bgr: np.ndarray[Any, Any],
    bbox: tuple[int, int, int, int],
    keypoints: tuple[tuple[float, float, float], ...],
    conf_threshold: float,
    pad_fraction: float,
) -> np.ndarray[Any, Any]:
    """Return a torso-region crop using shoulder+hip keypoints, or the full-bbox crop on fallback.

    Falls back to the full bbox when: keypoints tuple has < 17 entries, fewer than 3 of the
    4 torso landmarks (KP 5,6,11,12) exceed conf_threshold, or the padded rect is degenerate
    (< _MIN_H x _MIN_W). Fail-open: behaviour is never worse than the raw bbox crop.
    """
    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = bbox
    x1c, y1c = max(0, x1), max(0, y1)
    x2c, y2c = min(w, x2), min(h, y2)
    fallback: np.ndarray[Any, Any] = frame_bgr[y1c:y2c, x1c:x2c]

    if len(keypoints) < 17:
        return fallback

    # COCO torso landmarks: left_shoulder=5, right_shoulder=6, left_hip=11, right_hip=12
    valid: list[tuple[float, float]] = []
    for idx in (5, 6, 11, 12):
        kx, ky, kc = keypoints[idx]
        if kc >= conf_threshold:
            valid.append((kx, ky))

    if len(valid) < 3:
        return fallback

    xs = [p[0] for p in valid]
    ys = [p[1] for p in valid]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad_x = (max_x - min_x) * pad_fraction
    pad_y = (max_y - min_y) * pad_fraction
    tx1 = max(0, int(min_x - pad_x))
    ty1 = max(0, int(min_y - pad_y))
    tx2 = min(w, int(max_x + pad_x))
    ty2 = min(h, int(max_y + pad_y))

    if (ty2 - ty1) < _MIN_H or (tx2 - tx1) < _MIN_W:
        return fallback

    return frame_bgr[ty1:ty2, tx1:tx2]


def create_body_embedder(transreid_path: str = "") -> TransReIDBodyEmbedder | None:
    """Return a TransReIDBodyEmbedder when the ONNX path exists, else None."""
    if transreid_path and os.path.exists(transreid_path):
        return TransReIDBodyEmbedder(transreid_path)
    return None
