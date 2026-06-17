from __future__ import annotations

from vms.identity.topology import CameraTopology


def test_unknown_pair_allows_match() -> None:
    t = CameraTopology("{}")
    assert t.transit_ok(1, 2, elapsed_ms=5_000) is True


def test_within_window_allows() -> None:
    t = CameraTopology('{"1-2": {"min_ms": 2000, "max_ms": 120000}}')
    assert t.transit_ok(1, 2, elapsed_ms=30_000) is True


def test_too_fast_rejects() -> None:
    t = CameraTopology('{"1-2": {"min_ms": 2000, "max_ms": 120000}}')
    assert t.transit_ok(1, 2, elapsed_ms=500) is False


def test_too_slow_rejects() -> None:
    t = CameraTopology('{"1-2": {"min_ms": 2000, "max_ms": 120000}}')
    assert t.transit_ok(1, 2, elapsed_ms=200_000) is False


def test_symmetric_lookup() -> None:
    t = CameraTopology('{"1-2": {"min_ms": 2000, "max_ms": 120000}}')
    assert t.transit_ok(2, 1, elapsed_ms=30_000) is True


def test_invalid_json_allows_all() -> None:
    t = CameraTopology("{bad json")
    assert t.transit_ok(1, 2, elapsed_ms=5_000) is True


def test_same_camera_always_allowed() -> None:
    t = CameraTopology("{}")
    assert t.transit_ok(1, 1, elapsed_ms=0) is True


def test_multiple_pairs() -> None:
    t = CameraTopology(
        '{"1-2": {"min_ms": 1000, "max_ms": 60000}, "2-3": {"min_ms": 5000, "max_ms": 30000}}'
    )
    assert t.transit_ok(1, 2, elapsed_ms=5_000) is True
    assert t.transit_ok(2, 3, elapsed_ms=3_000) is False  # too fast for 2-3
    assert t.transit_ok(1, 3, elapsed_ms=3_000) is True  # no rule for 1-3 → allow
