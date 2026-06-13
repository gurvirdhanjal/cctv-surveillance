"""FaissIndex thread-safety tests."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import numpy as np

from vms.identity.faiss_index import FaissIndex


def _make_db_mock(vecs: np.ndarray) -> MagicMock:  # type: ignore[type-arg]
    rows = []
    for i, v in enumerate(vecs):
        row = MagicMock()
        row.embedding_id = i + 1
        row.person_id = i + 1
        row.embedding = v.tolist()
        rows.append(row)
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = rows
    return db


def test_faiss_index_concurrent_search_and_rebuild_no_exception() -> None:
    """Concurrent rebuild() and search() must not raise or return None."""
    rng = np.random.default_rng(0)
    vecs = rng.random((10, 512)).astype(np.float32)
    idx = FaissIndex()
    for i, v in enumerate(vecs):
        idx.add(embedding_id=i + 1, person_id=i + 1, embedding=v)

    errors: list[Exception] = []

    def do_rebuilds() -> None:
        db = _make_db_mock(vecs)
        for _ in range(5):
            try:
                idx.rebuild(db)
            except Exception as exc:
                errors.append(exc)

    def do_searches() -> None:
        q = rng.random(512).astype(np.float32)
        for _ in range(10):
            try:
                results = idx.search(q, k=3)
                assert results is not None
            except Exception as exc:
                errors.append(exc)

    t1 = threading.Thread(target=do_rebuilds)
    t2 = threading.Thread(target=do_searches)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Concurrent access raised: {errors}"
