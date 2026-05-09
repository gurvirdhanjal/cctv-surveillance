"""Tests for Redis Stream client helpers."""

from __future__ import annotations

import fakeredis.aioredis as fake_aioredis
import pytest

from vms.redis_client import stream_ack, stream_add, stream_read


@pytest.fixture
def fake_redis() -> fake_aioredis.FakeRedis:
    return fake_aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_stream_add_returns_string_id(fake_redis: fake_aioredis.FakeRedis) -> None:
    msg_id = await stream_add(fake_redis, "test:s", {"k": "v"})
    assert isinstance(msg_id, str)
    assert "-" in msg_id


@pytest.mark.asyncio
async def test_stream_read_returns_added_message(fake_redis: fake_aioredis.FakeRedis) -> None:
    await stream_add(fake_redis, "test:s", {"data": "hello"})
    messages = await stream_read(fake_redis, "test:s", last_id="0-0")
    assert len(messages) == 1
    _msg_id, fields = messages[0]
    assert fields["data"] == "hello"


@pytest.mark.asyncio
async def test_stream_read_empty_stream_returns_empty_list(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    messages = await stream_read(fake_redis, "empty:s", last_id="0-0", block_ms=10)
    assert messages == []


@pytest.mark.asyncio
async def test_stream_ack_succeeds_for_valid_group(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    await fake_redis.xgroup_create("ack:s", "grp", id="0", mkstream=True)
    msg_id = await stream_add(fake_redis, "ack:s", {"k": "v"})
    # Read into the group's PEL first (XREADGROUP) so XACK has something to acknowledge
    await fake_redis.xreadgroup("grp", "consumer1", {"ack:s": ">"}, count=1)
    await stream_ack(fake_redis, "ack:s", "grp", msg_id)
    # Verify no messages remain pending
    pending = await fake_redis.xpending("ack:s", "grp")
    assert pending["pending"] == 0
