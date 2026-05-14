"""Batch inserts DetectionFrame tracklets into tracking_events.

Uses INSERT ... ON CONFLICT DO NOTHING for idempotent replay (CLAUDE.md §6.3).
The unique constraint uq_tracking_idem is on (camera_id, local_track_id, event_ts).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.orm import Session

from vms.inference.messages import DetectionFrame
from vms.redis_client import stream_read

logger = logging.getLogger(__name__)

_DETECTIONS_STREAM = "detections"
_INSERT_SQL = text(
    """
    INSERT INTO tracking_events
        (camera_id, local_track_id, global_track_id,
         bbox_x1, bbox_y1, bbox_x2, bbox_y2,
         event_ts, ingest_ts, seq_id)
    VALUES
        (:camera_id, :local_track_id, :global_track_id,
         :bbox_x1, :bbox_y1, :bbox_x2, :bbox_y2,
         :event_ts, :ingest_ts, :seq_id)
    ON CONFLICT ON CONSTRAINT uq_tracking_idem DO NOTHING
    """
)


def flush_detection_frame(db: Session, frame: DetectionFrame) -> None:
    """Write all tracklets from one DetectionFrame to tracking_events (idempotent)."""
    if not frame.tracklets:
        return

    event_ts = datetime.fromtimestamp(frame.timestamp_ms / 1000.0, tz=timezone.utc).replace(
        tzinfo=None
    )
    now_utc = datetime.utcnow()
    rows = [
        {
            "camera_id": t.camera_id,
            "local_track_id": str(t.local_track_id),
            "global_track_id": str(uuid.uuid4()),
            "bbox_x1": t.bbox[0],
            "bbox_y1": t.bbox[1],
            "bbox_x2": t.bbox[2],
            "bbox_y2": t.bbox[3],
            "event_ts": event_ts,
            "ingest_ts": now_utc,
            "seq_id": frame.seq_id,
        }
        for t in frame.tracklets
    ]
    db.execute(_INSERT_SQL, rows)


class DBWriter:
    """Consumes the 'detections' Redis stream and batch-writes to tracking_events."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        db_factory: type[Session],
    ) -> None:
        self._redis = redis_client
        self._db_factory = db_factory
        self._running = False
        self._last_id = "0-0"

    async def run(self) -> None:
        self._running = True
        while self._running:
            messages = await stream_read(
                self._redis, _DETECTIONS_STREAM, last_id=self._last_id, count=100
            )
            if messages:
                db = self._db_factory()
                try:
                    for msg_id, fields in messages:
                        frame = DetectionFrame.from_redis_fields(fields)
                        flush_detection_frame(db, frame)
                        self._last_id = msg_id
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("DB writer flush failed")
                finally:
                    db.close()
            else:
                await asyncio.sleep(0.05)

    async def stop(self) -> None:
        self._running = False
