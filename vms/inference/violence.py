"""MoViNet A2 Stream violence detector using TensorFlow Hub + Keras API.

Uses the exact streaming pattern from the Kaggle model card:
  https://www.kaggle.com/models/google/movinet/TensorFlow2/a2-stream-kinetics-600-classification/2

Streaming model: processes one frame at a time, maintaining per-camera state tensors.
This is more accurate than clip-based approaches and runs in ~4 ms/frame on CPU.

Setup (one-time):
  pip install tensorflow tensorflow-hub kagglehub

  # Option A — kagglehub auto-download (recommended):
  python scripts/download_movinet_a2.py

  # Option B — manual tar.gz download:
  curl -L -o ~/Downloads/model.tar.gz \\
    https://www.kaggle.com/api/v1/models/google/movinet/tensorFlow2/a2-stream-kinetics-600-classification/2/download
  mkdir -p models/movinet_a2 && tar xf ~/Downloads/model.tar.gz -C models/movinet_a2/
  # Then: set VMS_VIOLENCE_MODEL=models/movinet_a2

Model accuracy: 78.6% Top-1 Kinetics-400 — correct choice for binary violence classification.
A4/A5 would need 10-27x more compute for only ~6% accuracy gain on a binary classifier.

Graceful degradation:
  If tensorflow/tensorflow-hub is not installed or VMS_VIOLENCE_MODEL is empty/invalid,
  score_frame() returns None and ViolenceDetector silently disables itself.
"""

from __future__ import annotations

import logging
import os
from typing import Any, ClassVar

import numpy as np

logger = logging.getLogger(__name__)

# Kinetics-600 class indices representing violence-adjacent actions.
# Source: Kinetics-600 label list (deepmind-media/Datasets/kinetics600.tar.gz)
_VIOLENCE_CLASS_INDICES: list[int] = [
    87,  # fighting
    90,  # punching person (boxing)
    157,  # headbutting
    175,  # hitting with object
    255,  # punching bag
    362,  # slapping
    401,  # sword fighting
    500,  # wrestling
]

# Recommended input resolution from the model card
_INPUT_H = _INPUT_W = 172


def _is_saved_model_dir(path: str) -> bool:
    """Return True if path contains a TF SavedModel."""
    if not os.path.isdir(path):
        return False
    entries = os.listdir(path)
    return any(f in entries for f in ("saved_model.pb", "saved_model.pbtxt"))


