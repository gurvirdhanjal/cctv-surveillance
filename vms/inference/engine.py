"""Inference engine: reads frames stream -> SCRFD + AdaFace + Tracker -> detections stream."""

from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis

from vms.inference.detector import SCRFDDetector
from vms.inference.embedder import AdaFaceEmbedder
from vms.inference.messages import DetectionFrame
from vms.inference.tracker import PerCameraTracker
from vms.ingestion.messages import FramePointer
from vms.ingestion.shm import SHMSlot
from vms.redis_client import stream_add, stream_read

logger = logging.getLogger(__name__)

_DETECTIONS_STREAM = "detections"


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
        tracklets = tracker.update(frame_bgr) if tracker else []

        detection_frame = DetectionFrame(
            camera_id=pointer.cam_id,
            seq_id=seq_id,
            timestamp_ms=timestamp_ms,
            tracklets=tuple(tracklets),
            face_embeddings=tuple(face_embeddings),
        )
        await stream_add(self._redis, _DETECTIONS_STREAM, detection_frame.to_redis_fields())
