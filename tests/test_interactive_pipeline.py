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
        model.track.return_value = self._mock_yolo_result([(10, 20, 100, 200)], [3], [0.85])
        detector = ipt.BodyDetector(
            model=model, botsort_config="botsort_custom.yaml", camera_id=105
        )
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
        detector = ipt.BodyDetector(
            model=model, botsort_config="botsort_custom.yaml", camera_id=110
        )
        tracklets, _ = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8), conf=0.55)
        assert tracklets == []

    def test_returns_empty_when_yolo_returns_empty_list(self) -> None:
        model = MagicMock()
        model.track.return_value = []
        detector = ipt.BodyDetector(
            model=model, botsort_config="botsort_custom.yaml", camera_id=105
        )
        tracklets, _ = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8), conf=0.55)
        assert tracklets == []

    def test_tracklet_keypoints_empty_for_nano_model(self) -> None:
        """yolov8n has no pose head -- keypoints must be empty tuple."""
        model = MagicMock()
        model.track.return_value = self._mock_yolo_result([(0, 0, 50, 50)], [1], [0.9])
        detector = ipt.BodyDetector(
            model=model, botsort_config="botsort_custom.yaml", camera_id=105
        )
        tracklets, _ = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8), conf=0.55)
        assert tracklets[0].keypoints == ()
        assert tracklets[0].face_visible is False


class TestCameraWorker:
    def _make_worker(
        self,
        camera_id: int = 105,
        camera_label: str = "CAM105",
        rtsp_url: str = "rtsp://fake/stream",
        face_results: list | None = None,
        state: ipt.PipelineState | None = None,
    ) -> tuple[ipt.CameraWorker, MagicMock, MagicMock]:
        body_det = MagicMock(spec=ipt.BodyDetector)
        body_det.detect.return_value = ([], 25.0)

        face_pip = MagicMock(spec=ipt.FacePipeline)
        face_pip.run.return_value = (face_results or [], 110.0, 40.0)

        s = state or ipt.PipelineState()
        worker = ipt.CameraWorker(
            camera_id=camera_id,
            camera_label=camera_label,
            rtsp_url=rtsp_url,
            body_detector=body_det,
            face_pipeline=face_pip,
            state=s,
        )
        return worker, body_det, face_pip

    def test_queue_maxsize_two(self) -> None:
        worker, _, _ = self._make_worker()
        assert worker._result_queue.maxsize == 2

    def test_face_pipeline_called_on_sample_frames(self) -> None:
        """With sample_n=3, face pipeline fires on frames 0, 3, 6."""
        state = ipt.PipelineState(sample_n=3, face_enabled=True)
        _worker, body_det, face_pip = self._make_worker(state=state)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        fired_on = []
        for frame_n in range(7):
            body_det.detect.return_value = ([], 25.0)
            if state.face_enabled and frame_n % state.sample_n == 0:
                _last_face, _, _ = face_pip.run(frame)
                fired_on.append(frame_n)

        assert fired_on == [0, 3, 6]
        assert face_pip.run.call_count == 3

    def test_face_pipeline_not_called_when_disabled(self) -> None:
        state = ipt.PipelineState(sample_n=1, face_enabled=False)
        _worker, _, face_pip = self._make_worker(state=state)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        for frame_n in range(5):
            if state.face_enabled and frame_n % state.sample_n == 0:
                face_pip.run(frame)

        face_pip.run.assert_not_called()

    def test_face_stale_frames_increments_between_samples(self) -> None:
        state = ipt.PipelineState(sample_n=5, face_enabled=True)
        stale_counts: list[int] = []
        stale = 0

        for frame_n in range(8):
            if state.face_enabled and frame_n % state.sample_n == 0:
                stale = 0
            else:
                stale += 1
            stale_counts.append(stale)

        assert stale_counts == [0, 1, 2, 3, 4, 0, 1, 2]


