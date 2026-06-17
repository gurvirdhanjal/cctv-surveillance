"""FAISS-backed person identification with similarity + margin gates."""

from __future__ import annotations

from typing import Any

import numpy as np

from vms.config import get_settings
from vms.identity.faiss_index import FaissIndex


class ReIdService:
    """Identifies a person from a face embedding using the FAISS index.

    Gates (both must pass):
      1. best_sim >= adaface_min_sim  (default 0.72)
      2. best_sim - second_sim >= reid_margin  (default 0.08)
         -- skipped when only one result is available
    """

    def __init__(self, index: FaissIndex) -> None:
        self._index = index

    def apply_add(self, embedding_id: int, person_id: int, vec: np.ndarray[Any, Any]) -> None:
        """Incrementally add one embedding to the FAISS index."""
        self._index.add(embedding_id, person_id, vec)

    def apply_remove(self, embedding_ids: list[int]) -> None:
        """Remove embeddings from the FAISS index by their DB IDs."""
        self._index.remove(embedding_ids)

    def identify(self, embedding: np.ndarray[Any, Any]) -> int | None:
        """Return person_id if the embedding matches a known person, else None."""
        settings = get_settings()
        results = self._index.search(embedding, k=2)
        if not results:
            return None

        best_id, best_sim = results[0]
        if best_sim < settings.adaface_min_sim:
            return None

        if len(results) >= 2:
            _, second_sim = results[1]
            if (best_sim - second_sim) < settings.reid_margin:
                return None

        return best_id
