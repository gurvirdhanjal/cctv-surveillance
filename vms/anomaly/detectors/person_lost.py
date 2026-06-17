"""PERSON_LOST detector.

The orchestrator injects the IdentityEngine.registry snapshot via the
_registry_last_seen() seam (overridden at wiring time). For unit tests,
the seam is monkey-patched.
"""

from __future__ import annotations

import time
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


class PersonLostDetector(AnomalyDetector, SeamProvider):
    alert_type = "PERSON_LOST"
    severity = Severity.MEDIUM
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL",)

    def __init__(self, config: dict[str, object]) -> None:
        super().__init__(config)
        raw = config.get("lost_after_s", 30)
        self._lost_after_s = int(str(raw)) if raw is not None else 30

    def should_run(self, ctx: DetectorContext) -> bool:
        return True

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        now_ms = int(time.time() * 1000)
        last_seen = self._registry_last_seen(ctx)
        threshold_ms = self._lost_after_s * 1000
        for gid, last_ms in last_seen.items():
            if now_ms - last_ms > threshold_ms:
                return AnomalyEvent(
                    alert_type=self.alert_type,
                    severity=self.severity,
                    camera_id=ctx.frame.camera_id,
                    zone_id=ctx.active_track_zones.get(gid),
                    global_track_id=gid,
                    person_id=None,
                    event_ts=datetime.now(timezone.utc).replace(tzinfo=None),
                    dedup_key=f"PERSON_LOST:gid={gid}",
                    payload={"lost_for_s": (now_ms - last_ms) // 1000},
                )
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=0, cooldown_ms=120_000, dedup_window_ms=120_000)

    def _registry_last_seen(self, ctx: DetectorContext) -> dict[uuid.UUID, int]:
        return {}
