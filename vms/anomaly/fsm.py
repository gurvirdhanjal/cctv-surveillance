"""AlertFSM — sustain/cooldown/dedup state machine + alerts persistence.

Memory state per dedup_key:
  - first_seen_ts: first event timestamp in the current sustain window
  - last_seen_ts: most recent event timestamp
  - alert_id: int if an active alert exists, else None
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import redis.asyncio as aioredis
from sqlalchemy.orm import Session

from vms.anomaly.base import AnomalyEvent, FSMConfig
from vms.anomaly.maintenance import MaintenanceCalendar
from vms.anomaly.streams import publish_alert_fired
from vms.db.models import Alert

logger = logging.getLogger(__name__)


class FSMDecision(str, enum.Enum):
    SUSTAINING = "SUSTAINING"
    FIRED = "FIRED"
    DEDUPED = "DEDUPED"
    SUPPRESSED = "SUPPRESSED"


@dataclass
class _Entry:
    first_seen_ts: datetime
    last_seen_ts: datetime
    alert_id: int | None


class AlertFSM:
    def __init__(
        self,
        *,
        redis_client: aioredis.Redis,
        calendar: MaintenanceCalendar,
        session_factory: Callable[[], Session],
    ) -> None:
        self._redis = redis_client
        self._cal = calendar
        self._sf = session_factory
        self._entries: dict[str, _Entry] = {}

    def rebuild_from_db(self) -> None:
        """Reload active alerts so dedup survives a process restart."""
        session = self._sf()
        rows = (
            session.query(Alert).filter(Alert.state == "active", Alert.dedup_key.is_not(None)).all()
        )
        self._entries.clear()
        for r in rows:
            assert r.dedup_key is not None
            self._entries[r.dedup_key] = _Entry(
                first_seen_ts=r.triggered_at,
                last_seen_ts=r.triggered_at,
                alert_id=r.alert_id,
            )

    def evict_closed(self, now: datetime) -> int:
        """Drop entries whose backing alert is no longer active. Returns evicted count."""
        if not self._entries:
            return 0
        session = self._sf()
        active_ids = {
            aid for (aid,) in session.query(Alert.alert_id).filter(Alert.state == "active").all()
        }
        stale = [k for k, e in self._entries.items() if e.alert_id not in active_ids]
        for k in stale:
            del self._entries[k]
        return len(stale)

    async def process(self, ev: AnomalyEvent, cfg: FSMConfig) -> FSMDecision:
        # Dedup is lifetime-of-alert: same dedup_key returns DEDUPED until the
        # alert is operator-resolved and evict_closed() clears the entry.
        # cfg.cooldown_ms / cfg.dedup_window_ms are reserved for a future
        # time-based auto-reset path; they are not enforced here.
        entry = self._entries.get(ev.dedup_key)

        if entry is None:
            self._entries[ev.dedup_key] = _Entry(
                first_seen_ts=ev.event_ts,
                last_seen_ts=ev.event_ts,
                alert_id=None,
            )
            entry = self._entries[ev.dedup_key]
            if cfg.sustain_ms == 0:
                return await self._fire(ev, entry)
            return FSMDecision.SUSTAINING

        entry.last_seen_ts = ev.event_ts

        if entry.alert_id is not None:
            return FSMDecision.DEDUPED

        elapsed_ms = int((ev.event_ts - entry.first_seen_ts).total_seconds() * 1000)
        if elapsed_ms < cfg.sustain_ms:
            return FSMDecision.SUSTAINING

        return await self._fire(ev, entry)

    async def _fire(self, ev: AnomalyEvent, entry: _Entry) -> FSMDecision:
        session = self._sf()
        window_id = self._cal.is_suppressed(
            camera_id=ev.camera_id,
            zone_id=ev.zone_id,
            alert_type=ev.alert_type,
            event_ts=ev.event_ts,
        )

        row = Alert(
            alert_type=ev.alert_type,
            severity=ev.severity.value,
            state="suppressed" if window_id is not None else "active",
            camera_id=ev.camera_id,
            zone_id=ev.zone_id,
            global_track_id=ev.global_track_id,
            person_id=ev.person_id,
            triggered_at=ev.event_ts,
            suppressed_by_window_id=window_id,
            dedup_key=ev.dedup_key,
        )
        session.add(row)
        session.flush()
        entry.alert_id = row.alert_id

        if window_id is not None:
            logger.info(
                "alert suppressed alert_id=%s dedup=%s window=%s",
                row.alert_id,
                ev.dedup_key,
                window_id,
            )
            return FSMDecision.SUPPRESSED

        await publish_alert_fired(
            self._redis,
            alert_id=row.alert_id,
            alert_type=ev.alert_type,
            severity=ev.severity.value,
            camera_id=ev.camera_id,
            zone_id=ev.zone_id,
            global_track_id=ev.global_track_id,
            person_id=ev.person_id,
            triggered_at=ev.event_ts,
        )
        logger.info(
            "alert fired alert_id=%s dedup=%s type=%s",
            row.alert_id,
            ev.dedup_key,
            ev.alert_type,
        )
        return FSMDecision.FIRED
