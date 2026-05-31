from __future__ import annotations

from vms.inference.keypoints import face_visible, nose_position


def _kpts(nose_c: float, leye_c: float, reye_c: float) -> tuple[tuple[float, float, float], ...]:
    base: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * 17
    base[0] = (100.0, 50.0, nose_c)
    base[1] = (90.0, 45.0, leye_c)
    base[2] = (110.0, 45.0, reye_c)
    return tuple(base)


def test_face_visible_frontal() -> None:
    assert face_visible(_kpts(0.9, 0.8, 0.85)) is True


def test_face_visible_one_eye_occluded() -> None:
    assert face_visible(_kpts(0.8, 0.1, 0.9)) is True


def test_face_visible_nose_occluded() -> None:
    assert face_visible(_kpts(0.2, 0.9, 0.9)) is False


def test_face_visible_both_eyes_low() -> None:
    assert face_visible(_kpts(0.8, 0.2, 0.3)) is False


def test_face_visible_empty_keypoints() -> None:
    assert face_visible(()) is False


def test_face_visible_custom_threshold() -> None:
    assert face_visible(_kpts(0.4, 0.4, 0.4), min_conf=0.3) is True
    assert face_visible(_kpts(0.4, 0.4, 0.4), min_conf=0.5) is False


def test_nose_position_returns_coords() -> None:
    kpts = _kpts(0.9, 0.8, 0.7)
    pos = nose_position(kpts)
    assert pos == (100.0, 50.0)


def test_nose_position_zero_conf_returns_none() -> None:
    kpts = _kpts(0.0, 0.8, 0.7)
    assert nose_position(kpts) is None
