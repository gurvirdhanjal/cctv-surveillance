"""HeadCountAggregator (spec §N.1).

In-memory aggregator subscribed (in production) to the same DetectionFrames
the orchestrator consumes. Maintains:
  - by_zone: dict[int, set[Key]]
  - last_seen: dict[Key, (zone_id, ts)]

Not thread-safe — single owner per process.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

# Identified persons dedup by int person_id; unknowns dedup per-track by gid.
Key = int | uuid.UUID


@dataclass(frozen=True)
class HeadCountSnapshot:
    plant_total: int
    by_zone: dict[int, int]
    ts: datetime
    uncertain_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plant_total": self.plant_total,
            "by_zone": dict(self.by_zone),
            "uncertain_count": self.uncertain_count,
            "ts": self.ts.isoformat() + "Z",
            "schema_version": "2",
        }


@dataclass
class HeadCountAggregator:
    _by_zone: dict[int, set[Key]] = field(default_factory=lambda: defaultdict(set))
    _last_seen: dict[Key, tuple[int, datetime]] = field(default_factory=dict)
    overlapping_zones: set[int] = field(default_factory=set)
    # EMA state for smooth_snapshot() — not used by snapshot()
    _ema_total: float = field(default=0.0)
    _ema_by_zone: dict[int, float] = field(default_factory=dict)
    _ema_initialized: bool = field(default=False)

    def on_tracking_event(
        self,
        gid: uuid.UUID,
        zone_id: int | None,
        ts: datetime,
        person_id: int | None = None,
    ) -> None:
        # Identified persons dedup globally by person_id; unknowns dedup per-track by gid.
        key: Key = person_id if person_id is not None else gid
        if zone_id is None:
            prev = self._last_seen.pop(key, None)
            if prev is not None:
                self._by_zone[prev[0]].discard(key)
            return
        prev = self._last_seen.get(key)
        if prev is not None and prev[0] != zone_id:
            self._by_zone[prev[0]].discard(key)
        self._by_zone[zone_id].add(key)
        self._last_seen[key] = (zone_id, ts)

    def evict_stale(self, now: datetime, ttl_s: int) -> int:
        cutoff = now - timedelta(seconds=ttl_s)
        stale = [key for key, (_z, ts) in self._last_seen.items() if ts < cutoff]
        for key in stale:
            zid, _ = self._last_seen.pop(key)
            self._by_zone[zid].discard(key)
        return len(stale)

    def snapshot(self) -> HeadCountSnapshot:
        non_empty = {zid: len(s) for zid, s in self._by_zone.items() if s}
        uncertain = sum(
            1
            for zid in self.overlapping_zones
            for key in self._by_zone.get(zid, set())
            if isinstance(key, uuid.UUID)
        )
        return HeadCountSnapshot(
            plant_total=sum(non_empty.values()),
            by_zone=non_empty,
            ts=datetime.now(timezone.utc).replace(tzinfo=None),
            uncertain_count=uncertain,
        )

    def counts_by_zone(self) -> dict[int, int]:
        return {zid: len(s) for zid, s in self._by_zone.items() if s}

    def smooth_snapshot(self, alpha: float = 0.3) -> HeadCountSnapshot:
        """Return a head-count snapshot with EMA smoothing applied.

        Uses an exponential moving average to dampen RTSP track-flicker.
        alpha=0.3 damps single-frame spikes while tracking real changes in ~5 frames.
        On the first call the EMA is seeded from the raw counts (no lag on startup).
        """
        raw = self.snapshot()
        if not self._ema_initialized:
            self._ema_total = float(raw.plant_total)
            self._ema_by_zone = {z: float(c) for z, c in raw.by_zone.items()}
            self._ema_initialized = True
        else:
            self._ema_total = alpha * raw.plant_total + (1.0 - alpha) * self._ema_total
            all_zones = set(raw.by_zone) | set(self._ema_by_zone)
            self._ema_by_zone = {
                z: alpha * float(raw.by_zone.get(z, 0))
                + (1.0 - alpha) * self._ema_by_zone.get(z, 0.0)
                for z in all_zones
            }
        smoothed_by_zone = {z: round(v) for z, v in self._ema_by_zone.items() if round(v) > 0}
        return HeadCountSnapshot(
            plant_total=round(self._ema_total),
            by_zone=smoothed_by_zone,
            ts=datetime.now(timezone.utc).replace(tzinfo=None),
            uncertain_count=raw.uncertain_count,
        )
