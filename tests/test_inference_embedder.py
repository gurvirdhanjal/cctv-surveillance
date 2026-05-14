from __future__ import annotations

from unittest.mock import MagicMock

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
