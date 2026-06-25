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

import logging
from typing import Any, Protocol, runtime_checkable

import cv2
import numpy as np

from vms.config import get_settings
from vms.inference.body_embedder import transreid_preprocess
from vms.inference.detector import scrfd_decode, scrfd_preprocess
from vms.inference.embedder import _align_face, adaface_preprocess
from vms.inference.messages import FaceWithEmbedding
from vms.inference.ppe import _MIN_CROP, ppe_decode, ppe_preprocess
from vms.inference.triton_client import TritonModelClient

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Triton backend — GPU kernel via gRPC (Phase 6c Task 4)
# ---------------------------------------------------------------------------


def _discover_model_io(url: str, model_name: str) -> tuple[str, list[str]]:
    """Query Triton server for the first input name and all output names of a model."""
    from vms.inference.triton_client import _import_grpc

    grpc = _import_grpc()
    client = grpc.InferenceServerClient(url=url)
    meta = client.get_model_metadata(model_name)
    input_name: str = meta.inputs[0].name
    output_names: list[str] = [o.name for o in meta.outputs]
    return input_name, output_names


class TritonInferenceBackend:
    """Routes all GPU kernels through Triton Inference Server via gRPC.

    Pre/post-processing (letterbox, normalise, decode, L2-normalise) runs
    in-process using the same module-level helpers as the ORT path, so
    embedding distributions are numerically identical (cosine ≥ 0.9999).

    Startup protocol:
      1. Query each model's tensor names from the Triton server.
      2. Create a TritonModelClient per model.
      3. Call check_health() on every client — fail-fast if any model is not ready.
    """

    def __init__(self, url: str) -> None:
        settings = get_settings()
        self._conf_thres: float = settings.scrfd_conf
        self._nms_thres: float = 0.35
        self._min_face_px: int = settings.min_face_px
        self._min_blur: float = settings.min_blur

        for model_name in ("scrfd", "adaface", "transreid", "ppe"):
            inp, outs = _discover_model_io(url, model_name)
            client = TritonModelClient(url, model_name, inp, outs)
            client.check_health()
            setattr(self, f"_{model_name}", client)

    def detect(self, frame_bgr: np.ndarray[Any, Any]) -> tuple[FaceWithEmbedding, ...]:
        blob, det_scale = scrfd_preprocess(frame_bgr)
        outputs: list[Any] = self._scrfd.infer(blob)  # type: ignore[attr-defined]
        return tuple(
            scrfd_decode(outputs, det_scale, self._conf_thres, self._nms_thres, self._min_face_px)
        )

    def embed(
        self, face: FaceWithEmbedding, frame_bgr: np.ndarray[Any, Any]
    ) -> FaceWithEmbedding | None:
        x1, y1, x2, y2 = face.bbox
        if (x2 - x1) < self._min_face_px or (y2 - y1) < self._min_face_px:
            return None

        if face.keypoints:
            aligned = _align_face(frame_bgr, face.keypoints)
            crop: np.ndarray[Any, Any] = aligned if aligned is not None else frame_bgr[y1:y2, x1:x2]
        else:
            crop = frame_bgr[y1:y2, x1:x2]

        if crop.size == 0:
            return None

        if float(cv2.Laplacian(crop, cv2.CV_64F).var()) < self._min_blur:
            return None

        blob = adaface_preprocess(crop)
        raw: list[Any] = self._adaface.infer(blob)  # type: ignore[attr-defined]
        emb_array = raw[0][0].astype(np.float32)
        norm = np.linalg.norm(emb_array)
        quality_norm = float(norm)
        if norm > 0:
            emb_array = emb_array / norm

        return FaceWithEmbedding(
            bbox=face.bbox,
            confidence=face.confidence,
            embedding=tuple(float(v) for v in emb_array),
            face_quality_norm=quality_norm,
        )

    def embed_body(self, torso_crop: np.ndarray[Any, Any]) -> tuple[tuple[float, ...], float]:
        h, w = torso_crop.shape[:2]
        if h < 16 or w < 8:
            return (), 0.0

        blob = transreid_preprocess(torso_crop)
        raw = self._transreid.infer(blob)  # type: ignore[attr-defined]
        emb = raw[0][0].astype(np.float32)
        norm = float(np.linalg.norm(emb))
        emb = emb / norm if norm > 1e-8 else emb
        quality = float(cv2.Laplacian(torso_crop, cv2.CV_64F).var())
        return tuple(float(x) for x in emb), quality

    def score_ppe(self, crop_bgr: np.ndarray[Any, Any]) -> dict[str, float] | None:
        h, w = crop_bgr.shape[:2]
        if h < _MIN_CROP or w < _MIN_CROP:
            return None

        tensor = ppe_preprocess(crop_bgr)
        raw = self._ppe.infer(tensor)  # type: ignore[attr-defined]
        return ppe_decode(raw[0])
