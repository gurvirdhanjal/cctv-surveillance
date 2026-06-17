# Cross-Camera Accuracy and Headcount Deduplication — Implementation Notes

**Phase:** Phase 3 Cross-Camera Accuracy  
**Plan:** `docs/superpowers/plans/2026-06-17-vms-phase3-crosscam-accuracy.md`  
**Completed:** 2026-06-17  
**Commits:** `3cf31fef` (config) → `c1d341ac` (headcount dedup) → `c4daeabf` (person_id wiring) → `dd4e3dc4` (overlap/uncertain) → `6ebf9b98` (predictor) → `ac1fda7b` (spatial gate) → `cd5cfe92` (wiring) → `71f00d0` (tracker buffer) + `cb166fa` (formatting)

---

## Task 1 — Config keys

Added three new settings to `vms/config.py`:
- `tracker_buffer_frames: int = 90` — BoT-SORT ghost-tracklet retention frames
- `reid_predictor_history_len: int = 8` — ring buffer depth per gid
- `reid_predictor_max_predict_gap_ms: int = 900_000` — 15-min predict horizon cap

All defaults are conservative/no-op (existing behaviour unchanged until explicitly configured).

## Task 2 — Headcount dedup by person_id

`HeadCountAggregator.on_tracking_event` gained `person_id: int | None`. Module-level type alias `Key = int | uuid.UUID`. Dedup key is `person_id` (int, globally unique) when known; falls back to `gid` (UUID, per-track) for unknowns. One person seen by two cameras now counts as 1, not 2.

`HeadCountSnapshot.to_dict()` bumped `schema_version` to `"2"` and adds `uncertain_count`.

## Task 3 — Pipeline wiring

`AnomalyOrchestrator._person_id_for(gid, ctx)` already existed. Modified the head-count update loop to pass the result as `person_id=`. No per-frame DB query: resolved via the existing in-memory identity registry.

## Task 4 — Overlap declaration and uncertain_count

`CameraTopology._PairWindow` gained `overlap: bool = False`. New methods `is_overlapping(cam_a, cam_b)` and `overlapping_cameras() -> set[int]`. `HeadCountAggregator` accepts `overlapping_zones: set[int]` at construction. `snapshot()` counts unknowns (`gid`-keyed) in declared overlapping zones as `uncertain_count` — a confidence indicator surfaced to the Guard view.

## Task 5 — CrossCameraPredictor

New `vms/identity/predictor.py`. Pure numpy constant-velocity Kalman filter (state `[px, py, vx, vy]`). Per-gid ring buffer (`deque(maxlen=history_len)`) of floor observations. `predict_position(gid, at_ms)` returns `None` if fewer than 2 observations, or if `at_ms - last_ts > max_predict_gap_ms`. Initialises from first two obs, runs forward update over remaining buffer, then extrapolates. No new dependency — uses numpy linear algebra only.

**Kalman parameters** (`_PROCESS_VAR = 1.0`, `_MEAS_VAR = 0.25`) are internal constants, not config. They are conservative: the operator-facing knob is `spatial_gate_m` in topology JSON.

## Task 6 — Spatial gate in transit_ok

`CameraTopology._PairWindow` gained `spatial_gate_m: float | None = None`. `transit_ok` gained `floor_xy: tuple[float, float] | None` and `predicted_xy: tuple[float, float] | None` kwargs. Gate is **opt-in** (default `None` = disabled) and **fail-open** (no prediction = gate skipped). Applied only after the time gate passes, additive not a bypass.

## Task 7 — Wiring into IdentityEngine

`IdentityEngine.__init__` now constructs a `CrossCameraPredictor` from config. `assign_global_track_id` gained `floor_xy` and `ts_ms` kwargs. Floor observations are fed to the predictor on every sighting (known track and newly matched). During `_cross_camera_match`, `predict_position` is called for each candidate gid; the spatial gate check is delegated to `transit_ok`.

`assign_and_identify` passes `floor_xy` through to `assign_global_track_id`. `db_writer.py` already computes `floor_coords` from homography; it now passes it to `assign_and_identify`.

## Task 8 — Config-driven BoT-SORT track_buffer

`vms/inference/tracker.py` gained `resolve_tracker_config()` (public) and `_render_tracker_config(base_config, track_buffer)` (LRU-cached). The rendered config is written to a temp file so YOLO can load it. `PerCameraTracker.update()` calls `resolve_tracker_config()` instead of passing the static YAML path. `botsort_custom.yaml` retains `track_buffer: 90` as the default (comment updated).

## Decisions made

- **No new third-party deps.** Numpy Kalman beats scipy.signal.KalmanFilter for this 4-state case; avoids a new install that could break the CUDA env.
- **`spatial_gate_m` is per-pair, not global.** Different cross-camera transitions have different physical distances; a single global threshold would either be too tight or too loose.
- **Fail-open on missing prediction.** If the predictor has < 2 obs (e.g. person just enrolled), the spatial check is skipped and the time gate alone governs. Consistent with the existing time-gate policy.
- **`uncertain_count` is read-only.** The Guard view can display it as a "±N possible double-counts" badge; it doesn't block any operation.
- **`types-PyYAML` installed** for mypy strict compliance (`yaml` import in `tracker.py`). Added as part of the mypy fix.

## Coverage

`vms/identity`: 97% (557 lines, 16 missed). Uncovered lines are error-path branches in engine.py and topology.py that require specific DB error injection.

## Test count

666 total (9 deselected as integration). All pass.
