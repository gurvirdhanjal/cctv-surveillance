"""Inference engine: reads frames stream -> SCRFD + AdaFace + Tracker -> detections stream."""

from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis

from vms.inference.detector import SCRFDDetector
from vms.inference.embedder import AdaFaceEmbedder
from vms.inference.messages import DetectionFrame, FaceWithEmbedding, Tracklet
from vms.inference.tracker import PerCameraTracker
from vms.ingestion.messages import FramePointer
from vms.ingestion.shm import SHMSlot
from vms.redis_client import stream_add, stream_read

logger = logging.getLogger(__name__)

_DETECTIONS_STREAM = "detections"


def _associate_faces(
    tracklets: tuple[Tracklet, ...],
    face_embeddings: tuple[FaceWithEmbedding, ...],
) -> dict[int, tuple[float, ...]]:
    """Map local_track_id -> face embedding by face-centre-inside-person-bbox heuristic.

    Each face is assigned to the first unmatched tracklet whose bbox contains the face centre.
    Faces with empty embeddings are skipped.
    """
    result: dict[int, tuple[float, ...]] = {}
    for fw in face_embeddings:
        if not fw.embedding:
            continue
        fx = (fw.bbox[0] + fw.bbox[2]) // 2
        fy = (fw.bbox[1] + fw.bbox[3]) // 2
        for t in tracklets:
            if t.local_track_id in result:
                continue
            x1, y1, x2, y2 = t.bbox
            if x1 <= fx <= x2 and y1 <= fy <= y2:
                result[t.local_track_id] = fw.embedding
    return result


class InferenceEngine:
    """Reads from frames:group{N} streams, runs model stack, publishes DetectionFrame."""

    def __init__(
        self,
        camera_ids: list[int],
        worker_group: int,
        detector: SCRFDDetector,
        embedder: AdaFaceEmbedder,
        trackers: dict[int, PerCameraTracker],
        redis_client: aioredis.Redis,
    ) -> None:
        self._camera_ids = camera_ids  # reserved for future per-engine camera filtering
        self._stream_name = f"frames:group{worker_group}"
        self._detector = detector
        self._embedder = embedder
        self._trackers = trackers
        self._redis = redis_client
        self._running = False
        self._last_id = "0-0"

    async def run(self) -> None:
        self._running = True
        while self._running:
            messages: list[tuple[str, dict[str, str]]] = await stream_read(
                self._redis, self._stream_name, last_id=self._last_id, count=10
            )
            for msg_id, fields in messages:
                await self._process_one_message(msg_id, fields)
                self._last_id = msg_id
            if not messages:
                await asyncio.sleep(0.01)

    async def stop(self) -> None:
        self._running = False

    async def _process_one_message(self, msg_id: str, fields: dict[str, str]) -> None:
        pointer = FramePointer.from_redis_fields(fields)
        slot = SHMSlot.open(name=pointer.shm_name, width=pointer.width, height=pointer.height)
        frame_result = slot.read()
        if frame_result is None:
            logger.debug("camera_id=%d seq=%d stale -- skipped", pointer.cam_id, pointer.seq_id)
            return

        frame_bgr, seq_id, timestamp_ms = frame_result

        raw_faces = self._detector.detect(frame_bgr)
        face_embeddings = []
        for face in raw_faces:
            with_emb = self._embedder.embed(face, frame_bgr)
            if with_emb is not None:
                face_embeddings.append(with_emb)

        tracker = self._trackers.get(pointer.cam_id)
        raw_tracklets = tracker.update(frame_bgr) if tracker else []

        emb_map = _associate_faces(tuple(raw_tracklets), tuple(face_embeddings))
        enriched_tracklets = tuple(
            Tracklet(
                local_track_id=t.local_track_id,
                camera_id=t.camera_id,
                bbox=t.bbox,
                confidence=t.confidence,
                embedding=emb_map.get(t.local_track_id, ()),
            )
            for t in raw_tracklets
        )

        detection_frame = DetectionFrame(
            camera_id=pointer.cam_id,
            seq_id=seq_id,
            timestamp_ms=timestamp_ms,
            tracklets=enriched_tracklets,
            face_embeddings=tuple(face_embeddings),
        )
        await stream_add(self._redis, _DETECTIONS_STREAM, detection_frame.to_redis_fields())
