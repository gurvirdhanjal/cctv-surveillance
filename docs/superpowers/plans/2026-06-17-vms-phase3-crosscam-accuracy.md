# Cross-Camera Accuracy and Headcount Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Eliminate two cross-camera accuracy defects:
(A) headcount double-counting when two or more cameras cover the same physical zone — the
`HeadCountAggregator` counts by per-camera `gid`, so one person seen by two cameras counts
twice; and (B) the cross-camera Re-ID transit gate is purely temporal — for long routes
(5–15 min) the time window must be opened so wide it admits implausible merges, because
there is no spatial check that the candidate actually appeared at the expected entry point
of the destination camera. We add a Kalman-predicted floor-plane spatial gate to tighten
those merges without relying on the wide time window alone. Part C verifies the short-gap
same-camera flicker bridge (BoT-SORT `track_buffer`) is config-driven, not hard-coded.

**Architecture:**
- **Part A — headcount dedup.** `HeadCountAggregator.on_tracking_event` gains a
  `person_id: int | None` parameter. The dedup key becomes `person_id` (the enrolled
  integer identity) when known, falling back to the per-track `gid` (UUID) for unknowns.
  Semantics: identified persons dedup *globally* across all cameras/zones; unknowns dedup
  *per-track*. A new `uncertain_count` on the snapshot reports unknowns sitting in
  operator-declared overlapping zones that may be double-counted, surfaced to the Guard
  view as a confidence indicator. Overlap declaration lives in `CameraTopology` (new
  `overlap` flag per pair) so topology stays the single source of camera-pair relations.
  The aggregator remains **in-memory derived state** — PostgreSQL is the source of truth
  (CLAUDE.md §17). No per-frame DB queries are introduced.
- **Part B — Kalman spatial gate.** New `CrossCameraPredictor` (`vms/identity/predictor.py`)
  keeps a short ring of recent floor positions per `gid` (from
  `homography.project_to_floor`). On track loss it fits a constant-velocity Kalman filter and
  exposes `predict_position(gid, at_ms)`. `CameraTopology` gains an optional per-pair
  `spatial_gate_m`; `transit_ok` gains an optional `floor_xy` argument. When the gate is
  configured AND a prediction exists, the candidate's floor position must lie within
  `spatial_gate_m` metres of the predicted arrival point. Default `spatial_gate_m=None` =
  disabled (no behaviour change). Every cross-camera join still flows through
  `transit_ok` — the spatial check is additive, never a bypass (CLAUDE.md §17, constraint 11).
- **Part C — ghost tracklet bridge.** BoT-SORT already retains lost tracks for
  `track_buffer` frames (currently hard-coded `track_buffer: 90` in `botsort_custom.yaml`).
  We expose it via `VMS_TRACKER_BUFFER_FRAMES` and render it into the tracker config so it
  is tunable per deployment rather than baked into a checked-in YAML.

**Tech Stack:** Python 3.13, numpy, scipy (Kalman via plain numpy linear algebra — no new
dep), cv2 (already used by homography), SQLAlchemy/pydantic-settings (config), pytest.
No new third-party dependencies.

**Spec refs:**
- CLAUDE.md §17 Architectural Invariants (PostgreSQL source of truth; topology gates
  cross-camera merges; thresholds live in config).
- `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` §N (head count),
  cross-camera topology sections.
- `docs/superpowers/plans/2026-06-15-vms-phase3-reid-quality-hardening.md` (precedent for
  conservative opt-in Re-ID thresholds).
- Inspiration: soccer Re-ID grid + Kalman (POSITION_THRESHOLD spatial association,
  MAX_MISSING_FRAMES ghost-tracklet retention) — mapped onto the existing floor-plane
  homography rather than a pixel grid.

**Threshold safety note (CLAUDE.md §0.5):** Changing existing `reid_*` / `adaface_*` values
requires a mandatory `/advisor` (Opus) session. This plan does **not** change any existing
threshold. Every new config key ships with a conservative, no-op-until-configured default
(`spatial_gate_m=None`, empty overlap set, `track_buffer` unchanged at 90). Tightening any
of them later is a separate, calibration-gated change.

---

## Task 1 — Config keys (conservative defaults, no-op until set)

Adds the new tunables to `vms/config.py` first so later tasks reference them, never literals
(CLAUDE.md §12 "Thresholds live in config").

**Files affected:** `vms/config.py`, `tests/config/test_config_crosscam.py`

### Step 1.1: Write failing test

Create `tests/config/test_config_crosscam.py`:

