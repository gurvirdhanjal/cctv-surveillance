"""Violence detection model — MoViNet A0 (ONNX clip) or A2 Stream (TF SavedModel).

Two supported backends, selected automatically by the model path:

A0 ONNX (original, simpler):
  path = "models/movinet_a0.onnx"
  - Buffers 16 frames per camera
  - Single inference per clip → score [0, 1]
  - Requires onnxruntime

A2 Stream (TF SavedModel, recommended):
  path = directory returned by kagglehub or manually extracted tar.gz
  - Stateful: one frame at a time, per-camera state tensor
  - More accurate (Kinetics-600, 600 classes)
  - Requires tensorflow (pip install tensorflow)
  - Download once with:
      import kagglehub
      path = kagglehub.model_download(
          "google/movinet/tensorFlow2/a2-stream-kinetics-600-classification"
      )
      # Set VMS_VIOLENCE_MODEL=<path> in environment

Graceful degradation:
  If neither is loadable, score() returns None and the ViolenceDetector
  silently disables itself — all other anomaly detectors are unaffected.
"""

from __future__ import annotations

import logging
import os
from typing import Any, ClassVar

import numpy as np

logger = logging.getLogger(__name__)


def _is_saved_model_dir(path: str) -> bool:
    """A SavedModel directory contains saved_model.pb or saved_model.pbtxt."""
    if not os.path.isdir(path):
        return False
    files = os.listdir(path)
    return any(f in files for f in ("saved_model.pb", "saved_model.pbtxt"))


class _A2StreamBackend:
    """MoViNet A2 Stream backend using TensorFlow SavedModel.

    Processes one frame at a time with per-camera streaming state.
    The model returns logits for 600 Kinetics classes; we use the
    'fighting'/'violence' class indices to derive a score in [0,1].

    Kinetics-600 violence-adjacent class indices (approximate):
      87: "fighting"
    We take sigmoid of the max across these classes as the violence score.
    """

    # Kinetics-600 indices most associated with violence
    _VIOLENCE_CLASS_INDICES: ClassVar[list[int]] = [87, 90, 157, 175, 255, 288, 362, 401, 500]

    def __init__(self, model_dir: str) -> None:
        import tensorflow as tf  # type: ignore

        self._model = tf.saved_model.load(model_dir)
        self._infer = self._model.signatures["serving_default"]
        # Per-camera state dict: camera_id -> state tensor
        self._states: dict[int, Any] = {}
        self._tf = tf
        logger.info("MoViNet A2 Stream loaded from %s", model_dir)

    def score_frame(self, camera_id: int, frame_bgr: np.ndarray[Any, Any]) -> float | None:
        """Feed one frame, return violence score [0,1] or None on error."""
        import tensorflow as tf  # type: ignore

        try:
            # Resize to 224x224, convert BGR to RGB, normalise to [-1, 1]
            import cv2

            frame_rgb = cv2.cvtColor(cv2.resize(frame_bgr, (224, 224)), cv2.COLOR_BGR2RGB)
            x = frame_rgb.astype(np.float32) / 127.5 - 1.0
            # Shape: (1, 1, H, W, C) — batch=1, time=1
            x_tensor = tf.constant(x[np.newaxis, np.newaxis, ...], dtype=tf.float32)

            # Init or reuse state for this camera
            if camera_id not in self._states:
                self._states[camera_id] = self._build_init_state()

            outputs = self._infer(inputs=x_tensor, states=self._states[camera_id])

            # Update streaming state for next frame
            new_state_keys = [k for k in outputs if k.startswith("state")]
            if new_state_keys:
                self._states[camera_id] = {k: outputs[k] for k in new_state_keys}

            # Get logits from output
            logits_key = next((k for k in outputs if "logit" in k.lower()), None)
            if logits_key is None:
                logits_key = next(k for k in outputs if k not in new_state_keys)
            logits = outputs[logits_key].numpy()[0]  # (600,)

            # Sigmoid of max violence-class logit
            violence_logits = logits[self._VIOLENCE_CLASS_INDICES]
            score = float(1.0 / (1.0 + np.exp(-np.max(violence_logits))))
            return score

        except Exception as exc:
            logger.debug("A2 stream inference error: %s", exc)
            return None

    def _build_init_state(self) -> dict[str, Any]:
        """Build zero-initialised streaming state for a new camera."""
        import tensorflow as tf  # type: ignore

        init_fn = getattr(self._model, "init_states", None)
        if init_fn is not None:
            # (1, 1, 224, 224, 3) dummy input shape
            dummy = tf.zeros([1, 1, 224, 224, 3], dtype=tf.float32)
            result: dict[str, Any] = init_fn(dummy)
            return result
        # Fallback: discover state shapes from signature
        state_inputs = {
            k: v
            for k, v in self._infer.structured_input_signature[1].items()
            if k.startswith("state")
        }
        return {k: tf.zeros(v.shape) for k, v in state_inputs.items()}

    def evict_camera(self, camera_id: int) -> None:
        """Release streaming state for a camera that's no longer active."""
        self._states.pop(camera_id, None)


