"""OSNet AIN body Re-ID embedder — Torchreid FeatureExtractor wrapper.

Model: osnet_ain_x1_0 trained on MSMT17, 512-dim L2-normalized output.
Input: BGR numpy crop (any size >=16h x 8w); resized internally to 256x128.

Install:  see scripts/download_osnet_ain_msmt17.py
Download: python scripts/download_osnet_ain_msmt17.py
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_MIN_H = 16
_MIN_W = 8


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

    def embed(self, crop_bgr: np.ndarray[Any, Any]) -> tuple[float, ...]:
        """Return 512-dim L2-normalized embedding, or () if crop is too small or model unavailable."""
        if not self._available or self._extractor is None:
            return ()
        h, w = crop_bgr.shape[:2]
        if h < _MIN_H or w < _MIN_W:
            return ()
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        import torch

        with torch.no_grad():
            features = self._extractor([crop_rgb])  # (1, 512) tensor
        vec: np.ndarray[Any, Any] = features[0].cpu().numpy().astype(np.float32)
        norm = float(np.linalg.norm(vec))
        if norm > 1e-8:
            vec = vec / norm
        return tuple(float(x) for x in vec)
