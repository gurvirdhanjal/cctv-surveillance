"""Multi-modal person_id fusion: Face >= Body anchor >= BLE badge.

Priority (highest first):
  1. Face (AdaFace + FAISS) — highest confidence, requires frontal view
  2. Body gallery anchor   — inherited from a previous camera's identification
  3. BLE badge             — hardware fallback, zone-level only

On conflict (two non-None sources disagree), face always wins and a warning is logged.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class FusionResolver:
    """Resolves person_id from up to three modalities with deterministic priority."""

    def resolve(
        self,
        face_person_id: int | None,
        body_anchored_id: int | None,
        ble_person_id: int | None,
    ) -> tuple[int | None, str]:
        """Return (person_id, resolved_via).

        resolved_via: 'face' | 'body' | 'ble' | 'unknown'
        """
        if self.has_conflict(face_person_id, body_anchored_id, ble_person_id):
            logger.warning(
                "identity conflict: face=%s body=%s ble=%s — trusting face",
                face_person_id,
                body_anchored_id,
                ble_person_id,
            )
        if face_person_id is not None:
            return face_person_id, "face"
        if body_anchored_id is not None:
            return body_anchored_id, "body"
        if ble_person_id is not None:
            return ble_person_id, "ble"
        return None, "unknown"

    def has_conflict(
        self,
        face_person_id: int | None,
        body_anchored_id: int | None,
        ble_person_id: int | None,
    ) -> bool:
        """True if two or more non-None sources disagree on person identity."""
        active = [p for p in (face_person_id, body_anchored_id, ble_person_id) if p is not None]
        return len(set(active)) > 1
