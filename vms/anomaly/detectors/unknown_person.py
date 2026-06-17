"""UNKNOWN_PERSON detector.

Fires on tracklets the IdentityEngine has flagged as belonging to a known
global_track_id but not yet mapped to a person_id (no FAISS match).
The orchestrator populates DetectorContext.active_track_zones for every
tracklet it could resolve to a gid; un-resolved tracklets are skipped here.
"""

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
from vms.inference.messages import Tracklet


class UnknownPersonDetector(AnomalyDetector, SeamProvider):
    alert_type = "UNKNOWN_PERSON"
    severity = Severity.HIGH
    requires_models: tuple[str, ...] = ("face_embedder",)
    requires_tier: tuple[str, ...] = ("FULL",)

    def should_run(self, ctx: DetectorContext) -> bool:
        return len(ctx.frame.tracklets) > 0

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        for tl in ctx.frame.tracklets:
            gid = self._gid_for_tracklet(tl, ctx)
            if gid is None:
                continue
            pid = self._person_id_for(gid, ctx)
            if pid is not None:
                continue
            zone_id = ctx.active_track_zones.get(gid)
            return AnomalyEvent(
                alert_type=self.alert_type,
                severity=self.severity,
                camera_id=ctx.frame.camera_id,
                zone_id=zone_id,
                global_track_id=gid,
                person_id=None,
                event_ts=datetime.fromtimestamp(
                    ctx.frame.timestamp_ms / 1000.0, tz=timezone.utc
                ).replace(tzinfo=None),
                dedup_key=f"UNKNOWN_PERSON:cam={ctx.frame.camera_id}:zone={zone_id}",
                payload={"local_track_id": tl.local_track_id},
            )
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=500, cooldown_ms=60_000, dedup_window_ms=60_000)

    def _gid_for_tracklet(self, tl: Tracklet, ctx: DetectorContext) -> uuid.UUID | None:
        return None  # orchestrator injects real lookup via _bind_seams

    def _person_id_for(self, gid: uuid.UUID, ctx: DetectorContext) -> int | None:
        return None
