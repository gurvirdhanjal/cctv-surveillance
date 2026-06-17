"""HeadCountAggregator (spec §N.1).

In-memory aggregator subscribed (in production) to the same DetectionFrames
the orchestrator consumes. Maintains:
  - by_zone: dict[int, set[gid]]
  - last_seen: dict[gid, (zone_id, ts)]

Not thread-safe — single owner per process.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class HeadCountSnapshot:
    plant_total: int
    by_zone: dict[int, int]
    ts: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "plant_total": self.plant_total,
            "by_zone": dict(self.by_zone),
            "ts": self.ts.isoformat() + "Z",
            "schema_version": "1",
        }


@dataclass
class HeadCountAggregator:
    _by_zone: dict[int, set[uuid.UUID]] = field(default_factory=lambda: defaultdict(set))
    _last_seen: dict[uuid.UUID, tuple[int, datetime]] = field(default_factory=dict)

    def on_tracking_event(self, gid: uuid.UUID, zone_id: int | None, ts: datetime) -> None:
        if zone_id is None:
            prev = self._last_seen.pop(gid, None)
            if prev is not None:
                self._by_zone[prev[0]].discard(gid)
            return
        prev = self._last_seen.get(gid)
        if prev is not None and prev[0] != zone_id:
            self._by_zone[prev[0]].discard(gid)
        self._by_zone[zone_id].add(gid)
        self._last_seen[gid] = (zone_id, ts)

    def evict_stale(self, now: datetime, ttl_s: int) -> int:
        cutoff = now - timedelta(seconds=ttl_s)
        stale = [gid for gid, (_z, ts) in self._last_seen.items() if ts < cutoff]
        for gid in stale:
            zid, _ = self._last_seen.pop(gid)
            self._by_zone[zid].discard(gid)
        return len(stale)

    def snapshot(self) -> HeadCountSnapshot:
        non_empty = {zid: len(s) for zid, s in self._by_zone.items() if s}
        return HeadCountSnapshot(
            plant_total=sum(non_empty.values()),
            by_zone=non_empty,
            ts=datetime.now(timezone.utc).replace(tzinfo=None),
        )

    def counts_by_zone(self) -> dict[int, int]:
        return {zid: len(s) for zid, s in self._by_zone.items() if s}
