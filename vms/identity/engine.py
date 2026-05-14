"""Identity engine: tracklet registry, cross-camera re-ID, person identification.

Cross-camera matching algorithm:
  1. (cam_id, local_track_id) known -> return cached global_track_id.
  2. Unknown + has embedding -> scan OTHER cameras' active tracklets
     (last_seen < 5 min) for cosine similarity:
       best >= reid_cross_cam_sim AND margin >= reid_margin -> reuse global_track_id
       else -> new UUID.
  3. Unknown + no embedding -> new UUID.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np

from vms.config import get_settings
from vms.identity.reid import ReIdService

logger = logging.getLogger(__name__)

_STALE_MS = 5 * 60 * 1000  # 5 minutes


@dataclass
class _TrackletEntry:
    global_track_id: uuid.UUID
    person_id: int | None
    last_embedding: np.ndarray[Any, Any] | None
    last_seen_ms: int
    camera_id: int


class IdentityEngine:
    """Stateful per-process identity assignment for detection frames."""

    def __init__(self, reid_service: ReIdService) -> None:
        self._reid = reid_service
        self._registry: dict[tuple[int, int], _TrackletEntry] = {}

    def assign_global_track_id(
        self,
        camera_id: int,
        local_track_id: int,
        embedding: tuple[float, ...] | None,
    ) -> uuid.UUID:
        """Return a stable global_track_id for this (camera, local_track) pair."""
        key = (camera_id, local_track_id)
        now_ms = time.time_ns() // 1_000_000

        if key in self._registry:
            entry = self._registry[key]
            entry.last_seen_ms = now_ms
            if embedding:
                entry.last_embedding = np.array(embedding, dtype=np.float32)
            return entry.global_track_id

        emb_arr = np.array(embedding, dtype=np.float32) if embedding else None
        matched_gid = self._cross_camera_match(emb_arr, camera_id, now_ms) if emb_arr is not None else None
        gid = matched_gid if matched_gid is not None else uuid.uuid4()

        self._registry[key] = _TrackletEntry(
            global_track_id=gid,
            person_id=None,
            last_embedding=emb_arr,
            last_seen_ms=now_ms,
            camera_id=camera_id,
        )
        return gid

    def identify_person(self, embedding: tuple[float, ...]) -> int | None:
        """Return person_id from FAISS if embedding is non-empty, else None."""
        if not embedding:
            return None
        return self._reid.identify(np.array(embedding, dtype=np.float32))

    def _cross_camera_match(
        self,
        query: np.ndarray[Any, Any],
        camera_id: int,
        now_ms: int,
    ) -> uuid.UUID | None:
        """Scan other-camera active tracklets for a cosine similarity match."""
        settings = get_settings()
        q = query / (np.linalg.norm(query) + 1e-8)
        best_sim = -1.0
        second_sim = -1.0
        best_gid: uuid.UUID | None = None

        for (cam, _), entry in self._registry.items():
            if cam == camera_id:
                continue
            if now_ms - entry.last_seen_ms > _STALE_MS:
                continue
            if entry.last_embedding is None:
                continue
            e = entry.last_embedding / (np.linalg.norm(entry.last_embedding) + 1e-8)
            sim = float(np.dot(q, e))
            if sim > best_sim:
                second_sim = best_sim
                best_sim = sim
                best_gid = entry.global_track_id
            elif sim > second_sim:
                second_sim = sim

        if best_sim < settings.reid_cross_cam_sim:
            return None
        margin = best_sim - second_sim if second_sim > -1.0 else best_sim
        if margin < settings.reid_margin:
            return None
        return best_gid
