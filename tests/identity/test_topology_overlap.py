"""Overlapping-zone declaration on CameraTopology (Phase 3 crosscam-accuracy, Task 4)."""

from vms.identity.topology import CameraTopology


def test_overlap_flag_parsed_and_symmetric() -> None:
    topo = CameraTopology('{"1-2": {"min_ms": 0, "max_ms": 5000, "overlap": true}}')
    assert topo.is_overlapping(1, 2) is True
    assert topo.is_overlapping(2, 1) is True  # key ordering independent


def test_overlap_defaults_false_and_unknown_pair_false() -> None:
    topo = CameraTopology('{"1-2": {"min_ms": 0, "max_ms": 5000}}')
    assert topo.is_overlapping(1, 2) is False
    assert topo.is_overlapping(3, 4) is False


def test_overlapping_cameras_listed() -> None:
    topo = CameraTopology(
        '{"1-2": {"min_ms": 0, "max_ms": 5000, "overlap": true}, '
        '"2-3": {"min_ms": 0, "max_ms": 5000}}'
    )
    assert topo.overlapping_cameras() == {1, 2}
