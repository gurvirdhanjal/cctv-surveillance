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

from vms.db.models import Camera
from vms.identity.engine import IdentityEngine
from vms.identity.homography import project_to_floor
from vms.identity.zone_presence import ZonePresenceTracker
from vms.inference.messages import DetectionFrame
from vms.redis_client import stream_read

logger = logging.getLogger(__name__)

_DETECTIONS_STREAM = "detections"
_EVICT_EVERY = 1000  # evict stale registry entries every N messages

_INSERT_SQL = text(
    """
    INSERT INTO tracking_events
        (camera_id, local_track_id, global_track_id, person_id,
         bbox_x1, bbox_y1, bbox_x2, bbox_y2,
         floor_x, floor_y,
         event_ts, ingest_ts, seq_id)
    VALUES
        (:camera_id, :local_track_id, :global_track_id, :person_id,
         :bbox_x1, :bbox_y1, :bbox_x2, :bbox_y2,
         :floor_x, :floor_y,
         :event_ts, :ingest_ts, :seq_id)
    ON CONFLICT ON CONSTRAINT uq_tracking_idem DO NOTHING
    """
)


def flush_detection_frame(
    db: Session,
    frame: DetectionFrame,
    *,
    identity: IdentityEngine | None = None,
    homography_json: str | None = None,
    zone_tracker: ZonePresenceTracker | None = None,
) -> None:
    """Write all tracklets from one DetectionFrame to tracking_events (idempotent).

    When identity is provided, global_track_id and person_id are resolved through
    IdentityEngine rather than generated randomly.
    """
    if not frame.tracklets:
        return

    event_ts = datetime.fromtimestamp(frame.timestamp_ms / 1000.0, tz=timezone.utc).replace(
        tzinfo=None
    )
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    rows = []
    for t in frame.tracklets:
        embedding = t.embedding if t.embedding else None

        if identity is not None:
            gid = identity.assign_global_track_id(t.camera_id, t.local_track_id, embedding)
            person_id = identity.identify_person(embedding) if embedding else None
        else:
            gid = uuid.uuid4()
            person_id = None

        floor_coords = project_to_floor(t.bbox, homography_json) if homography_json else None
        floor_x: float | None = floor_coords[0] if floor_coords else None
        floor_y: float | None = floor_coords[1] if floor_coords else None

        if zone_tracker is not None and floor_coords is not None:
            zone_tracker.update(db, gid, floor_coords[0], floor_coords[1])

        rows.append(
            {
                "camera_id": t.camera_id,
                "local_track_id": str(t.local_track_id),
                "global_track_id": str(gid),
                "person_id": person_id,
                "bbox_x1": t.bbox[0],
                "bbox_y1": t.bbox[1],
                "bbox_x2": t.bbox[2],
                "bbox_y2": t.bbox[3],
                "floor_x": floor_x,
                "floor_y": floor_y,
                "event_ts": event_ts,
                "ingest_ts": now_utc,
                "seq_id": frame.seq_id,
            }
        )
    db.execute(_INSERT_SQL, rows)


class DBWriter:
    """Consumes the 'detections' Redis stream and batch-writes to tracking_events."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        db_factory: type[Session],
        identity: IdentityEngine | None = None,
        zone_tracker: ZonePresenceTracker | None = None,
    ) -> None:
        self._redis = redis_client
        self._db_factory = db_factory
        self._identity = identity
        self._zone_tracker = zone_tracker
        self._running = False
        self._last_id = "0-0"
        self._msg_count = 0
        self._cam_homography: dict[int, str | None] = {}

    def _get_homography(self, db: Session, camera_id: int) -> str | None:
        if camera_id not in self._cam_homography:
            cam = db.get(Camera, camera_id)
            self._cam_homography[camera_id] = cam.homography_matrix if cam else None
        return self._cam_homography[camera_id]

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
                        homography_json = self._get_homography(db, frame.camera_id)
                        flush_detection_frame(
                            db,
                            frame,
                            identity=self._identity,
                            homography_json=homography_json,
                            zone_tracker=self._zone_tracker,
                        )
                        self._last_id = msg_id
                        self._msg_count += 1

                    if self._identity is not None and self._msg_count % _EVICT_EVERY == 0:
                        evicted = self._identity.evict_stale()
                        if evicted:
                            logger.debug("evicted %d stale tracklets", evicted)

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
