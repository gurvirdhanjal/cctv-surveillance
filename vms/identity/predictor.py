"""Cross-camera floor-plane trajectory predictor (Phase 3 crosscam-accuracy).

Maintains a short ring of recent floor positions per gid (from homography.project_to_floor)
and fits a constant-velocity Kalman filter to extrapolate where a person will be at a future
timestamp. Used by CameraTopology's optional spatial gate to reject implausible long-gap
cross-camera merges. Floor coordinates are in metres.

Pure numpy: state x = [px, py, vx, vy]^T, constant-velocity model. Measurement is position
only. The filter is run forward over the buffered observations, then projected to the target
time. State is per-gid and in-memory; eviction is the caller's responsibility via drop().
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field

import numpy as np

# Constant-velocity process/measurement noise. Conservative: trusts measurements, allows
# moderate acceleration drift over multi-second gaps. Not exposed as config — internal to the
# fit; the operator-facing knob is spatial_gate_m in the topology JSON.
_PROCESS_VAR = 1.0  # m^2/s^4 acceleration noise
_MEAS_VAR = 0.25  # m^2 floor-projection measurement noise (~0.5 m std)


@dataclass
class _Track:
    obs: deque[tuple[float, float, int]]  # (floor_x, floor_y, ts_ms)


@dataclass
class CrossCameraPredictor:
    history_len: int
    max_predict_gap_ms: int
    _tracks: dict[uuid.UUID, _Track] = field(default_factory=dict)

    def observe(self, gid: uuid.UUID, floor_xy: tuple[float, float], ts_ms: int) -> None:
        track = self._tracks.get(gid)
        if track is None:
            track = _Track(obs=deque(maxlen=self.history_len))
            self._tracks[gid] = track
        track.obs.append((floor_xy[0], floor_xy[1], ts_ms))

    def drop(self, gid: uuid.UUID) -> None:
        self._tracks.pop(gid, None)

    def predict_position(self, gid: uuid.UUID, at_ms: int) -> tuple[float, float] | None:
        track = self._tracks.get(gid)
        if track is None or len(track.obs) < 2:
            return None
        last_ts = track.obs[-1][2]
        if at_ms - last_ts > self.max_predict_gap_ms:
            return None

        # Initialise state from the first two observations.
        x0, y0, t0 = track.obs[0]
        x1, y1, t1 = track.obs[1]
        dt01 = max((t1 - t0) / 1000.0, 1e-3)
        state = np.array([x0, y0, (x1 - x0) / dt01, (y1 - y0) / dt01], dtype=np.float64)
        cov = np.eye(4, dtype=np.float64) * 10.0
        prev_ts = t0

        H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float64)
        R = np.eye(2, dtype=np.float64) * _MEAS_VAR

        for px, py, ts in list(track.obs)[1:]:
            dt = max((ts - prev_ts) / 1000.0, 1e-3)
            state, cov = self._predict_step(state, cov, dt)
            z = np.array([px, py], dtype=np.float64)
            y_res = z - H @ state
            s = H @ cov @ H.T + R
            k = cov @ H.T @ np.linalg.inv(s)
            state = state + k @ y_res
            cov = (np.eye(4) - k @ H) @ cov
            prev_ts = ts

        dt_future = (at_ms - prev_ts) / 1000.0
        state, _ = self._predict_step(state, cov, dt_future)
        return float(state[0]), float(state[1])

    @staticmethod
    def _predict_step(
        state: np.ndarray, cov: np.ndarray, dt: float
    ) -> tuple[np.ndarray, np.ndarray]:
        f = np.array(
            [
                [1.0, 0.0, dt, 0.0],
                [0.0, 1.0, 0.0, dt],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt2 * dt2
        q1d = np.array([[dt4 / 4.0, dt3 / 2.0], [dt3 / 2.0, dt2]], dtype=np.float64) * _PROCESS_VAR
        q = np.zeros((4, 4), dtype=np.float64)
        q[np.ix_([0, 2], [0, 2])] = q1d
        q[np.ix_([1, 3], [1, 3])] = q1d
        return f @ state, f @ cov @ f.T + q
