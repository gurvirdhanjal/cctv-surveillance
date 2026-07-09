"""Redis → Socket.io bridge — consumes alert + metrics streams, emits §10 events."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from vms.api.realtime.server import sio
from vms.scheduler.system_metrics import METRICS_STREAM

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


async def _emit_system_metrics(entry: dict[str, Any]) -> None:
    """Emit system_metrics from a raw metrics-stream entry (spec §8.4)."""
    await sio.emit("system_metrics", json.loads(entry["payload"]))


async def run_bridge(redis_url: str) -> None:
    """Read the Redis alert + metrics streams and emit Socket.io events.

    Runs indefinitely until cancelled. Reconnects on Redis errors with a 1s backoff.
    """
    import redis.asyncio as aioredis

    r: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
        redis_url, decode_responses=True
    )
    # typed to redis-py's xread parameter (dict is invariant in its key type)
    last_ids: dict[bytes | str | memoryview, int | bytes | str | memoryview] = {
        "vms:alerts": "$",
        METRICS_STREAM: "$",
    }
    degraded = False

    while True:
        try:
            messages = await r.xread(last_ids, block=1000, count=10)
            if degraded:
                await sio.emit("degraded_mode", {"enabled": False, "reason": ""})
                degraded = False
            for stream, entries in messages or []:
                stream_name = str(stream)
                for msg_id, data in entries:
                    last_ids[stream_name] = str(msg_id)
                    if stream_name == METRICS_STREAM:
                        await _emit_system_metrics(data)
                    else:
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
