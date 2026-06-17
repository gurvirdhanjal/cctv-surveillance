"""Camera pair transit-time gate for cross-camera re-ID.

Config format (VMS_REID_CAMERA_TOPOLOGY_JSON):
  {"1-2": {"min_ms": 2000, "max_ms": 120000}, "2-3": {...}, ...}

Key is always "{min_id}-{max_id}" (sorted ascending, hyphen-separated).
Unknown pairs are unconditionally allowed (fail-open — no false negatives).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PairWindow:
    min_ms: int
    max_ms: int


class CameraTopology:
    """Checks whether a cross-camera transit time is physically plausible."""

    def __init__(self, topology_json: str) -> None:
        self._pairs: dict[str, _PairWindow] = {}
        try:
            raw: dict[str, dict[str, int]] = json.loads(topology_json)
        except (json.JSONDecodeError, ValueError):
            logger.warning("CameraTopology: invalid JSON — all cross-camera matches allowed")
            return
        for key, val in raw.items():
            try:
                self._pairs[key] = _PairWindow(min_ms=int(val["min_ms"]), max_ms=int(val["max_ms"]))
            except (KeyError, ValueError):
                logger.warning("CameraTopology: skipping malformed pair entry %r", key)

    def transit_ok(self, cam_a: int, cam_b: int, elapsed_ms: int) -> bool:
        """Return True if transit from cam_a to cam_b in elapsed_ms is plausible.

        Unknown pairs are unconditionally allowed (fail-open).
        """
        key = f"{min(cam_a, cam_b)}-{max(cam_a, cam_b)}"
        window = self._pairs.get(key)
        if window is None:
            return True
        return window.min_ms <= elapsed_ms <= window.max_ms
