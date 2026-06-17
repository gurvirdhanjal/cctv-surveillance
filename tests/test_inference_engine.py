from __future__ import annotations

from typing import Any
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
    from unittest.mock import MagicMock, patch

    import numpy as np

    from vms.inference.engine import _extract_body_embeddings
    from vms.inference.messages import Tracklet

    embedder = MagicMock()
    embedder.embed.return_value = (tuple([0.1] * 512), 0.95)

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracklets = (
        Tracklet(local_track_id=1, camera_id=1, bbox=(10, 20, 80, 160), confidence=0.9),
        Tracklet(local_track_id=2, camera_id=1, bbox=(200, 100, 280, 300), confidence=0.8),
    )
    with patch("vms.inference.engine._blur_score", return_value=100.0):
        result = _extract_body_embeddings(frame, tracklets, embedder)
    assert len(result) == 2
    assert result[0].body_embedding == tuple([0.1] * 512)
    assert result[1].body_embedding == tuple([0.1] * 512)
    assert result[0].body_quality_norm == 0.95
    assert result[1].body_quality_norm == 0.95
    assert embedder.embed.call_count == 2


def test_extract_body_embeddings_no_embedder_returns_empty() -> None:
    import numpy as np

    from vms.inference.engine import _extract_body_embeddings
    from vms.inference.messages import Tracklet

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracklets = (Tracklet(local_track_id=1, camera_id=1, bbox=(10, 20, 60, 120), confidence=0.9),)
    result = _extract_body_embeddings(frame, tracklets, None)
    assert result[0].body_embedding == ()


def test_score_ppe_returns_tracklets_unchanged_when_model_none() -> None:
    import numpy as np

    from vms.inference.engine import _score_ppe
    from vms.inference.messages import Tracklet

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracklets = (Tracklet(local_track_id=1, camera_id=1, bbox=(10, 20, 60, 120), confidence=0.9),)
    result = _score_ppe(frame, tracklets, None)
    assert result[0].ppe_helmet_conf is None
    assert result[0].ppe_vest_conf is None
    assert result[0].ppe_gloves_conf is None
    assert result[0].ppe_mask_conf is None


def test_score_ppe_populates_all_four_ppe_fields() -> None:
    from unittest.mock import MagicMock

    import numpy as np

    from vms.inference.engine import _score_ppe
    from vms.inference.messages import Tracklet

    ppe_model = MagicMock()
    ppe_model.score_crop.return_value = {
        "helmet": 0.88,
        "vest": 0.73,
        "gloves": 0.55,
        "mask": 0.0,
    }

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracklets = (Tracklet(local_track_id=1, camera_id=1, bbox=(10, 20, 60, 120), confidence=0.9),)
    result = _score_ppe(frame, tracklets, ppe_model)
    assert abs(result[0].ppe_helmet_conf - 0.88) < 1e-6
    assert abs(result[0].ppe_vest_conf - 0.73) < 1e-6
    assert abs(result[0].ppe_gloves_conf - 0.55) < 1e-6
    assert result[0].ppe_mask_conf == 0.0
    assert ppe_model.score_crop.call_count == 1


def test_score_ppe_handles_none_return_from_model() -> None:
    """When score_crop returns None (e.g. crop too small), ppe fields stay None."""
    from unittest.mock import MagicMock

    import numpy as np

    from vms.inference.engine import _score_ppe
    from vms.inference.messages import Tracklet

    ppe_model = MagicMock()
    ppe_model.is_available = True
    ppe_model.score_crop.return_value = None

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    tracklets = (Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 10, 10), confidence=0.8),)
    result = _score_ppe(frame, tracklets, ppe_model)
    assert result[0].ppe_helmet_conf is None
    assert result[0].ppe_vest_conf is None


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


# -------------------------------------------------------------------------
# Task 2 — pose-normalized torso crop + keypoints/face_visible preservation
# -------------------------------------------------------------------------


def _make_torso_kpts(conf: float = 0.9) -> tuple[tuple[float, float, float], ...]:
    """17 COCO kpts with valid torso landmarks at a known position."""
    raw: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * 17
    raw[5] = (150.0, 100.0, conf)  # left_shoulder
    raw[6] = (250.0, 100.0, conf)  # right_shoulder
    raw[11] = (150.0, 280.0, conf)  # left_hip
    raw[12] = (250.0, 280.0, conf)  # right_hip
    return tuple(raw)


def test_extract_body_embeddings_uses_torso_crop_when_keypoints_present() -> None:
    """When valid torso keypoints exist, embedder receives a smaller (torso) crop."""
    from unittest.mock import MagicMock, patch

    from vms.inference.engine import _extract_body_embeddings
    from vms.inference.messages import Tracklet

    received_crops: list[Any] = []

    def _capture_embed(crop: Any) -> tuple[tuple[float, ...], float]:
        received_crops.append(crop)
        return tuple([0.1] * 768), 0.9

    embedder = MagicMock()
    embedder.embed.side_effect = _capture_embed

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    kpts = _make_torso_kpts(conf=0.9)
    # bbox spans x 50-400, y 30-450 (full person box)
    tracklet = Tracklet(
        local_track_id=1, camera_id=1, bbox=(50, 30, 400, 450), confidence=0.9, keypoints=kpts
    )
    with patch("vms.inference.engine._blur_score", return_value=100.0):
        _extract_body_embeddings(frame, (tracklet,), embedder)

    assert len(received_crops) == 1
    crop_h, crop_w = received_crops[0].shape[:2]
    # Full bbox would be 420h x 350w; torso crop should be smaller
    assert crop_h < 420
    assert crop_w < 350


def test_extract_body_embeddings_falls_back_to_bbox_without_keypoints() -> None:
    """When keypoints are empty, embedder receives the full-bbox crop."""
    from unittest.mock import MagicMock, patch

    from vms.inference.engine import _extract_body_embeddings
    from vms.inference.messages import Tracklet

    received_crops: list[Any] = []

    def _capture_embed(crop: Any) -> tuple[tuple[float, ...], float]:
        received_crops.append(crop)
        return tuple([0.1] * 768), 0.9

    embedder = MagicMock()
    embedder.embed.side_effect = _capture_embed

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracklet = Tracklet(
        local_track_id=1, camera_id=1, bbox=(50, 30, 250, 430), confidence=0.9, keypoints=()
    )
    with patch("vms.inference.engine._blur_score", return_value=100.0):
        _extract_body_embeddings(frame, (tracklet,), embedder)

    assert len(received_crops) == 1
    # Full bbox: y30:430, x50:250 -> 400h x 200w
    assert received_crops[0].shape[:2] == (400, 200)


def test_extract_body_embeddings_preserves_keypoints_and_face_visible() -> None:
    """Rebuilt Tracklet must carry forward the input keypoints and face_visible."""
    from unittest.mock import MagicMock, patch

    from vms.inference.engine import _extract_body_embeddings
    from vms.inference.messages import Tracklet

    embedder = MagicMock()
    embedder.embed.return_value = (tuple([0.1] * 768), 0.9)

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    kpts = _make_torso_kpts()
    tracklet = Tracklet(
        local_track_id=1,
        camera_id=1,
        bbox=(50, 30, 400, 450),
        confidence=0.9,
        keypoints=kpts,
        face_visible=True,
    )
    with patch("vms.inference.engine._blur_score", return_value=100.0):
        result = _extract_body_embeddings(frame, (tracklet,), embedder)

    assert result[0].keypoints == kpts
    assert result[0].face_visible is True