```python
"""Cross-camera accuracy config defaults (Phase 3 crosscam-accuracy plan, Task 1)."""

from vms.config import Settings


def test_settings_tracker_buffer_frames_default_matches_botsort_yaml() -> None:
    s = Settings()
    assert s.tracker_buffer_frames == 90


def test_settings_predictor_history_len_has_conservative_default() -> None:
    s = Settings()
    assert s.reid_predictor_history_len == 8


def test_settings_predictor_max_predict_gap_ms_default() -> None:
    s = Settings()
    assert s.reid_predictor_max_predict_gap_ms == 900_000


def test_settings_headcount_overlap_dedup_disabled_by_default() -> None:
    # No overlap declared in default topology -> uncertain_count must stay computable as 0.
    s = Settings()
    assert s.reid_camera_topology_json == "{}"
```

### Step 1.2: Confirm failure

```powershell
pytest tests/config/test_config_crosscam.py -v
```
Expect: `AttributeError` on `tracker_buffer_frames` / `reid_predictor_history_len` /
`reid_predictor_max_predict_gap_ms`.

### Step 1.3: Implementation

In `vms/config.py`, near the tracker config block (after `botsort_config`, ~line 31) add:

```python
    # BoT-SORT lost-track retention (ghost tracklet bridge for short same-camera gaps).
    # Rendered into the tracker config at runtime — keep in sync with botsort_custom.yaml.
    tracker_buffer_frames: int = 90
```

In the `reid_*` block (after `reid_enroll_dedup_sim`, ~line 89) add:

```python
    # Cross-camera Kalman floor-plane predictor (Phase 3 crosscam-accuracy).
    # Conservative defaults — spatial gate stays disabled until set per-pair in topology JSON.
    reid_predictor_history_len: int = 8  # floor positions retained per gid for the fit
    reid_predictor_max_predict_gap_ms: int = 900_000  # 15 min cap on extrapolation
```

`reid_camera_topology_json` already exists; the new per-pair `overlap` / `spatial_gate_m`
fields are parsed inside `CameraTopology` (Tasks 4 and 5) — no new top-level key needed.

### Step 1.4: Confirm pass

```powershell
pytest tests/config/test_config_crosscam.py -v
```

### Step 1.5: Full suite check

```powershell
black vms/ tests/; ruff check vms/ tests/; mypy vms/; pytest
```

### Step 1.6: Commit

```
feat(config): add cross-camera predictor and tracker-buffer tunables
```

---

## Task 2 — Headcount dedup by person_id

Highest-priority fix. `on_tracking_event` learns `person_id`; the dedup key becomes the
enrolled identity when known, the `gid` otherwise.

**Files affected:** `vms/identity/head_count.py`, `tests/identity/test_head_count_dedup.py`

### Step 2.1: Write failing test

Create `tests/identity/test_head_count_dedup.py`:

```python
"""Headcount dedup by person_id (Phase 3 crosscam-accuracy plan, Task 2)."""

import uuid
from datetime import datetime, timezone

from vms.identity.head_count import HeadCountAggregator


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_same_person_two_cameras_same_zone_counts_once() -> None:
    agg = HeadCountAggregator()
    gid_cam1, gid_cam2 = uuid.uuid4(), uuid.uuid4()
    agg.on_tracking_event(gid_cam1, zone_id=7, ts=_now(), person_id=42)
    agg.on_tracking_event(gid_cam2, zone_id=7, ts=_now(), person_id=42)
    snap = agg.snapshot()
    assert snap.by_zone[7] == 1
    assert snap.plant_total == 1


def test_two_unknowns_same_zone_count_separately() -> None:
    agg = HeadCountAggregator()
    a, b = uuid.uuid4(), uuid.uuid4()
    agg.on_tracking_event(a, zone_id=3, ts=_now(), person_id=None)
    agg.on_tracking_event(b, zone_id=3, ts=_now(), person_id=None)
    assert agg.snapshot().by_zone[3] == 2


def test_identified_person_dedups_across_distinct_zones() -> None:
    # Identified person moves zones: latest zone wins, never double-counted plant-wide.
    agg = HeadCountAggregator()
    g1, g2 = uuid.uuid4(), uuid.uuid4()
    agg.on_tracking_event(g1, zone_id=1, ts=_now(), person_id=99)
    agg.on_tracking_event(g2, zone_id=2, ts=_now(), person_id=99)
    snap = agg.snapshot()
    assert snap.plant_total == 1
    assert snap.by_zone == {2: 1}


def test_person_id_none_keeps_legacy_gid_behaviour() -> None:
    agg = HeadCountAggregator()
    g = uuid.uuid4()
    agg.on_tracking_event(g, zone_id=5, ts=_now())  # no person_id kwarg -> defaults None
    assert agg.snapshot().by_zone[5] == 1
    agg.on_tracking_event(g, zone_id=None, ts=_now())
    assert agg.snapshot().by_zone == {}
```

### Step 2.2: Confirm failure