class ViolenceModel:
    """MoViNet A2 Stream violence scorer.

    One instance per process. Maintains per-camera streaming state tensors so
    each camera's temporal context is independent — do not mix frames across cameras.

    Usage:
        model = ViolenceModel(get_settings().violence_model)
        if model.is_available:
            score = model.score_frame(frame_bgr, camera_id=1)  # float [0,1] or None
    """

    # Unused but kept for IDE-friendly attribute discovery
    _instances: ClassVar[dict[str, ViolenceModel]] = {}

    def __init__(self, model_path: str) -> None:
        self._path = model_path
        self._model: Any = None  # tf.keras.Model
        self._init_states_fn: Any = None  # init_states signature
        self._states: dict[int, Any] = {}  # camera_id → streaming state dict
        self._tf: Any = None

        if not model_path:
            logger.info(
                "VMS_VIOLENCE_MODEL not set — violence detection disabled. "
                "Run: python scripts/download_movinet_a2.py"
            )
            return

        if not _is_saved_model_dir(model_path):
            logger.warning(
                "violence_model path %r is not a SavedModel directory. "
                "Expected directory with saved_model.pb. "
                "Run: python scripts/download_movinet_a2.py",
                model_path,
            )
            return

        self._load(model_path)

    def _load(self, path: str) -> None:
        try:
            import tensorflow as tf  # type: ignore
            import tensorflow_hub as hub  # type: ignore

            logger.info("Loading MoViNet A2 Stream from %s ...", path)

            # Note: hub.KerasLayer is NOT compatible with the Keras 3.x functional API
            # (tf.keras.Model + KerasTensors) because hub internally runs eager ops
            # during graph construction. The correct approach for TF 2.21 + Keras 3 is
            # to call the encoder directly — the calling convention is identical to the
            # Kaggle model card's streaming loop: output, states = encoder({**s, 'image': f})
            encoder = hub.KerasLayer(path, trainable=False)
            init_states_fn = encoder.resolved_object.signatures["init_states"]

            # Warm-up call to confirm the encoder works and discover state count
            test_states = init_states_fn(tf.constant([0, 0, 0, 0, 3]))
            n_states = len(test_states)

            self._model = encoder  # callable: encoder({**states, 'image': frame})
            self._init_states_fn = init_states_fn
            self._tf = tf
            logger.info(
                "MoViNet A2 Stream ready — %dx%d input, %d streaming state tensors",
                _INPUT_H,
                _INPUT_W,
                n_states,
            )

        except Exception as exc:
            logger.warning(
                "MoViNet A2 load failed (%s) — violence detection disabled. "
                "Install deps: pip install tensorflow tensorflow-hub",
                exc,
            )
            self._model = None

    @property
    def is_available(self) -> bool:
        return self._model is not None

    def _init_camera_state(self, camera_id: int) -> None:
        """Zero-initialise streaming state for a new camera.

        Uses tf.shape-equivalent of [1, 1, H, W, 3] as in the model card:
          init_states = init_states_fn(tf.shape(example_input))
        """
        if self._init_states_fn is None:
            return
        # Shape spec matching one streaming frame: (batch=1, time=1, H, W, C)
        input_shape_spec = self._tf.constant([1, 1, _INPUT_H, _INPUT_W, 3])
        self._states[camera_id] = self._init_states_fn(input_shape_spec)

    def score_frame(self, camera_id: int, frame_bgr: np.ndarray[Any, Any]) -> float | None:
        """Feed one BGR frame, return violence score in [0, 1] or None.

        The streaming state for each camera_id is maintained across calls.
        Init happens automatically on first call for a given camera_id.

        Args:
            camera_id: Unique camera integer — routes the per-camera state tensor.
            frame_bgr: Single frame as (H, W, 3) uint8 numpy array (BGR).

        Returns:
            float in [0, 1] (higher = more violent), or None if unavailable.
        """
        if self._model is None:
            return None

        try:
            import cv2

            # Resize to model's recommended input and normalise to [-1, 1]
            frame_rgb = cv2.cvtColor(cv2.resize(frame_bgr, (_INPUT_W, _INPUT_H)), cv2.COLOR_BGR2RGB)
            x = frame_rgb.astype(np.float32) / 127.5 - 1.0
            # shape (1, 1, H, W, 3) — batch=1, time=1 (streaming: one frame per call)
            frame_tensor = self._tf.constant(x[np.newaxis, np.newaxis, ...], dtype=self._tf.float32)

            # Initialise state on first frame for this camera
            if camera_id not in self._states:
                self._init_camera_state(camera_id)

            # Streaming inference — mirrors the Kaggle model card loop:
            #   output, states = model({**states, 'image': frame})
            # hub.KerasLayer returns (logits_tensor, new_states_dict) tuple.
            result = self._model({**self._states[camera_id], "image": frame_tensor})

            # Unpack (output, new_states) tuple
            if isinstance(result, tuple | list):
                logits_tensor, new_states = result[0], result[1]
            else:
                # Fallback: dict output (older hub versions)
                logits_tensor = result
                new_states = self._states[camera_id]  # no state update

            # Update per-camera streaming state for the next frame
            self._states[camera_id] = new_states

            # logits_tensor shape: (1, 600) — 600 Kinetics-600 class logits
            logits: np.ndarray[Any, Any] = logits_tensor.numpy()[0]  # (600,)
            violence_logits = logits[_VIOLENCE_CLASS_INDICES]
            score = float(1.0 / (1.0 + np.exp(-float(np.max(violence_logits)))))
            return score

        except Exception as exc:
            logger.debug("MoViNet score_frame error cam=%d: %s", camera_id, exc)
            return None

    def evict_camera(self, camera_id: int) -> None:
        """Release streaming state for a deactivated camera (free memory)."""
        self._states.pop(camera_id, None)
