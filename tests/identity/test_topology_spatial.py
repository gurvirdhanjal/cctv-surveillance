"""Spatial gate on CameraTopology.transit_ok (Phase 3 crosscam-accuracy, Task 6)."""

from vms.identity.topology import CameraTopology

_TOPO = (
    '{"1-4": {"min_ms": 60000, "max_ms": 900000, "spatial_gate_m": 3.0}, '
    '"2-3": {"min_ms": 0, "max_ms": 5000}}'
)


def test_time_gate_unchanged_when_no_spatial_args() -> None:
    topo = CameraTopology(_TOPO)
    assert topo.transit_ok(1, 4, elapsed_ms=120_000) is True
    assert topo.transit_ok(1, 4, elapsed_ms=10_000) is False  # below min_ms


def test_spatial_gate_passes_within_threshold() -> None:
    topo = CameraTopology(_TOPO)
    assert (
        topo.transit_ok(
            1,
            4,
            elapsed_ms=120_000,
            floor_xy=(10.0, 10.0),
            predicted_xy=(11.0, 12.0),  # ~2.24 m < 3.0
        )
        is True
    )


def test_spatial_gate_rejects_beyond_threshold() -> None:
    topo = CameraTopology(_TOPO)
    assert (
        topo.transit_ok(
            1,
            4,
            elapsed_ms=120_000,
            floor_xy=(10.0, 10.0),
            predicted_xy=(20.0, 20.0),  # ~14 m > 3.0
        )
        is False
    )


def test_spatial_gate_skipped_when_no_prediction() -> None:
    # Predictor returned None -> spatial check is a no-op (fail-open on missing prediction).
    topo = CameraTopology(_TOPO)
    assert (
        topo.transit_ok(1, 4, elapsed_ms=120_000, floor_xy=(10.0, 10.0), predicted_xy=None) is True
    )


def test_spatial_gate_disabled_pair_ignores_floor_args() -> None:
    topo = CameraTopology(_TOPO)
    # 2-3 has no spatial_gate_m configured -> floor args ignored, time gate only.
    assert (
        topo.transit_ok(2, 3, elapsed_ms=1000, floor_xy=(0.0, 0.0), predicted_xy=(99.0, 99.0))
        is True
    )
