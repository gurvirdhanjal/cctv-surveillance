"""Inference engine: reads frames stream -> SCRFD/YOLO + AdaFace + Tracker -> detections stream.

Violence scoring:
  A0 ONNX (clip mode):  buffers violence_clip_frames per camera, runs every violence_inference_every_s
  A2 Stream (TF mode):  calls ViolenceModel.score(frame, camera_id) once per frame — stateful,
                        no buffer needed. Gate: only when >= violence_gate_min_persons detected.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

import numpy as np
import redis.asyncio as aioredis

from vms.config import get_settings
from vms.inference.detector import (
    SCRFDDetector,
    _InsightFaceBackend,
    _NullDetector,
    _YoloFaceBackend,
)
from vms.inference.embedder import AdaFaceEmbedder, _InsightFaceEmbedder, _NullEmbedder
from vms.inference.messages import DetectionFrame, FaceWithEmbedding, Tracklet
from vms.inference.tracker import PerCameraTracker
from vms.inference.violence import ViolenceModel
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
        detector: SCRFDDetector | _InsightFaceBackend | _YoloFaceBackend | _NullDetector,
        embedder: AdaFaceEmbedder | _InsightFaceEmbedder | _NullEmbedder,
        trackers: dict[int, PerCameraTracker],
        redis_client: aioredis.Redis,
        violence: ViolenceModel | None = None,
    ) -> None:
        self._camera_ids = camera_ids
        self._stream_name = f"frames:group{worker_group}"
        self._detector = detector
        self._embedder = embedder
        self._trackers = trackers
        self._redis = redis_client
        self._violence = violence
        self._running = False
        self._last_id = "0-0"

        # A0 ONNX clip buffers: camera_id -> deque of frames
        self._clip_buffers: dict[int, deque[Any]] = {}
        self._last_violence_ts: dict[int, float] = {}

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

        violence_score = self._compute_violence_score(
            pointer.cam_id, frame_bgr, len(raw_tracklets), timestamp_ms
        )

        detection_frame = DetectionFrame(
            camera_id=pointer.cam_id,
            seq_id=seq_id,
            timestamp_ms=timestamp_ms,
            tracklets=enriched_tracklets,
            face_embeddings=tuple(face_embeddings),
            violence_score=violence_score,
        )
        await stream_add(self._redis, _DETECTIONS_STREAM, detection_frame.to_redis_fields())

    def _compute_violence_score(
        self,
        cam_id: int,
        frame_bgr: np.ndarray[Any, Any],
        person_count: int,
        timestamp_ms: int,
    ) -> float | None:
        if self._violence is None or not self._violence.is_available:
            return None
        settings = get_settings()
        if person_count < settings.violence_gate_min_persons:
            return None

        if self._violence.is_a2_stream:
            # A2 Stream: one frame at a time, no buffering needed
            return self._violence.score(frame_bgr, cam_id)

        # A0 ONNX: buffer violence_clip_frames, run every violence_inference_every_s
        buf = self._clip_buffers.setdefault(cam_id, deque(maxlen=settings.violence_clip_frames))
        buf.append(frame_bgr.copy())
        last_ts = self._last_violence_ts.get(cam_id, 0.0)
        now_s = timestamp_ms / 1000.0
        if len(buf) == settings.violence_clip_frames and (
            now_s - last_ts >= settings.violence_inference_every_s
        ):
            clip = np.stack(list(buf), axis=0)
            self._last_violence_ts[cam_id] = now_s
            return self._violence.score(clip, cam_id)
        return None