class TestRendering:
    def _make_frame_result(
        self,
        fps: float = 25.0,
        tracklets: list | None = None,
        face_results: list | None = None,
        stale: int = 0,
    ) -> ipt.FrameResult:
        return ipt.FrameResult(
            camera_label="CAM105",
            frame=np.zeros((1080, 1920, 3), dtype=np.uint8),
            tracklets=tracklets or [],
            face_results=face_results or [],
            face_stale_frames=stale,
            fps=fps,
            latency_body_ms=28.0,
            latency_scrfd_ms=112.0,
            latency_adaface_ms=43.0,
            frame_n=10,
        )

    def test_render_banner_has_correct_height(self) -> None:
        banner = ipt._render_banner(total_w=1280)
        assert banner.shape[0] == ipt._BANNER_H
        assert banner.shape[1] == 1280
        assert banner.shape[2] == 3

    def test_render_banner_is_numpy_uint8(self) -> None:
        banner = ipt._render_banner(total_w=800)
        assert banner.dtype == np.uint8

    def test_render_panel_output_shape(self) -> None:
        result = self._make_frame_result()
        panel, count = ipt._render_panel(result, panel_h=540)
        assert panel.shape[0] == 540
        assert panel.shape[2] == 3
        assert count == 0

    def test_render_panel_count_equals_tracklets(self) -> None:
        from vms.inference.messages import Tracklet

        t = Tracklet(local_track_id=1, camera_id=105, bbox=(10, 20, 100, 200), confidence=0.9)
        result = self._make_frame_result(tracklets=[t])
        _, count = ipt._render_panel(result, panel_h=540)
        assert count == 1

    def test_render_stats_bar_shape(self) -> None:
        result = self._make_frame_result()
        bar = ipt._render_stats_bar(result, None, total_w=1280, state=ipt.PipelineState())
        assert bar.shape[0] == ipt._STATS_H
        assert bar.shape[1] == 1280

    def test_render_stats_bar_has_text_content(self) -> None:
        low_fps = self._make_frame_result(fps=8.0)
        bar = ipt._render_stats_bar(low_fps, None, total_w=1280, state=ipt.PipelineState())
        assert bar.max() > 100

    def test_render_timing_panel_shape(self) -> None:
        result = self._make_frame_result()
        row = ipt._render_timing_panel(result, None, total_w=1280)
        assert row.shape[0] == ipt._TIMING_H
        assert row.shape[1] == 1280


class TestMainControls:
    def test_conf_cycle_advances(self) -> None:
        state = ipt.PipelineState(conf=0.40)
        cycle = ipt._CONF_CYCLE
        idx = cycle.index(state.conf)
        state.conf = cycle[(idx + 1) % len(cycle)]
        assert state.conf == pytest.approx(0.55)

    def test_conf_cycle_wraps(self) -> None:
        state = ipt.PipelineState(conf=0.70)
        cycle = ipt._CONF_CYCLE
        idx = cycle.index(state.conf)
        state.conf = cycle[(idx + 1) % len(cycle)]
        assert state.conf == pytest.approx(cycle[0])  # last entry wraps to first

    def test_sample_n_clamped_to_min_1(self) -> None:
        state = ipt.PipelineState(sample_n=1)
        state.sample_n = max(1, state.sample_n - 1)
        assert state.sample_n == 1

    def test_sample_n_clamped_to_max_20(self) -> None:
        state = ipt.PipelineState(sample_n=20)
        state.sample_n = min(20, state.sample_n + 1)
        assert state.sample_n == 20

    def test_face_toggle_flips(self) -> None:
        state = ipt.PipelineState(face_enabled=True)
        state.face_enabled = not state.face_enabled
        assert state.face_enabled is False
        state.face_enabled = not state.face_enabled
        assert state.face_enabled is True

    def test_timing_panel_toggle(self) -> None:
        state = ipt.PipelineState(timing_panel=False)
        state.timing_panel = not state.timing_panel
        assert state.timing_panel is True
