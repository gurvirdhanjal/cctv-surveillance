"""R(2+1)D-18 violence scorer (torchvision — no TensorFlow required).

Replaces MoViNet A2 Stream with torchvision R(2+1)D-18 pretrained on Kinetics-400.
No additional dependencies beyond torch/torchvision already in requirements.txt.

Model: 3D ResNet R(2+1)D-18, 79.8% Top-1 Kinetics-400 (KINETICS400_V1 weights).
Input: 16-frame clip at 112x112 RGB, normalised with Kinetics-400 mean/std.
Violence score: sigmoid(max logit) over violence-adjacent Kinetics-400 classes.

Violence-adjacent K400 classes resolved by name at load time from the weights
metadata, so index lookups stay correct across torchvision releases.

Per-camera clip buffer accumulates frames; inference runs every `clip_stride`
frames to control throughput. The last computed score is returned between
inference runs so callers never block waiting for a new clip.

To pre-cache the ~130 MB weights before first use (avoids download on startup):
  from torchvision.models.video import R2Plus1D_18_Weights, r2plus1d_18
  import torch
  m = r2plus1d_18(weights=R2Plus1D_18_Weights.KINETICS400_V1)
  torch.save(m.state_dict(), "models/r2plus1d_18_violence.pt")
  # Then set: VMS_VIOLENCE_MODEL=models/r2plus1d_18_violence.pt
"""

from __future__ import annotations

import logging
import os
from collections import deque
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Violence-adjacent class names from Kinetics-400.
# Indices are resolved at load time from the weights metadata (name-based lookup)
# so they remain correct across torchvision releases.
_VIOLENCE_CLASS_NAMES: frozenset[str] = frozenset(
    {
        "arm wrestling",
        "drop kicking",
        "faceplanting",
        "headbutting",
        "high kick",
        "side kick",
        "slapping",
        "sword fighting",
        "wrestling",
    }
)

# Fallback indices (alphabetically-sorted K400, torchvision 0.15.x) used only when
# the weights metadata does not include category names.
_VIOLENCE_CLASS_INDICES_FALLBACK: list[int] = [6, 103, 120, 149, 151, 286, 294, 323, 374]

# R(2+1)D-18 KINETICS400_V1 normalisation constants (mean/std per channel, RGB order)
_INPUT_H = _INPUT_W = 112
_KINETICS_MEAN = np.array([0.43216, 0.394666, 0.37645], dtype=np.float32)
_KINETICS_STD = np.array([0.22803, 0.22145, 0.216989], dtype=np.float32)


