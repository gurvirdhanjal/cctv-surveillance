"""VIOLENCE detector. Reads ctx.violence_score from the InferenceEngine gated pool."""

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


class ViolenceDetector(AnomalyDetector):
    alert_type = "VIOLENCE"
    severity = Severity.CRITICAL
    requires_models: tuple[str, ...] = ("violence",)
    requires_tier: tuple[str, ...] = ("FULL", "MID")

    def __init__(self, config: dict[str, object]) -> None:
        super().__init__(config)
        cfg_th = config.get("threshold")
        self._threshold: float = (
            float(str(cfg_th)) if cfg_th is not None else get_settings().violence_threshold
        )

    def should_run(self, ctx: DetectorContext) -> bool:
        return ctx.violence_score is not None

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        score = ctx.violence_score
        if score is None or score < self._threshold:
            return None
        when = datetime.fromtimestamp(ctx.frame.timestamp_ms / 1000.0, tz=timezone.utc).replace(
            tzinfo=None
        )
        return AnomalyEvent(
            alert_type=self.alert_type,
            severity=self.severity,
            camera_id=ctx.frame.camera_id,
            zone_id=None,
            global_track_id=None,
            person_id=None,
            event_ts=when,
            dedup_key=f"VIOLENCE:cam={ctx.frame.camera_id}",
            payload={"score": score},
        )

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=2_000, cooldown_ms=30_000, dedup_window_ms=30_000)
