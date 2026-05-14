from __future__ import annotations

import json

import numpy as np

from vms.identity.homography import load_homography, project_to_floor


def test_load_homography_parses_json() -> None:
    flat = list(range(9))
    H = load_homography(json.dumps([float(x) for x in flat]))
    assert H is not None
    assert H.shape == (3, 3)
    assert H[0, 0] == 0.0
    assert H[2, 2] == 8.0


def test_load_homography_returns_none_for_none() -> None:
    assert load_homography(None) is None


def test_project_to_floor_identity_matrix() -> None:
    H = np.eye(3, dtype=np.float64)
    H_json = json.dumps(H.flatten().tolist())
    # bbox (100, 200, 200, 400) -> foot point = (150.0, 400.0)
    result = project_to_floor((100, 200, 200, 400), H_json)
    assert result is not None
    fx, fy = result
    assert abs(fx - 150.0) < 0.5
    assert abs(fy - 400.0) < 0.5


def test_project_to_floor_returns_none_for_no_matrix() -> None:
    assert project_to_floor((0, 0, 100, 200), None) is None


def test_load_homography_malformed_json_returns_none() -> None:
    result = load_homography("not valid json {{")
    assert result is None


def test_project_to_floor_malformed_json_returns_none() -> None:
    result = project_to_floor((100, 100, 200, 200), "not valid json {{")
    assert result is None
