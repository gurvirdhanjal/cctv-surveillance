"""InferenceBackend Protocol and OrtInferenceBackend adapter (Phase 6c).

The Protocol defines the four methods InferenceEngine uses from the model stack:
  detect   — SCRFD face detection
  embed    — AdaFace face embedding
  embed_body — TransReID body embedding
  score_ppe  — SH17 PPE class scoring

OrtInferenceBackend is a thin adapter that delegates to the existing standalone
detector / embedder / body_embedder / ppe objects unchanged. It exists solely to
give TritonInferenceBackend (Task 4) a sibling with an identical signature so
InferenceEngine can swap between the two via a single config flag.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np

from vms.inference.messages import FaceWithEmbedding

# ---------------------------------------------------------------------------
# Structural protocols for the wrapped objects (used only for mypy)
# ---------------------------------------------------------------------------


class _HasDetect(Protocol):
    def detect(self, frame_bgr: np.ndarray[Any, Any]) -> list[FaceWithEmbedding]: ...


class _HasEmbed(Protocol):
    def embed(
        self, face: FaceWithEmbedding, frame_bgr: np.ndarray[Any, Any]
    ) -> FaceWithEmbedding | None: ...


class _HasEmbedBody(Protocol):
    def embed(self, crop_bgr: np.ndarray[Any, Any]) -> tuple[tuple[float, ...], float]: ...


class _HasScoreCrop(Protocol):
    def score_crop(self, crop_bgr: np.ndarray[Any, Any]) -> dict[str, float] | None: ...


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


@runtime_checkable
class InferenceBackend(Protocol):
    """Structural interface for the GPU model-stack used by InferenceEngine.

    Both OrtInferenceBackend (in-process ORT) and TritonInferenceBackend (gRPC)
    must satisfy this Protocol. The engine selects between them via the factory
    in engine.py based on VMS_GPU_TRITON_URL.
    """

    def detect(self, frame_bgr: np.ndarray[Any, Any]) -> tuple[FaceWithEmbedding, ...]: ...

    def embed(
        self, face: FaceWithEmbedding, frame_bgr: np.ndarray[Any, Any]
    ) -> FaceWithEmbedding | None: ...

    def embed_body(self, torso_crop: np.ndarray[Any, Any]) -> tuple[tuple[float, ...], float]: ...

    def score_ppe(self, crop_bgr: np.ndarray[Any, Any]) -> dict[str, float] | None: ...


# ---------------------------------------------------------------------------
# ORT adapter — pure pass-through, no behavior change
# ---------------------------------------------------------------------------


class OrtInferenceBackend:
    """Delegates all calls to the existing standalone detector / embedder objects.

    This adapter exists only to satisfy the InferenceBackend Protocol so the
    engine's _build_inference_backend factory (Task 5) can select between ORT
    and Triton at startup without touching the rest of the pipeline.
    """

    def __init__(
        self,
        detector: _HasDetect,
        embedder: _HasEmbed,
        body_embedder: _HasEmbedBody | None = None,
        ppe: _HasScoreCrop | None = None,
    ) -> None:
        self._detector = detector
        self._embedder = embedder
        self._body_embedder = body_embedder
        self._ppe = ppe

    def detect(self, frame_bgr: np.ndarray[Any, Any]) -> tuple[FaceWithEmbedding, ...]:
        return tuple(self._detector.detect(frame_bgr))

    def embed(
        self, face: FaceWithEmbedding, frame_bgr: np.ndarray[Any, Any]
    ) -> FaceWithEmbedding | None:
        return self._embedder.embed(face, frame_bgr)

    def embed_body(self, torso_crop: np.ndarray[Any, Any]) -> tuple[tuple[float, ...], float]:
        if self._body_embedder is None:
            return (), 0.0
        return self._body_embedder.embed(torso_crop)

    def score_ppe(self, crop_bgr: np.ndarray[Any, Any]) -> dict[str, float] | None:
        if self._ppe is None:
            return None
        return self._ppe.score_crop(crop_bgr)
