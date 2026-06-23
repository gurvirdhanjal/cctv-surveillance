"""Redis → Socket.io bridge — consumes alert stream, emits §10 events."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from vms.api.realtime.server import sio

logger = logging.getLogger(__name__)


async def _emit_alert(event: dict[str, Any]) -> None:
    """Emit alert_fired from a raw Redis stream entry dict."""
    payload: dict[str, Any] = {
        "alert_id": int(event.get("alert_id", 0)),
        "alert_type": str(event.get("alert_type", "")),
        "severity": str(event.get("severity", "")),
        "camera_id": int(event["camera_id"]) if event.get("camera_id") else None,
        "zone_id": int(event["zone_id"]) if event.get("zone_id") else None,
        "global_track_id": event.get("global_track_id"),
        "snapshot_url": event.get("snapshot_url"),
        "ts": str(event.get("ts", "")),
    }
    await sio.emit("alert_fired", payload)


async def run_bridge(redis_url: str) -> None:
    """Read the Redis alerts stream and emit Socket.io events to connected clients.

    Runs indefinitely until cancelled. Reconnects on Redis errors with a 1s backoff.
    """
    import redis.asyncio as aioredis

    r: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
        redis_url, decode_responses=True
    )
    last_id = "$"
    degraded = False

    while True:
        try:
            messages = await r.xread({"vms:alerts": last_id}, block=1000, count=10)
            if degraded:
                await sio.emit("degraded_mode", {"enabled": False, "reason": ""})
                degraded = False
            for _stream, entries in messages or []:
                for msg_id, data in entries:
                    last_id = str(msg_id)
                    await _emit_alert(data)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Bridge error; reconnecting in 1s")
            if not degraded:
                await sio.emit(
                    "degraded_mode",
                    {"enabled": True, "reason": "Redis stream unavailable"},
                )
                degraded = True
            await asyncio.sleep(1)

    with contextlib.suppress(Exception):
        await r.aclose()
