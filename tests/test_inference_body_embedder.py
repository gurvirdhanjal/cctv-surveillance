"""Tests for body_embedder: TransReIDBodyEmbedder and extract_torso_crop.

OSNet/BodyEmbedder tests removed — model deleted, class being removed in Task 3.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# extract_torso_crop uses module-level _MIN_H/_MIN_W constants.
from vms.inference.body_embedder import _MIN_H, _MIN_W, extract_torso_crop


def _kpts(positions: list[tuple[float, float, float]]) -> tuple[tuple[float, float, float], ...]:
    """Build 17-kpt tuple; fill unspecified positions with (0,0,0) for irrelevant joints."""
    kpts: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * 17
    for idx, val in enumerate(positions):
        kpts[idx] = val
    return tuple(kpts)


def _frame(h: int = 480, w: int = 640) -> np.ndarray[Any, Any]:
    return np.zeros((h, w, 3), dtype=np.uint8)


# KP indices: left_shoulder=5, right_shoulder=6, left_hip=11, right_hip=12
_LS, _RS, _LH, _RH = 5, 6, 11, 12


def _torso_kpts(
    ls: tuple[float, float],
    rs: tuple[float, float],
    lh: tuple[float, float],
    rh: tuple[float, float],
    conf: float = 0.9,
) -> tuple[tuple[float, float, float], ...]:
    raw: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * 17
    raw[_LS] = (ls[0], ls[1], conf)
    raw[_RS] = (rs[0], rs[1], conf)
    raw[_LH] = (lh[0], lh[1], conf)
    raw[_RH] = (rh[0], rh[1], conf)
    return tuple(raw)


class TestExtractTorsoCrop:
    def test_all_keypoints_returns_torso_rect(self) -> None:
        """4 high-conf torso kpts → crop strictly inside bbox and at shoulder→hip span."""
        frame = _frame(480, 640)
        bbox = (100, 50, 300, 450)
        # Shoulder at y=120, hips at y=280; x spans 150-250
        kpts = _torso_kpts(
            ls=(150.0, 120.0), rs=(250.0, 120.0), lh=(150.0, 280.0), rh=(250.0, 280.0)
        )
        crop = extract_torso_crop(frame, bbox, kpts, conf_threshold=0.5, pad_fraction=0.0)
        # Without padding, crop should be the exact shoulder/hip span
        h_crop, w_crop = crop.shape[:2]
        assert h_crop == 280 - 120  # 160
        assert w_crop == 250 - 150  # 100

    def test_three_of_four_keypoints_uses_torso(self) -> None:
        """Exactly 3 of 4 above threshold → torso rect (not fallback)."""
        frame = _frame(480, 640)
        bbox = (100, 50, 300, 450)
        raw: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * 17
        raw[_LS] = (150.0, 120.0, 0.9)
        raw[_RS] = (250.0, 120.0, 0.9)
        raw[_LH] = (150.0, 280.0, 0.9)
        raw[_RH] = (250.0, 280.0, 0.1)  # below threshold
        kpts = tuple(raw)
        crop = extract_torso_crop(frame, bbox, kpts, conf_threshold=0.5, pad_fraction=0.0)
        # 3 valid points: LS(150,120), RS(250,120), LH(150,280) → x:150-250, y:120-280
        h_crop, w_crop = crop.shape[:2]
        assert h_crop == 280 - 120
        assert w_crop == 250 - 150

    def test_two_keypoints_falls_back_to_bbox(self) -> None:
        """Only 2 above threshold → full-bbox fallback."""
        frame = _frame(480, 640)
        bbox = (100, 50, 300, 450)
        raw: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * 17
        raw[_LS] = (150.0, 120.0, 0.9)
        raw[_RS] = (250.0, 120.0, 0.9)
        # _LH and _RH below threshold
        kpts = tuple(raw)
        crop = extract_torso_crop(frame, bbox, kpts, conf_threshold=0.5, pad_fraction=0.0)
        # fallback = full bbox clamped: 100:300 x 50:450 -> 400h x 200w
        assert crop.shape[:2] == (400, 200)

    def test_no_keypoints_falls_back_to_bbox(self) -> None:
        """Empty keypoints tuple → full-bbox fallback."""
        frame = _frame(480, 640)
        bbox = (100, 50, 300, 450)
        crop = extract_torso_crop(frame, bbox, (), conf_threshold=0.5, pad_fraction=0.0)
        assert crop.shape[:2] == (400, 200)

    def test_low_confidence_keypoints_fall_back(self) -> None:
        """4 points present but all conf < threshold → fallback."""
        frame = _frame(480, 640)
        bbox = (50, 50, 250, 400)
        kpts = _torso_kpts(
            ls=(80.0, 100.0), rs=(200.0, 100.0), lh=(80.0, 300.0), rh=(200.0, 300.0), conf=0.1
        )
        crop = extract_torso_crop(frame, bbox, kpts, conf_threshold=0.5, pad_fraction=0.0)
        assert crop.shape[:2] == (350, 200)

    def test_padding_expands_rect(self) -> None:
        """pad_fraction=0.20 expands the bare shoulder/hip rect by 20% on each side."""
        frame = _frame(480, 640)
        bbox = (0, 0, 640, 480)
        # torso rect: x 200-400 (w=200), y 100-300 (h=200)
        kpts = _torso_kpts(
            ls=(200.0, 100.0), rs=(400.0, 100.0), lh=(200.0, 300.0), rh=(400.0, 300.0)
        )
        crop = extract_torso_crop(frame, bbox, kpts, conf_threshold=0.5, pad_fraction=0.20)
        # pad_x = 200 * 0.20 = 40; pad_y = 200 * 0.20 = 40
        # rect after pad: x 160-440 (w=280), y 60-340 (h=280)
        h_crop, w_crop = crop.shape[:2]
        assert h_crop == 280
        assert w_crop == 280

    def test_clamps_to_frame_bounds(self) -> None:
        """Padding near frame edge is clamped — slice indices never exceed frame dims."""
        frame = _frame(480, 640)
        bbox = (0, 0, 200, 200)
        # Torso landmarks near the top-left corner; padding would go negative
        kpts = _torso_kpts(ls=(10.0, 10.0), rs=(50.0, 10.0), lh=(10.0, 80.0), rh=(50.0, 80.0))
        crop = extract_torso_crop(frame, bbox, kpts, conf_threshold=0.5, pad_fraction=0.5)
        # Should not raise; crop must be a valid (non-zero) slice
        assert crop.size > 0
        h_crop, w_crop = crop.shape[:2]
        assert h_crop >= _MIN_H
        assert w_crop >= _MIN_W

    def test_degenerate_rect_falls_back_to_bbox(self) -> None:
        """Torso rect after padding smaller than _MIN_H x _MIN_W -> fallback."""
        frame = _frame(480, 640)
        bbox = (100, 100, 300, 400)
        # All 4 points at nearly the same pixel → degenerate (0 size) torso rect
        kpts = _torso_kpts(
            ls=(150.0, 200.0), rs=(151.0, 200.0), lh=(150.0, 201.0), rh=(151.0, 201.0)
        )
        crop = extract_torso_crop(frame, bbox, kpts, conf_threshold=0.5, pad_fraction=0.0)
        # Padded rect: x 150-151 (w=1 < _MIN_W=8) → fallback
        assert crop.shape[:2] == (300, 200)  # full bbox: y100:400, x100:300