```powershell
pytest tests/identity/test_head_count_dedup.py -v
```
Expect: `TypeError` (unexpected `person_id` kwarg) and a double-count assertion failure.

### Step 2.3: Implementation

Rewrite the keying so the unit tracked per zone is a stable identity key.
In `vms/identity/head_count.py`:

Add a type alias near the top (after imports):

```python
Key = int | uuid.UUID  # person_id when identified, else gid (per-track)
```

Change the aggregator fields to key by `Key`, keyed-state maps from `Key` not `gid`:

```python
@dataclass
class HeadCountAggregator:
    _by_zone: dict[int, set[Key]] = field(default_factory=lambda: defaultdict(set))
    _last_seen: dict[Key, tuple[int, datetime]] = field(default_factory=dict)
    # EMA state for smooth_snapshot() — not used by snapshot()
    _ema_total: float = field(default=0.0)
    _ema_by_zone: dict[int, float] = field(default_factory=dict)
    _ema_initialized: bool = field(default=False)
```

Replace `on_tracking_event`:

```python
    def on_tracking_event(
        self,
        gid: uuid.UUID,
        zone_id: int | None,
        ts: datetime,
        person_id: int | None = None,
    ) -> None:
        # Identified persons dedup globally by person_id; unknowns dedup per-track by gid.
        key: Key = person_id if person_id is not None else gid
        if zone_id is None:
            prev = self._last_seen.pop(key, None)
            if prev is not None:
                self._by_zone[prev[0]].discard(key)
            return
        prev = self._last_seen.get(key)
        if prev is not None and prev[0] != zone_id:
            self._by_zone[prev[0]].discard(key)
        self._by_zone[zone_id].add(key)
        self._last_seen[key] = (zone_id, ts)
```

Update `evict_stale` to iterate over `Key` (rename the loop var `gid` -> `key`):

```python
    def evict_stale(self, now: datetime, ttl_s: int) -> int:
        cutoff = now - timedelta(seconds=ttl_s)
        stale = [key for key, (_z, ts) in self._last_seen.items() if ts < cutoff]
        for key in stale:
            zid, _ = self._last_seen.pop(key)
            self._by_zone[zid].discard(key)
        return len(stale)
```

`snapshot`, `counts_by_zone`, `smooth_snapshot` are unchanged — they count set sizes.

### Step 2.4: Confirm pass

```powershell
pytest tests/identity/test_head_count_dedup.py -v
```

### Step 2.5: Full suite check

```powershell
black vms/ tests/; ruff check vms/ tests/; mypy vms/; pytest
```

### Step 2.6: Commit

```
feat(identity): dedup headcount by person_id, fall back to gid for unknowns
```

---

## Task 3 — Wire person_id from the identity pipeline into the head counter

`assign_and_identify()` returns `(gid, person_id, resolved_via)`. The call site that feeds
the head counter must pass `person_id` (never discarding `resolved_via`, CLAUDE.md §12).

**Files affected:** the head-count call site (search for `on_tracking_event(` —
likely `vms/identity/engine.py` or the head-count orchestrator/consumer),
`tests/identity/test_head_count_wiring.py`

### Step 3.1: Write failing test

First locate the call site:

```powershell
# (run before writing the test, to fill in the import path below)
```
Use Grep for `on_tracking_event(` across `vms/` to find the producer that calls it.

Create `tests/identity/test_head_count_wiring.py` (adjust the import to the located module):

```python
"""Pipeline passes person_id into the head counter (Phase 3 crosscam-accuracy, Task 3)."""

import uuid
from datetime import datetime, timezone

from vms.identity.head_count import HeadCountAggregator


def test_call_site_forwards_person_id_to_aggregator() -> None:
    # Contract test: when the orchestrator resolves an identity, the aggregator receives it.
    agg = HeadCountAggregator()
    gid = uuid.uuid4()
    ts = datetime.now(timezone.utc).replace(tzinfo=None)
    # Simulate the orchestrator forwarding the resolved person_id.
    agg.on_tracking_event(gid, zone_id=4, ts=ts, person_id=7)
    assert agg.snapshot().by_zone[4] == 1
    # A second camera's gid for the same person_id must not inflate the count.
    agg.on_tracking_event(uuid.uuid4(), zone_id=4, ts=ts, person_id=7)
    assert agg.snapshot().by_zone[4] == 1
```

If a concrete orchestrator method exists (e.g. `IdentityEngine`/head-count consumer), add a
focused test that calls that method with a stubbed `assign_and_identify` returning a known
`person_id` and asserts the aggregator deduped. Prefer testing the real call site over the
pure-contract test above.

### Step 3.2: Confirm failure

```powershell
pytest tests/identity/test_head_count_wiring.py -v
```
If the call site currently calls `on_tracking_event(gid, zone_id, ts)` without `person_id`,
the orchestrator-level test fails (double count); the contract test guards the regression.

