"""ShutterProfile: per-camera config resolution based on shutter type."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Adjustments applied when shutter_type == "rolling"
_ROLLING_DELTAS: dict[str, float | int] = {
    "adaface_min_sim": -0.10,
    "scrfd_conf": -0.10,
}
_ROLLING_ABSOLUTES: dict[str, float | int] = {
    "burst_frames": 5,
    "body_weight_multiplier": 1.2,
}


@dataclass(frozen=True)
class ResolvedSetting:
    value: float | int | str
    source: str


def resolve_camera_config(
    shutter_type: str,
    model_overrides_json: str | None,
    base_adaface_min_sim: float,
    base_scrfd_conf: float,
    base_burst_frames: int = 3,
    base_body_weight: float = 1.0,
) -> dict[str, ResolvedSetting]:
    """Resolve per-camera config applying shutter-type adjustments and manual overrides.

    Resolution order (first match wins):
      1. manual_override (from model_overrides JSON)
      2. shutter:rolling adjustment
      3. global_default (base_ params)
    """
    overrides: dict[str, Any] = {}
    if model_overrides_json:
        try:
            parsed = json.loads(model_overrides_json)
            if not isinstance(parsed, dict):
                logger.warning("model_overrides is not a JSON object; ignoring")
            else:
                overrides = parsed
        except json.JSONDecodeError:
            logger.warning("model_overrides is not valid JSON; ignoring")

    is_rolling = shutter_type == "rolling"

    def _resolve(
        key: str,
        base_value: float | int,
        delta: float | int | None = None,
        absolute: float | int | None = None,
    ) -> ResolvedSetting:
        if key in overrides:
            return ResolvedSetting(value=overrides[key], source="manual_override")
        if is_rolling:
            if delta is not None:
                return ResolvedSetting(value=round(base_value + delta, 2), source="shutter:rolling")
            if absolute is not None:
                return ResolvedSetting(value=absolute, source="shutter:rolling")
        return ResolvedSetting(value=base_value, source="global_default")

    return {
        "adaface_min_sim": _resolve(
            "adaface_min_sim", base_adaface_min_sim, delta=_ROLLING_DELTAS["adaface_min_sim"]
        ),
        "scrfd_conf": _resolve(
            "scrfd_conf", base_scrfd_conf, delta=_ROLLING_DELTAS["scrfd_conf"]
        ),
        "burst_frames": _resolve(
            "burst_frames", base_burst_frames, absolute=_ROLLING_ABSOLUTES["burst_frames"]
        ),
        "body_weight_multiplier": _resolve(
            "body_weight_multiplier",
            base_body_weight,
            absolute=_ROLLING_ABSOLUTES["body_weight_multiplier"],
        ),
    }
