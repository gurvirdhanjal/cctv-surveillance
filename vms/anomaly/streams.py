"""Stream contracts for anomaly subsystem.

Stream: alerts
Schema (v1):
  payload (JSON): {
    alert_id, alert_type, severity, camera_id, zone_id,
    global_track_id, person_id, triggered_at (ISO8601 UTC),
    schema_version: "1"
  }
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import redis.asyncio as aioredis

from vms.config import get_settings
from vms.redis_client import stream_add

_STREAM = "alerts"


async def publish_alert_fired(
    client: aioredis.Redis,
    *,
    alert_id: int,
    alert_type: str,
    severity: str,
    camera_id: int,
    zone_id: int | None,
    global_track_id: uuid.UUID | None,
    person_id: int | None,
    triggered_at: datetime,
) -> str:
    payload = {
        "alert_id": alert_id,
        "alert_type": alert_type,
        "severity": severity,
        "camera_id": camera_id,
        "zone_id": zone_id,
        "global_track_id": str(global_track_id) if global_track_id else None,
        "person_id": person_id,
        "triggered_at": triggered_at.isoformat() + "Z",
        "schema_version": "1",
    }
    return await stream_add(
        client,
        _STREAM,
        {"payload": json.dumps(payload)},
        maxlen=get_settings().alerts_stream_maxlen,
    )
