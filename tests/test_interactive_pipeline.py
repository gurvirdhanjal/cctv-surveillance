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


from unittest.mock import MagicMock  # noqa: E402

from vms.inference.messages import FaceWithEmbedding  # noqa: E402


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


from typing import Any  # noqa: E402


class TestBodyDetector:
    def _mock_yolo_result(
        self, boxes: list[tuple[int, int, int, int]], ids: list[int], confs: list[float]
    ) -> Any:
        """Build a mock ultralytics result object."""
        import torch

        mock_r = MagicMock()
        mock_r.boxes.id = torch.tensor(ids, dtype=torch.float32) if ids else None
        mock_r.boxes.xyxy = torch.tensor(
            [[float(x1), float(y1), float(x2), float(y2)] for x1, y1, x2, y2 in boxes],
            dtype=torch.float32,
        )
        mock_r.boxes.conf = torch.tensor(confs, dtype=torch.float32)
        return [mock_r]

    def test_returns_tracklets_for_detected_persons(self) -> None:
        model = MagicMock()
        model.track.return_value = self._mock_yolo_result(
            [(10, 20, 100, 200)], [3], [0.85]
        )
        detector = ipt.BodyDetector(model=model, botsort_config="botsort_custom.yaml", camera_id=105)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracklets, latency_ms = detector.detect(frame, conf=0.55)
        assert len(tracklets) == 1
        assert tracklets[0].local_track_id == 3
        assert tracklets[0].camera_id == 105
        assert tracklets[0].bbox == (10, 20, 100, 200)
        assert latency_ms >= 0.0

    def test_returns_empty_when_no_tracks(self) -> None:
        model = MagicMock()
        no_id_result = MagicMock()
        no_id_result.boxes.id = None
        model.track.return_value = [no_id_result]
        detector = ipt.BodyDetector(model=model, botsort_config="botsort_custom.yaml", camera_id=110)
        tracklets, _ = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8), conf=0.55)
        assert tracklets == []

    def test_returns_empty_when_yolo_returns_empty_list(self) -> None:
        model = MagicMock()
        model.track.return_value = []
        detector = ipt.BodyDetector(model=model, botsort_config="botsort_custom.yaml", camera_id=105)
        tracklets, _ = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8), conf=0.55)
        assert tracklets == []

    def test_tracklet_keypoints_empty_for_nano_model(self) -> None:
        """yolov8n has no pose head -- keypoints must be empty tuple."""
        model = MagicMock()
        model.track.return_value = self._mock_yolo_result([(0, 0, 50, 50)], [1], [0.9])
        detector = ipt.BodyDetector(model=model, botsort_config="botsort_custom.yaml", camera_id=105)
        tracklets, _ = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8), conf=0.55)
        assert tracklets[0].keypoints == ()
        assert tracklets[0].face_visible is False
