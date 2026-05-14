"""Zone presence state machine.

On each update():
  - Find which zone (if any) the floor point falls in via point-in-polygon.
  - If entering a new zone: INSERT zone_presence (exited_at=NULL).
  - If leaving a zone: UPDATE exited_at on the open row.
  - If staying in same zone: no-op.

Maintains an in-memory cache of each tracklet's current zone to avoid
redundant DB queries on every frame.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

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
    """Tracks zone_presence rows for all active global_track_ids."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._current: dict[uuid.UUID, int | None] = {}  # gid -> zone_id or None

    def update(
        self,
        global_track_id: uuid.UUID,
        floor_x: float,
        floor_y: float,
    ) -> None:
        """Reconcile zone membership for one tracklet."""
        zones: list[Zone] = self._db.query(Zone).all()
        matched: int | None = None
        for z in zones:
            if z.polygon_json is None:
                continue
            poly: list[list[float]] = json.loads(z.polygon_json)
            if point_in_polygon(floor_x, floor_y, poly):
                matched = z.zone_id
                break

        prev = self._current.get(global_track_id)
        if matched == prev:
            return  # no change

        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        if prev is not None:
            self._close(global_track_id, prev, now)
        if matched is not None:
            self._open(global_track_id, matched, now)
        self._current[global_track_id] = matched

    def _open(self, gid: uuid.UUID, zone_id: int, ts: datetime) -> None:
        self._db.add(ZonePresence(zone_id=zone_id, global_track_id=gid, entered_at=ts))

    def _close(self, gid: uuid.UUID, zone_id: int, ts: datetime) -> None:
        row = (
            self._db.query(ZonePresence)
            .filter_by(zone_id=zone_id, global_track_id=gid)
            .filter(ZonePresence.exited_at.is_(None))
            .first()
        )
        if row is not None:
            row.exited_at = ts