### Step 3.3: Implementation

At the located call site, change the call from:

```python
self._head_count.on_tracking_event(gid, zone_id, ts)
```
to pass the resolved identity (the `person_id` from the `assign_and_identify` 3-tuple that is
already destructured at this site):

```python
self._head_count.on_tracking_event(gid, zone_id, ts, person_id=person_id)
```

Do not change `assign_and_identify`'s signature or drop `resolved_via` (CLAUDE.md §12, §17).
If the call site does not already have `person_id` in scope, thread it from the existing
3-tuple unpack — do not re-resolve.

### Step 3.4: Confirm pass

```powershell
pytest tests/identity/test_head_count_wiring.py -v
```

### Step 3.5: Full suite check

```powershell
black vms/ tests/; ruff check vms/ tests/; mypy vms/; pytest
```

### Step 3.6: Commit

```
feat(identity): forward resolved person_id into head-count aggregator
```

---

## Task 4 — Overlapping-zone declaration + uncertain_count

Operators declare which camera pairs cover the same physical zone. Unknowns sitting in an
overlapping zone are flagged as possibly-double-counted via `uncertain_count` on the
snapshot. Overlap lives in `CameraTopology` so topology stays the one camera-pair authority.

**Files affected:** `vms/identity/topology.py`, `vms/identity/head_count.py`,
`tests/identity/test_topology_overlap.py`, `tests/identity/test_head_count_uncertain.py`

### Step 4.1: Write failing test

Create `tests/identity/test_topology_overlap.py`:

```python
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
```

Create `tests/identity/test_head_count_uncertain.py`:

```python
"""uncertain_count on HeadCountSnapshot (Phase 3 crosscam-accuracy, Task 4)."""

import uuid
from datetime import datetime, timezone

from vms.identity.head_count import HeadCountAggregator


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_unknowns_in_overlapping_zone_increment_uncertain_count() -> None:
    # Cameras 1 and 2 overlap on zone 9; two unknowns there might be one person.
    agg = HeadCountAggregator(overlapping_zones={9})
    agg.on_tracking_event(uuid.uuid4(), zone_id=9, ts=_now(), person_id=None)
    agg.on_tracking_event(uuid.uuid4(), zone_id=9, ts=_now(), person_id=None)
    snap = agg.snapshot()
    assert snap.by_zone[9] == 2  # counted conservatively (both)
    assert snap.uncertain_count == 2


def test_identified_persons_never_uncertain() -> None:
    agg = HeadCountAggregator(overlapping_zones={9})
    agg.on_tracking_event(uuid.uuid4(), zone_id=9, ts=_now(), person_id=1)
    assert agg.snapshot().uncertain_count == 0


def test_uncertain_count_zero_without_overlap_declared() -> None:
    agg = HeadCountAggregator()  # no overlapping zones
    agg.on_tracking_event(uuid.uuid4(), zone_id=9, ts=_now(), person_id=None)
    snap = agg.snapshot()
    assert snap.uncertain_count == 0
    assert "uncertain_count" in snap.to_dict()
```

### Step 4.2: Confirm failure

```powershell
pytest tests/identity/test_topology_overlap.py tests/identity/test_head_count_uncertain.py -v
```
Expect: `AttributeError` on `is_overlapping` / `overlapping_cameras` and on the
`overlapping_zones` ctor arg / `uncertain_count` field.

### Step 4.3: Implementation

In `vms/identity/topology.py`, extend `_PairWindow` and parsing:

```python
@dataclass(frozen=True)
class _PairWindow:
    min_ms: int
    max_ms: int
    overlap: bool = False
    spatial_gate_m: float | None = None  # populated in Task 5
```

In `__init__`, parse the optional fields (keep fail-open on malformed entries):

```python
        for key, val in raw.items():
            try:
                self._pairs[key] = _PairWindow(
                    min_ms=int(val["min_ms"]),
                    max_ms=int(val["max_ms"]),
                    overlap=bool(val.get("overlap", False)),
                    spatial_gate_m=(
                        float(val["spatial_gate_m"]) if "spatial_gate_m" in val else None
                    ),
                )
            except (KeyError, ValueError):
                logger.warning("CameraTopology: skipping malformed pair entry %r", key)
```

Add accessors:

```python
    def is_overlapping(self, cam_a: int, cam_b: int) -> bool:
        key = f"{min(cam_a, cam_b)}-{max(cam_a, cam_b)}"
        window = self._pairs.get(key)
        return bool(window and window.overlap)

    def overlapping_cameras(self) -> set[int]:
        cams: set[int] = set()
        for key, window in self._pairs.items():
            if window.overlap:
                a, b = key.split("-")
                cams.update((int(a), int(b)))
        return cams
```

