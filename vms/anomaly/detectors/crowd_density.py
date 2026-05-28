"""CROWD_DENSITY detector. Reads ctx.head_count + ctx.zone_lookup."""

from __future__ import annotations

from datetime import datetime, timezone

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    Severity,
)


class CrowdDensityDetector(AnomalyDetector):
    alert_type = "CROWD_DENSITY"
    severity = Severity.MEDIUM
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL", "MID")

    def should_run(self, ctx: DetectorContext) -> bool:
        return bool(ctx.head_count)

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        for zone_id, count in ctx.head_count.items():
            z = ctx.zone_lookup.get(zone_id)
            if z is None or z.max_capacity is None:
                continue
            if count > z.max_capacity:
                return AnomalyEvent(
                    alert_type=self.alert_type,
                    severity=self.severity,
                    camera_id=ctx.frame.camera_id,
                    zone_id=zone_id,
                    global_track_id=None,
                    person_id=None,
                    event_ts=datetime.fromtimestamp(
                        ctx.frame.timestamp_ms / 1000.0, tz=timezone.utc
                    ).replace(tzinfo=None),
                    dedup_key=f"CROWD_DENSITY:zone={zone_id}",
                    payload={"count": count, "max_capacity": z.max_capacity},
                )
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=10_000, cooldown_ms=300_000, dedup_window_ms=300_000)
