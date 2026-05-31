"""Unit tests for BodyEmbedder. Mocks Torchreid FeatureExtractor — no model file required."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
import torch


def _mock_extractor(out_dim: int = 512) -> MagicMock:
    """Return a mock FeatureExtractor instance whose __call__ returns (N, out_dim) tensor."""
    instance = MagicMock()
    instance.side_effect = lambda imgs: torch.from_numpy(
        np.random.default_rng(0).standard_normal((len(imgs), out_dim)).astype(np.float32)
    )
    return instance


def _patch_extractor(monkeypatch: pytest.MonkeyPatch, out_dim: int = 512) -> MagicMock:
    instance = _mock_extractor(out_dim)
    monkeypatch.setattr("torchreid.utils.FeatureExtractor", MagicMock(return_value=instance))
    return instance


from vms.inference.body_embedder import BodyEmbedder  # noqa: E402


def test_body_embedder_returns_512_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_extractor(monkeypatch)
    emb = BodyEmbedder("fake.pth", device="cpu").embed(np.zeros((64, 32, 3), dtype=np.uint8))
    assert isinstance(emb, tuple) and len(emb) == 512


def test_body_embedder_output_is_l2_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_extractor(monkeypatch)
    emb = BodyEmbedder("fake.pth", device="cpu").embed(np.zeros((64, 32, 3), dtype=np.uint8))
    norm = float(np.linalg.norm(np.array(emb, dtype=np.float32)))
    assert abs(norm - 1.0) < 1e-5


def test_body_embedder_tiny_crop_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_extractor(monkeypatch)
    emb = BodyEmbedder("fake.pth", device="cpu").embed(np.zeros((15, 7, 3), dtype=np.uint8))
    assert emb == ()


def test_body_embedder_minimum_crop_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_extractor(monkeypatch)
    emb = BodyEmbedder("fake.pth", device="cpu").embed(np.zeros((16, 8, 3), dtype=np.uint8))
    assert len(emb) == 512


def test_body_embedder_unavailable_when_import_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """BodyEmbedder degrades gracefully when torchreid raises ImportError."""
    monkeypatch.setattr(
        "torchreid.utils.FeatureExtractor",
        MagicMock(side_effect=ImportError("torchreid missing")),
    )
    emb = BodyEmbedder("fake.pth", device="cpu").embed(np.zeros((64, 32, 3), dtype=np.uint8))
    assert emb == ()
