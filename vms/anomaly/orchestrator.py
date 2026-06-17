"""AnomalyOrchestrator — consumes detections stream, runs detectors, feeds FSM."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.orm import Session

from vms.anomaly.base import AnomalyDetector, DetectorContext, FSMConfig, SeamProvider, ZoneLookup
from vms.anomaly.fsm import AlertFSM, FSMDecision
from vms.anomaly.maintenance import MaintenanceCalendar
from vms.config import get_settings
from vms.db.models import Zone, ZonePresence
from vms.identity.head_count import HeadCountAggregator
from vms.inference.messages import DetectionFrame
from vms.redis_client import stream_read

logger = logging.getLogger(__name__)

_DETECTIONS_STREAM = "detections"


@dataclass
class _DetectorState:
    consecutive_errors: int = 0
    total_errors: int = 0
    fires: int = 0
    suppressed: int = 0
    deduped: int = 0
    sustaining: int = 0
    disabled: bool = False


class AnomalyOrchestrator:
    """Single-process orchestrator.

    Production wiring:
      orch = AnomalyOrchestrator(
          redis_client=...,
          session_factory=SessionLocal,
          detectors=load_enabled_detectors(...).detectors,
          identity=IdentityEngine(...),
          zone_tracker=ZonePresenceTracker(),
          head_count=HeadCountAggregator(),
      )
      await orch.run()
    """

    def __init__(
        self,
        *,
        redis_client: aioredis.Redis,
        session_factory: Callable[[], Session],
        detectors: dict[str, AnomalyDetector],
        identity: Any | None = None,
        zone_tracker: Any | None = None,
        head_count: HeadCountAggregator | None = None,
        calendar: MaintenanceCalendar | None = None,
        max_consecutive_errors: int | None = None,
    ) -> None:
        self._redis = redis_client
        self._sf = session_factory
        self._detectors = detectors
        self._identity = identity
        self._zone_tracker = zone_tracker
        self._head_count = head_count or HeadCountAggregator()
        self._cal = calendar or MaintenanceCalendar(session_factory)
        self._fsm = AlertFSM(
            redis_client=redis_client, calendar=self._cal, session_factory=session_factory
        )
        self._fsm.rebuild_from_db()
        self._state: dict[str, _DetectorState] = {k: _DetectorState() for k in detectors}
        self._fsm_configs: dict[str, FSMConfig] = {k: d.fsm_config() for k, d in detectors.items()}
        self._max_errors = (
            max_consecutive_errors
            if max_consecutive_errors is not None
            else get_settings().anomaly_max_consecutive_errors
        )
        self._zone_cache: dict[int, ZoneLookup] | None = None
        self._zone_cache_expires: float = 0.0
        self._last_id = "0-0"
        self._running = False

        for det in detectors.values():
            self._bind_seams(det)

    def _bind_seams(self, det: AnomalyDetector) -> None:
        if not isinstance(det, SeamProvider):
            return
        det._gid_for_tracklet = self._gid_for_tracklet  # type: ignore[method-assign]
        det._person_id_for = self._person_id_for  # type: ignore[method-assign]
        det._registry_last_seen = self._registry_last_seen  # type: ignore[method-assign]
        det._entered_at = self._entered_at  # type: ignore[method-assign]

    def _zone_lookup(self) -> dict[int, ZoneLookup]:
        now = time.monotonic()
        if self._zone_cache is None or now >= self._zone_cache_expires:
            session = self._sf()
            rows = session.query(Zone).all()
            self._zone_cache = {
                r.zone_id: ZoneLookup(
                    zone_id=r.zone_id,
                    name=r.name,
                    is_restricted=r.is_restricted,
                    max_capacity=r.max_capacity,
                    allowed_hours=r.allowed_hours,
                    loiter_threshold_s=r.loiter_threshold_s,
                    polygon_json=r.polygon_json,
                )
                for r in rows
            }
            self._zone_cache_expires = now + get_settings().zone_cache_ttl_s
        return self._zone_cache

    def _active_track_zones(self) -> dict[uuid.UUID, int]:
        if self._zone_tracker is None:
            return {}
        return {gid: zid for gid, zid in self._zone_tracker._current.items() if zid is not None}

    def _gid_for_tracklet(self, tl: Any, ctx: DetectorContext) -> uuid.UUID | None:
        if self._identity is None:
            return None
        entry = self._identity._registry.get((tl.camera_id, tl.local_track_id))
        return entry.global_track_id if entry else None

    def _person_id_for(self, gid: uuid.UUID, ctx: DetectorContext) -> int | None:
        if self._identity is None:
            return None
        for entry in self._identity._registry.values():
            if entry.global_track_id == gid:
                return int(entry.person_id) if entry.person_id is not None else None
        return None

    def _registry_last_seen(self, ctx: DetectorContext) -> dict[uuid.UUID, int]:
        if self._identity is None:
            return {}
        return {e.global_track_id: e.last_seen_ms for e in self._identity._registry.values()}

    def _entered_at(self, gid: uuid.UUID, zone_id: int, ctx: DetectorContext) -> datetime | None:
        session = self._sf()
        row = (
            session.query(ZonePresence)
            .filter_by(global_track_id=gid, zone_id=zone_id)
            .filter(ZonePresence.exited_at.is_(None))
            .order_by(ZonePresence.entered_at.desc())
            .first()
        )
        return row.entered_at if row else None

    async def process_frame(self, frame: DetectionFrame) -> None:
        ctx = DetectorContext(
            frame=frame,
            zone_lookup=self._zone_lookup(),
            active_track_zones=self._active_track_zones(),
            head_count=self._head_count.counts_by_zone(),
            violence_score=frame.violence_score,
        )

        # Feed HeadCountAggregator from this frame
        if self._identity is not None and self._zone_tracker is not None:
            now = datetime.fromtimestamp(frame.timestamp_ms / 1000.0, tz=timezone.utc).replace(
                tzinfo=None
            )
            for gid, zid in ctx.active_track_zones.items():
                self._head_count.on_tracking_event(gid, zid, now)
            self._head_count.evict_stale(now, ttl_s=get_settings().head_count_track_ttl_s)

        for alert_type, det in self._detectors.items():
            st = self._state[alert_type]
            if st.disabled:
                continue
            try:
                if not det.should_run(ctx):
                    continue
                ev = det.evaluate(ctx)
            except Exception:
                st.consecutive_errors += 1
                st.total_errors += 1
                logger.exception("detector %s evaluate() raised", alert_type)
                if st.consecutive_errors >= self._max_errors:
                    st.disabled = True
                    logger.error(
                        "detector %s auto-disabled after %d errors",
                        alert_type,
                        st.consecutive_errors,
                    )
                continue
            st.consecutive_errors = 0
            if ev is None:
                continue
            decision = await self._fsm.process(ev, self._fsm_configs[alert_type])
            if decision is FSMDecision.FIRED:
                st.fires += 1
            elif decision is FSMDecision.SUPPRESSED:
                st.suppressed += 1
            elif decision is FSMDecision.DEDUPED:
                st.deduped += 1
            elif decision is FSMDecision.SUSTAINING:
                st.sustaining += 1

    def health(self) -> dict[str, dict[str, Any]]:
        return {
            k: {
                "consecutive_errors": v.consecutive_errors,
                "total_errors": v.total_errors,
                "fires": v.fires,
                "suppressed": v.suppressed,
                "deduped": v.deduped,
                "sustaining": v.sustaining,
                "disabled": v.disabled,
            }
            for k, v in self._state.items()
        }

    async def run(self) -> None:
        self._running = True
        _frames_since_evict = 0
        while self._running:
            messages = await stream_read(
                self._redis, _DETECTIONS_STREAM, last_id=self._last_id, count=100
            )
            if not messages:
                await asyncio.sleep(0.05)
                continue
            for msg_id, fields in messages:
                try:
                    frame = DetectionFrame.from_redis_fields(fields)
                    await self.process_frame(frame)
                except Exception:
                    logger.exception("orchestrator frame handle failed msg=%s", msg_id)
                self._last_id = msg_id
                _frames_since_evict += 1
                if _frames_since_evict >= 100:
                    self._fsm.evict_closed(datetime.now(timezone.utc).replace(tzinfo=None))
                    _frames_since_evict = 0

    async def stop(self) -> None:
        self._running = False
