from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vms.inference.embedder import AdaFaceEmbedder
from vms.inference.messages import FaceWithEmbedding


def _make_mock_session() -> MagicMock:
    sess = MagicMock()
    embedding = np.random.randn(1, 512).astype(np.float32)
    sess.run.return_value = [embedding]
    return sess


def _make_embedder(min_face_px: int | None = None) -> AdaFaceEmbedder:
    """Create an AdaFaceEmbedder with blur gate disabled (min_blur=0.0).

    Pre-blur-gate tests use uniform/zero frames that would fail the Laplacian
    check. Disable blur here so those tests stay focused on their own concerns.
    """
    return AdaFaceEmbedder(session=_make_mock_session(), min_face_px=min_face_px, min_blur=0.0)


def test_adaface_embedder_returns_512_dim_embedding() -> None:
    embedder = _make_embedder()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    face = FaceWithEmbedding(bbox=(10, 10, 100, 100), confidence=0.9, embedding=())
    result = embedder.embed(face, frame)
    assert len(result.embedding) == 512
    assert result.bbox == face.bbox
    assert result.confidence == face.confidence


def test_adaface_embedder_returns_none_for_empty_crop() -> None:
    embedder = _make_embedder()
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # bbox outside frame bounds -> empty crop
    face = FaceWithEmbedding(bbox=(200, 200, 300, 300), confidence=0.9, embedding=())
    result = embedder.embed(face, frame)
    assert result is None


def test_adaface_embedder_skips_small_face() -> None:
    sess = _make_mock_session()
    embedder = AdaFaceEmbedder(session=sess, min_face_px=100, min_blur=0.0)
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
    embedder = _make_embedder()
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
    embedder = _make_embedder()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    face = FaceWithEmbedding(bbox=(80, 60, 160, 140), confidence=0.9, embedding=())

    with patch("vms.inference.embedder._align_face") as mock_align:
        result = embedder.embed(face, frame)

    mock_align.assert_not_called()
    assert result is not None
    assert len(result.embedding) == 512


def test_adaface_embedder_l2_normalises_output() -> None:
    """Embedder must L2-normalise the raw backbone output (IR101 does not normalise internally)."""
    sess = MagicMock()
    # Raw output with norm ~12 — as measured from IR101 backbone
    raw_emb = np.ones((1, 512), dtype=np.float32) * 0.5  # norm = sqrt(512)*0.5 ~= 11.3
    sess.run.return_value = [raw_emb]
    embedder = AdaFaceEmbedder(session=sess, min_blur=0.0)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    face = FaceWithEmbedding(bbox=(10, 10, 100, 100), confidence=0.9, embedding=())
    result = embedder.embed(face, frame)
    assert result is not None
    norm = sum(v ** 2 for v in result.embedding) ** 0.5
    assert abs(norm - 1.0) < 1e-4


def test_adaface_preprocess_converts_bgr_to_rgb() -> None:
    """_preprocess must convert BGR->RGB: red channel of input becomes channel 0 of blob."""
    embedder = _make_embedder()
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


def test_embedder_rejects_blurry_crop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Laplacian variance below min_blur -> embed() returns None."""
    emb = AdaFaceEmbedder.__new__(AdaFaceEmbedder)
    emb._min_face_px = 10
    emb._min_blur = 25.0

    # Uniform grey crop -> Laplacian variance ~= 0 (very blurry)
    blurry_frame = np.full((200, 200, 3), 128, dtype=np.uint8)
    face = FaceWithEmbedding(bbox=(0, 0, 80, 80), confidence=0.9, embedding=())

    monkeypatch.setattr(emb, "_preprocess", lambda crop: np.zeros((1, 3, 112, 112)))

    class _FakeSess:
        def run(self, _out: object, _inp: object) -> list[object]:
            return [np.random.randn(1, 512).astype(np.float32)]

    emb._sess = _FakeSess()
    emb._input_name = "input"

    result = emb.embed(face, blurry_frame)
    assert result is None


def test_embedder_populates_quality_norm(monkeypatch: pytest.MonkeyPatch) -> None:
    """face_quality_norm is pre-norm L2 of raw embedding output."""
    emb = AdaFaceEmbedder.__new__(AdaFaceEmbedder)
    emb._min_face_px = 10
    emb._min_blur = 0.0  # disable blur reject

    # Sharp crop: checkerboard -> high Laplacian variance
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    frame[::2, ::2] = 255

    face = FaceWithEmbedding(bbox=(0, 0, 100, 100), confidence=0.9, embedding=())

    raw_vec = np.full((1, 512), 2.0, dtype=np.float32)
    expected_norm = float(np.linalg.norm(raw_vec[0]))

    monkeypatch.setattr(emb, "_preprocess", lambda crop: np.zeros((1, 3, 112, 112)))

    class _FakeSess:
        def run(self, _out: object, _inp: object) -> list[object]:
            return [raw_vec.copy()]

    emb._sess = _FakeSess()
    emb._input_name = "input"

    result = emb.embed(face, frame)
    assert result is not None
    assert abs(result.face_quality_norm - expected_norm) < 0.01
