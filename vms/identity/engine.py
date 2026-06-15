"""Identity engine: tracklet registry, cross-camera re-ID, person identification.

Cross-camera matching algorithm:
  1. (cam_id, local_track_id) known → return cached global_track_id; update gallery.
  2. Unknown + has embedding →
       a. Spatial-temporal gate: skip entries with implausible transit time.
       b. Gallery similarity: max cosine(query, gallery[i]) across all gallery entries.
          Face queries compare against face gallery; body queries against body gallery.
       c. Threshold: confirmed entry → reid_confirmed_sim; unconfirmed → reid_cross_cam_sim.
       d. Margin gate: best_sim - second_sim >= reid_margin.
       e. Match → reuse global_track_id; no match → new UUID.
  3. Unknown + no embedding → new UUID.

Face embedding always takes priority over body embedding for gallery storage.
Body embedding is only stored when face is absent, enabling crowd-dense scenarios
where face detection fails (occlusion, helmets, angle).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from vms.config import get_settings
from vms.identity.reid import ReIdService
from vms.identity.topology import CameraTopology

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class _TrackletEntry:
    global_track_id: uuid.UUID
    camera_id: int
    last_seen_ms: int
    person_id: int | None = None
    local_track_id: int = 0
    first_seen_ms: int = 0
    gallery: list[np.ndarray[Any, Any]] = field(default_factory=list)
    body_gallery: list[np.ndarray[Any, Any]] = field(default_factory=list)
    sighting_count: int = 0
    confirmed: bool = False
    face_window_start_ms: int = 0
    face_window_best_quality: float = -1.0
    body_window_start_ms: int = 0
    body_window_best_quality: float = -1.0


class IdentityEngine:
    """Stateful per-process identity assignment for detection frames."""

    def __init__(self, reid_service: ReIdService) -> None:
        self._reid = reid_service
        self._registry: dict[tuple[int, int], _TrackletEntry] = {}
        self._topology: CameraTopology | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assign_global_track_id(
        self,
        camera_id: int,
        local_track_id: int,
        embedding: tuple[float, ...] | None,
        body_embedding: tuple[float, ...] | None = None,
        face_quality: float = 1.0,
        body_quality: float = 1.0,
    ) -> uuid.UUID:
        """Return a stable global_track_id for (camera_id, local_track_id).

        Matching priority:
          1. Body Re-ID (OSNet) — angle-invariant, works from top-down CCTV views.
          2. Face Re-ID (AdaFace) — used when body is absent (e.g. face-only crop).
        Both galleries are maintained independently and searched when available.
        Face wins for FAISS person identification; body wins for cross-camera tracking.
        """
        key = (camera_id, local_track_id)
        now_ms = time.time_ns() // 1_000_000
        settings = get_settings()

        if key in self._registry:
            entry = self._registry[key]
            entry.last_seen_ms = now_ms
            self._update_galleries(
                entry, embedding, body_embedding, settings,
                timestamp_ms=now_ms,
                face_quality=face_quality,
                body_quality=body_quality,
            )
            return entry.global_track_id

        emb_arr = np.array(embedding, dtype=np.float32) if embedding else None
        body_arr = np.array(body_embedding, dtype=np.float32) if body_embedding else None

        # Cross-camera match: body first (angle-invariant for CCTV), face as fallback.
        # Two-pass search handles mixed scenarios where cam1 may have a face gallery
        # but no body gallery (or vice versa). Body match wins if found; face match
        # only runs if body finds nothing — ensuring we never miss an existing identity.
        matched_gid: uuid.UUID | None = None
        if body_arr is not None:
            matched_gid = self._cross_camera_match(body_arr, "body", camera_id, now_ms)
        if matched_gid is None and emb_arr is not None:
            matched_gid = self._cross_camera_match(emb_arr, "face", camera_id, now_ms)
        gid = matched_gid if matched_gid is not None else uuid.uuid4()
        entry = _TrackletEntry(
            global_track_id=gid,
            person_id=None,
            last_seen_ms=now_ms,
            camera_id=camera_id,
        )
        self._update_galleries(entry, embedding, body_embedding, settings, timestamp_ms=now_ms)
        self._registry[key] = entry
        return gid

    def assign_and_identify(
        self,
        camera_id: int,
        local_track_id: int,
        embedding: tuple[float, ...] | None,
        body_embedding: tuple[float, ...] | None = None,
        ble_person_id: int | None = None,
    ) -> tuple[uuid.UUID, int | None, str]:
        """Assign a global_track_id and resolve person identity via FusionResolver.

        Returns (global_track_id, person_id, resolved_via).
        resolved_via: 'face' | 'body' | 'ble' | 'unknown'

        Priority: face (FAISS) > body gallery anchor > BLE badge.
        Once resolved, person_id propagates to all tracklets sharing the gid.
        """
        from vms.identity.fusion import FusionResolver

        gid = self.assign_global_track_id(camera_id, local_track_id, embedding, body_embedding)

        # Face identification via FAISS
        face_person_id: int | None = None
        if embedding:
            face_person_id = self._reid.identify(np.array(embedding, dtype=np.float32))

        # Body gallery anchor — inherited from a previous camera's identification
        body_anchored_id = self._get_known_person_id(gid)

        person_id, resolved_via = FusionResolver().resolve(
            face_person_id=face_person_id,
            body_anchored_id=body_anchored_id,
            ble_person_id=ble_person_id,
        )

        if person_id is not None:
            self._anchor_person_id(gid, person_id)

        return gid, person_id, resolved_via

    def identify_person(self, embedding: tuple[float, ...]) -> int | None:
        """Return person_id from FAISS if embedding is non-empty, else None."""
        if not embedding:
            return None
        return self._reid.identify(np.array(embedding, dtype=np.float32))

    def _get_known_person_id(self, gid: uuid.UUID) -> int | None:
        """Return person_id if any registry entry for this gid has already been identified."""
        for entry in self._registry.values():
            if entry.global_track_id == gid and entry.person_id is not None:
                return entry.person_id
        return None

    def _anchor_person_id(self, gid: uuid.UUID, person_id: int) -> None:
        """Write person_id to every registry entry sharing this global_track_id.

        This is the cross-camera identity anchor: once a person is identified on
        any camera (e.g. the entry gate), every other camera tracking the same
        global_track_id immediately knows who that person is.
        """
        for entry in self._registry.values():
            if entry.global_track_id == gid:
                entry.person_id = person_id

    def anchor_person_by_badge(self, person_id: int, badge_id: str) -> None:
        """Propagate person_id to registry entries that have no identification yet.

        Called by BleConsumer when a badge is detected near a BLE reader.
        Only fills entries without an existing person_id to avoid overwriting
        a higher-confidence face identification.
        """
        for entry in self._registry.values():
            if entry.person_id is None:
                entry.person_id = person_id

    def get_person_id(self, camera_id: int, local_track_id: int) -> int | None:
        """Return the resolved person_id for a (camera, track) pair, or None."""
        entry = self._registry.get((camera_id, local_track_id))
        return entry.person_id if entry is not None else None

    def faiss_apply_add(self, embedding_id: int, person_id: int, db: Session) -> None:
        """Fetch embedding from DB and add it to the FAISS index."""
        from vms.db.models import PersonEmbedding

        row = db.get(PersonEmbedding, embedding_id)
        if row is None:
            logger.warning("faiss_dirty add: embedding_id=%d not found in DB", embedding_id)
            return
        vec = np.array(row.embedding, dtype=np.float32)
        self._reid.apply_add(embedding_id, person_id, vec)

    def faiss_apply_remove(self, embedding_ids: list[int]) -> None:
        """Remove embeddings from the FAISS index."""
        self._reid.apply_remove(embedding_ids)

    def evict_stale(self, now_ms: int | None = None) -> int:
        """Remove tracklets not seen within their stale TTL.

        Confirmed tracklets: reid_confirmed_stale_ms (default 10 min).
        Unconfirmed tracklets: reid_stale_ms (default 5 min).
        Returns evicted count.
        """
        if now_ms is None:
            now_ms = time.time_ns() // 1_000_000
        settings = get_settings()
        stale = [
            k
            for k, e in self._registry.items()
            if now_ms - e.last_seen_ms
            > (settings.reid_confirmed_stale_ms if e.confirmed else settings.reid_stale_ms)
        ]
        for k in stale:
            del self._registry[k]
        return len(stale)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_topology(self) -> CameraTopology:
        if self._topology is None:
            self._topology = CameraTopology(get_settings().reid_camera_topology_json)
        return self._topology

    def _update_galleries(
        self,
        entry: _TrackletEntry,
        embedding: tuple[float, ...] | None,
        body_embedding: tuple[float, ...] | None,
        settings: Any,
        timestamp_ms: int = 0,
        face_quality: float = 1.0,
        body_quality: float = 1.0,
    ) -> None:
        """Update face and/or body galleries using temporal quality-windowed sub-sampling.

        Within each time window (reid_quality_window_s), only the highest-quality
        embedding is kept — lower-quality frames in the same window are discarded
        or replaced. A new window always appends a fresh slot. This prevents blurry
        or occluded frames from polluting the gallery while preserving temporal
        diversity across windows.
        """
        window_ms = int(settings.reid_quality_window_s * 1000)
        norm_floor: float = settings.reid_quality_norm_floor

        if embedding and face_quality >= norm_floor:
            in_window = (timestamp_ms - entry.face_window_start_ms) < window_ms
            if in_window:
                if face_quality > entry.face_window_best_quality:
                    if entry.gallery:
                        entry.gallery[-1] = np.array(embedding, dtype=np.float32)
                    else:
                        entry.gallery.append(np.array(embedding, dtype=np.float32))
                    entry.face_window_best_quality = face_quality
            else:
                entry.gallery.append(np.array(embedding, dtype=np.float32))
                if len(entry.gallery) > settings.reid_gallery_size:
                    entry.gallery = entry.gallery[-settings.reid_gallery_size :]
                entry.face_window_start_ms = timestamp_ms
                entry.face_window_best_quality = face_quality

        if body_embedding and body_quality >= norm_floor:
            in_window = (timestamp_ms - entry.body_window_start_ms) < window_ms
            if in_window:
                if body_quality > entry.body_window_best_quality:
                    if entry.body_gallery:
                        entry.body_gallery[-1] = np.array(body_embedding, dtype=np.float32)
                    else:
                        entry.body_gallery.append(np.array(body_embedding, dtype=np.float32))
                    entry.body_window_best_quality = body_quality
            else:
                entry.body_gallery.append(np.array(body_embedding, dtype=np.float32))
                if len(entry.body_gallery) > settings.reid_gallery_size:
                    entry.body_gallery = entry.body_gallery[-settings.reid_gallery_size :]
                entry.body_window_start_ms = timestamp_ms
                entry.body_window_best_quality = body_quality

        if embedding or body_embedding:
            entry.sighting_count += 1
            if (
                not entry.confirmed
                and entry.sighting_count >= settings.reid_confirm_after_sightings
            ):
                entry.confirmed = True

    def _gallery_sim(
        self,
        query_norm: np.ndarray[Any, Any],
        gallery: list[np.ndarray[Any, Any]],
    ) -> float:
        """Return max cosine similarity between a normalized query and any gallery entry."""
        best = -1.0
        for g in gallery:
            g_norm = g / (np.linalg.norm(g) + 1e-8)
            sim = float(np.dot(query_norm, g_norm))
            if sim > best:
                best = sim
        return best

    def _cross_camera_match(
        self,
        query: np.ndarray[Any, Any],
        query_type: str,
        camera_id: int,
        now_ms: int,
    ) -> uuid.UUID | None:
        """Scan other-camera tracklets for a gallery-aware match with topology gate.

        query_type: "face" -> compare against entry.gallery;
                    "body" -> compare against entry.body_gallery.
        """
        settings = get_settings()
        topology = self._get_topology()
        q = query / (np.linalg.norm(query) + 1e-8)

        # Track best similarity per global_track_id (one person may appear on multiple cameras).
        # Using per-gid tracking ensures the margin is computed across distinct identities,
        # not across multiple tracklets of the same person on different cameras.
        best_by_gid: dict[uuid.UUID, tuple[float, bool]] = {}  # gid -> (max_sim, confirmed)

        for (cam, _), entry in self._registry.items():
            if cam == camera_id:
                continue

            # Two-tier stale check
            stale_limit = (
                settings.reid_confirmed_stale_ms if entry.confirmed else settings.reid_stale_ms
            )
            if now_ms - entry.last_seen_ms > stale_limit:
                continue

            # Choose gallery by query type
            target_gallery = entry.gallery if query_type == "face" else entry.body_gallery
            if not target_gallery:
                continue

            # Spatial-temporal gate
            elapsed_ms = now_ms - entry.last_seen_ms
            if not topology.transit_ok(camera_id, cam, elapsed_ms):
                continue

            sim = self._gallery_sim(q, target_gallery)
            gid = entry.global_track_id
            existing = best_by_gid.get(gid)
            if existing is None or sim > existing[0]:
                best_by_gid[gid] = (sim, entry.confirmed)

        if not best_by_gid:
            return None

        sorted_gids = sorted(best_by_gid.items(), key=lambda x: x[1][0], reverse=True)
        best_gid, (best_sim, best_confirmed) = sorted_gids[0]
        second_sim = sorted_gids[1][1][0] if len(sorted_gids) >= 2 else -1.0

        # Body Re-ID (OSNet) operates at higher similarity range than face Re-ID (AdaFace).
        # Use separate thresholds so body matches are not penalised for being "too low"
        # relative to the face baseline.
        if query_type == "body":
            threshold = (
                settings.reid_body_confirmed_sim
                if best_confirmed
                else settings.reid_body_cross_cam_sim
            )
        else:
            threshold = (
                settings.reid_confirmed_sim if best_confirmed else settings.reid_cross_cam_sim
            )
        if best_sim < threshold:
            return None
        margin = best_sim - second_sim if second_sim > -1.0 else best_sim
        if margin < settings.reid_margin:
            return None
        return best_gid
