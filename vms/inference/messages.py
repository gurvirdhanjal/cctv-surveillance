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
    embedding: tuple[float, ...] = ()
    body_embedding: tuple[float, ...] = ()
    keypoints: tuple[tuple[float, float, float], ...] = ()  # 17 COCO kpts: (x, y, conf)
    face_visible: bool = False  # True when nose + eye keypoints have sufficient confidence


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
    violence_score: float | None = None

    def to_redis_fields(self) -> dict[str, str]:
        tracklets_json = json.dumps(
            [
                {
                    "local_track_id": t.local_track_id,
                    "camera_id": t.camera_id,
                    "bbox": list(t.bbox),
                    "confidence": t.confidence,
                    "embedding": list(t.embedding),
                    "body_embedding": list(t.body_embedding),
                    "keypoints": [list(kp) for kp in t.keypoints],
                    "face_visible": t.face_visible,
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
        fields: dict[str, str] = {
            "camera_id": str(self.camera_id),
            "seq_id": str(self.seq_id),
            "timestamp_ms": str(self.timestamp_ms),
            "tracklets": tracklets_json,
            "face_embeddings": faces_json,
        }
        if self.violence_score is not None:
            fields["violence_score"] = str(self.violence_score)
        return fields

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
                embedding=tuple(float(v) for v in t.get("embedding", [])),
                body_embedding=tuple(float(v) for v in t.get("body_embedding", [])),
                keypoints=tuple(
                    cast(tuple[float, float, float], tuple(float(v) for v in kp))
                    for kp in t.get("keypoints", [])
                ),
                face_visible=bool(t.get("face_visible", False)),
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
        violence_raw = fields.get("violence_score")
        violence_score = float(violence_raw) if violence_raw is not None else None
        return cls(
            camera_id=int(fields["camera_id"]),
            seq_id=int(fields["seq_id"]),
            timestamp_ms=int(fields["timestamp_ms"]),
            tracklets=tracklets,
            face_embeddings=face_embeddings,
            violence_score=violence_score,
        )
