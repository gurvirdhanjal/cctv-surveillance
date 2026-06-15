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
