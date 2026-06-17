"""LOITERING detector — tracklet dwell > zone.loiter_threshold_s."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    SeamProvider,
    Severity,
)


class LoiteringDetector(AnomalyDetector, SeamProvider):
    alert_type = "LOITERING"
    severity = Severity.LOW
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL", "MID")

    def should_run(self, ctx: DetectorContext) -> bool:
        return len(ctx.active_track_zones) > 0

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        now = datetime.fromtimestamp(ctx.frame.timestamp_ms / 1000.0, tz=timezone.utc).replace(
            tzinfo=None
        )

        for gid, zone_id in ctx.active_track_zones.items():
            z = ctx.zone_lookup.get(zone_id)
            if z is None:
                continue
            entered = self._entered_at(gid, zone_id, ctx)
            if entered is None:
                continue
            dwell_s = (now - entered).total_seconds()
            if dwell_s >= z.loiter_threshold_s:
                return AnomalyEvent(
                    alert_type=self.alert_type,
                    severity=self.severity,
                    camera_id=ctx.frame.camera_id,
                    zone_id=zone_id,
                    global_track_id=gid,
                    person_id=None,
                    event_ts=now,
                    dedup_key=f"LOITERING:zone={zone_id}:gid={gid}",
                    payload={"dwell_s": int(dwell_s)},
                )
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=0, cooldown_ms=600_000, dedup_window_ms=600_000)

    def _entered_at(
        self,
        gid: uuid.UUID,
        zone_id: int,
        ctx: DetectorContext,
    ) -> datetime | None:
        return None
