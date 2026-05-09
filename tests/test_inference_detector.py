from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from vms.inference.detector import SCRFDDetector
from vms.inference.messages import FaceWithEmbedding


def _make_mock_session_with_detection() -> MagicMock:
    """Mock ort.InferenceSession returning one detectable face at stride-8 grid cell (40,40)."""
    sess = MagicMock()
    sess.get_inputs.return_value = [MagicMock(name="input.1")]

    # stride-8: 80x80 grid, 2 anchors/cell = 12800 rows
    cls8 = np.zeros((12800, 1), dtype=np.float32)
    # Cell (row=40, col=40), anchor 0 -> index (40*80 + 40)*2 = 6480
    cls8[6480, 0] = 4.0  # sigmoid(4.0) ~= 0.982 -- well above 0.60 threshold

    bbox8 = np.zeros((12800, 4), dtype=np.float32)
    bbox8[6480] = [5.0, 5.0, 5.0, 5.0]  # 40px box in stride-8 units

    cls16 = np.zeros((3200, 1), dtype=np.float32)
    bbox16 = np.zeros((3200, 4), dtype=np.float32)
    cls32 = np.zeros((800, 1), dtype=np.float32)
    bbox32 = np.zeros((800, 4), dtype=np.float32)

    sess.run.return_value = [cls8, cls16, cls32, bbox8, bbox16, bbox32]
    return sess


def _make_mock_session_no_detection() -> MagicMock:
    sess = MagicMock()
    sess.get_inputs.return_value = [MagicMock(name="input.1")]
    sess.run.return_value = [
        np.zeros((12800, 1), dtype=np.float32),
        np.zeros((3200, 1), dtype=np.float32),
        np.zeros((800, 1), dtype=np.float32),
        np.zeros((12800, 4), dtype=np.float32),
        np.zeros((3200, 4), dtype=np.float32),
        np.zeros((800, 4), dtype=np.float32),
    ]
    return sess


def test_scrfd_detector_returns_face_detection() -> None:
    sess = _make_mock_session_with_detection()
    detector = SCRFDDetector(session=sess)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    detections = detector.detect(frame)
    assert len(detections) >= 1
    assert isinstance(detections[0], FaceWithEmbedding)
    x1, y1, x2, y2 = detections[0].bbox
    assert x2 > x1 and y2 > y1
    assert 0.0 < detections[0].confidence <= 1.0
    assert detections[0].embedding == ()  # embedding not filled at detect time


def test_scrfd_detector_returns_empty_for_blank_output() -> None:
    sess = _make_mock_session_no_detection()
    detector = SCRFDDetector(session=sess)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    assert detector.detect(frame) == []


def test_scrfd_detector_filters_below_min_face_px() -> None:
    sess = _make_mock_session_with_detection()
    detector = SCRFDDetector(session=sess, min_face_px=1000)  # impossible threshold
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert detector.detect(frame) == []


def test_scrfd_detector_uses_conf_from_settings_by_default() -> None:
    sess = _make_mock_session_no_detection()
    detector = SCRFDDetector(session=sess)
    # Default from config is 0.60 -- verify no override was applied
    assert detector._conf_thres == pytest.approx(0.60, abs=1e-6)
