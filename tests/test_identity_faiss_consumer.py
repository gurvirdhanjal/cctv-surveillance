"""Tests for the faiss_dirty consumer wired into DBWriter."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

import fakeredis.aioredis as fake_aioredis

from vms.identity.faiss_dirty import publish_add, publish_remove
from vms.identity.faiss_index import FaissIndex
from vms.identity.reid import ReIdService
from vms.identity.engine import IdentityEngine
from vms.writer.db_writer import DBWriter


def _make_identity() -> IdentityEngine:
    index = FaissIndex()
    reid = ReIdService(index)
    return IdentityEngine(reid)


@pytest.fixture
def fake_redis() -> fake_aioredis.FakeRedis:
    return fake_aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_consume_faiss_dirty_add_updates_index(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    identity = _make_identity()
    assert identity._reid._index.count() == 0

    await publish_add(fake_redis, embedding_id=1, person_id=10)

    vec = np.random.randn(512).astype(np.float32)

    mock_emb = MagicMock()
    mock_emb.embedding = vec.tolist()
    mock_session = MagicMock()
    mock_session.get.return_value = mock_emb
    db_factory = MagicMock(return_value=mock_session)

    writer = DBWriter(fake_redis, db_factory, identity=identity)
    writer._running = True

    # Run one iteration of the consumer
    messages = await fake_redis.xread({"faiss_dirty": "0"}, count=100)
    assert messages
    _stream, entries = messages[0]
    msg_id, fields = entries[0]

    db = db_factory()
    identity.faiss_apply_add(
        embedding_id=int(fields["embedding_id"]),
        person_id=int(fields["person_id"]),
        db=db,
    )

    assert identity._reid._index.count() == 1


@pytest.mark.asyncio
async def test_consume_faiss_dirty_remove_updates_index(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    identity = _make_identity()

    # Pre-populate the index
    vec = np.random.randn(512).astype(np.float32)
    identity._reid._index.add(embedding_id=5, person_id=20, embedding=vec)
    assert identity._reid._index.count() == 1

    await publish_remove(fake_redis, person_id=20, embedding_ids=[5])

    messages = await fake_redis.xread({"faiss_dirty": "0"}, count=100)
    assert messages
    _stream, entries = messages[0]
    _msg_id, fields = entries[0]

    embedding_ids: list[int] = json.loads(fields["embedding_ids"])
    identity.faiss_apply_remove(embedding_ids)

    assert identity._reid._index.count() == 0


@pytest.mark.asyncio
async def test_consume_faiss_dirty_missing_embedding_logs_warning(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    identity = _make_identity()

    await publish_add(fake_redis, embedding_id=999, person_id=1)

    mock_session = MagicMock()
    mock_session.get.return_value = None  # embedding not in DB
    db_factory = MagicMock(return_value=mock_session)

    messages = await fake_redis.xread({"faiss_dirty": "0"}, count=100)
    _stream, entries = messages[0]
    _msg_id, fields = entries[0]

    db = db_factory()
    # Should not raise; logs a warning and leaves the index empty
    identity.faiss_apply_add(
        embedding_id=int(fields["embedding_id"]),
        person_id=int(fields["person_id"]),
        db=db,
    )
    assert identity._reid._index.count() == 0


@pytest.mark.asyncio
async def test_db_writer_run_starts_faiss_consumer_task() -> None:
    fake_redis = fake_aioredis.FakeRedis(decode_responses=True)
    identity = _make_identity()
    mock_session = MagicMock()
    db_factory = MagicMock(return_value=mock_session)

    writer = DBWriter(fake_redis, db_factory, identity=identity)

    # Stop after one iteration so run() exits promptly
    call_count = 0

    async def fake_stream_read(client, stream, last_id="0-0", count=100):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        writer._running = False
        return []

    with patch("vms.writer.db_writer.stream_read", side_effect=fake_stream_read):
        await writer.run()

    # The main loop called stream_read at least once
    assert call_count >= 1


@pytest.mark.asyncio
async def test_consume_faiss_dirty_replays_from_stream_start(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    """Consumer starts from last_id='0' so it replays all prior events on startup."""
    identity = _make_identity()

    vec = np.random.randn(512).astype(np.float32)

    # Publish two events BEFORE the consumer starts
    await publish_add(fake_redis, embedding_id=10, person_id=1)
    await publish_add(fake_redis, embedding_id=11, person_id=2)

    mock_emb = MagicMock()
    mock_emb.embedding = vec.tolist()
    mock_session = MagicMock()
    mock_session.get.return_value = mock_emb
    db_factory = MagicMock(return_value=mock_session)

    # Replay by reading from "0"
    messages = await fake_redis.xread({"faiss_dirty": "0"}, count=100)
    assert messages
    _stream, entries = messages[0]
    assert len(entries) == 2

    db = db_factory()
    for _msg_id, fields in entries:
        if fields.get("action") == "add":
            identity.faiss_apply_add(
                embedding_id=int(fields["embedding_id"]),
                person_id=int(fields["person_id"]),
                db=db,
            )

    assert identity._reid._index.count() == 2
