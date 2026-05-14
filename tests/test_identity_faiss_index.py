from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy.orm import Session

from vms.db.models import Person, PersonEmbedding
from vms.identity.faiss_index import FaissIndex


def _unit_vec(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(512).astype(np.float32)
    return v / np.linalg.norm(v)


# ── unit tests (no DB) ────────────────────────────────────────────────

def test_faiss_index_starts_empty() -> None:
    idx = FaissIndex()
    assert idx.count() == 0


def test_faiss_index_add_increments_count() -> None:
    idx = FaissIndex()
    idx.add(embedding_id=1, person_id=10, embedding=_unit_vec(seed=0))
    assert idx.count() == 1


def test_faiss_index_search_returns_known_person() -> None:
    idx = FaissIndex()
    v = _unit_vec(seed=0)
    idx.add(embedding_id=1, person_id=10, embedding=v)
    results = idx.search(v, k=1)
    assert len(results) == 1
    assert results[0][0] == 10      # person_id
    assert results[0][1] > 0.99    # near-identical vector → similarity ≈ 1.0


def test_faiss_index_remove_decrements_count() -> None:
    idx = FaissIndex()
    idx.add(embedding_id=1, person_id=10, embedding=_unit_vec(seed=0))
    idx.remove([1])
    assert idx.count() == 0


def test_faiss_index_search_on_empty_returns_empty() -> None:
    idx = FaissIndex()
    assert idx.search(_unit_vec(), k=5) == []


# ── integration tests (real PostgreSQL) ──────────────────────────────

@pytest.mark.integration
def test_faiss_index_rebuild_loads_active_embeddings(db_session: Session) -> None:
    person = Person(name="FaissAlice", employee_id="E_FAISS_01")
    db_session.add(person)
    db_session.flush()
    db_session.add(PersonEmbedding(
        person_id=person.person_id,
        embedding=_unit_vec(seed=1),
        quality_score=0.9,
    ))
    db_session.flush()

    idx = FaissIndex()
    idx.rebuild(db_session)
    assert idx.count() >= 1


@pytest.mark.integration
def test_faiss_index_rebuild_excludes_inactive_persons(db_session: Session) -> None:
    person = Person(name="FaissBob", employee_id="E_FAISS_02", is_active=False)
    db_session.add(person)
    db_session.flush()
    emb = PersonEmbedding(
        person_id=person.person_id,
        embedding=_unit_vec(seed=2),
        quality_score=0.8,
    )
    db_session.add(emb)
    db_session.flush()

    idx = FaissIndex()
    idx.rebuild(db_session)
    # Inactive person's person_id must not appear in any search result
    assert person.person_id not in {pid for pid, _ in idx.search(_unit_vec(seed=2), k=10)}
