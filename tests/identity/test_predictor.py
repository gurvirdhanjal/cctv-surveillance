"""CrossCameraPredictor Kalman floor-plane prediction (Phase 3 crosscam-accuracy, Task 5)."""

import uuid

import pytest

from vms.identity.predictor import CrossCameraPredictor


def test_constant_velocity_prediction_is_accurate() -> None:
    pred = CrossCameraPredictor(history_len=8, max_predict_gap_ms=900_000)
    gid = uuid.uuid4()
    # Walk in +x at 1 m/s, sampled every 1000 ms.
    for t in range(0, 5000, 1000):
        pred.observe(gid, floor_xy=(float(t) / 1000.0, 0.0), ts_ms=t)
    out = pred.predict_position(gid, at_ms=7000)  # 3 s after last sample at t=4000
    assert out is not None
    x, y = out
    assert x == pytest.approx(7.0, abs=0.5)  # ~4.0 + 3 s * 1 m/s
    assert y == pytest.approx(0.0, abs=0.5)


def test_unknown_gid_returns_none() -> None:
    pred = CrossCameraPredictor(history_len=8, max_predict_gap_ms=900_000)
    assert pred.predict_position(uuid.uuid4(), at_ms=1000) is None


def test_single_observation_returns_none() -> None:
    # Cannot estimate velocity from one point.
    pred = CrossCameraPredictor(history_len=8, max_predict_gap_ms=900_000)
    gid = uuid.uuid4()
    pred.observe(gid, floor_xy=(1.0, 1.0), ts_ms=0)
    assert pred.predict_position(gid, at_ms=1000) is None


def test_prediction_past_max_gap_returns_none() -> None:
    pred = CrossCameraPredictor(history_len=8, max_predict_gap_ms=10_000)
    gid = uuid.uuid4()
    pred.observe(gid, floor_xy=(0.0, 0.0), ts_ms=0)
    pred.observe(gid, floor_xy=(1.0, 0.0), ts_ms=1000)
    # Requested 20 s after last obs > 10 s cap -> refuse to extrapolate.
    assert pred.predict_position(gid, at_ms=21_000) is None


def test_drop_evicts_state() -> None:
    pred = CrossCameraPredictor(history_len=8, max_predict_gap_ms=900_000)
    gid = uuid.uuid4()
    pred.observe(gid, floor_xy=(0.0, 0.0), ts_ms=0)
    pred.observe(gid, floor_xy=(1.0, 0.0), ts_ms=1000)
    pred.drop(gid)
    assert pred.predict_position(gid, at_ms=2000) is None
