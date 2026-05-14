from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from vms.identity.reid import ReIdService


def _vec() -> np.ndarray:  # type: ignore[type-arg]
    return np.ones(512, dtype=np.float32)


def test_reid_returns_person_id_when_above_thresholds() -> None:
    index = MagicMock()
    index.search.return_value = [(42, 0.85), (99, 0.70)]  # margin = 0.15 >= 0.08
    svc = ReIdService(index=index)
    assert svc.identify(_vec()) == 42


def test_reid_returns_none_when_below_similarity_threshold() -> None:
    index = MagicMock()
    index.search.return_value = [(42, 0.60)]  # 0.60 < 0.72
    svc = ReIdService(index=index)
    assert svc.identify(_vec()) is None


def test_reid_returns_none_when_margin_too_small() -> None:
    index = MagicMock()
    index.search.return_value = [(42, 0.80), (99, 0.75)]  # margin = 0.05 < 0.08
    svc = ReIdService(index=index)
    assert svc.identify(_vec()) is None


def test_reid_skips_margin_check_for_single_result() -> None:
    index = MagicMock()
    index.search.return_value = [(42, 0.75)]  # only one result — margin N/A
    svc = ReIdService(index=index)
    assert svc.identify(_vec()) == 42


def test_reid_returns_none_for_empty_index() -> None:
    index = MagicMock()
    index.search.return_value = []
    svc = ReIdService(index=index)
    assert svc.identify(_vec()) is None
