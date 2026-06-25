"""Tests for InferenceBackend Protocol + OrtInferenceBackend adapter (Phase 6c Task 3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from vms.inference.messages import FaceWithEmbedding


def _make_face() -> FaceWithEmbedding:
    return FaceWithEmbedding(
        bbox=(10, 10, 50, 50),
        confidence=0.9,
        embedding=(0.1,) * 512,
    )


def _make_ort_backend(
    *,
    detector: object | None = None,
    embedder: object | None = None,
    body_embedder: object | None = None,
    ppe: object | None = None,
) -> object:
    from vms.inference.backend import OrtInferenceBackend

    det = detector or MagicMock()
    emb = embedder or MagicMock()
    return OrtInferenceBackend(
        detector=det,
        embedder=emb,
        body_embedder=body_embedder,
        ppe=ppe,
    )


# ---------------------------------------------------------------------------
# Delegation — detect + embed
# ---------------------------------------------------------------------------


def test_ort_backend_delegates_detect_to_detector() -> None:
    """detect() must forward the frame to detector.detect() and return its results as a tuple."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    face = _make_face()

    mock_detector = MagicMock()
    mock_detector.detect.return_value = [face]

    backend = _make_ort_backend(detector=mock_detector)
    result = backend.detect(frame)  # type: ignore[union-attr]

    mock_detector.detect.assert_called_once_with(frame)
    assert result == (face,)


def test_ort_backend_delegates_embed_to_embedder() -> None:
    """embed() must forward face + frame to embedder.embed() and pass through its return value."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    face = _make_face()
    embedded = FaceWithEmbedding(bbox=(10, 10, 50, 50), confidence=0.9, embedding=(0.5,) * 512)

    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = embedded

    backend = _make_ort_backend(embedder=mock_embedder)
    result = backend.embed(face, frame)  # type: ignore[union-attr]

    mock_embedder.embed.assert_called_once_with(face, frame)
    assert result is embedded


def test_ort_backend_embed_returns_none_when_embedder_returns_none() -> None:
    """embed() must pass through None from embedder (no face visible / below quality gate)."""
    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = None

    backend = _make_ort_backend(embedder=mock_embedder)
    result = backend.embed(_make_face(), np.zeros((480, 640, 3), dtype=np.uint8))  # type: ignore[union-attr]

    assert result is None


# ---------------------------------------------------------------------------
# embed_body
# ---------------------------------------------------------------------------


def test_ort_backend_delegates_embed_body_to_body_embedder() -> None:
    """embed_body() must forward the crop to body_embedder.embed() and pass back the result."""
    crop = np.zeros((128, 64, 3), dtype=np.uint8)
    expected = ((0.1,) * 768, 45.0)

    mock_body = MagicMock()
    mock_body.embed.return_value = expected

    backend = _make_ort_backend(body_embedder=mock_body)
    result = backend.embed_body(crop)  # type: ignore[union-attr]

    mock_body.embed.assert_called_once_with(crop)
    assert result == expected


def test_ort_backend_embed_body_returns_empty_when_no_body_embedder() -> None:
    """embed_body() must return ((), 0.0) when body_embedder is None."""
    backend = _make_ort_backend(body_embedder=None)
    result = backend.embed_body(np.zeros((128, 64, 3), dtype=np.uint8))  # type: ignore[union-attr]

    assert result == ((), 0.0)


# ---------------------------------------------------------------------------
# score_ppe
# ---------------------------------------------------------------------------


def test_ort_backend_delegates_score_ppe_to_ppe_model() -> None:
    """score_ppe() must forward the crop to ppe.score_crop() and pass back the result."""
    crop = np.zeros((100, 60, 3), dtype=np.uint8)
    scores = {"helmet": 0.8, "vest": 0.6, "gloves": 0.2, "mask": 0.1}

    mock_ppe = MagicMock()
    mock_ppe.score_crop.return_value = scores

    backend = _make_ort_backend(ppe=mock_ppe)
    result = backend.score_ppe(crop)  # type: ignore[union-attr]

    mock_ppe.score_crop.assert_called_once_with(crop)
    assert result == scores


def test_ort_backend_score_ppe_returns_none_when_no_ppe() -> None:
    """score_ppe() must return None when ppe is None (PPE model not loaded)."""
    backend = _make_ort_backend(ppe=None)
    result = backend.score_ppe(np.zeros((100, 60, 3), dtype=np.uint8))  # type: ignore[union-attr]

    assert result is None


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_ort_backend_is_instance_of_inference_backend_protocol() -> None:
    """OrtInferenceBackend must satisfy InferenceBackend (runtime_checkable Protocol)."""
    from vms.inference.backend import InferenceBackend, OrtInferenceBackend

    backend = OrtInferenceBackend(
        detector=MagicMock(),
        embedder=MagicMock(),
        body_embedder=None,
        ppe=None,
    )
    assert isinstance(backend, InferenceBackend)
