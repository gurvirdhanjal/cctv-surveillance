"""FAISS-backed embedding index for fast person identification.

Uses IndexIDMap2(IndexFlatIP(512)) so we can:
  add_with_ids — assign DB embedding_id as the FAISS row ID
  remove_ids   — precise removal on GDPR purge
  search       — inner-product similarity (== cosine after L2 normalisation)
"""

from __future__ import annotations

import logging
from typing import Any

import faiss  # type: ignore[import-untyped]
import numpy as np
from sqlalchemy.orm import Session

from vms.db.models import Person, PersonEmbedding

logger = logging.getLogger(__name__)

_DIM = 512


class FaissIndex:
    """In-memory FAISS index keyed by embedding_id. Not thread-safe."""

    def __init__(self) -> None:
        flat = faiss.IndexFlatIP(_DIM)
        self._index: faiss.IndexIDMap2 = faiss.IndexIDMap2(flat)
        self._emb_to_person: dict[int, int] = {}  # embedding_id → person_id

    def rebuild(self, db: Session) -> None:
        """Wipe and reload all active-person embeddings from the DB."""
        self._index.reset()
        self._emb_to_person.clear()

        rows: list[PersonEmbedding] = (
            db.query(PersonEmbedding)
            .join(Person, PersonEmbedding.person_id == Person.person_id)
            .filter(Person.is_active.is_(True))
            .all()
        )
        if not rows:
            return

        ids = np.array([r.embedding_id for r in rows], dtype=np.int64)
        # pgvector returns list[float] — must convert to float32 ndarray
        vecs = np.array([r.embedding for r in rows], dtype=np.float32)
        faiss.normalize_L2(vecs)
        self._index.add_with_ids(vecs, ids)
        for r in rows:
            self._emb_to_person[r.embedding_id] = r.person_id
        logger.info("FAISS index rebuilt: %d embeddings", len(rows))

    def add(self, embedding_id: int, person_id: int, embedding: np.ndarray[Any, Any]) -> None:
        """Incrementally add one embedding after enrolment."""
        vec = np.array(embedding, dtype=np.float32).reshape(1, _DIM)
        faiss.normalize_L2(vec)
        self._index.add_with_ids(vec, np.array([embedding_id], dtype=np.int64))
        self._emb_to_person[embedding_id] = person_id

    def remove(self, embedding_ids: list[int]) -> None:
        """Remove embeddings by their DB IDs after GDPR purge."""
        if not embedding_ids:
            return
        self._index.remove_ids(np.array(embedding_ids, dtype=np.int64))
        for eid in embedding_ids:
            self._emb_to_person.pop(eid, None)

    def search(self, query: np.ndarray[Any, Any], k: int = 5) -> list[tuple[int, float]]:
        """Return (person_id, cosine_similarity) for top-k results, best first.

        Returns [] when the index is empty.
        """
        if self._index.ntotal == 0:
            return []
        vec = np.array(query, dtype=np.float32).reshape(1, _DIM)
        faiss.normalize_L2(vec)
        sims, ids = self._index.search(vec, min(k, self._index.ntotal))
        results: list[tuple[int, float]] = []
        for sim, eid in zip(sims[0], ids[0], strict=False):
            if eid == -1:
                continue
            pid = self._emb_to_person.get(int(eid))
            if pid is not None:
                results.append((pid, float(sim)))
        return results

    def count(self) -> int:
        return int(self._index.ntotal)
