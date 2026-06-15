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
    cls8[6480, 0] = 0.95  # model outputs pre-sigmoid [0,1]; 0.95 > 0.60 threshold

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


def _make_mock_session_kps() -> MagicMock:
    """9-output KPS session with one detection at stride-8 cell (col=40, row=40, anchor=0).

    Nose keypoint (index 2) placed at stride-unit offset (Δx=2.0, Δy=1.0) from anchor
    centre (320, 320).  In 640×640 input coords: nose = (336, 328).
    """
    sess = MagicMock()
    sess.get_inputs.return_value = [MagicMock(name="input.1")]

    # stride-8: side=80, N=80*80*2=12800 rows
    cls8 = np.zeros((12800, 1), dtype=np.float32)
    # cell (row=40, col=40, anchor=0): flat_idx=40*80+40=3240, array_idx=6480
    cls8[6480, 0] = 4.0  # sigmoid(4.0) ~= 0.982

    bbox8 = np.zeros((12800, 4), dtype=np.float32)
    bbox8[6480] = [5.0, 5.0, 5.0, 5.0]  # 40px box in stride-8 units

    kps8 = np.zeros((12800, 10), dtype=np.float32)
    # j=2 (nose): offsets at indices 4,5 in stride-8 units
    kps8[6480, 4] = 2.0  # Δx → nose_x = 320 + 2.0*8 = 336
    kps8[6480, 5] = 1.0  # Δy → nose_y = 320 + 1.0*8 = 328

    cls16 = np.zeros((3200, 1), dtype=np.float32)
    bbox16 = np.zeros((3200, 4), dtype=np.float32)
    kps16 = np.zeros((3200, 10), dtype=np.float32)
    cls32 = np.zeros((800, 1), dtype=np.float32)
    bbox32 = np.zeros((800, 4), dtype=np.float32)
    kps32 = np.zeros((800, 10), dtype=np.float32)

    sess.run.return_value = [cls8, cls16, cls32, bbox8, bbox16, bbox32, kps8, kps16, kps32]
    return sess


def test_scrfd_detector_no_kps_model_returns_empty_keypoints() -> None:
    """6-output (no KPS) session must produce FaceWithEmbedding with keypoints=()."""
    sess = _make_mock_session_with_detection()
    detector = SCRFDDetector(session=sess)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    detections = detector.detect(frame)
    assert len(detections) >= 1
    assert detections[0].keypoints == ()


def test_scrfd_detector_kps_model_returns_five_keypoints() -> None:
    """9-output (KPS) session must produce FaceWithEmbedding with exactly 5 keypoints."""
    sess = _make_mock_session_kps()
    detector = SCRFDDetector(session=sess)
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    detections = detector.detect(frame)
    assert len(detections) >= 1
    assert len(detections[0].keypoints) == 5


def test_scrfd_detector_kps_nose_coords_correct_at_unit_scale() -> None:
    """Nose landmark (index 2) must land at (336, 328) for a 640×640 input frame."""
    sess = _make_mock_session_kps()
    detector = SCRFDDetector(session=sess)
    frame = np.zeros((640, 640, 3), dtype=np.uint8)  # scale_x = scale_y = 1.0
    detections = detector.detect(frame)
    nose_x, nose_y = detections[0].keypoints[2]
    assert nose_x == pytest.approx(336.0, abs=1.5)
    assert nose_y == pytest.approx(328.0, abs=1.5)


def test_scrfd_detector_kps_scales_to_original_frame() -> None:
    """Keypoint coordinates must be scaled to original frame size (1280×320)."""
    sess = _make_mock_session_kps()
    detector = SCRFDDetector(session=sess)
    frame = np.zeros((320, 1280, 3), dtype=np.uint8)  # scale_x=2.0, scale_y=0.5
    detections = detector.detect(frame)
    assert len(detections) >= 1
    nose_x, nose_y = detections[0].keypoints[2]
    # 640×640 coords (336, 328) → 1280×320 frame: x*2=672, y*0.5=164
    assert nose_x == pytest.approx(672.0, abs=2.0)
    assert nose_y == pytest.approx(164.0, abs=2.0)
