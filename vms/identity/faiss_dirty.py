"""Redis Stream events for FAISS index synchronisation.

publish_add:    call after a new PersonEmbedding is committed to the DB.
publish_remove: call after a GDPR purge blanks/removes embeddings.
"""

from __future__ import annotations

import json

import redis.asyncio as aioredis

from vms.redis_client import stream_add

_STREAM = "faiss_dirty"


async def publish_add(
    client: aioredis.Redis,
    embedding_id: int,
    person_id: int,
) -> None:
    """Notify identity services that a new embedding was enrolled."""
    await stream_add(
        client,
        _STREAM,
        {"action": "add", "embedding_id": str(embedding_id), "person_id": str(person_id)},
    )


async def publish_remove(
    client: aioredis.Redis,
    person_id: int,
    embedding_ids: list[int],
) -> None:
    """Notify identity services that embeddings were purged for a person."""
    await stream_add(
        client,
        _STREAM,
        {
            "action": "remove",
            "person_id": str(person_id),
            "embedding_ids": json.dumps(embedding_ids),
        },
    )
