"""PPE_VIOLATION detector. Reads ppe_helmet_conf/ppe_vest_conf from each Tracklet."""

from __future__ import annotations

from datetime import datetime, timezone

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    Severity,
)
from vms.config import get_settings


class PPEDetector(AnomalyDetector):
    alert_type = "PPE_VIOLATION"
    severity = Severity.HIGH
    requires_models: tuple[str, ...] = ("ppe",)
    requires_tier: tuple[str, ...] = ("FULL", "MID")

    def __init__(self, config: dict[str, object]) -> None:
        super().__init__(config)
        ht = config.get("helmet_threshold")
        vt = config.get("vest_threshold")
        settings = get_settings()
        self._helmet_threshold: float = (
            float(str(ht)) if ht is not None else settings.ppe_helmet_threshold
        )
        self._vest_threshold: float = (
            float(str(vt)) if vt is not None else settings.ppe_vest_threshold
        )

    def should_run(self, ctx: DetectorContext) -> bool:
        return any(
            t.ppe_helmet_conf is not None or t.ppe_vest_conf is not None
            for t in ctx.frame.tracklets
        )

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        when = datetime.fromtimestamp(ctx.frame.timestamp_ms / 1000.0, tz=timezone.utc).replace(
            tzinfo=None
        )
        for t in ctx.frame.tracklets:
            if t.ppe_helmet_conf is None and t.ppe_vest_conf is None:
                continue

            violations: list[str] = []
            if t.ppe_helmet_conf is not None and t.ppe_helmet_conf < self._helmet_threshold:
                violations.append("helmet")
            if t.ppe_vest_conf is not None and t.ppe_vest_conf < self._vest_threshold:
                violations.append("vest")

            if not violations:
                continue

            return AnomalyEvent(
                alert_type=self.alert_type,
                severity=self.severity,
                camera_id=ctx.frame.camera_id,
                zone_id=None,
                global_track_id=None,
                person_id=None,
                event_ts=when,
                dedup_key=f"PPE_VIOLATION:cam={ctx.frame.camera_id}:track={t.local_track_id}",
                payload={
                    "local_track_id": t.local_track_id,
                    "violations": violations,
                    "ppe_helmet_conf": t.ppe_helmet_conf,
                    "ppe_vest_conf": t.ppe_vest_conf,
                },
            )
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=3_000, cooldown_ms=120_000, dedup_window_ms=120_000)
