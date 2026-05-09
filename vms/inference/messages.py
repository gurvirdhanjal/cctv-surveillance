"""Inter-process message types for the inference layer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast


@dataclass(frozen=True)
class Tracklet:
    """One ByteTrack-confirmed person tracklet from a single camera."""

    local_track_id: int
    camera_id: int
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float


@dataclass(frozen=True)
class FaceWithEmbedding:
    """Face detection with 512-dim AdaFace embedding."""

    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in original frame coords
    confidence: float
    embedding: tuple[float, ...]  # 512 float32 values; empty tuple when not yet embedded


@dataclass(frozen=True)
class DetectionFrame:
    """All detections for one camera frame, published to the 'detections' Redis stream."""

    camera_id: int
    seq_id: int
    timestamp_ms: int
    tracklets: tuple[Tracklet, ...]
    face_embeddings: tuple[FaceWithEmbedding, ...]

    def to_redis_fields(self) -> dict[str, str]:
        tracklets_json = json.dumps(
            [
                {
                    "local_track_id": t.local_track_id,
                    "camera_id": t.camera_id,
                    "bbox": list(t.bbox),
                    "confidence": t.confidence,
                }
                for t in self.tracklets
            ]
        )
        faces_json = json.dumps(
            [
                {
                    "bbox": list(f.bbox),
                    "confidence": f.confidence,
                    "embedding": list(f.embedding),
                }
                for f in self.face_embeddings
            ]
        )
        return {
            "camera_id": str(self.camera_id),
            "seq_id": str(self.seq_id),
            "timestamp_ms": str(self.timestamp_ms),
            "tracklets": tracklets_json,
            "face_embeddings": faces_json,
        }

    @classmethod
    def from_redis_fields(cls, fields: dict[str, str]) -> DetectionFrame:
        raw_tracklets: Any = json.loads(fields["tracklets"])
        raw_faces: Any = json.loads(fields["face_embeddings"])

        tracklets = tuple(
            Tracklet(
                local_track_id=int(t["local_track_id"]),
                camera_id=int(t["camera_id"]),
                bbox=cast(tuple[int, int, int, int], tuple(int(v) for v in t["bbox"])),
                confidence=float(t["confidence"]),
            )
            for t in raw_tracklets
        )
        face_embeddings = tuple(
            FaceWithEmbedding(
                bbox=cast(tuple[int, int, int, int], tuple(int(v) for v in f["bbox"])),
                confidence=float(f["confidence"]),
                embedding=tuple(float(v) for v in f["embedding"]),
            )
            for f in raw_faces
        )
        return cls(
            camera_id=int(fields["camera_id"]),
            seq_id=int(fields["seq_id"]),
            timestamp_ms=int(fields["timestamp_ms"]),
            tracklets=tracklets,
            face_embeddings=face_embeddings,
        )
