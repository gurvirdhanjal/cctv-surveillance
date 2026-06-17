"""Inference engine: reads frames stream -> SCRFD/YOLO + AdaFace + Tracker -> detections stream.

Violence scoring (MoViNet A2 Stream):
  score_frame(camera_id, frame) is called once per frame when >= violence_gate_min_persons
  are detected. The model maintains per-camera streaming state internally (stateful).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import cv2
import numpy as np
import redis.asyncio as aioredis

from vms.config import get_settings
from vms.inference.body_embedder import TransReIDBodyEmbedder, extract_torso_crop
from vms.inference.detector import (
    SCRFDDetector,
    _InsightFaceBackend,
    _NullDetector,
    _YoloFaceBackend,
)
from vms.inference.embedder import AdaFaceEmbedder, _InsightFaceEmbedder, _NullEmbedder
from vms.inference.messages import DetectionFrame, FaceWithEmbedding, Tracklet
from vms.inference.ppe import PPEModel
from vms.inference.tracker import PerCameraTracker
from vms.inference.violence import ViolenceModel
from vms.ingestion.messages import FramePointer
from vms.ingestion.shm import SHMSlot
from vms.redis_client import stream_add, stream_read

logger = logging.getLogger(__name__)

_DETECTIONS_STREAM = "detections"


def _blur_score(crop_bgr: np.ndarray[Any, np.dtype[Any]]) -> float:
    """Laplacian variance — higher = sharper."""
    return float(cv2.Laplacian(crop_bgr, cv2.CV_64F).var())


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


def _extract_body_embeddings(
    frame_bgr: np.ndarray[Any, Any],
    tracklets: tuple[Tracklet, ...],
    body_embedder: TransReIDBodyEmbedder | None,
) -> tuple[Tracklet, ...]:
    """Return tracklets with body_embedding and body_quality_norm populated from person bbox crops.

    Crops below the configured min_blur Laplacian-variance threshold are skipped (body_embedding
    is left empty, body_quality_norm set to 0.0). Bbox is clamped to frame dimensions.
    Returns original tracklets unchanged when body_embedder is None.
    """
    if body_embedder is None:
        return tracklets
    settings = get_settings()
    h, w = frame_bgr.shape[:2]
    min_px = settings.min_body_bbox_px
    result: list[Tracklet] = []
    for t in tracklets:
        x1, y1, x2, y2 = t.bbox
        x1c, y1c = max(0, x1), max(0, y1)
        x2c, y2c = min(w, x2), min(h, y2)
        crop_w, crop_h = x2c - x1c, y2c - y1c
        crop = frame_bgr[y1c:y2c, x1c:x2c]
        if crop.size > 0 and crop_w >= min_px and crop_h >= min_px:
            blur = _blur_score(crop)
            if blur >= settings.min_blur:
                torso = extract_torso_crop(
                    frame_bgr,
                    t.bbox,
                    t.keypoints,
                    settings.torso_kp_conf_threshold,
                    settings.torso_crop_pad_fraction,
                )
                body_emb_tuple, body_quality = body_embedder.embed(torso)
            else:
                body_emb_tuple, body_quality = (), 0.0
        else:
            body_emb_tuple, body_quality = (), 0.0
        result.append(
            Tracklet(
                local_track_id=t.local_track_id,
                camera_id=t.camera_id,
                bbox=t.bbox,
                confidence=t.confidence,
                embedding=t.embedding,
                body_embedding=body_emb_tuple,
                body_quality_norm=body_quality,
                keypoints=t.keypoints,
                face_visible=t.face_visible,
            )
        )
    return tuple(result)


def _score_ppe(
    frame_bgr: np.ndarray[Any, Any],
    tracklets: tuple[Tracklet, ...],
    ppe_model: PPEModel | None,
) -> tuple[Tracklet, ...]:
    """Return tracklets with ppe_helmet_conf/ppe_vest_conf populated from person crops.

    Returns original tracklets unchanged when ppe_model is None.
    Bbox is clamped to frame dimensions before cropping.
    """
    if ppe_model is None:
        return tracklets
    h, w = frame_bgr.shape[:2]
    result: list[Tracklet] = []
    for t in tracklets:
        x1, y1, x2, y2 = t.bbox
        x1c, y1c = max(0, x1), max(0, y1)
        x2c, y2c = min(w, x2), min(h, y2)
        crop = frame_bgr[y1c:y2c, x1c:x2c]
        scores = ppe_model.score_crop(crop) if crop.size > 0 else None
        result.append(
            Tracklet(
                local_track_id=t.local_track_id,
                camera_id=t.camera_id,
                bbox=t.bbox,
                confidence=t.confidence,
                embedding=t.embedding,
                body_embedding=t.body_embedding,
                keypoints=t.keypoints,
                face_visible=t.face_visible,
                ppe_helmet_conf=scores["helmet"] if scores is not None else None,
                ppe_vest_conf=scores["vest"] if scores is not None else None,
                ppe_gloves_conf=scores["gloves"] if scores is not None else None,
                ppe_mask_conf=scores["mask"] if scores is not None else None,
            )
        )
    return tuple(result)


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
        body_embedder: TransReIDBodyEmbedder | None = None,
        ppe: PPEModel | None = None,
    ) -> None:
        self._camera_ids = camera_ids
        self._stream_name = f"frames:group{worker_group}"
        self._detector = detector
        self._embedder = embedder
        self._trackers = trackers
        self._redis = redis_client
        self._violence = violence
        self._body_embedder = body_embedder
        self._ppe = ppe
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

        tracker = self._trackers.get(pointer.cam_id)
        raw_tracklets = tracker.update(frame_bgr) if tracker else []

        # Keypoint gate: only run SCRFD+AdaFace when at least one tracklet has a
        # visible frontal face (nose+eye confidence >= face_kpt_min_conf).
        # On ceiling cameras showing top-of-head, this skips face detection entirely,
        # saving ~30% GPU and eliminating spurious low-confidence face embeddings.
        any_face_visible = any(t.face_visible for t in raw_tracklets)
        face_embeddings: list[FaceWithEmbedding] = []
        if any_face_visible:
            raw_faces = self._detector.detect(frame_bgr)
            for face in raw_faces:
                with_emb = self._embedder.embed(face, frame_bgr)
                if with_emb is not None:
                    face_embeddings.append(with_emb)

        emb_map = _associate_faces(tuple(raw_tracklets), tuple(face_embeddings))
        enriched_tracklets = tuple(
            Tracklet(
                local_track_id=t.local_track_id,
                camera_id=t.camera_id,
                bbox=t.bbox,
                confidence=t.confidence,
                embedding=emb_map.get(t.local_track_id, ()),
                keypoints=t.keypoints,
                face_visible=t.face_visible,
            )
            for t in raw_tracklets
        )

        enriched_tracklets = _extract_body_embeddings(
            frame_bgr, enriched_tracklets, self._body_embedder
        )
        enriched_tracklets = _score_ppe(frame_bgr, enriched_tracklets, self._ppe)

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
        """A2 Stream: score one frame per call. Gate: only when >= N persons detected."""
        if self._violence is None or not self._violence.is_available:
            return None
        settings = get_settings()
        if person_count < settings.violence_gate_min_persons:
            return None
        return self._violence.score_frame(cam_id, frame_bgr)