class ViolenceModel:
    """Unified violence model — auto-detects A0 ONNX or A2 Stream SavedModel.

    Public interface:
      score(clip_or_frame, camera_id) -> float | None
        For A0 (ONNX): clip is np.ndarray (16, H, W, 3) uint8
        For A2 (TF):   clip is np.ndarray (H, W, 3)  uint8, camera_id required
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._a0_session: Any = None
        self._a2_backend: _A2StreamBackend | None = None

        if not path:
            logger.warning("violence_model path not set; violence detection disabled")
            return

        if _is_saved_model_dir(path):
            self._load_a2(path)
        elif os.path.isfile(path) and path.endswith(".onnx"):
            self._load_a0_onnx(path)
        else:
            logger.warning(
                "violence model path %r is neither an ONNX file nor a SavedModel directory. "
                "Violence detection disabled. "
                "To download MoViNet A2 Stream: "
                "pip install kagglehub tensorflow && python scripts/download_movinet_a2.py",
                path,
            )

    def _load_a0_onnx(self, path: str) -> None:
        try:
            import onnxruntime as ort  # type: ignore[import-untyped]

            self._a0_session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
            logger.info("ViolenceModel: A0 ONNX loaded from %s", path)
        except Exception as exc:
            logger.warning("ViolenceModel A0 ONNX load failed (%s); disabled", exc)

    def _load_a2(self, path: str) -> None:
        try:
            self._a2_backend = _A2StreamBackend(path)
        except Exception as exc:
            logger.warning("ViolenceModel A2 Stream load failed (%s); disabled", exc)

    @property
    def is_a2_stream(self) -> bool:
        return self._a2_backend is not None

    @property
    def is_available(self) -> bool:
        return self._a0_session is not None or self._a2_backend is not None

    def score(
        self,
        frame_or_clip: np.ndarray[Any, Any],
        camera_id: int = 0,
    ) -> float | None:
        """Return violence score in [0, 1], or None if model unavailable.

        A0 mode: frame_or_clip is a (16, H, W, 3) uint8 clip.
        A2 mode: frame_or_clip is a (H, W, 3) uint8 single frame; camera_id required.
        """
        if self._a2_backend is not None:
            return self._a2_backend.score_frame(camera_id, frame_or_clip)

        if self._a0_session is not None:
            return self._score_a0(frame_or_clip)

        return None

    def _score_a0(self, clip: np.ndarray[Any, Any]) -> float | None:
        if clip.shape[0] != 16:
            return None
        x = (clip.astype(np.float32) / 255.0).transpose(0, 3, 1, 2)[np.newaxis, ...]
        name = self._a0_session.get_inputs()[0].name
        out = self._a0_session.run(None, {name: x})
        return float(out[0].ravel()[0])

    def evict_camera(self, camera_id: int) -> None:
        """Release A2 streaming state for a camera. No-op for A0."""
        if self._a2_backend is not None:
            self._a2_backend.evict_camera(camera_id)
