"""Zone presence state machine.

On each update():
  - Load zone polygons from DB (cached by zone_cache_ttl_s setting).
  - Find which zone (if any) the floor point falls in via point-in-polygon.
  - If entering a new zone: INSERT zone_presence (exited_at=NULL).
  - If leaving a zone: UPDATE exited_at on the open row.
  - If staying in same zone: no-op.

Session is passed per-call so the tracker can be long-lived without holding
a stale DB connection.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from vms.config import get_settings
from vms.db.models import Zone, ZonePresence

logger = logging.getLogger(__name__)


def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test. polygon is a list of [x, y] pairs."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


class ZonePresenceTracker:
    """Tracks zone_presence rows for all active global_track_ids.

    Thread-safety: not thread-safe. Use one instance per worker process.
    """

    def __init__(self) -> None:
        self._current: dict[uuid.UUID, int | None] = {}  # gid -> current zone_id or None
        self._zones_cache: list[Zone] = []
        self._cache_expires_at: float = 0.0

    def _get_zones(self, db: Session) -> list[Zone]:
        now = time.monotonic()
        if now >= self._cache_expires_at:
            self._zones_cache = db.query(Zone).all()
            self._cache_expires_at = now + get_settings().zone_cache_ttl_s
        return self._zones_cache

    def update(
        self,
        db: Session,
        global_track_id: uuid.UUID,
        floor_x: float,
        floor_y: float,
    ) -> None:
        """Reconcile zone membership for one tracklet."""
        zones = self._get_zones(db)
        matched: int | None = None
        for z in zones:
            if z.polygon_json is None:
                continue
            try:
                poly: list[list[float]] = json.loads(z.polygon_json)
            except (json.JSONDecodeError, ValueError):
                continue
            if point_in_polygon(floor_x, floor_y, poly):
                matched = z.zone_id
                break

        prev = self._current.get(global_track_id)
        if matched == prev:
            return

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if prev is not None:
            self._close(db, global_track_id, prev, now_utc)
        if matched is not None:
            self._open(db, global_track_id, matched, now_utc)
        self._current[global_track_id] = matched

    def _open(self, db: Session, gid: uuid.UUID, zone_id: int, ts: datetime) -> None:
        db.add(ZonePresence(zone_id=zone_id, global_track_id=gid, entered_at=ts))

    def _close(self, db: Session, gid: uuid.UUID, zone_id: int, ts: datetime) -> None:
        db.flush()  # ensure any pending _open rows are visible to the query
        row = (
            db.query(ZonePresence)
            .filter_by(zone_id=zone_id, global_track_id=gid)
            .filter(ZonePresence.exited_at.is_(None))
            .first()
        )
        if row is not None:
            row.exited_at = ts
