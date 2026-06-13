"""Tier assignment logic: maps measured ProfileData to FULL/MID/LOW."""

from __future__ import annotations

from vms.api.schemas import ProfileData
from vms.config import get_settings


def assign_tier(data: ProfileData) -> tuple[str, str]:
    """Return (tier, reason) from measured profile data.

    Tier decision order: LOW conditions are checked first (most restrictive).
    If none apply, MID conditions are checked. Otherwise FULL.
    """
    s = get_settings()

    h = data.resolution_h
    fps = data.fps_measured
    focus = data.focus_score

    # -- LOW tier conditions (any single condition = LOW) --
    if h is not None and h < s.profiler_res_mid_min_h:
        return "LOW", f"<720p resolution ({h}p)"
    if fps is not None and fps < s.profiler_fps_mid_min:
        return "LOW", f"<8fps measured ({fps:.1f} fps)"
    if data.is_analog_via_encoder is True:
        return "LOW", "analog-via-encoder deinterlace artifact detected"
    if focus is not None and focus < s.profiler_focus_mid_min:
        return "LOW", f"focus_score<{s.profiler_focus_mid_min} ({focus:.1f})"

    # -- MID tier conditions (any single condition = MID, but no LOW) --
    mid_reasons: list[str] = []
    if h is not None and h < s.profiler_res_full_min_h:
        mid_reasons.append(f"resolution {h}p < {s.profiler_res_full_min_h}p")
    if fps is not None and fps < s.profiler_fps_full_min:
        mid_reasons.append(f"fps {fps:.1f} < {s.profiler_fps_full_min}")
    if focus is not None and focus < s.profiler_focus_full_min:
        mid_reasons.append(f"focus_score {focus:.1f} < {s.profiler_focus_full_min}")
    if mid_reasons:
        return "MID", "; ".join(mid_reasons)

    # -- FULL --
    parts: list[str] = []
    if h is not None:
        parts.append(f">={s.profiler_res_full_min_h}p")
    if fps is not None:
        parts.append(f"fps>={s.profiler_fps_full_min}")
    if focus is not None:
        parts.append(f"focus>={s.profiler_focus_full_min}")
    reason = " AND ".join(parts) if parts else "defaults"
    return "FULL", reason
