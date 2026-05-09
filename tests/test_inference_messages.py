from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from vms.inference.messages import DetectionFrame, FaceWithEmbedding, Tracklet


def test_tracklet_is_immutable() -> None:
    t = Tracklet(local_track_id=1, camera_id=2, bbox=(0, 0, 100, 200), confidence=0.9)
    with pytest.raises(FrozenInstanceError):
        t.local_track_id = 99  # type: ignore[misc]


def test_face_with_embedding_stores_512_floats() -> None:
    emb = tuple(float(x) for x in np.random.randn(512).astype(np.float32))
    face = FaceWithEmbedding(bbox=(10, 20, 50, 80), confidence=0.75, embedding=emb)
    assert len(face.embedding) == 512


def test_detection_frame_json_round_trip() -> None:
    emb = tuple(0.1 for _ in range(512))
    frame = DetectionFrame(
        camera_id=5,
        seq_id=100,
        timestamp_ms=999000,
        tracklets=(Tracklet(local_track_id=1, camera_id=5, bbox=(0, 0, 100, 200), confidence=0.8),),
        face_embeddings=(FaceWithEmbedding(bbox=(10, 10, 50, 60), confidence=0.9, embedding=emb),),
    )
    payload = frame.to_redis_fields()
    assert payload["camera_id"] == "5"
    recovered = DetectionFrame.from_redis_fields(payload)
    assert recovered.camera_id == 5
    assert recovered.seq_id == 100
    assert len(recovered.tracklets) == 1
    assert recovered.tracklets[0].local_track_id == 1
    assert len(recovered.face_embeddings) == 1
    assert len(recovered.face_embeddings[0].embedding) == 512


def test_detection_frame_with_no_detections_round_trips() -> None:
    frame = DetectionFrame(
        camera_id=1, seq_id=0, timestamp_ms=0, tracklets=(), face_embeddings=()
    )
    recovered = DetectionFrame.from_redis_fields(frame.to_redis_fields())
    assert recovered.tracklets == ()
    assert recovered.face_embeddings == ()
