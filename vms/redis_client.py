"""Redis connection and Stream helpers.

stream_read() uses XREAD (no consumer group) — suitable for simple consumers
that track their own last_id. stream_ack() requires a consumer group and is
only valid for messages read via XREADGROUP (called directly by the consumer).
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis

from vms.config import get_settings


def get_redis() -> aioredis.Redis:
    """Return a Redis client using VMS_REDIS_URL."""
    return aioredis.from_url(  # type: ignore[no-untyped-call,no-any-return]
        get_settings().redis_url, decode_responses=True
    )


async def stream_add(
    client: aioredis.Redis,
    stream: str,
    fields: dict[str, str],
    maxlen: int | None = None,
) -> str:
    """XADD with MAXLEN cap. Returns the new message ID."""
    if maxlen is None:
        maxlen = get_settings().redis_stream_maxlen
    result: str = await client.xadd(stream, fields, maxlen=maxlen)  # type: ignore[arg-type]
    return result


async def stream_read(
    client: aioredis.Redis,
    stream: str,
    last_id: str = "$",
    count: int = 100,
    block_ms: int = 100,
) -> list[tuple[str, dict[str, str]]]:
    """Blocking XREAD. Returns list of (message_id, fields) pairs."""
    raw: Any = await client.xread({stream: last_id}, count=count, block=block_ms)
    if not raw:
        return []
    _, messages = raw[0]
    return [(msg_id, dict(fields)) for msg_id, fields in messages]


async def stream_ack(
    client: aioredis.Redis,
    stream: str,
    group: str,
    msg_id: str,
) -> None:
    """XACK a processed message in the given consumer group."""
    await client.xack(stream, group, msg_id)
