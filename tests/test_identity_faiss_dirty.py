from __future__ import annotations

import json

import fakeredis.aioredis as fake_aioredis
import pytest

from vms.identity.faiss_dirty import publish_add, publish_remove


@pytest.fixture
def fake_redis() -> fake_aioredis.FakeRedis:
    return fake_aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_publish_add_writes_correct_fields(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    await publish_add(fake_redis, embedding_id=7, person_id=3)
    msgs = await fake_redis.xread({"faiss_dirty": "0-0"}, count=10)
    assert len(msgs) == 1
    _stream, entries = msgs[0]
    _msg_id, fields = entries[0]
    assert fields["action"] == "add"
    assert fields["embedding_id"] == "7"
    assert fields["person_id"] == "3"


@pytest.mark.asyncio
async def test_publish_remove_writes_correct_fields(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    await publish_remove(fake_redis, person_id=5, embedding_ids=[1, 2, 3])
    msgs = await fake_redis.xread({"faiss_dirty": "0-0"}, count=10)
    assert len(msgs) == 1
    _stream, entries = msgs[0]
    _msg_id, fields = entries[0]
    assert fields["action"] == "remove"
    assert fields["person_id"] == "5"
    assert json.loads(fields["embedding_ids"]) == [1, 2, 3]
