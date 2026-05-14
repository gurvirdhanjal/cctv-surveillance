"""Floor-plane homography projection.

cameras.homography_matrix JSON format: [h00,h01,h02, h10,h11,h12, h20,h21,h22]
(3x3 row-major float64)

project_to_floor uses bottom-centre (foot point) for better accuracy on standing persons.
"""

from __future__ import annotations

import json
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def load_homography(homography_json: str | None) -> np.ndarray | None:  # type: ignore[type-arg]
    """Parse a camera's homography_matrix JSON into a (3, 3) float64 ndarray.

    Returns None if the input is None or malformed JSON.
    """
    if homography_json is None:
        return None
    try:
        flat: list[float] = json.loads(homography_json)
        return np.array(flat, dtype=np.float64).reshape(3, 3)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Invalid homography_matrix JSON — skipping floor projection")
        return None


def project_to_floor(
    bbox: tuple[int, int, int, int],
    homography_json: str | None,
) -> tuple[float, float] | None:
    """Project bounding box foot point to floor coordinates.

    Returns (floor_x, floor_y) or None if no homography matrix is stored.
    Foot point is bottom-centre: ((x1+x2)/2, y2).
    """
    H = load_homography(homography_json)
    if H is None:
        return None
    x1, _y1, x2, y2 = bbox
    foot = np.array([[[((x1 + x2) / 2.0), float(y2)]]], dtype=np.float32)
    out = cv2.perspectiveTransform(foot, H.astype(np.float32))
    return float(out[0, 0, 0]), float(out[0, 0, 1])
