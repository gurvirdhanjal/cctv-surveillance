"""Unit tests for BodyEmbedder. Uses a mock ONNX session — no model file required."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from vms.inference.body_embedder import BodyEmbedder


def _mock_session(out_dim: int = 512) -> MagicMock:
    session = MagicMock()
    out = np.random.default_rng(0).standard_normal((1, out_dim)).astype(np.float32)
    session.run.return_value = [out]
    session.get_inputs.return_value = [MagicMock(name="input")]
    return session


def test_body_embedder_returns_512_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.inference.body_embedder.ort.InferenceSession",
        lambda *a, **kw: _mock_session(),
    )
    emb = BodyEmbedder("x.onnx").embed(np.zeros((64, 32, 3), dtype=np.uint8))
    assert isinstance(emb, tuple) and len(emb) == 512


def test_body_embedder_output_is_l2_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.inference.body_embedder.ort.InferenceSession",
        lambda *a, **kw: _mock_session(),
    )
    emb = BodyEmbedder("x.onnx").embed(np.zeros((64, 32, 3), dtype=np.uint8))
    norm = float(np.linalg.norm(np.array(emb, dtype=np.float32)))
    assert abs(norm - 1.0) < 1e-5


def test_body_embedder_tiny_crop_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.inference.body_embedder.ort.InferenceSession",
        lambda *a, **kw: _mock_session(),
    )
    emb = BodyEmbedder("x.onnx").embed(np.zeros((15, 7, 3), dtype=np.uint8))
    assert emb == ()


def test_body_embedder_minimum_crop_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vms.inference.body_embedder.ort.InferenceSession",
        lambda *a, **kw: _mock_session(),
    )
    emb = BodyEmbedder("x.onnx").embed(np.zeros((16, 8, 3), dtype=np.uint8))
    assert len(emb) == 512
