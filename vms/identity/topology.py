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
    overlap: bool = False
    spatial_gate_m: float | None = None  # populated in Task 5/6; None = disabled


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
                self._pairs[key] = _PairWindow(
                    min_ms=int(val["min_ms"]),
                    max_ms=int(val["max_ms"]),
                    overlap=bool(val.get("overlap", False)),
                    spatial_gate_m=(
                        float(val["spatial_gate_m"]) if "spatial_gate_m" in val else None
                    ),
                )
            except (KeyError, ValueError):
                logger.warning("CameraTopology: skipping malformed pair entry %r", key)

    def transit_ok(
        self,
        cam_a: int,
        cam_b: int,
        elapsed_ms: int,
        floor_xy: tuple[float, float] | None = None,
        predicted_xy: tuple[float, float] | None = None,
    ) -> bool:
        """Return True if cam_a -> cam_b transit is plausible in time and (optionally) space.

        Unknown pairs are unconditionally allowed (fail-open). The spatial gate is additive:
        it only narrows an already-passing time gate, and only when the pair declares
        spatial_gate_m AND both floor_xy and predicted_xy are supplied. A missing prediction
        is fail-open — consistent with the time gate policy.
        """
        key = f"{min(cam_a, cam_b)}-{max(cam_a, cam_b)}"
        window = self._pairs.get(key)
        if window is None:
            return True
        if not (window.min_ms <= elapsed_ms <= window.max_ms):
            return False
        if window.spatial_gate_m is not None and floor_xy is not None and predicted_xy is not None:
            dx = floor_xy[0] - predicted_xy[0]
            dy = floor_xy[1] - predicted_xy[1]
            if (dx * dx + dy * dy) ** 0.5 > window.spatial_gate_m:
                return False
        return True

    def is_overlapping(self, cam_a: int, cam_b: int) -> bool:
        """Return True if cam_a and cam_b are declared as covering the same physical zone."""
        key = f"{min(cam_a, cam_b)}-{max(cam_a, cam_b)}"
        window = self._pairs.get(key)
        return bool(window and window.overlap)

    def overlapping_cameras(self) -> set[int]:
        """Return the set of camera IDs involved in at least one overlapping pair."""
        cams: set[int] = set()
        for key, window in self._pairs.items():
            if window.overlap:
                a, b = key.split("-")
                cams.update((int(a), int(b)))
        return cams
