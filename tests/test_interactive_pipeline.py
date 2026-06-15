"""Unit tests for interactive_pipeline_test.py components."""

from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np
import pytest

# Add scripts/ to path so we can import the test harness module
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import interactive_pipeline_test as ipt


class TestFaceResult:
    def test_frozen(self) -> None:
        fr = ipt.FaceResult(
            bbox=(0, 0, 50, 50), confidence=0.9, embedding_norm=18.4, label="UNKNOWN"
        )
        with pytest.raises(FrozenInstanceError):
            fr.label = "X"  # type: ignore[misc]

    def test_label_is_always_unknown(self) -> None:
        fr = ipt.FaceResult(
            bbox=(0, 0, 50, 50), confidence=0.9, embedding_norm=18.4, label="UNKNOWN"
        )
        assert fr.label == "UNKNOWN"

    def test_embedding_norm_stored(self) -> None:
        fr = ipt.FaceResult(
            bbox=(10, 20, 60, 70), confidence=0.8, embedding_norm=17.3, label="UNKNOWN"
        )
        assert abs(fr.embedding_norm - 17.3) < 1e-5


class TestFrameResult:
    def test_mutable(self) -> None:
        result = ipt.FrameResult(
            camera_label="CAM105",
            frame=np.zeros((480, 640, 3), dtype=np.uint8),
            tracklets=[],
            face_results=[],
            face_stale_frames=0,
            fps=25.0,
            latency_body_ms=28.0,
            latency_scrfd_ms=0.0,
            latency_adaface_ms=0.0,
            frame_n=1,
        )
        result.fps = 30.0
        assert result.fps == 30.0


class TestPipelineState:
    def test_defaults(self) -> None:
        s = ipt.PipelineState()
        assert s.sample_n == ipt.FACE_SAMPLE_EVERY_N
        assert s.conf == pytest.approx(0.55)
        assert s.face_enabled is True
        assert s.timing_panel is False

    def test_mutability(self) -> None:
        s = ipt.PipelineState()
        s.sample_n = 10
        assert s.sample_n == 10


from unittest.mock import MagicMock

from vms.inference.messages import FaceWithEmbedding


class TestFacePipeline:
    def _make_pipeline(self, detector_faces, embedder_result):
        detector = MagicMock()
        detector.detect.return_value = detector_faces
        embedder = MagicMock()
        embedder.embed.return_value = embedder_result
        return ipt.FacePipeline(detector=detector, embedder=embedder)

    def _fake_face(self, embedding: tuple[float, ...] = ()) -> FaceWithEmbedding:
        return FaceWithEmbedding(
            bbox=(10, 10, 60, 60),
            confidence=0.9,
            embedding=embedding,
            keypoints=(),
        )

    def test_run_returns_unknown_label(self) -> None:
        embedding = tuple([1.0] * 512)
        face = self._fake_face(embedding)
        embedded_face = FaceWithEmbedding(
            bbox=(10, 10, 60, 60),
            confidence=0.9,
            embedding=embedding,
            keypoints=(),
        )
        pipeline = self._make_pipeline([face], embedded_face)
        results, _, _ = pipeline.run(np.zeros((480, 640, 3), dtype=np.uint8))
        assert len(results) == 1
        assert results[0].label == "UNKNOWN"

    def test_run_computes_embedding_norm(self) -> None:
        embedding = tuple([1.0] * 512)
        face = self._fake_face(embedding)
        embedded_face = FaceWithEmbedding(
            bbox=(10, 10, 60, 60),
            confidence=0.9,
            embedding=embedding,
            keypoints=(),
        )
        pipeline = self._make_pipeline([face], embedded_face)
        results, _, _ = pipeline.run(np.zeros((480, 640, 3), dtype=np.uint8))
        expected_norm = float(np.linalg.norm(np.ones(512)))
        assert abs(results[0].embedding_norm - expected_norm) < 1e-4

    def test_run_skips_face_with_empty_embedding(self) -> None:
        face = self._fake_face(embedding=())
        embedded_face = FaceWithEmbedding(
            bbox=(10, 10, 60, 60),
            confidence=0.9,
            embedding=(),
            keypoints=(),
        )
        pipeline = self._make_pipeline([face], embedded_face)
        results, _, _ = pipeline.run(np.zeros((480, 640, 3), dtype=np.uint8))
        assert results == []

    def test_run_skips_when_embedder_returns_none(self) -> None:
        face = self._fake_face()
        pipeline = self._make_pipeline([face], None)
        results, _, _ = pipeline.run(np.zeros((480, 640, 3), dtype=np.uint8))
        assert results == []

    def test_run_returns_scrfd_and_adaface_timings(self) -> None:
        embedding = tuple([1.0] * 512)
        face = self._fake_face(embedding)
        embedded_face = FaceWithEmbedding(
            bbox=(10, 10, 60, 60),
            confidence=0.9,
            embedding=embedding,
            keypoints=(),
        )
        pipeline = self._make_pipeline([face], embedded_face)
        _, scrfd_ms, adaface_ms = pipeline.run(np.zeros((480, 640, 3), dtype=np.uint8))
        assert scrfd_ms >= 0.0
        assert adaface_ms >= 0.0

    def test_run_empty_frame_no_detections(self) -> None:
        pipeline = self._make_pipeline([], None)
        results, _, _ = pipeline.run(np.zeros((480, 640, 3), dtype=np.uint8))
        assert results == []