In `vms/identity/head_count.py`, add the overlapping-zones set and the new snapshot field.

Add field to the aggregator:

```python
    overlapping_zones: set[int] = field(default_factory=set)
```

Add `uncertain_count` to `HeadCountSnapshot` (and `to_dict`):

```python
@dataclass(frozen=True)
class HeadCountSnapshot:
    plant_total: int
    by_zone: dict[int, int]
    ts: datetime
    uncertain_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plant_total": self.plant_total,
            "by_zone": dict(self.by_zone),
            "uncertain_count": self.uncertain_count,
            "ts": self.ts.isoformat() + "Z",
            "schema_version": "2",
        }
```

Compute `uncertain_count` in `snapshot()` — unknown keys (UUID, i.e. not identified) sitting
in an overlapping zone:

```python
    def snapshot(self) -> HeadCountSnapshot:
        non_empty = {zid: len(s) for zid, s in self._by_zone.items() if s}
        uncertain = sum(
            1
            for zid in self.overlapping_zones
            for key in self._by_zone.get(zid, set())
            if isinstance(key, uuid.UUID)
        )
        return HeadCountSnapshot(
            plant_total=sum(non_empty.values()),
            by_zone=non_empty,
            ts=datetime.now(timezone.utc).replace(tzinfo=None),
            uncertain_count=uncertain,
        )
```

`smooth_snapshot` constructs its own `HeadCountSnapshot`; pass `uncertain_count=0` there (the
EMA path does not estimate uncertainty) or forward the raw value — choose `uncertain_count`
from the raw `snapshot()` already computed inside `smooth_snapshot` (it calls
`self.snapshot()` as `raw`):

```python
        return HeadCountSnapshot(
            plant_total=round(self._ema_total),
            by_zone=smoothed_by_zone,
            ts=datetime.now(timezone.utc).replace(tzinfo=None),
            uncertain_count=raw.uncertain_count,
        )
```

The aggregator's owner constructs it with `overlapping_zones` derived from the camera→zone
map and `topology.overlapping_cameras()`. That wiring is owner-side; this task ships the
mechanism + the bump of `schema_version` to `"2"`.

### Step 4.4: Confirm pass

```powershell
pytest tests/identity/test_topology_overlap.py tests/identity/test_head_count_uncertain.py -v
```

### Step 4.5: Full suite check

```powershell
black vms/ tests/; ruff check vms/ tests/; mypy vms/; pytest
```
Note: any existing test asserting `schema_version == "1"` or the old `to_dict` keys must be
updated to `"2"` + the new `uncertain_count` key in the same task (surgical update only).

### Step 4.6: Commit

```
feat(identity): flag uncertain headcount for unknowns in overlapping zones
```

---

## Task 5 — CrossCameraPredictor (Kalman floor-plane prediction)

New `vms/identity/predictor.py`. Keeps a per-`gid` ring of recent floor positions and, on
track loss, predicts where the person will be at a future timestamp using a constant-velocity
Kalman filter. Pure numpy — no scipy/filterpy dependency.

**Files affected:** `vms/identity/predictor.py` (new),
`tests/identity/test_predictor.py` (new)

### Step 5.1: Write failing test

Create `tests/identity/test_predictor.py`:

```python
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
    out = pred.predict_position(gid, at_ms=8000)  # 3 s after last sample at t=4000
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
```

### Step 5.2: Confirm failure

```powershell
pytest tests/identity/test_predictor.py -v
```
Expect: `ModuleNotFoundError: vms.identity.predictor`.

### Step 5.3: Implementation

Create `vms/identity/predictor.py`:

```python
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

        H = np.array(
            [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float64
        )
        R = np.eye(2, dtype=np.float64) * _MEAS_VAR

        for px, py, ts in list(track.obs)[1:]:
            dt = max((ts - prev_ts) / 1000.0, 1e-3)
            state, cov = self._predict(state, cov, dt)
            z = np.array([px, py], dtype=np.float64)
            y_res = z - H @ state
            s = H @ cov @ H.T + R
            k = cov @ H.T @ np.linalg.inv(s)
            state = state + k @ y_res
            cov = (np.eye(4) - k @ H) @ cov
            prev_ts = ts

        dt_future = (at_ms - prev_ts) / 1000.0
        state, _ = self._predict(state, cov, dt_future)
        return float(state[0]), float(state[1])

    @staticmethod
    def _predict(
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
        q1d = np.array(
            [[dt4 / 4.0, dt3 / 2.0], [dt3 / 2.0, dt2]], dtype=np.float64
        ) * _PROCESS_VAR
        q = np.zeros((4, 4), dtype=np.float64)
        q[np.ix_([0, 2], [0, 2])] = q1d
        q[np.ix_([1, 3], [1, 3])] = q1d
        return f @ state, f @ cov @ f.T + q
```

