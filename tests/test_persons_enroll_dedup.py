"""Tests for near-duplicate enrollment rejection."""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np


def _unit_vec(seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(512).astype(np.float32)
    v /= np.linalg.norm(v)
    return v.tolist()


def _near_dup(emb: list[float], noise: float = 0.005) -> list[float]:
    """Return embedding perturbed so cosine sim is very close to 1."""
    v = np.array(emb, dtype=np.float32)
    rng = np.random.default_rng(99)
    delta = rng.standard_normal(512).astype(np.float32)
    delta *= noise / np.linalg.norm(delta)
    v2 = v + delta
    v2 /= np.linalg.norm(v2)
    return v2.tolist()


def test_is_near_duplicate_true_for_identical() -> None:
    """Identical embedding → cosine sim 1.0 → near duplicate."""
    from vms.api.routes.persons import _is_near_duplicate
    emb = np.array(_unit_vec(1), dtype=np.float32)
    row = MagicMock()
    row.embedding = emb.tolist()
    assert _is_near_duplicate(emb, [row], threshold=0.95) is True


def test_is_near_duplicate_false_for_orthogonal() -> None:
    """Orthogonal embedding → cosine sim ~0 → not near duplicate."""
    from vms.api.routes.persons import _is_near_duplicate
    emb1 = np.zeros(512, dtype=np.float32)
    emb1[0] = 1.0
    emb2 = np.zeros(512, dtype=np.float32)
    emb2[1] = 1.0
    row = MagicMock()
    row.embedding = emb2.tolist()
    assert _is_near_duplicate(emb1, [row], threshold=0.95) is False


def test_is_near_duplicate_empty_existing() -> None:
    """No existing embeddings → never a near duplicate."""
    from vms.api.routes.persons import _is_near_duplicate
    emb = np.array(_unit_vec(2), dtype=np.float32)
    assert _is_near_duplicate(emb, [], threshold=0.95) is False


def test_is_near_duplicate_high_sim_above_threshold() -> None:
    """Embedding with cosine sim >= threshold → near duplicate."""
    from vms.api.routes.persons import _is_near_duplicate
    base = np.array(_unit_vec(3), dtype=np.float32)
    near = np.array(_near_dup(base.tolist(), noise=0.005), dtype=np.float32)
    row = MagicMock()
    row.embedding = base.tolist()
    # near-dup should have sim > 0.95
    assert _is_near_duplicate(near, [row], threshold=0.95) is True