class ViolenceModel:
    """R(2+1)D-18 clip-based violence scorer — one instance per process.

    Maintains a per-camera frame buffer; runs inference every `clip_stride` frames.
    Returns the last computed score between inference runs for low-latency response.

    Usage:
        model = ViolenceModel(get_settings().violence_model)
        if model.is_available:
            score = model.score_frame(camera_id=1, frame_bgr=frame)  # float [0, 1] | None
    """

    def __init__(
        self,
        model_path: str,
        clip_frames: int = 16,
        clip_stride: int = 8,
    ) -> None:
        self._path = model_path
        self._clip_frames = clip_frames
        self._clip_stride = clip_stride
        self._model: Any = None
        self._device: str = "cpu"
        self._violence_indices: list[int] = []
        self._buffers: dict[int, deque[np.ndarray[Any, Any]]] = {}
        self._counters: dict[int, int] = {}
        self._last_scores: dict[int, float] = {}

        if not model_path:
            logger.info("VMS_VIOLENCE_MODEL not set — violence detection disabled.")
            return

        self._load(model_path)

    def _load(self, path: str) -> None:
        try:
            import torch
            from torchvision.models.video import (  # type: ignore[import-untyped]
                R2Plus1D_18_Weights,
                r2plus1d_18,
            )

            weights = R2Plus1D_18_Weights.KINETICS400_V1

            # Resolve violence class indices from weights metadata (name-based — robust).
            categories: list[str] = list(weights.meta.get("categories", []))
            if categories:
                self._violence_indices = [
                    i for i, name in enumerate(categories) if name in _VIOLENCE_CLASS_NAMES
                ]
                matched = {categories[i] for i in self._violence_indices}
                logger.info(
                    "R(2+1)D-18 violence classes (%d matched): %s",
                    len(self._violence_indices),
                    sorted(matched),
                )
            else:
                self._violence_indices = _VIOLENCE_CLASS_INDICES_FALLBACK
                logger.info(
                    "R(2+1)D-18 weights missing category metadata — using fallback indices %s",
                    self._violence_indices,
                )

            # Determine how to obtain weights.
            # A .pt/.pth extension → local state-dict file; directory or anything
            # else (including old MoViNet SavedModel paths) → auto-download.
            is_pt_ext = not os.path.isdir(path) and path.endswith((".pt", ".pth"))

            if is_pt_ext:
                if not os.path.isfile(path):
                    logger.warning(
                        "violence_model path %r not found — violence detection disabled.", path
                    )
                    return
                logger.info("Loading R(2+1)D-18 weights from %s …", path)
                model = r2plus1d_18(weights=None)
                model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
            else:
                if os.path.isdir(path):
                    logger.info(
                        "MoViNet SavedModel detected at %r — switching to R(2+1)D-18 "
                        "(TensorFlow not required). First run downloads ~130 MB to torch cache.",
                        path,
                    )
                else:
                    logger.info("Loading R(2+1)D-18 (first run downloads ~130 MB to torch cache) …")
                model = r2plus1d_18(weights=weights)

            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = model.to(self._device).eval()
            logger.info(
                "R(2+1)D-18 violence detector ready on %s — %d-frame clip, stride=%d",
                self._device,
                self._clip_frames,
                self._clip_stride,
            )

        except Exception as exc:
            logger.warning(
                "R(2+1)D-18 load failed (%s) — violence detection disabled. "
                "Ensure torchvision>=0.13 is installed.",
                exc,
            )
            self._model = None

    @property
    def is_available(self) -> bool:
        return self._model is not None

    def score_frame(self, camera_id: int, frame_bgr: np.ndarray[Any, Any]) -> float | None:
        """Feed one BGR frame; return violence score in [0, 1] or None.

        Buffers frames per camera_id and runs clip inference every `clip_stride` frames.
        Returns the last computed score between inference runs.

        Args:
            camera_id: Unique camera integer for per-camera buffer routing.
            frame_bgr: Single (H, W, 3) uint8 BGR numpy array.

        Returns:
            float in [0, 1] (higher = more violent activity), or None before
            the first clip completes for this camera_id.
        """
        if self._model is None:
            return None

        try:
            import torch

            if camera_id not in self._buffers:
                self._buffers[camera_id] = deque(maxlen=self._clip_frames)
                self._counters[camera_id] = 0

            resized = cv2.resize(frame_bgr, (_INPUT_W, _INPUT_H))
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            x = rgb.astype(np.float32) / 255.0
            x = (x - _KINETICS_MEAN) / _KINETICS_STD  # (H, W, C) normalised

            self._buffers[camera_id].append(x)
            self._counters[camera_id] += 1

            # Run inference when buffer holds a full clip and stride elapses.
            if (
                len(self._buffers[camera_id]) == self._clip_frames
                and self._counters[camera_id] % self._clip_stride == 0
            ):
                # (T, H, W, C) → (C, T, H, W) → (1, C, T, H, W)
                clip = np.stack(list(self._buffers[camera_id]), axis=0)
                clip_t = torch.from_numpy(clip).permute(3, 0, 1, 2).unsqueeze(0).to(self._device)
                with torch.no_grad():
                    logits: Any = self._model(clip_t)[0]  # (400,)

                if self._violence_indices:
                    v_idx = torch.tensor(
                        self._violence_indices, dtype=torch.long, device=self._device
                    )
                    score = float(torch.sigmoid(logits[v_idx].max()).item())
                else:
                    score = 0.0

                self._last_scores[camera_id] = score
                logger.debug(
                    "violence cam=%d score=%.3f (top class=%d)",
                    camera_id,
                    score,
                    int(logits.argmax().item()),
                )

        except Exception as exc:
            logger.debug("R(2+1)D-18 score_frame error cam=%d: %s", camera_id, exc)

        return self._last_scores.get(camera_id)

    def evict_camera(self, camera_id: int) -> None:
        """Release per-camera buffer when a camera is deactivated."""
        self._buffers.pop(camera_id, None)
        self._counters.pop(camera_id, None)
        self._last_scores.pop(camera_id, None)