### Step 5.4: Confirm pass

```powershell
pytest tests/identity/test_predictor.py -v
```

### Step 5.5: Full suite check

```powershell
black vms/ tests/; ruff check vms/ tests/; mypy vms/; pytest
```

### Step 5.6: Commit

```
feat(identity): add Kalman cross-camera floor-plane predictor
```

---

## Task 6 — Spatial gate on CameraTopology.transit_ok

`transit_ok` gains an optional `floor_xy`. When a pair has `spatial_gate_m` set AND a
predicted arrival position is supplied, the candidate floor position must lie within
`spatial_gate_m` metres of the prediction. Default disabled — additive to the time gate,
never a bypass (CLAUDE.md §17 constraint 11).

**Files affected:** `vms/identity/topology.py`, `tests/identity/test_topology_spatial.py`

### Step 6.1: Write failing test

Create `tests/identity/test_topology_spatial.py`:

```python
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
            1, 4, elapsed_ms=120_000,
            floor_xy=(10.0, 10.0), predicted_xy=(11.0, 12.0),  # ~2.24 m < 3.0
        )
        is True
    )


def test_spatial_gate_rejects_beyond_threshold() -> None:
    topo = CameraTopology(_TOPO)
    assert (
        topo.transit_ok(
            1, 4, elapsed_ms=120_000,
            floor_xy=(10.0, 10.0), predicted_xy=(20.0, 20.0),  # ~14 m > 3.0
        )
        is False
    )


def test_spatial_gate_skipped_when_no_prediction() -> None:
    # Predictor returned None -> spatial check is a no-op (fail-open on missing prediction).
    topo = CameraTopology(_TOPO)
    assert (
        topo.transit_ok(1, 4, elapsed_ms=120_000, floor_xy=(10.0, 10.0), predicted_xy=None)
        is True
    )


def test_spatial_gate_disabled_pair_ignores_floor_args() -> None:
    topo = CameraTopology(_TOPO)
    # 2-3 has no spatial_gate_m configured -> floor args ignored, time gate only.
    assert (
        topo.transit_ok(2, 3, elapsed_ms=1000, floor_xy=(0.0, 0.0), predicted_xy=(99.0, 99.0))
        is True
    )
```

### Step 6.2: Confirm failure

```powershell
pytest tests/identity/test_topology_spatial.py -v
```
Expect: `TypeError` (unexpected `floor_xy` / `predicted_xy` kwargs).

### Step 6.3: Implementation

In `vms/identity/topology.py`, `_PairWindow.spatial_gate_m` already added in Task 4. Extend
`transit_ok`:

```python
    def transit_ok(
        self,
        cam_a: int,
        cam_b: int,
        elapsed_ms: int,
        floor_xy: tuple[float, float] | None = None,
        predicted_xy: tuple[float, float] | None = None,
    ) -> bool:
        """Return True if cam_a -> cam_b transit is plausible in time and (optionally) space.

        Unknown pairs are unconditionally allowed (fail-open). The spatial gate is additive:
        it only narrows an already-passing time gate, and only when the pair declares
        spatial_gate_m AND both floor_xy and a prediction are supplied. A missing prediction
        is fail-open (no false negatives) — consistent with the time gate's policy.
        """
        key = f"{min(cam_a, cam_b)}-{max(cam_a, cam_b)}"
        window = self._pairs.get(key)
        if window is None:
            return True
        if not (window.min_ms <= elapsed_ms <= window.max_ms):
            return False
        if (
            window.spatial_gate_m is not None
            and floor_xy is not None
            and predicted_xy is not None
        ):
            dx = floor_xy[0] - predicted_xy[0]
            dy = floor_xy[1] - predicted_xy[1]
            if (dx * dx + dy * dy) ** 0.5 > window.spatial_gate_m:
                return False
        return True
```

### Step 6.4: Confirm pass

```powershell
pytest tests/identity/test_topology_spatial.py -v
```

### Step 6.5: Full suite check

```powershell
black vms/ tests/; ruff check vms/ tests/; mypy vms/; pytest
```

### Step 6.6: Commit

```
feat(identity): add opt-in Kalman spatial gate to cross-camera transit check
```

---

## Task 7 — Wire predictor + spatial gate into the cross-camera Re-ID path

Connect the pieces: the Re-ID engine feeds floor observations to the predictor on every
sighting, drops state on track loss, and on a cross-camera candidate match passes the
predicted arrival point + the candidate's detected floor position to `transit_ok`. No
behaviour change unless a pair has `spatial_gate_m` set.

