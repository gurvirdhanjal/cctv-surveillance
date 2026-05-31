"""PPE_VIOLATION detector. Reads per-tracklet PPE scores from DetectionFrame."""

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
        settings = get_settings()

        ht = config.get("helmet_threshold")
        vt = config.get("vest_threshold")
        gt = config.get("gloves_threshold")
        mt = config.get("mask_threshold")

        self._helmet_threshold: float = (
            float(str(ht)) if ht is not None else settings.ppe_helmet_threshold
        )
        self._vest_threshold: float = (
            float(str(vt)) if vt is not None else settings.ppe_vest_threshold
        )
        self._gloves_threshold: float = (
            float(str(gt)) if gt is not None else settings.ppe_gloves_threshold
        )
        self._mask_threshold: float = (
            float(str(mt)) if mt is not None else settings.ppe_mask_threshold
        )

        # Gloves and mask checking is opt-in — factories may not require them
        cg = config.get("check_gloves")
        cm = config.get("check_mask")
        self._check_gloves: bool = bool(cg) if cg is not None else False
        self._check_mask: bool = bool(cm) if cm is not None else False

    def should_run(self, ctx: DetectorContext) -> bool:
        return any(
            t.ppe_helmet_conf is not None
            or t.ppe_vest_conf is not None
            or t.ppe_gloves_conf is not None
            or t.ppe_mask_conf is not None
            for t in ctx.frame.tracklets
        )

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        when = datetime.fromtimestamp(ctx.frame.timestamp_ms / 1000.0, tz=timezone.utc).replace(
            tzinfo=None
        )
        for t in ctx.frame.tracklets:
            violations: list[str] = []

            if t.ppe_helmet_conf is not None and t.ppe_helmet_conf < self._helmet_threshold:
                violations.append("helmet")
            if t.ppe_vest_conf is not None and t.ppe_vest_conf < self._vest_threshold:
                violations.append("vest")
            if (
                self._check_gloves
                and t.ppe_gloves_conf is not None
                and t.ppe_gloves_conf < self._gloves_threshold
            ):
                violations.append("gloves")
            if (
                self._check_mask
                and t.ppe_mask_conf is not None
                and t.ppe_mask_conf < self._mask_threshold
            ):
                violations.append("mask")

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
                    "ppe_gloves_conf": t.ppe_gloves_conf,
                    "ppe_mask_conf": t.ppe_mask_conf,
                },
            )
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=3_000, cooldown_ms=120_000, dedup_window_ms=120_000)
