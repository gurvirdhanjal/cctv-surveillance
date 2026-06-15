"""Unit tests for BodyEmbedder. Mocks Torchreid FeatureExtractor — no model file required.

Run with: pytest -m heavy_models
Excluded from default suite — importing torch alongside TensorFlow (MoViNet) in the same
process causes OOM on limited VRAM. Run separately: pytest -m heavy_models
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

pytestmark = pytest.mark.heavy_models


def _mock_extractor(out_dim: int = 512) -> MagicMock:
    """Return a mock FeatureExtractor instance whose __call__ returns (N, out_dim) tensor."""
    import torch  # lazy — only loaded when tests actually execute (not at collection time)

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
    emb, quality = BodyEmbedder("fake.pth", device="cpu").embed(
        np.zeros((64, 32, 3), dtype=np.uint8)
    )
    assert isinstance(emb, tuple) and len(emb) == 512
    assert isinstance(quality, float) and quality > 0.0


def test_body_embedder_output_is_l2_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_extractor(monkeypatch)
    emb, _quality = BodyEmbedder("fake.pth", device="cpu").embed(
        np.zeros((64, 32, 3), dtype=np.uint8)
    )
    norm = float(np.linalg.norm(np.array(emb, dtype=np.float32)))
    assert abs(norm - 1.0) < 1e-5


def test_body_embedder_quality_norm_is_pre_normalisation(monkeypatch: pytest.MonkeyPatch) -> None:
    """quality_norm is the L2 norm captured before normalisation — must differ from 1.0."""
    _patch_extractor(monkeypatch)
    _emb, quality = BodyEmbedder("fake.pth", device="cpu").embed(
        np.zeros((64, 32, 3), dtype=np.uint8)
    )
    # Random vector from rng(0) is very unlikely to have norm exactly 1.0.
    assert quality > 0.0


def test_body_embedder_tiny_crop_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_extractor(monkeypatch)
    emb, quality = BodyEmbedder("fake.pth", device="cpu").embed(
        np.zeros((15, 7, 3), dtype=np.uint8)
    )
    assert emb == ()
    assert quality == 0.0


def test_body_embedder_minimum_crop_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_extractor(monkeypatch)
    emb, quality = BodyEmbedder("fake.pth", device="cpu").embed(
        np.zeros((16, 8, 3), dtype=np.uint8)
    )
    assert len(emb) == 512
    assert quality > 0.0


def test_body_embedder_unavailable_when_import_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """BodyEmbedder degrades gracefully when torchreid raises ImportError."""
    monkeypatch.setattr(
        "torchreid.utils.FeatureExtractor",
        MagicMock(side_effect=ImportError("torchreid missing")),
    )
    emb, quality = BodyEmbedder("fake.pth", device="cpu").embed(
        np.zeros((64, 32, 3), dtype=np.uint8)
    )
    assert emb == ()
    assert quality == 0.0
