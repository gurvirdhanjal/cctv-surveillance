from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from vms.inference.embedder import AdaFaceEmbedder
from vms.inference.messages import FaceWithEmbedding


def _make_mock_session() -> MagicMock:
    sess = MagicMock()
    embedding = np.random.randn(1, 512).astype(np.float32)
    sess.run.return_value = [embedding]
    return sess


def test_adaface_embedder_returns_512_dim_embedding() -> None:
    sess = _make_mock_session()
    embedder = AdaFaceEmbedder(session=sess)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    face = FaceWithEmbedding(bbox=(10, 10, 100, 100), confidence=0.9, embedding=())
    result = embedder.embed(face, frame)
    assert len(result.embedding) == 512
    assert result.bbox == face.bbox
    assert result.confidence == face.confidence


def test_adaface_embedder_returns_none_for_empty_crop() -> None:
    sess = _make_mock_session()
    embedder = AdaFaceEmbedder(session=sess)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # bbox outside frame bounds -> empty crop
    face = FaceWithEmbedding(bbox=(200, 200, 300, 300), confidence=0.9, embedding=())
    result = embedder.embed(face, frame)
    assert result is None


def test_adaface_embedder_skips_small_face() -> None:
    sess = _make_mock_session()
    embedder = AdaFaceEmbedder(session=sess, min_face_px=100)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    face = FaceWithEmbedding(bbox=(10, 10, 50, 50), confidence=0.9, embedding=())  # 40px face
    result = embedder.embed(face, frame)
    assert result is None
    sess.run.assert_not_called()


_SAMPLE_KPS: tuple[tuple[float, float], ...] = (
    (100.0, 80.0),
    (140.0, 80.0),
    (120.0, 100.0),
    (105.0, 125.0),
    (135.0, 125.0),
)


def test_adaface_embedder_uses_alignment_when_keypoints_present() -> None:
    """_align_face is called when keypoints are provided and its result is embedded."""
    sess = _make_mock_session()
    embedder = AdaFaceEmbedder(session=sess)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    face = FaceWithEmbedding(
        bbox=(80, 60, 160, 140), confidence=0.9, embedding=(), keypoints=_SAMPLE_KPS
    )
    aligned_img = np.ones((112, 112, 3), dtype=np.uint8) * 42

    with patch("vms.inference.embedder._align_face", return_value=aligned_img) as mock_align:
        result = embedder.embed(face, frame)

    mock_align.assert_called_once()
    assert result is not None
    assert len(result.embedding) == 512


def test_adaface_embedder_does_not_call_align_without_keypoints() -> None:
    """_align_face must not be called when keypoints is empty."""
    sess = _make_mock_session()
    embedder = AdaFaceEmbedder(session=sess)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    face = FaceWithEmbedding(bbox=(80, 60, 160, 140), confidence=0.9, embedding=())

    with patch("vms.inference.embedder._align_face") as mock_align:
        result = embedder.embed(face, frame)

    mock_align.assert_not_called()
    assert result is not None
    assert len(result.embedding) == 512


def test_adaface_preprocess_converts_bgr_to_rgb() -> None:
    """_preprocess must convert BGR→RGB: red channel of input becomes channel 0 of blob."""
    sess = _make_mock_session()
    embedder = AdaFaceEmbedder(session=sess)
    # BGR face: B=50, G=100, R=200 — all pixels identical per channel
    face_bgr = np.zeros((112, 112, 3), dtype=np.uint8)
    face_bgr[:, :, 0] = 50   # Blue
    face_bgr[:, :, 1] = 100  # Green
    face_bgr[:, :, 2] = 200  # Red
    blob = embedder._preprocess(face_bgr)
    # After BGR→RGB: blob channel 0 = Red = 200, channel 2 = Blue = 50
    import pytest as _pytest
    assert blob[0, 0, 0, 0] == _pytest.approx((200 - 127.5) / 127.5, abs=1e-4)
    assert blob[0, 2, 0, 0] == _pytest.approx((50 - 127.5) / 127.5, abs=1e-4)


def test_adaface_embedder_falls_back_to_bbox_when_alignment_returns_none() -> None:
    """When _align_face returns None (degenerate landmarks), bbox crop is used instead."""
    sess = _make_mock_session()
    embedder = AdaFaceEmbedder(session=sess)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    face = FaceWithEmbedding(
        bbox=(80, 60, 160, 140), confidence=0.9, embedding=(), keypoints=_SAMPLE_KPS
    )

    with patch("vms.inference.embedder._align_face", return_value=None) as mock_align:
        result = embedder.embed(face, frame)

    mock_align.assert_called_once()
    assert result is not None  # still produces an embedding via bbox fallback
    assert len(result.embedding) == 512
