"""Body Re-ID embedders.

Two implementations — same embed() interface, selected by create_body_embedder():

  TransReIDBodyEmbedder — ViT-B/16+ICS msmt17 ONNX (768-dim, 384x128).  Current production.
                          Requires onnxruntime. Export: python scripts/export_transreid_onnx.py
                          Calibrated 2026-06-16; thresholds: confirmed=0.65, cross_cam=0.70.

  BodyEmbedder          — OSNet AIN x1.0 msmt17 (512-dim, 256x128).  Legacy / fallback.
                          Requires torchreid. Model file deleted from this deployment.
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


class BodyEmbedder:
    """Wraps OSNet AIN x1.0 msmt17 via Torchreid FeatureExtractor for 512-dim body embeddings."""

    def __init__(self, model_path: str, device: str = "cuda") -> None:
        try:
            from torchreid.utils import FeatureExtractor  # type: ignore[import-not-found]

            self._extractor: Any = FeatureExtractor(
                model_name="osnet_ain_x1_0",
                model_path=model_path,
                device=device,
                verbose=False,
            )
            self._available = True
            logger.info(
                "BodyEmbedder: osnet_ain_x1_0 msmt17 loaded from %s (device=%s)", model_path, device
            )
        except ImportError:
            logger.warning(
                "torchreid not installed — BodyEmbedder disabled. "
                "pip install torchreid (see scripts/download_osnet_ain_msmt17.py)"
            )
            self._extractor = None
            self._available = False
        except Exception as exc:
            logger.warning("BodyEmbedder failed to load model %s: %s", model_path, exc)
            self._extractor = None
            self._available = False

    def embed(self, crop_bgr: np.ndarray[Any, Any]) -> tuple[tuple[float, ...], float]:
        """Return (embedding, pre_norm_quality) tuple.

        embedding: 512-dim L2-normalised vector, or () on failure.
        pre_norm_quality: L2 norm before normalisation; 0.0 on failure.
        """
        if not self._available or self._extractor is None:
            return (), 0.0
        h, w = crop_bgr.shape[:2]
        if h < _MIN_H or w < _MIN_W:
            return (), 0.0
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        import torch

        with torch.no_grad():
            features = self._extractor([crop_rgb])  # (1, 512) tensor
        vec: np.ndarray[Any, Any] = features[0].cpu().numpy().astype(np.float32)
        quality_norm = float(np.linalg.norm(vec))
        if quality_norm > 1e-8:
            vec = vec / quality_norm
        return tuple(float(x) for x in vec), quality_norm


class TransReIDBodyEmbedder:
    """ViT-B/16+ICS msmt17 ONNX body Re-ID embedder — 768-dim L2-normalised output.

    Drop-in replacement for BodyEmbedder. Swap in by changing the embedder construction
    in the engine — the embed() signature is identical.

    Input:  BGR numpy crop, any size >= 16h x 8w; resized internally to 384x128.
    Output: 768-dim L2-normalised embedding as tuple[float, ...], or () on failure.

    Export the ONNX first:
        python scripts/export_transreid_onnx.py
    Then activate via config:
        VMS_TRANSREID_BODY_MODEL=models/transreid_body_msmt17.onnx

    NOTE: reid_body_confirmed_sim (currently 0.51, calibrated for OSNet) must be
    re-calibrated on real footage before deploying this embedder in production.
    Mandatory /advisor before changing that threshold (CLAUDE.md §0.5).
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
        """Return (embedding, pre_norm_quality) tuple.

        embedding: 768-dim L2-normalised vector, or () on failure.
        pre_norm_quality: L2 norm before normalisation; 0.0 on failure.
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
        quality_norm = float(np.linalg.norm(emb))
        if quality_norm > 1e-8:
            emb = emb / quality_norm
        return tuple(float(x) for x in emb), quality_norm

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


def create_body_embedder(
    transreid_path: str = "",
    osnet_path: str = "",
    device: str = "cpu",
) -> "BodyEmbedder | TransReIDBodyEmbedder | None":
    """Return the best available body embedder based on configured model paths.

    Priority: TransReID ONNX > OSNet torchreid > None.
    TransReID is preferred when both paths are set because it uses onnxruntime
    (no torch dependency) and is lighter on CPU.

    Pass empty string or omit a path to skip that embedder.
    Returns None when no valid model path is provided.
    """
    import os

    if transreid_path and os.path.exists(transreid_path):
        return TransReIDBodyEmbedder(transreid_path)
    if osnet_path and os.path.exists(osnet_path):
        return BodyEmbedder(osnet_path, device=device)
    return None
