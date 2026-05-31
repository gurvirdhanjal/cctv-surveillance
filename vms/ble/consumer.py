"""BLE stream consumer — links badge_id to person_id and anchors in IdentityEngine."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from vms.ble.messages import BleEvent
from vms.ble.resolver import ZoneResolver, lookup_person_by_badge
from vms.config import get_settings
from vms.redis_client import stream_read

logger = logging.getLogger(__name__)

_BLE_STREAM = "ble_events"


class BleConsumer:
    """Reads ble_events stream, resolves person_id, anchors identity in IdentityEngine."""

    def __init__(
        self,
        redis_client: Any,
        db_factory: Any,       # callable returning SQLAlchemy Session
        identity_engine: Any,  # IdentityEngine
    ) -> None:
        self._redis = redis_client
        self._db_factory = db_factory
        self._engine = identity_engine
        self._running = False
        self._last_id = "0"
        self._resolver: ZoneResolver | None = None

    def _get_resolver(self) -> ZoneResolver:
        if self._resolver is None:
            self._resolver = ZoneResolver(get_settings().ble_zone_reader_map_json)
        return self._resolver

    async def run(self) -> None:
        self._running = True
        while self._running:
            messages = await stream_read(
                self._redis, _BLE_STREAM, last_id=self._last_id, count=50
            )
            for msg_id, fields in messages:
                await self._process(fields)
                self._last_id = msg_id
            if not messages:
                await asyncio.sleep(0.5)

    async def stop(self) -> None:
        self._running = False

    async def _process(self, fields: dict[str, str]) -> None:
        event = BleEvent.from_redis_fields(fields)
        resolver = self._get_resolver()
        zone_id = resolver.zone_for_reader(event.reader_id)

        db = self._db_factory()
        try:
            person_id = lookup_person_by_badge(db, event.badge_id)
            if person_id is None:
                return  # unregistered badge — ignore

            # Anchor person_id to any in-flight registry entry for this person
            self._engine.anchor_person_by_badge(person_id, event.badge_id)

            _write_ble_event(db, event, person_id, zone_id)
            db.commit()
            logger.debug("BLE: badge=%s person=%d zone=%s", event.badge_id, person_id, zone_id)
        except Exception:
            db.rollback()
            logger.exception("BLE consumer error for badge %s", event.badge_id)
        finally:
            db.close()


def _write_ble_event(
    db: Any,
    event: BleEvent,
    person_id: int | None,
    zone_id: int | None,
) -> None:
    from vms.db.models import BleEvent as BleEventORM

    db.add(
        BleEventORM(
            person_id=person_id,
            badge_id=event.badge_id,
            zone_id=zone_id,
            rssi=event.rssi,
            reader_id=event.reader_id,
            event_ts=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