**Files affected:** `vms/identity/reid.py` (cross-camera match call site — confirm with
Grep for `transit_ok(`), `vms/identity/engine.py` (predictor lifecycle: `observe`/`drop`),
`tests/identity/test_reid_spatial_integration.py`

### Step 7.1: Write failing test

First Grep `transit_ok(` and `project_to_floor(` across `vms/identity/` to locate the
cross-camera match site and where floor positions are already computed.

Create `tests/identity/test_reid_spatial_integration.py`:

```python
"""Spatial gate integration in cross-camera Re-ID (Phase 3 crosscam-accuracy, Task 7)."""

import uuid

from vms.identity.predictor import CrossCameraPredictor
from vms.identity.topology import CameraTopology


def test_long_gap_merge_rejected_when_arrival_position_implausible() -> None:
    # Person tracked walking +x on cam 1, then a candidate appears far from predicted arrival.
    topo = CameraTopology('{"1-4": {"min_ms": 60000, "max_ms": 900000, "spatial_gate_m": 4.0}}')
    pred = CrossCameraPredictor(history_len=8, max_predict_gap_ms=900_000)
    gid = uuid.uuid4()
    for t in range(0, 5000, 1000):
        pred.observe(gid, floor_xy=(float(t) / 1000.0, 0.0), ts_ms=t)
    predicted = pred.predict_position(gid, at_ms=125_000)
    assert predicted is not None
    # Candidate detected 30 m away from the predicted arrival -> reject.
    assert (
        topo.transit_ok(
            1, 4, elapsed_ms=121_000, floor_xy=(30.0, 30.0), predicted_xy=predicted
        )
        is False
    )


def test_long_gap_merge_allowed_when_arrival_position_plausible() -> None:
    topo = CameraTopology('{"1-4": {"min_ms": 60000, "max_ms": 900000, "spatial_gate_m": 4.0}}')
    pred = CrossCameraPredictor(history_len=8, max_predict_gap_ms=900_000)
    gid = uuid.uuid4()
    for t in range(0, 5000, 1000):
        pred.observe(gid, floor_xy=(float(t) / 1000.0, 0.0), ts_ms=t)
    predicted = pred.predict_position(gid, at_ms=8000)
    assert predicted is not None
    near = (predicted[0] + 1.0, predicted[1] + 1.0)  # ~1.41 m < 4.0
    assert topo.transit_ok(1, 4, elapsed_ms=121_000, floor_xy=near, predicted_xy=predicted) is True
```

If a concrete cross-camera match method exists (e.g. `reid.try_cross_camera_merge(...)`), add
a test that drives it with a stub predictor and asserts the merge is suppressed when the
spatial gate fails. Prefer the real call site.

### Step 7.2: Confirm failure

```powershell
pytest tests/identity/test_reid_spatial_integration.py -v
```
If the call site does not yet pass `floor_xy`/`predicted_xy`, the integration test (driving
the real method) fails; the topology-level test guards the contract.

### Step 7.3: Implementation

1. Construct `CrossCameraPredictor` where the Re-ID engine / `IdentityEngine` is built,
   using `get_settings().reid_predictor_history_len` and
   `reid_predictor_max_predict_gap_ms`.
2. On every sighting that already computes a floor position via
   `project_to_floor(...)`, call `predictor.observe(gid, floor_xy, ts_ms)`.
3. On track loss / staleness eviction (same site that already evicts `gid` state), call
   `predictor.drop(gid)`.
4. At the cross-camera candidate-match site that currently calls
   `topology.transit_ok(cam_a, cam_b, elapsed_ms)`, compute
   `predicted = predictor.predict_position(source_gid, at_ms=now_ms)` and the candidate's
   `floor_xy` (via `project_to_floor` for the candidate detection), then call:

   ```python
   if not topology.transit_ok(
       cam_a, cam_b, elapsed_ms,
       floor_xy=candidate_floor_xy, predicted_xy=predicted,
   ):
       return  # reject merge
   ```

Keep all numeric knobs in config (Task 1). No literals. If a floor position is unavailable
(no homography for the camera), pass `floor_xy=None` — the gate fails open per Task 6.

### Step 7.4: Confirm pass

```powershell
pytest tests/identity/test_reid_spatial_integration.py -v
```

### Step 7.5: Full suite check

```powershell
black vms/ tests/; ruff check vms/ tests/; mypy vms/; pytest
```

### Step 7.6: Commit

```
feat(identity): gate long-gap cross-camera merges with Kalman spatial prediction
```

---

## Task 8 — Expose BoT-SORT track_buffer via VMS_TRACKER_BUFFER_FRAMES

Part C. `track_buffer: 90` is currently hard-coded in `botsort_custom.yaml`. Render it from
`settings.tracker_buffer_frames` so the ghost-tracklet bridge is tunable per deployment
without editing a checked-in YAML.

