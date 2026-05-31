from __future__ import annotations

from unittest.mock import MagicMock, patch

import fakeredis.aioredis as fake_aioredis
import numpy as np
import pytest

from vms.inference.engine import InferenceEngine
from vms.inference.messages import DetectionFrame
from vms.ingestion.messages import FramePointer


@pytest.fixture
def fake_redis() -> fake_aioredis.FakeRedis:
    return fake_aioredis.FakeRedis(decode_responses=True)


def _make_engine(fake_redis: fake_aioredis.FakeRedis) -> InferenceEngine:
    detector = MagicMock()
    detector.detect.return_value = []
    embedder = MagicMock()
    tracker = MagicMock()
    tracker.update.return_value = []
    return InferenceEngine(
        camera_ids=[1],
        worker_group=1,
        detector=detector,
        embedder=embedder,
        trackers={1: tracker},
        redis_client=fake_redis,
    )


@pytest.mark.asyncio
async def test_engine_publishes_detection_frame_to_detections_stream(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    engine = _make_engine(fake_redis)

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    pointer = FramePointer(
        cam_id=1, shm_name="vms_cam_1", seq_id=0, timestamp_ms=1000, width=640, height=480
    )

    mock_slot = MagicMock()
    mock_slot.read.return_value = (frame, 0, 1000)

    published: list[dict[str, str]] = []

    async def fake_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        published.append({"stream": stream, **fields})
        engine._running = False
        return "1-0"

    with (
        patch("vms.inference.engine.SHMSlot.open", return_value=mock_slot),
        patch("vms.inference.engine.stream_add", side_effect=fake_stream_add),
        patch(
            "vms.inference.engine.stream_read", return_value=[("1-0", pointer.to_redis_fields())]
        ),
    ):
        await engine._process_one_message("1-0", pointer.to_redis_fields())

    assert len(published) == 1
    assert published[0]["stream"] == "detections"
    frame_data = DetectionFrame.from_redis_fields(published[0])
    assert frame_data.camera_id == 1
    assert frame_data.seq_id == 0


def test_associate_faces_assigns_embedding_when_face_center_in_person_bbox() -> None:
    from vms.inference.engine import _associate_faces
    from vms.inference.messages import FaceWithEmbedding, Tracklet

    tracklets = (
        Tracklet(local_track_id=1, camera_id=1, bbox=(100, 100, 300, 400), confidence=0.9),
    )
    face_emb = tuple([0.1] * 512)
    faces = (FaceWithEmbedding(bbox=(150, 150, 250, 250), confidence=0.95, embedding=face_emb),)
    result = _associate_faces(tracklets, faces)
    assert result[1] == face_emb


def test_associate_faces_ignores_face_outside_all_bboxes() -> None:
    from vms.inference.engine import _associate_faces
    from vms.inference.messages import FaceWithEmbedding, Tracklet

    tracklets = (Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 100, 100), confidence=0.9),)
    faces = (
        FaceWithEmbedding(bbox=(500, 500, 600, 600), confidence=0.95, embedding=tuple([0.1] * 512)),
    )
    result = _associate_faces(tracklets, faces)
    assert 1 not in result


def test_associate_faces_ignores_face_with_empty_embedding() -> None:
    from vms.inference.engine import _associate_faces
    from vms.inference.messages import FaceWithEmbedding, Tracklet

    tracklets = (Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 300, 300), confidence=0.9),)
    faces = (FaceWithEmbedding(bbox=(50, 50, 150, 150), confidence=0.95, embedding=()),)
    result = _associate_faces(tracklets, faces)
    assert 1 not in result


@pytest.mark.asyncio
async def test_engine_skips_stale_frame(fake_redis: fake_aioredis.FakeRedis) -> None:
    engine = _make_engine(fake_redis)
    pointer = FramePointer(
        cam_id=1, shm_name="vms_cam_1", seq_id=0, timestamp_ms=1000, width=640, height=480
    )

    mock_slot = MagicMock()
    mock_slot.read.return_value = None  # stale

    published: list[dict[str, str]] = []

    async def fake_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        published.append(fields)
        return "1-0"

    with (
        patch("vms.inference.engine.SHMSlot.open", return_value=mock_slot),
        patch("vms.inference.engine.stream_add", side_effect=fake_stream_add),
    ):
        await engine._process_one_message("1-0", pointer.to_redis_fields())

    assert published == []  # nothing published for stale frame


def test_extract_body_embeddings_populates_tracklets() -> None:
    from unittest.mock import MagicMock
    import numpy as np
    from vms.inference.engine import _extract_body_embeddings
    from vms.inference.messages import Tracklet

    embedder = MagicMock()
    embedder.embed.return_value = tuple([0.1] * 512)

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracklets = (
        Tracklet(local_track_id=1, camera_id=1, bbox=(10, 20, 60, 120), confidence=0.9),
        Tracklet(local_track_id=2, camera_id=1, bbox=(200, 100, 280, 300), confidence=0.8),
    )
    result = _extract_body_embeddings(frame, tracklets, embedder)
    assert len(result) == 2
    assert result[0].body_embedding == tuple([0.1] * 512)
    assert result[1].body_embedding == tuple([0.1] * 512)
    assert embedder.embed.call_count == 2


def test_extract_body_embeddings_no_embedder_returns_empty() -> None:
    import numpy as np
    from vms.inference.engine import _extract_body_embeddings
    from vms.inference.messages import Tracklet

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracklets = (
        Tracklet(local_track_id=1, camera_id=1, bbox=(10, 20, 60, 120), confidence=0.9),
    )
    result = _extract_body_embeddings(frame, tracklets, None)
    assert result[0].body_embedding == ()


def test_extract_body_embeddings_clamps_bbox_to_frame() -> None:
    """Out-of-bounds bbox is clamped -- no array index error."""
    from unittest.mock import MagicMock
    import numpy as np
    from vms.inference.engine import _extract_body_embeddings
    from vms.inference.messages import Tracklet

    embedder = MagicMock()
    embedder.embed.return_value = ()

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    tracklets = (
        Tracklet(local_track_id=1, camera_id=1, bbox=(-10, -10, 200, 200), confidence=0.9),
    )
    result = _extract_body_embeddings(frame, tracklets, embedder)
    assert len(result) == 1  # no crash
