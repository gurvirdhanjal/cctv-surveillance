"""INTRUSION detector — restricted zone outside allowed_hours."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, time, timezone

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    Severity,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _AllowedSlot:
    days: frozenset[int]
    start: time
    end: time


def _parse_allowed_hours(raw: str | None) -> list[_AllowedSlot] | None:
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return None
        out: list[_AllowedSlot] = []
        for item in parsed:
            days = frozenset(int(d) for d in item["days"])
            s_h, s_m = item["start"].split(":")
            e_h, e_m = item["end"].split(":")
            out.append(
                _AllowedSlot(
                    days=days,
                    start=time(int(s_h), int(s_m)),
                    end=time(int(e_h), int(e_m)),
                )
            )
        return out
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None


def _slot_covers(slot: _AllowedSlot, when: datetime) -> bool:
    if when.isoweekday() not in slot.days:
        return False
    t = when.time()
    return slot.start <= t <= slot.end


class IntrusionDetector(AnomalyDetector):
    alert_type = "INTRUSION"
    severity = Severity.CRITICAL
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL", "MID", "LOW")

    def __init__(self, config: dict[str, object]) -> None:
        super().__init__(config)
        self._slot_cache: dict[int, list[_AllowedSlot] | None] = {}

    def should_run(self, ctx: DetectorContext) -> bool:
        return len(ctx.active_track_zones) > 0

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        when = datetime.fromtimestamp(ctx.frame.timestamp_ms / 1000.0, tz=timezone.utc).replace(
            tzinfo=None
        )

        for gid, zone_id in ctx.active_track_zones.items():
            z = ctx.zone_lookup.get(zone_id)
            if z is None or not z.is_restricted:
                continue
            slots = self._slots_for(zone_id, z.allowed_hours)
            allowed = False if slots is None else any(_slot_covers(s, when) for s in slots)
            if not allowed:
                return AnomalyEvent(
                    alert_type=self.alert_type,
                    severity=self.severity,
                    camera_id=ctx.frame.camera_id,
                    zone_id=zone_id,
                    global_track_id=gid,
                    person_id=None,
                    event_ts=when,
                    dedup_key=f"INTRUSION:zone={zone_id}:gid={gid}",
                    payload={},
                )
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=2_000, cooldown_ms=60_000, dedup_window_ms=60_000)

    def _slots_for(self, zone_id: int, raw: str | None) -> list[_AllowedSlot] | None:
        if zone_id in self._slot_cache:
            return self._slot_cache[zone_id]
        slots = _parse_allowed_hours(raw)
        self._slot_cache[zone_id] = slots
        return slots
