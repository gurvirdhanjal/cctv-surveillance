"""Zone resolver and badge-to-person lookup for BLE events.

Zone reader map (VMS_BLE_ZONE_READER_MAP_JSON):
  {"AA:BB:CC:DD:EE:FF": 3, "11:22:33:44:55:66": 7, ...}
  Maps BLE reader MAC address -> zone_id.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ZoneResolver:
    """Maps BLE reader_id to zone_id using configured JSON map."""

    def __init__(self, zone_reader_map_json: str) -> None:
        try:
            self._map: dict[str, int] = json.loads(zone_reader_map_json)
        except (json.JSONDecodeError, ValueError):
            logger.warning("ZoneResolver: invalid JSON — all readers map to zone None")
            self._map = {}

    def zone_for_reader(self, reader_id: str) -> int | None:
        """Return zone_id for a reader_id, or None if not configured."""
        return self._map.get(reader_id)


def lookup_person_by_badge(db: Session, badge_id: str) -> int | None:
    """Return person_id for the given badge_id, or None if not enrolled."""
    from vms.db.models import Person

    row = (
        db.query(Person)
        .filter(Person.badge_id == badge_id, Person.is_active.is_(True))
        .first()
    )
    return row.person_id if row is not None else None