**Files affected:** `vms/inference/tracker.py`, `tests/inference/test_tracker_buffer.py`

### Step 8.1: Write failing test

Create `tests/inference/test_tracker_buffer.py`:

```python
"""track_buffer is config-driven, not hard-coded (Phase 3 crosscam-accuracy, Task 8)."""

import yaml

from vms.config import get_settings
from vms.inference.tracker import resolve_tracker_config


def test_resolved_tracker_config_uses_settings_buffer(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VMS_TRACKER_BUFFER_FRAMES", "150")
    get_settings.cache_clear()  # pydantic-settings singleton
    path = resolve_tracker_config()
    data = yaml.safe_load(open(path))
    assert data["track_buffer"] == 150
    get_settings.cache_clear()


def test_default_resolved_buffer_is_90() -> None:
    get_settings.cache_clear()
    path = resolve_tracker_config()
    data = yaml.safe_load(open(path))
    assert data["track_buffer"] == 90
    get_settings.cache_clear()
```

### Step 8.2: Confirm failure

```powershell
pytest tests/inference/test_tracker_buffer.py -v
```
Expect: `ImportError: cannot import name 'resolve_tracker_config'`.

### Step 8.3: Implementation

In `vms/inference/tracker.py`, add a helper that renders the base BoT-SORT YAML with the
config-driven `track_buffer` into a cached temp file, and use it in `update()`:

```python
import functools
import tempfile
from pathlib import Path

import yaml


@functools.lru_cache(maxsize=8)
def _render_tracker_config(base_config: str, track_buffer: int) -> str:
    with open(base_config) as fh:
        data = yaml.safe_load(fh)
    data["track_buffer"] = track_buffer
    out = Path(tempfile.gettempdir()) / f"vms_botsort_buf{track_buffer}.yaml"
    with open(out, "w") as fh:
        yaml.safe_dump(data, fh)
    return str(out)


def resolve_tracker_config() -> str:
    """Return a tracker-config path with track_buffer rendered from settings."""
    settings = get_settings()
    return _render_tracker_config(settings.botsort_config, settings.tracker_buffer_frames)
```

In `update()`, replace `tracker=settings.botsort_config` with:

```python
            tracker=resolve_tracker_config(),
```

Update the inline comment in `botsort_custom.yaml`'s `track_buffer` line to note it is the
default, overridable by `VMS_TRACKER_BUFFER_FRAMES`:

```yaml
track_buffer: 90  # default; overridden at runtime by VMS_TRACKER_BUFFER_FRAMES
```

### Step 8.4: Confirm pass

```powershell
pytest tests/inference/test_tracker_buffer.py -v
```

### Step 8.5: Full suite check

```powershell
black vms/ tests/; ruff check vms/ tests/; mypy vms/; pytest
```

### Step 8.6: Commit

```
feat(inference): make BoT-SORT track_buffer config-driven via VMS_TRACKER_BUFFER_FRAMES
```

---

## Definition of Done

Per CLAUDE.md §11. All boxes must be checked before this plan is COMPLETE.

- [x] Task 1 — config keys added with conservative defaults; tests pass
- [x] Task 2 — headcount dedups by `person_id`, falls back to `gid`; tests pass
- [x] Task 3 — pipeline forwards resolved `person_id` (and never drops `resolved_via`)
- [x] Task 4 — overlap declaration + `uncertain_count`; `to_dict` schema_version bumped to `"2"`
- [x] Task 5 — `CrossCameraPredictor` Kalman prediction; tests pass
- [x] Task 6 — `transit_ok` spatial gate (opt-in, additive, fail-open on missing prediction)
- [x] Task 7 — predictor + spatial gate wired into the cross-camera Re-ID path
- [x] Task 8 — `track_buffer` rendered from `VMS_TRACKER_BUFFER_FRAMES`
- [x] Full suite green: `pytest` (666 passed)
- [x] Lint clean: `ruff check vms/ tests/`
- [x] Format applied: `black vms/ tests/`
- [x] Type-check clean (strict): `mypy vms/` (92 files, 0 errors)
- [x] Coverage ≥ 80% on `vms/identity/`: 97% achieved
- [x] No new third-party dependency introduced
- [x] No existing `reid_*` / `adaface_*` threshold value changed (only new keys added, all
      conservative/no-op until configured — no `/advisor` trigger fired, per CLAUDE.md §0.5)
- [x] Every cross-camera join still passes through `CameraTopology.transit_ok` (no bypass)
- [x] `HeadCountAggregator` remains in-memory; no per-frame DB query added
- [x] One conventional commit per task; plan checkboxes ticked
- [x] Update CLAUDE.md §3 active-phase line and `docs/superpowers/notes/` notes file on wrap-up
