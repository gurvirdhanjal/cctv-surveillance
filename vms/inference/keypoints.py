"""COCO 17-keypoint constants and face-visibility helper for YOLOv8-pose output."""

from __future__ import annotations

# COCO keypoint indices
NOSE = 0
LEFT_EYE = 1
RIGHT_EYE = 2
LEFT_EAR = 3
RIGHT_EAR = 4
LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_ELBOW = 7
RIGHT_ELBOW = 8
LEFT_WRIST = 9
RIGHT_WRIST = 10
LEFT_HIP = 11
RIGHT_HIP = 12
LEFT_KNEE = 13
RIGHT_KNEE = 14
LEFT_ANKLE = 15
RIGHT_ANKLE = 16

KP_DIM = 17  # total keypoints per person


def face_visible(
    keypoints: tuple[tuple[float, float, float], ...],
    min_conf: float = 0.5,
) -> bool:
    """Return True if the face is likely frontal enough for AdaFace embedding.

    Requires nose AND at least one eye to have confidence >= min_conf.
    Low confidence means the keypoint is occluded, outside frame, or facing away.
    """
    if len(keypoints) < 3:
        return False
    nose_conf = keypoints[NOSE][2]
    leye_conf = keypoints[LEFT_EYE][2]
    reye_conf = keypoints[RIGHT_EYE][2]
    return nose_conf >= min_conf and (leye_conf >= min_conf or reye_conf >= min_conf)


def nose_position(
    keypoints: tuple[tuple[float, float, float], ...],
) -> tuple[float, float] | None:
    """Return (x, y) of nose keypoint if confidence > 0, else None."""
    if len(keypoints) <= NOSE:
        return None
    x, y, conf = keypoints[NOSE]
    return (x, y) if conf > 0 else None
