# Phase 2b — Anomaly Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED**

**Goal:** Ship the pluggable `AnomalyDetector` framework, the six v1 detectors (UNKNOWN_PERSON, PERSON_LOST, CROWD_DENSITY, INTRUSION, VIOLENCE, LOITERING), the `AlertFSM` (sustain + cooldown + dedup + maintenance suppression), the `MaintenanceCalendar`, the `HeadCountAggregator`, and the read-only inspection APIs that let us verify behaviour without a frontend.

**Architecture:** A new `vms.anomaly` package houses the framework (ABC, registry, FSM, maintenance, orchestrator). Detectors live in `vms.anomaly.detectors.*`. Each detector reads `DetectionFrame` payloads from the `detections` Redis Stream — no detector touches the raw frame except `VIOLENCE`, whose model (MoViNet-A0) runs inside `InferenceEngine`'s gated pool and exports a `violence_score` field on `DetectionFrame`. The orchestrator subscribes to `detections`, fans each frame through every enabled detector, pipes positive events through `AlertFSM`, persists firing alerts to `alerts` (DB) and publishes them to the `alerts` Redis Stream. `HeadCountAggregator` subscribes to the same stream and emits `head_count` snapshots that power both `CROWD_DENSITY` and `/api/state/snapshot`. Three new read-only HTTP routes (`/api/state/snapshot`, `/api/alerts`, `/api/anomaly-detectors`, `/api/maintenance`) and a CLI inspector (`vms-cli`) provide observability in the absence of a UI.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, PostgreSQL + pgvector, Redis Streams (`redis.asyncio`), ONNX Runtime (MoViNet-A0), `croniter` (cron parsing), `prometheus-client` (metrics), pytest + pytest-asyncio + fakeredis.

**Spec refs:**
- `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` §C (anomaly framework), §D (maintenance windows), §I (phase placement), §N (HeadCountAggregator + snapshot API)
- `docs/superpowers/specs/2026-05-01-vms-db-edge-cases.md` §C5 (maintenance double-create), §11 (alert state CHECK constraint), §14 (audit chain for alerts)
- `docs/superpowers/specs/2026-04-23-vms-facial-recognition-design.md` v1 §9 (alert FSM dedup/cooldown), §11 (`alert_fired` event), §14 (degraded mode), §15 (event versioning), §16 (observability)

---

## Context

Phase 2a completed the identity framework (FAISS index, ReIdService, IdentityEngine, ZonePresenceTracker, homography projection) and Phase 2a Hardening wired it into the `DBWriter` so `global_track_id` and `person_id` are now real (no more random UUIDs). What we still cannot do today: **detect anomalies, raise alerts, suppress them during maintenance, or count heads.**

Phase 2b closes that loop. After this phase, the pipeline becomes:

```
RTSP → IngestionWorker → frames stream → InferenceEngine
                                          ├→ SCRFD + AdaFace + YOLO + ByteTrack (always-on)
                                          └→ MoViNet (gated; ≥2 persons)
                                          → detections stream
                                              ├→ DBWriter      → tracking_events
                                              ├→ AnomalyOrchestrator
                                              │     └→ 6 detectors → AlertFSM
                                              │                       → alerts DB
                                              │                       → alerts stream
                                              └→ HeadCountAggregator
                                                    └→ head_count_zone_<id> stream
                                                    └→ /api/state/snapshot
```

The `AlertDispatcher` (Phase 3) will consume the `alerts` stream and fan out to Email/Slack/Telegram/Webhook. **Phase 2b does not implement dispatch** — it lands the events on the stream and persists them; the dispatcher hooks up later. WebSocket fanout to a frontend also waits for Phase 3.

### What "production-grade without a frontend" looks like

The codebase has no UI, so every behaviour must be verifiable via tests, structured logs, HTTP inspection endpoints, and a CLI. The plan enforces this by:

1. **One detector at a time** — each detector ships with isolated unit tests against synthetic `DetectionFrame` inputs, then an integration test that pushes through the orchestrator into the DB.
2. **Error isolation as a first-class concern** — every detector is wrapped in a try/except that increments a per-detector failure counter and disables the detector after `anomaly_max_consecutive_errors` (default 5). A failing detector never crashes the orchestrator or any other detector.
3. **Read-only inspection routes** — `/api/state/snapshot`, `/api/alerts`, `/api/anomaly-detectors/health` give a complete live view without needing the frontend.
4. **CLI tool** — `vms-cli alerts tail` / `vms-cli detectors status` / `vms-cli head-count` for ops-style probing.
5. **Structured logs with correlation IDs** — every alert log line carries `camera_id`, `seq_id`, `alert_id`, `dedup_key` so a single grep can reconstruct the lifecycle.
6. **Prometheus metrics** — per-detector eval rate, gate skip rate, fire rate, p50/p95 latency; per-FSM dedup hit rate; orchestrator stream lag.

### Backward-compatibility guarantees (no cascade from Phase 1B / 2a)

- `DetectionFrame.violence_score` is added with a default of `None`. All existing Phase 1B / 2a tests continue to pass — they never produce or consume the field.
- `DBWriter.flush_detection_frame` signature is **not changed**. The orchestrator is a **separate** consumer of the `detections` stream — there is no coupling.
- `InferenceEngine` gains a `_violence_model` attribute that defaults to `None`. When the MoViNet ONNX file is absent, the engine logs a warning, skips the gated pool, and continues exactly as in Phase 1B.
- `alerts.state` gets a `CHECK` constraint added; the previous data is unaffected because no rows exist yet (`alerts` table is empty in all environments).
- All new endpoints require auth via the existing `get_current_user` dependency.
- All new tables/columns ship in a single Alembic migration with a working `downgrade()`. Round-trip is tested in Task 1.

### Cascading failure prevention checklist (applied across all tasks)

| Failure mode | Mitigation | Task |
|---|---|---|
| Detector raises | try/except → counter → disable after N | Task 14 |
| MoViNet ONNX missing | warning log, gated pool no-op, `violence_score=None` | Task 12 |
| Maintenance calendar stale | 30 s TTL cache + manual invalidation on POST/PATCH | Task 5 |
| FSM state lost on restart | Reconstruct sustain/cooldown windows from `alerts` table (DB is source of truth) | Task 6 |
| Alerts stream backed up | `MAXLEN=10_000` cap; orchestrator measures lag and emits metric | Task 14, Task 16 |
| Detector misconfig | Pydantic-validated `config_json` per detector; refuse to enable on bad config | Task 4 |
| Head-count drift | TTL eviction (30 s) + periodic snapshot vs `ZonePresence` reconciliation | Task 13 |
| Stream consumer crash | Idempotent: alerts dedup_key + `alerts` UNIQUE constraint absorb replays | Task 6 |
| Cron-parse error | Per-window try/except; failed window logs CRITICAL + treated as inactive | Task 5 |
| Detector model not in registry | Registry load fails fast at startup; admin alert via metric | Task 4 |

---

## Files Modified / Created

| Action | Path |
|---|---|
| Modify | `CLAUDE.md` |
| Modify | `requirements.txt` |
| Modify | `vms/config.py` |
| Modify | `vms/db/models.py` |
| Create | `alembic/versions/<id>_phase2b_anomaly_framework.py` |
| Create | `vms/anomaly/__init__.py` |
| Create | `vms/anomaly/base.py` |
| Create | `vms/anomaly/registry.py` |
| Create | `vms/anomaly/maintenance.py` |
| Create | `vms/anomaly/fsm.py` |
| Create | `vms/anomaly/streams.py` |
| Create | `vms/anomaly/orchestrator.py` |
| Create | `vms/anomaly/detectors/__init__.py` |
| Create | `vms/anomaly/detectors/unknown_person.py` |
| Create | `vms/anomaly/detectors/person_lost.py` |
| Create | `vms/anomaly/detectors/crowd_density.py` |
| Create | `vms/anomaly/detectors/intrusion.py` |
| Create | `vms/anomaly/detectors/loitering.py` |
| Create | `vms/anomaly/detectors/violence.py` |
| Create | `vms/identity/head_count.py` |
| Create | `vms/inference/violence.py` |
| Modify | `vms/inference/messages.py` |
| Modify | `vms/inference/engine.py` |
| Create | `vms/api/routes/state.py` |
| Create | `vms/api/routes/alerts.py` |
| Create | `vms/api/routes/maintenance.py` |
| Create | `vms/api/routes/anomaly_detectors.py` |
| Modify | `vms/api/main.py` |
| Modify | `vms/api/schemas.py` |
| Modify | `vms/api/deps.py` |
| Create | `vms/cli/__init__.py` |
| Create | `vms/cli/main.py` |
| Modify | `pyproject.toml` (or `setup.cfg`) for `vms-cli` entry point |
| Create | `vms/observability/__init__.py` |
| Create | `vms/observability/metrics.py` |
| Create | `vms/observability/logging.py` |
| Create | `vms/api/routes/metrics.py` |
| Create | `tests/test_anomaly_base.py` |
| Create | `tests/test_anomaly_registry.py` |
| Create | `tests/test_anomaly_maintenance.py` |
| Create | `tests/test_anomaly_fsm.py` |
| Create | `tests/test_anomaly_orchestrator.py` |
| Create | `tests/test_anomaly_unknown_person.py` |
| Create | `tests/test_anomaly_person_lost.py` |
| Create | `tests/test_anomaly_crowd_density.py` |
| Create | `tests/test_anomaly_intrusion.py` |
| Create | `tests/test_anomaly_loitering.py` |
| Create | `tests/test_anomaly_violence.py` |
| Create | `tests/test_identity_head_count.py` |
| Create | `tests/test_inference_violence.py` |
| Modify | `tests/test_inference_messages.py` |
| Modify | `tests/test_inference_engine.py` |
| Create | `tests/test_api_state.py` |
| Create | `tests/test_api_alerts.py` |
| Create | `tests/test_api_maintenance.py` |
| Create | `tests/test_api_anomaly_detectors.py` |
| Create | `tests/test_api_metrics.py` |
| Create | `tests/test_cli.py` |
| Create | `tests/test_observability_metrics.py` |
| Create | `tests/test_anomaly_integration.py` |

---

## Task ordering rationale

Tasks 1–6 build the foundation (schema, types, calendar, FSM) without any detector. Tasks 7–12 ship the six detectors against the now-stable framework. Task 13 lands the `HeadCountAggregator` (which `CROWD_DENSITY` needs, but the detector tests in Task 9 mock it — landing it as a real component here lets us write the snapshot API). Task 14 wires it all together in the orchestrator. Task 15 adds the read-only inspection HTTP routes + CLI. Task 16 closes with metrics, structured logs, and an end-to-end integration test.

Each task ends with `pytest -v` over the full suite — a regression in earlier tests stops the plan.

---

## Task 1: Schema migration — alerts state CHECK, dedup_key, anomaly_detector seed data

**Background:** The Alert FSM in Task 6 needs a `dedup_key` column (one active alert per `(dedup_key)`) and a state CHECK constraint that includes `'suppressed'` (spec §D). The `anomaly_detectors` table also needs seed data so the registry has rows to load. We ship both in one migration to keep upgrade atomic.

**Files:**
- Modify: `vms/db/models.py`
- Create: `alembic/versions/<id>_phase2b_anomaly_framework.py`
- Modify: `tests/test_db_migrations.py` (or create — check existing)

- [ ] **Step 1: Write the failing migration round-trip test**

Add to `tests/test_db_migrations.py` (create the file if absent — follow the Phase 1A `tests/test_db_models.py` pattern):

```python
"""Phase 2b migration round-trip test."""
from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_phase2b_migration_adds_alerts_dedup_key(db_session: Session) -> None:
    insp = inspect(db_session.bind)
    cols = {c["name"] for c in insp.get_columns("alerts")}
    assert "dedup_key" in cols


@pytest.mark.integration
def test_phase2b_migration_adds_alerts_state_check(db_session: Session) -> None:
    """alerts.state CHECK constraint forbids unknown states."""
    from vms.db.models import Camera
    cam = Camera(name="MigC", rtsp_url="rtsp://x/1", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    with pytest.raises(Exception):
        db_session.execute(
            text(
                "INSERT INTO alerts (alert_type, severity, state, camera_id, triggered_at) "
                "VALUES ('UNKNOWN_PERSON', 'HIGH', 'NOT_A_STATE', :cid, NOW())"
            ),
            {"cid": cam.camera_id},
        )
        db_session.flush()


@pytest.mark.integration
def test_phase2b_migration_seeds_six_default_detectors(db_session: Session) -> None:
    rows = db_session.execute(
        text("SELECT alert_type FROM anomaly_detectors ORDER BY alert_type")
    ).all()
    types = [r[0] for r in rows]
    assert types == [
        "CROWD_DENSITY",
        "INTRUSION",
        "LOITERING",
        "PERSON_LOST",
        "UNKNOWN_PERSON",
        "VIOLENCE",
    ]


@pytest.mark.integration
def test_phase2b_migration_round_trip() -> None:
    """upgrade head -> downgrade -1 -> upgrade head must round-trip cleanly."""
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_db_migrations.py -v
```

Expected: FAIL — `dedup_key` column missing, default detector rows missing.

- [ ] **Step 3: Update `vms/db/models.py`**

In the `Alert` class `__table_args__`, add a state CHECK constraint, a type CHECK constraint, and a partial index on `dedup_key`. Also add the `dedup_key` column:

```python
class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "(acknowledged_at IS NULL OR acknowledged_at >= triggered_at)"
            " AND (resolved_at IS NULL OR resolved_at >= triggered_at)"
            " AND (resolved_at IS NULL OR acknowledged_at IS NULL"
            "      OR resolved_at >= acknowledged_at)",
            name="chk_alert_resolution_order",
        ),
        CheckConstraint(
            "state IN ('active', 'acknowledged', 'resolved', 'suppressed')",
            name="chk_alert_state",
        ),
        CheckConstraint(
            "alert_type IN ('UNKNOWN_PERSON','PERSON_LOST','CROWD_DENSITY',"
            "'INTRUSION','VIOLENCE','LOITERING')",
            name="chk_alert_type",
        ),
        Index("ix_alerts_alert_type", "alert_type"),
        Index("ix_alerts_triggered_at", "triggered_at"),
        Index(
            "ix_alerts_dedup_key_active",
            "dedup_key",
            postgresql_where=text("state = 'active'"),
        ),
    )
    # ... existing columns unchanged ...
    dedup_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

Add `from sqlalchemy import text` to the imports if not already present.

- [ ] **Step 4: Generate the migration**

```powershell
alembic revision -m "phase2b anomaly framework"
```

Edit `alembic/versions/<id>_phase2b_anomaly_framework.py`:

```python
"""phase2b anomaly framework

Revision ID: <auto>
Revises: <previous head revision id>
Create Date: 2026-05-15

Adds:
  - alerts.dedup_key (String 100, nullable)
  - Partial index ix_alerts_dedup_key_active where state='active'
  - alerts CHECK constraints: chk_alert_state, chk_alert_type
  - Seed: 6 default rows in anomaly_detectors
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "<auto>"
down_revision = "<prev>"
branch_labels = None
depends_on = None

_DETECTORS = [
    ("UNKNOWN_PERSON", "vms.anomaly.detectors.unknown_person.UnknownPersonDetector"),
    ("PERSON_LOST",    "vms.anomaly.detectors.person_lost.PersonLostDetector"),
    ("CROWD_DENSITY",  "vms.anomaly.detectors.crowd_density.CrowdDensityDetector"),
    ("INTRUSION",      "vms.anomaly.detectors.intrusion.IntrusionDetector"),
    ("VIOLENCE",       "vms.anomaly.detectors.violence.ViolenceDetector"),
    ("LOITERING",      "vms.anomaly.detectors.loitering.LoiteringDetector"),
]


def upgrade() -> None:
    op.add_column("alerts", sa.Column("dedup_key", sa.String(length=100), nullable=True))
    op.create_index(
        "ix_alerts_dedup_key_active",
        "alerts",
        ["dedup_key"],
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_check_constraint(
        "chk_alert_state",
        "alerts",
        "state IN ('active', 'acknowledged', 'resolved', 'suppressed')",
    )
    op.create_check_constraint(
        "chk_alert_type",
        "alerts",
        "alert_type IN ('UNKNOWN_PERSON','PERSON_LOST','CROWD_DENSITY',"
        "'INTRUSION','VIOLENCE','LOITERING')",
    )
    op.create_index("ix_alerts_state", "alerts", ["state"])

    detectors = sa.table(
        "anomaly_detectors",
        sa.column("alert_type", sa.String),
        sa.column("class_path", sa.String),
        sa.column("is_enabled", sa.Boolean),
    )
    op.bulk_insert(
        detectors,
        [{"alert_type": at, "class_path": cp, "is_enabled": True} for at, cp in _DETECTORS],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM anomaly_detectors WHERE alert_type IN ("
        "'UNKNOWN_PERSON','PERSON_LOST','CROWD_DENSITY',"
        "'INTRUSION','VIOLENCE','LOITERING')"
    )
    op.drop_index("ix_alerts_state", table_name="alerts")
    op.drop_constraint("chk_alert_type", "alerts", type_="check")
    op.drop_constraint("chk_alert_state", "alerts", type_="check")
    op.drop_index("ix_alerts_dedup_key_active", table_name="alerts")
    op.drop_column("alerts", "dedup_key")
```

- [ ] **Step 5: Apply locally and confirm**

```powershell
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Expected: all three commands succeed.

- [ ] **Step 6: Run tests to verify they pass**

```powershell
pytest tests/test_db_migrations.py -v
```

Expected: all PASS.

- [ ] **Step 7: Run full suite**

```powershell
pytest -v
```

Expected: 159+ tests still pass (Phase 2a hardening baseline + new migration tests).

- [ ] **Step 8: Commit**

```powershell
git add vms/db/models.py alembic/versions/ tests/test_db_migrations.py
git commit -m "feat(db): phase2b — alerts.dedup_key, state/type CHECK, seed 6 anomaly_detectors"
```

---

## Task 2: Config additions — anomaly, FSM, head-count, violence

**Files:**
- Modify: `vms/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_anomaly_defaults() -> None:
    s = Settings(db_url="postgresql://x/y", jwt_secret="s")  # type: ignore[call-arg]
    assert s.violence_model == "models/movinet_a0.onnx"
    assert s.violence_threshold == 0.65
    assert s.violence_gate_min_persons == 2
    assert s.violence_clip_frames == 16
    assert s.violence_inference_every_s == 1.0
    assert s.alert_fsm_default_dedup_window_ms == 60_000
    assert s.alert_fsm_default_cooldown_ms == 60_000
    assert s.alert_fsm_default_sustain_ms == 500
    assert s.head_count_emit_interval_s == 1.0
    assert s.head_count_track_ttl_s == 30
    assert s.maintenance_cache_ttl_s == 30
    assert s.anomaly_max_consecutive_errors == 5
    assert s.alerts_stream_maxlen == 10_000
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_config.py::test_anomaly_defaults -v
```

Expected: FAIL — fields not defined.

- [ ] **Step 3: Add fields to `vms/config.py`**

Insert in `Settings` after the existing `zone_cache_ttl_s` line:

```python
    # violence (gated pool in InferenceEngine)
    violence_model: str = "models/movinet_a0.onnx"
    violence_threshold: float = 0.65
    violence_gate_min_persons: int = 2
    violence_clip_frames: int = 16
    violence_inference_every_s: float = 1.0

    # alert FSM
    alert_fsm_default_dedup_window_ms: int = 60_000
    alert_fsm_default_cooldown_ms: int = 60_000
    alert_fsm_default_sustain_ms: int = 500

    # head count
    head_count_emit_interval_s: float = 1.0
    head_count_track_ttl_s: int = 30

    # maintenance
    maintenance_cache_ttl_s: int = 30

    # anomaly orchestrator
    anomaly_max_consecutive_errors: int = 5
    alerts_stream_maxlen: int = 10_000
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_config.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add vms/config.py tests/test_config.py
git commit -m "feat(config): phase2b — violence, FSM, head-count, maintenance, orchestrator settings"
```

---

## Task 3: AnomalyDetector ABC + DTOs (AnomalyEvent, FSMConfig, DetectorContext)

**Background:** Every detector implements one interface. The framework calls `should_run(ctx)` to cheaply gate evaluation, then `evaluate(ctx)` to produce a candidate `AnomalyEvent`. The FSM consumes events and decides whether to fire an alert. Each detector reports its `fsm_config()` once at load time.

**Files:**
- Create: `vms/anomaly/__init__.py`
- Create: `vms/anomaly/base.py`
- Create: `tests/test_anomaly_base.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_anomaly_base.py`:

```python
"""Tests for the AnomalyDetector ABC + DTOs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    Severity,
)
from vms.inference.messages import DetectionFrame


def _empty_frame(camera_id: int = 1) -> DetectionFrame:
    return DetectionFrame(
        camera_id=camera_id,
        seq_id=1,
        timestamp_ms=1_700_000_000_000,
        tracklets=(),
        face_embeddings=(),
    )


def test_severity_enum_values() -> None:
    assert Severity.LOW.value == "LOW"
    assert Severity.CRITICAL.value == "CRITICAL"


def test_fsm_config_defaults() -> None:
    cfg = FSMConfig()
    assert cfg.sustain_ms == 500
    assert cfg.cooldown_ms == 60_000
    assert cfg.dedup_window_ms == 60_000


def test_anomaly_event_is_frozen() -> None:
    ev = AnomalyEvent(
        alert_type="UNKNOWN_PERSON",
        severity=Severity.HIGH,
        camera_id=1,
        zone_id=2,
        global_track_id=uuid.uuid4(),
        person_id=None,
        event_ts=datetime.now(timezone.utc).replace(tzinfo=None),
        dedup_key="UNKNOWN_PERSON:zone=2:track=abc",
        payload={"confidence": 0.95},
    )
    with pytest.raises(Exception):
        ev.alert_type = "VIOLENCE"  # type: ignore[misc]


def test_detector_context_has_required_fields() -> None:
    ctx = DetectorContext(
        frame=_empty_frame(),
        zone_lookup={},
        active_track_zones={},
        head_count={},
        violence_score=None,
    )
    assert ctx.frame.camera_id == 1
    assert ctx.head_count == {}


def test_concrete_detector_cannot_skip_abstract_methods() -> None:
    class Bad(AnomalyDetector):
        alert_type = "X"
        severity = Severity.LOW
        requires_models: tuple[str, ...] = ()
        requires_tier: tuple[str, ...] = ("FULL",)

    with pytest.raises(TypeError):
        Bad({})  # cannot instantiate — missing abstract methods


def test_concrete_detector_passes_smoke() -> None:
    class Echo(AnomalyDetector):
        alert_type = "UNKNOWN_PERSON"
        severity = Severity.HIGH
        requires_models: tuple[str, ...] = ()
        requires_tier: tuple[str, ...] = ("FULL",)

        def should_run(self, ctx: DetectorContext) -> bool:
            return True

        def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
            return None

        def fsm_config(self) -> FSMConfig:
            return FSMConfig()

    d = Echo({})
    ctx = DetectorContext(
        frame=_empty_frame(), zone_lookup={}, active_track_zones={},
        head_count={}, violence_score=None,
    )
    assert d.should_run(ctx) is True
    assert d.evaluate(ctx) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_anomaly_base.py -v
```

Expected: FAIL — `vms.anomaly` package not present.

- [ ] **Step 3: Create `vms/anomaly/__init__.py`**

```python
"""Anomaly framework — detectors, FSM, maintenance, orchestrator."""
```

- [ ] **Step 4: Create `vms/anomaly/base.py`**

```python
"""AnomalyDetector ABC + supporting DTOs.

Every detector subclasses AnomalyDetector and implements three methods:
  - should_run(ctx): cheap CPU-side gate; returning False skips evaluate().
  - evaluate(ctx): runs the rule/model and emits a candidate event or None.
  - fsm_config(): one-time configuration (sustain, cooldown, dedup).

The orchestrator calls should_run() first; if it returns True, evaluate()
runs. A returned AnomalyEvent is handed to AlertFSM, which decides whether
to materialise it as an alert.
"""

from __future__ import annotations

import enum
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from vms.inference.messages import DetectionFrame


class Severity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class FSMConfig:
    sustain_ms: int = 500
    cooldown_ms: int = 60_000
    dedup_window_ms: int = 60_000


@dataclass(frozen=True)
class AnomalyEvent:
    alert_type: str
    severity: Severity
    camera_id: int
    zone_id: int | None
    global_track_id: uuid.UUID | None
    person_id: int | None
    event_ts: datetime
    dedup_key: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ZoneLookup:
    zone_id: int
    name: str
    is_restricted: bool
    max_capacity: int | None
    allowed_hours: str | None
    loiter_threshold_s: int
    polygon_json: str | None


@dataclass(frozen=True)
class DetectorContext:
    frame: DetectionFrame
    zone_lookup: dict[int, ZoneLookup]
    active_track_zones: dict[uuid.UUID, int]
    head_count: dict[int, int]
    violence_score: float | None


class AnomalyDetector(ABC):
    alert_type: str
    severity: Severity
    requires_models: tuple[str, ...]
    requires_tier: tuple[str, ...]

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = dict(config)

    @abstractmethod
    def should_run(self, ctx: DetectorContext) -> bool: ...

    @abstractmethod
    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None: ...

    @abstractmethod
    def fsm_config(self) -> FSMConfig: ...


@runtime_checkable
class SeamProvider(Protocol):
    """Opt-in protocol for detectors that need IdentityEngine/ZonePresence lookups.

    Declare `class MyDetector(AnomalyDetector, SeamProvider)` to opt in.
    The orchestrator checks `isinstance(det, SeamProvider)` in `_bind_seams`
    and replaces these methods with live implementations before the first frame.
    Default implementations are safe no-ops (return None / empty dict) so unit
    tests can instantiate detectors without wiring the orchestrator.
    """

    def _gid_for_tracklet(
        self, tl: Any, ctx: DetectorContext
    ) -> uuid.UUID | None:
        return None

    def _person_id_for(
        self, gid: uuid.UUID, ctx: DetectorContext
    ) -> int | None:
        return None

    def _registry_last_seen(
        self, ctx: DetectorContext
    ) -> dict[uuid.UUID, int]:
        return {}

    def _entered_at(
        self, gid: uuid.UUID, zone_id: int, ctx: DetectorContext
    ) -> datetime | None:
        return None
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
pytest tests/test_anomaly_base.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git add vms/anomaly/ tests/test_anomaly_base.py
git commit -m "feat(anomaly): add AnomalyDetector ABC, AnomalyEvent, FSMConfig, DetectorContext DTOs"
```

---

## Task 4: Detector registry + dynamic class loader

**Background:** The registry reads enabled rows from `anomaly_detectors`, imports each `class_path`, instantiates with `config_json` (parsed + validated), and exposes a `dict[str, AnomalyDetector]` keyed by `alert_type`. Misconfigured rows fail loudly: the registry returns errors per-row and increments a Prometheus counter, but does not crash the orchestrator startup.

**Files:**
- Create: `vms/anomaly/registry.py`
- Create: `tests/test_anomaly_registry.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_anomaly_registry.py`:

```python
"""Tests for the detector registry."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from vms.anomaly.base import AnomalyDetector, DetectorContext, FSMConfig, Severity
from vms.anomaly.registry import RegistryLoadResult, load_enabled_detectors


class _StubOK(AnomalyDetector):
    alert_type = "UNKNOWN_PERSON"
    severity = Severity.HIGH
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL",)

    def should_run(self, ctx: DetectorContext) -> bool:
        return True

    def evaluate(self, ctx: DetectorContext) -> None:
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig()


def test_load_skips_disabled_rows(db_session: Session) -> None:
    db_session.execute(
        text("UPDATE anomaly_detectors SET is_enabled = false WHERE alert_type = 'VIOLENCE'")
    )
    db_session.execute(
        text("UPDATE anomaly_detectors SET class_path = :cp WHERE alert_type = 'UNKNOWN_PERSON'"),
        {"cp": "tests.test_anomaly_registry._StubOK"},
    )
    db_session.flush()

    result = load_enabled_detectors(db_session)
    assert "VIOLENCE" not in result.detectors
    assert "UNKNOWN_PERSON" in result.detectors
    assert isinstance(result.detectors["UNKNOWN_PERSON"], _StubOK)


def test_load_records_errors_per_row(db_session: Session) -> None:
    db_session.execute(
        text(
            "UPDATE anomaly_detectors SET class_path = 'nonexistent.module.Bogus' "
            "WHERE alert_type = 'INTRUSION'"
        )
    )
    db_session.flush()
    result = load_enabled_detectors(db_session)
    assert "INTRUSION" not in result.detectors
    assert any(e.alert_type == "INTRUSION" for e in result.errors)


def test_load_parses_config_json(db_session: Session) -> None:
    db_session.execute(
        text(
            "UPDATE anomaly_detectors SET class_path = :cp, config_json = :cfg "
            "WHERE alert_type = 'UNKNOWN_PERSON'"
        ),
        {
            "cp": "tests.test_anomaly_registry._StubOK",
            "cfg": json.dumps({"foo": "bar"}),
        },
    )
    db_session.flush()
    result = load_enabled_detectors(db_session)
    assert result.detectors["UNKNOWN_PERSON"].config == {"foo": "bar"}


def test_load_malformed_config_json_records_error(db_session: Session) -> None:
    db_session.execute(
        text(
            "UPDATE anomaly_detectors SET class_path = :cp, config_json = '{ not json' "
            "WHERE alert_type = 'CROWD_DENSITY'"
        ),
        {"cp": "tests.test_anomaly_registry._StubOK"},
    )
    db_session.flush()
    result = load_enabled_detectors(db_session)
    assert "CROWD_DENSITY" not in result.detectors
    assert any("config_json" in e.reason for e in result.errors)


def test_load_returns_result_summary(db_session: Session) -> None:
    result = load_enabled_detectors(db_session)
    assert isinstance(result, RegistryLoadResult)
    assert isinstance(result.detectors, dict)
    assert isinstance(result.errors, list)
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_anomaly_registry.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `vms/anomaly/registry.py`**

```python
"""Detector registry: read anomaly_detectors rows, instantiate classes."""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from vms.anomaly.base import AnomalyDetector
from vms.db.models import AnomalyDetector as AnomalyDetectorRow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegistryLoadError:
    alert_type: str
    class_path: str
    reason: str


@dataclass(frozen=True)
class RegistryLoadResult:
    detectors: dict[str, AnomalyDetector] = field(default_factory=dict)
    errors: list[RegistryLoadError] = field(default_factory=list)


def _import_class(path: str) -> type:
    module_name, _, class_name = path.rpartition(".")
    if not module_name:
        raise ImportError(f"class_path missing module prefix: {path!r}")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)  # type: ignore[no-any-return]


def load_enabled_detectors(session: Session) -> RegistryLoadResult:
    """Read enabled anomaly_detectors rows, instantiate each, collect errors."""
    detectors: dict[str, AnomalyDetector] = {}
    errors: list[RegistryLoadError] = []

    rows = session.query(AnomalyDetectorRow).filter_by(is_enabled=True).all()
    for row in rows:
        try:
            config: dict[str, object] = {}
            if row.config_json is not None:
                try:
                    config = json.loads(row.config_json)
                except json.JSONDecodeError as exc:
                    errors.append(
                        RegistryLoadError(
                            alert_type=row.alert_type,
                            class_path=row.class_path,
                            reason=f"config_json parse error: {exc}",
                        )
                    )
                    continue
                if not isinstance(config, dict):
                    errors.append(
                        RegistryLoadError(
                            alert_type=row.alert_type,
                            class_path=row.class_path,
                            reason="config_json must be a JSON object",
                        )
                    )
                    continue

            cls = _import_class(row.class_path)
            if not issubclass(cls, AnomalyDetector):
                errors.append(
                    RegistryLoadError(
                        alert_type=row.alert_type,
                        class_path=row.class_path,
                        reason="class is not an AnomalyDetector subclass",
                    )
                )
                continue
            instance = cls(config)
            detectors[row.alert_type] = instance
            logger.info("loaded detector %s -> %s", row.alert_type, row.class_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                RegistryLoadError(
                    alert_type=row.alert_type,
                    class_path=row.class_path,
                    reason=f"{type(exc).__name__}: {exc}",
                )
            )

    return RegistryLoadResult(detectors=detectors, errors=errors)
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_anomaly_registry.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add vms/anomaly/registry.py tests/test_anomaly_registry.py
git commit -m "feat(anomaly): add detector registry with class_path loader and per-row error capture"
```

---

## Task 5: MaintenanceCalendar — TTL cache, cron parsing, suppression query

**Background:** Before any alert fires, `AlertFSM.process()` calls `MaintenanceCalendar.is_suppressed(camera_id, zone_id, alert_type, event_ts)`. The calendar refreshes from `maintenance_windows` every `maintenance_cache_ttl_s` seconds. ONE_TIME windows use `starts_at`/`ends_at`. RECURRING windows use `cron_expr` + `duration_minutes`. `suppress_alert_types` is NULL (suppress all) or a JSON array.

**Files:**
- Modify: `requirements.txt`
- Create: `vms/anomaly/maintenance.py`
- Create: `tests/test_anomaly_maintenance.py`

- [ ] **Step 1: Add `croniter` dependency**

In `requirements.txt`:

```
croniter==2.0.5
```

Install:

```powershell
pip install croniter==2.0.5
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_anomaly_maintenance.py`:

```python
"""Tests for MaintenanceCalendar."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from vms.anomaly.maintenance import MaintenanceCalendar
from vms.db.models import Camera, MaintenanceWindow, User, Zone


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_user(db: Session) -> int:
    u = User(username=f"mw_creator_{id(db)}", password_hash="x", role="admin", is_active=True)
    db.add(u)
    db.flush()
    return u.user_id


def test_one_time_window_suppresses_active_camera(db_session: Session) -> None:
    cid = Camera(name="C1", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cid)
    db_session.flush()
    uid = _seed_user(db_session)
    now = _now_naive()
    db_session.add(
        MaintenanceWindow(
            name="planned",
            scope_type="CAMERA",
            scope_id=cid.camera_id,
            schedule_type="ONE_TIME",
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=5),
            suppress_alert_types=None,
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()
    win = cal.is_suppressed(camera_id=cid.camera_id, zone_id=None,
                             alert_type="INTRUSION", event_ts=now)
    assert win is not None


def test_one_time_window_outside_range_not_suppressed(db_session: Session) -> None:
    cid = Camera(name="C2", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cid)
    db_session.flush()
    uid = _seed_user(db_session)
    now = _now_naive()
    db_session.add(
        MaintenanceWindow(
            name="past",
            scope_type="CAMERA",
            scope_id=cid.camera_id,
            schedule_type="ONE_TIME",
            starts_at=now - timedelta(hours=2),
            ends_at=now - timedelta(hours=1),
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()
    assert cal.is_suppressed(camera_id=cid.camera_id, zone_id=None,
                              alert_type="INTRUSION", event_ts=now) is None


def test_zone_scope_does_not_match_camera_scope(db_session: Session) -> None:
    z = Zone(name="Z1")
    db_session.add(z)
    db_session.flush()
    uid = _seed_user(db_session)
    now = _now_naive()
    db_session.add(
        MaintenanceWindow(
            name="zone-down",
            scope_type="ZONE",
            scope_id=z.zone_id,
            schedule_type="ONE_TIME",
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=5),
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()
    assert cal.is_suppressed(camera_id=999, zone_id=None,
                              alert_type="INTRUSION", event_ts=now) is None
    assert cal.is_suppressed(camera_id=None, zone_id=z.zone_id,
                              alert_type="INTRUSION", event_ts=now) is not None


def test_alert_type_filter_excludes_other_types(db_session: Session) -> None:
    cid = Camera(name="C3", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cid)
    db_session.flush()
    uid = _seed_user(db_session)
    now = _now_naive()
    db_session.add(
        MaintenanceWindow(
            name="only-violence-supp",
            scope_type="CAMERA",
            scope_id=cid.camera_id,
            schedule_type="ONE_TIME",
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=5),
            suppress_alert_types=json.dumps(["VIOLENCE"]),
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()
    assert cal.is_suppressed(camera_id=cid.camera_id, zone_id=None,
                              alert_type="VIOLENCE", event_ts=now) is not None
    assert cal.is_suppressed(camera_id=cid.camera_id, zone_id=None,
                              alert_type="INTRUSION", event_ts=now) is None


def test_recurring_window_matches_inside_cron_slot(db_session: Session) -> None:
    cid = Camera(name="C4", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cid)
    db_session.flush()
    uid = _seed_user(db_session)
    now = datetime(2026, 5, 16, 14, 5, 0)  # Saturday 14:05
    db_session.add(
        MaintenanceWindow(
            name="sat-2pm",
            scope_type="CAMERA",
            scope_id=cid.camera_id,
            schedule_type="RECURRING",
            cron_expr="0 14 * * 6",
            duration_minutes=30,
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()
    assert cal.is_suppressed(camera_id=cid.camera_id, zone_id=None,
                              alert_type="INTRUSION", event_ts=now) is not None


def test_recurring_outside_cron_slot_not_suppressed(db_session: Session) -> None:
    cid = Camera(name="C5", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cid)
    db_session.flush()
    uid = _seed_user(db_session)
    now = datetime(2026, 5, 17, 14, 5, 0)  # Sunday
    db_session.add(
        MaintenanceWindow(
            name="sat-2pm",
            scope_type="CAMERA",
            scope_id=cid.camera_id,
            schedule_type="RECURRING",
            cron_expr="0 14 * * 6",
            duration_minutes=30,
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()
    assert cal.is_suppressed(camera_id=cid.camera_id, zone_id=None,
                              alert_type="INTRUSION", event_ts=now) is None


def test_malformed_cron_skipped_logged(db_session: Session, caplog: pytest.LogCaptureFixture) -> None:
    cid = Camera(name="C6", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cid)
    db_session.flush()
    uid = _seed_user(db_session)
    db_session.add(
        MaintenanceWindow(
            name="bad-cron",
            scope_type="CAMERA",
            scope_id=cid.camera_id,
            schedule_type="RECURRING",
            cron_expr="not a cron",
            duration_minutes=15,
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()  # must not raise
    assert cal.is_suppressed(camera_id=cid.camera_id, zone_id=None,
                              alert_type="INTRUSION", event_ts=_now_naive()) is None


def test_cache_respects_ttl(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Calendar does not re-query DB inside TTL window."""
    cal = MaintenanceCalendar(session_factory=lambda: db_session, ttl_s=10)
    cal.refresh_now()
    call_count = {"n": 0}
    orig = db_session.query
    def spy(*a, **kw):
        call_count["n"] += 1
        return orig(*a, **kw)
    monkeypatch.setattr(db_session, "query", spy)
    # Within TTL: no DB call
    cal.is_suppressed(camera_id=1, zone_id=None, alert_type="X", event_ts=_now_naive())
    assert call_count["n"] == 0
```

- [ ] **Step 3: Run tests to verify they fail**

```powershell
pytest tests/test_anomaly_maintenance.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 4: Create `vms/anomaly/maintenance.py`**

```python
"""MaintenanceCalendar — TTL-cached suppression lookup."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from croniter import CroniterBadCronError, croniter
from sqlalchemy.orm import Session

from vms.config import get_settings
from vms.db.models import MaintenanceWindow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _CompiledWindow:
    window_id: int
    scope_type: str
    scope_id: int
    schedule_type: str
    starts_at: datetime | None
    ends_at: datetime | None
    cron_expr: str | None
    duration_minutes: int | None
    suppress_alert_types: tuple[str, ...] | None  # None = suppress all


class MaintenanceCalendar:
    """In-memory cache of active maintenance windows.

    Thread-safety: single writer (the refresh loop) + many readers. Pythons GIL
    plus the atomic list/dict swap in _replace_cache keeps reads consistent.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        ttl_s: int | None = None,
    ) -> None:
        self._sf = session_factory
        self._ttl_s = ttl_s if ttl_s is not None else get_settings().maintenance_cache_ttl_s
        self._windows: list[_CompiledWindow] = []
        self._expires_at: float = 0.0

    def invalidate(self) -> None:
        """Force the next is_suppressed() call to refresh from DB."""
        self._expires_at = 0.0

    def refresh_now(self) -> None:
        session = self._sf()
        rows = session.query(MaintenanceWindow).filter_by(is_active=True).all()
        compiled: list[_CompiledWindow] = []
        for r in rows:
            types: tuple[str, ...] | None = None
            if r.suppress_alert_types is not None:
                try:
                    parsed = json.loads(r.suppress_alert_types)
                    if isinstance(parsed, list):
                        types = tuple(str(t) for t in parsed)
                except json.JSONDecodeError:
                    logger.warning(
                        "maintenance_window %s: malformed suppress_alert_types JSON",
                        r.window_id,
                    )
                    continue
            compiled.append(
                _CompiledWindow(
                    window_id=r.window_id,
                    scope_type=r.scope_type,
                    scope_id=r.scope_id,
                    schedule_type=r.schedule_type,
                    starts_at=r.starts_at,
                    ends_at=r.ends_at,
                    cron_expr=r.cron_expr,
                    duration_minutes=r.duration_minutes,
                    suppress_alert_types=types,
                )
            )
        self._windows = compiled
        self._expires_at = time.monotonic() + self._ttl_s

    def _maybe_refresh(self) -> None:
        if time.monotonic() >= self._expires_at:
            self.refresh_now()

    def is_suppressed(
        self,
        *,
        camera_id: int | None,
        zone_id: int | None,
        alert_type: str,
        event_ts: datetime,
    ) -> int | None:
        """Return window_id of the matching active window, or None."""
        self._maybe_refresh()
        for w in self._windows:
            if w.scope_type == "CAMERA":
                if camera_id is None or w.scope_id != camera_id:
                    continue
            elif w.scope_type == "ZONE":
                if zone_id is None or w.scope_id != zone_id:
                    continue
            else:
                continue

            if w.suppress_alert_types is not None and alert_type not in w.suppress_alert_types:
                continue

            if not self._covers(w, event_ts):
                continue
            return w.window_id
        return None

    @staticmethod
    def _covers(w: _CompiledWindow, ts: datetime) -> bool:
        if w.schedule_type == "ONE_TIME":
            if w.starts_at is None or w.ends_at is None:
                return False
            return w.starts_at <= ts <= w.ends_at
        if w.schedule_type == "RECURRING":
            if w.cron_expr is None or w.duration_minutes is None:
                return False
            try:
                it = croniter(w.cron_expr, ts)
            except (CroniterBadCronError, ValueError):
                logger.warning("maintenance_window %s: invalid cron %r",
                               w.window_id, w.cron_expr)
                return False
            prev_fire: datetime = it.get_prev(datetime)  # type: ignore[no-untyped-call]
            end = prev_fire + timedelta(minutes=w.duration_minutes)
            return prev_fire <= ts <= end
        return False
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
pytest tests/test_anomaly_maintenance.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git add requirements.txt vms/anomaly/maintenance.py tests/test_anomaly_maintenance.py
git commit -m "feat(anomaly): add MaintenanceCalendar with TTL cache + cron + alert-type filter"
```

---

## Task 6: AlertFSM — sustain, cooldown, dedup, persistence, alerts stream publish

**Background:** The FSM is a per-process in-memory state machine that maps `dedup_key` -> sustain timer + cooldown timer + (optional) materialised `alert_id`. On every AnomalyEvent it goes through these states:

> **Requires Task 1 migration** (adds `dedup_key` UNIQUE column, `chk_alert_state` CHECK constraint, and `suppressed_by_window_id` FK to `alerts`). Run `alembic upgrade head` before running these tests or the FSM will silently lose dedup_key writes.

```
seen -> (continues until sustain_ms elapses) -> firing -> active
active -> (cooldown_ms after the last sighting) -> closed
```

A successful fire (a) checks `MaintenanceCalendar`; if suppressed, persists the alert with `state='suppressed'` and `suppressed_by_window_id` set, and **does not publish to the stream**; (b) otherwise inserts an `alerts` row, publishes `{alert_id, alert_type, ...}` to the `alerts` Redis Stream, and returns the new `alert_id`.

The DB is the source of truth: at startup, the FSM rebuilds active `dedup_key -> alert_id` from `SELECT alert_id, dedup_key FROM alerts WHERE state='active'`.

**Files:**
- Create: `vms/anomaly/streams.py`
- Create: `vms/anomaly/fsm.py`
- Create: `tests/test_anomaly_fsm.py`

- [ ] **Step 1: Write failing tests for the stream helper**

Create `tests/test_anomaly_fsm.py` (will be filled out further below, start with stream test):

```python
"""Tests for AlertFSM and the alerts stream publisher."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import redis.asyncio as aioredis
from sqlalchemy.orm import Session

from vms.anomaly.base import AnomalyEvent, FSMConfig, Severity
from vms.anomaly.fsm import AlertFSM, FSMDecision
from vms.anomaly.maintenance import MaintenanceCalendar
from vms.anomaly.streams import publish_alert_fired
from vms.db.models import Alert, Camera, MaintenanceWindow, User


def _utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ev(
    *, dedup: str = "k", ts: datetime | None = None,
    alert_type: str = "UNKNOWN_PERSON", camera_id: int = 1,
) -> AnomalyEvent:
    return AnomalyEvent(
        alert_type=alert_type,
        severity=Severity.HIGH,
        camera_id=camera_id,
        zone_id=None,
        global_track_id=uuid.uuid4(),
        person_id=None,
        event_ts=ts or _utc_naive(),
        dedup_key=dedup,
        payload={},
    )


@pytest.mark.asyncio
async def test_publish_alert_fired_writes_to_stream() -> None:
    from fakeredis.aioredis import FakeRedis
    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    msg_id = await publish_alert_fired(
        client,
        alert_id=42,
        alert_type="VIOLENCE",
        severity="CRITICAL",
        camera_id=7,
        zone_id=3,
        global_track_id=uuid.uuid4(),
        person_id=None,
        triggered_at=_utc_naive(),
    )
    assert msg_id
    raw = await client.xrange("alerts")
    assert len(raw) == 1
    _, fields = raw[0]
    body = json.loads(fields["payload"])
    assert body["alert_id"] == 42
    assert body["schema_version"] == "1"
```

Continue with FSM behaviour tests in `tests/test_anomaly_fsm.py`:

```python
def _seed_cam(db: Session, name: str = "FSMCam") -> int:
    c = Camera(name=name, rtsp_url="rtsp://x", capability_tier="FULL")
    db.add(c)
    db.flush()
    return c.camera_id


@pytest.mark.asyncio
async def test_first_event_below_sustain_does_not_fire(db_session: Session) -> None:
    cid = _seed_cam(db_session)
    cfg = FSMConfig(sustain_ms=500, cooldown_ms=60_000, dedup_window_ms=60_000)
    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis
    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)

    t0 = _utc_naive()
    dec = await fsm.process(_ev(dedup="k1", ts=t0, camera_id=cid), cfg)
    assert dec is FSMDecision.SUSTAINING


@pytest.mark.asyncio
async def test_sustained_event_fires_and_publishes(db_session: Session) -> None:
    cid = _seed_cam(db_session, name="FSMCam2")
    cfg = FSMConfig(sustain_ms=100, cooldown_ms=60_000, dedup_window_ms=60_000)
    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis
    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)

    t0 = _utc_naive()
    await fsm.process(_ev(dedup="k2", ts=t0, camera_id=cid), cfg)
    dec = await fsm.process(_ev(dedup="k2", ts=t0 + timedelta(milliseconds=150), camera_id=cid), cfg)
    assert dec is FSMDecision.FIRED

    db_session.flush()
    rows = db_session.query(Alert).filter_by(dedup_key="k2").all()
    assert len(rows) == 1
    assert rows[0].state == "active"

    raw = await client.xrange("alerts")
    assert len(raw) == 1


@pytest.mark.asyncio
async def test_duplicate_event_during_active_alert_is_deduped(db_session: Session) -> None:
    cid = _seed_cam(db_session, name="FSMCam3")
    cfg = FSMConfig(sustain_ms=0, cooldown_ms=60_000, dedup_window_ms=60_000)
    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis
    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)

    t0 = _utc_naive()
    await fsm.process(_ev(dedup="k3", ts=t0, camera_id=cid), cfg)
    db_session.flush()
    dec = await fsm.process(_ev(dedup="k3", ts=t0 + timedelta(seconds=2), camera_id=cid), cfg)
    assert dec is FSMDecision.DEDUPED
    assert db_session.query(Alert).filter_by(dedup_key="k3").count() == 1


@pytest.mark.asyncio
async def test_after_cooldown_a_new_alert_can_fire(db_session: Session) -> None:
    cid = _seed_cam(db_session, name="FSMCam4")
    cfg = FSMConfig(sustain_ms=0, cooldown_ms=1_000, dedup_window_ms=1_000)
    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis
    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)

    t0 = _utc_naive()
    await fsm.process(_ev(dedup="k4", ts=t0, camera_id=cid), cfg)
    db_session.flush()
    # mark first alert resolved so dedup window cleans up
    db_session.query(Alert).filter_by(dedup_key="k4").update(
        {"state": "resolved", "resolved_at": t0 + timedelta(seconds=2)}
    )
    db_session.flush()
    fsm.evict_closed(now=t0 + timedelta(seconds=5))

    dec = await fsm.process(_ev(dedup="k4", ts=t0 + timedelta(seconds=10), camera_id=cid), cfg)
    assert dec is FSMDecision.FIRED
    assert db_session.query(Alert).filter_by(dedup_key="k4").count() == 2


@pytest.mark.asyncio
async def test_maintenance_suppression_writes_suppressed_state(db_session: Session) -> None:
    cid = _seed_cam(db_session, name="FSMCam5")
    u = User(username="fsm_op", password_hash="x", role="admin", is_active=True)
    db_session.add(u)
    db_session.flush()
    now = _utc_naive()
    db_session.add(
        MaintenanceWindow(
            name="window",
            scope_type="CAMERA",
            scope_id=cid,
            schedule_type="ONE_TIME",
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(minutes=10),
            created_by=u.user_id,
        )
    )
    db_session.flush()

    cfg = FSMConfig(sustain_ms=0, cooldown_ms=60_000, dedup_window_ms=60_000)
    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis
    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)

    dec = await fsm.process(_ev(dedup="k5", ts=now, camera_id=cid), cfg)
    assert dec is FSMDecision.SUPPRESSED
    db_session.flush()
    row = db_session.query(Alert).filter_by(dedup_key="k5").one()
    assert row.state == "suppressed"
    assert row.suppressed_by_window_id is not None
    raw = await client.xrange("alerts")
    assert len(raw) == 0  # not published


@pytest.mark.asyncio
async def test_rebuild_active_from_db_on_construct(db_session: Session) -> None:
    cid = _seed_cam(db_session, name="FSMCam6")
    db_session.add(
        Alert(
            alert_type="UNKNOWN_PERSON",
            severity="HIGH",
            state="active",
            camera_id=cid,
            triggered_at=_utc_naive(),
            dedup_key="k6",
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis
    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)
    fsm.rebuild_from_db()
    cfg = FSMConfig(sustain_ms=0, cooldown_ms=60_000, dedup_window_ms=60_000)
    dec = await fsm.process(_ev(dedup="k6", ts=_utc_naive(), camera_id=cid), cfg)
    assert dec is FSMDecision.DEDUPED


@pytest.mark.asyncio
async def test_evict_closed_removes_resolved_entry_and_allows_new_fire(
    db_session: Session,
) -> None:
    cid = _seed_cam(db_session, name="FSMCam7")
    cfg = FSMConfig(sustain_ms=0, cooldown_ms=60_000, dedup_window_ms=60_000)
    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis
    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)

    t0 = _utc_naive()
    await fsm.process(_ev(dedup="k7", ts=t0, camera_id=cid), cfg)
    db_session.flush()
    db_session.query(Alert).filter_by(dedup_key="k7").update(
        {"state": "resolved", "resolved_at": t0}
    )
    db_session.flush()

    evicted = fsm.evict_closed(now=t0)
    assert evicted == 1, "resolved alert entry must be evicted"

    dec = await fsm.process(_ev(dedup="k7", ts=t0, camera_id=cid), cfg)
    assert dec is FSMDecision.FIRED, "after eviction same key must fire again"
    assert db_session.query(Alert).filter_by(dedup_key="k7").count() == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_anomaly_fsm.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `vms/anomaly/streams.py`**

```python
"""Stream contracts for anomaly subsystem.

Stream: alerts
Schema (v1):
  payload (JSON): {
    alert_id, alert_type, severity, camera_id, zone_id,
    global_track_id, person_id, triggered_at (ISO8601 UTC),
    schema_version: "1"
  }
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import redis.asyncio as aioredis

from vms.config import get_settings
from vms.redis_client import stream_add

_STREAM = "alerts"


async def publish_alert_fired(
    client: aioredis.Redis,
    *,
    alert_id: int,
    alert_type: str,
    severity: str,
    camera_id: int,
    zone_id: int | None,
    global_track_id: uuid.UUID | None,
    person_id: int | None,
    triggered_at: datetime,
) -> str:
    payload = {
        "alert_id": alert_id,
        "alert_type": alert_type,
        "severity": severity,
        "camera_id": camera_id,
        "zone_id": zone_id,
        "global_track_id": str(global_track_id) if global_track_id else None,
        "person_id": person_id,
        "triggered_at": triggered_at.isoformat() + "Z",
        "schema_version": "1",
    }
    return await stream_add(
        client,
        _STREAM,
        {"payload": json.dumps(payload)},
        maxlen=get_settings().alerts_stream_maxlen,
    )
```

- [ ] **Step 4: Create `vms/anomaly/fsm.py`**

```python
"""AlertFSM — sustain/cooldown/dedup state machine + alerts persistence.

Memory state per dedup_key:
  - first_seen_ts: first event timestamp in the current sustain window
  - last_seen_ts: most recent event timestamp
  - alert_id: int if an active alert exists, else None
"""

from __future__ import annotations

import enum
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import redis.asyncio as aioredis
from sqlalchemy.orm import Session

from vms.anomaly.base import AnomalyEvent, FSMConfig
from vms.anomaly.maintenance import MaintenanceCalendar
from vms.anomaly.streams import publish_alert_fired
from vms.db.models import Alert

logger = logging.getLogger(__name__)


class FSMDecision(str, enum.Enum):
    SUSTAINING = "SUSTAINING"
    FIRED = "FIRED"
    DEDUPED = "DEDUPED"
    SUPPRESSED = "SUPPRESSED"


@dataclass
class _Entry:
    first_seen_ts: datetime
    last_seen_ts: datetime
    alert_id: int | None


class AlertFSM:
    def __init__(
        self,
        *,
        redis_client: aioredis.Redis,
        calendar: MaintenanceCalendar,
        session_factory: Callable[[], Session],
    ) -> None:
        self._redis = redis_client
        self._cal = calendar
        self._sf = session_factory
        self._entries: dict[str, _Entry] = {}

    def rebuild_from_db(self) -> None:
        """Reload active alerts so dedup survives a process restart."""
        session = self._sf()
        rows = (
            session.query(Alert)
            .filter(Alert.state == "active", Alert.dedup_key.is_not(None))
            .all()
        )
        self._entries.clear()
        for r in rows:
            assert r.dedup_key is not None
            self._entries[r.dedup_key] = _Entry(
                first_seen_ts=r.triggered_at,
                last_seen_ts=r.triggered_at,
                alert_id=r.alert_id,
            )

    def evict_closed(self, now: datetime) -> int:
        """Drop entries whose backing alert is no longer active. Returns evicted count."""
        if not self._entries:
            return 0
        session = self._sf()
        active_ids = {
            aid
            for (aid,) in session.query(Alert.alert_id).filter(Alert.state == "active").all()
        }
        stale = [k for k, e in self._entries.items() if e.alert_id not in active_ids]
        for k in stale:
            del self._entries[k]
        return len(stale)

    async def process(self, ev: AnomalyEvent, cfg: FSMConfig) -> FSMDecision:
        # Dedup is lifetime-of-alert: same dedup_key returns DEDUPED until the
        # alert is operator-resolved and evict_closed() clears the entry.
        # cfg.cooldown_ms / cfg.dedup_window_ms are reserved for a future
        # time-based auto-reset path; they are not enforced here.
        entry = self._entries.get(ev.dedup_key)

        if entry is None:
            self._entries[ev.dedup_key] = _Entry(
                first_seen_ts=ev.event_ts, last_seen_ts=ev.event_ts, alert_id=None,
            )
            entry = self._entries[ev.dedup_key]
            if cfg.sustain_ms == 0:
                return await self._fire(ev, entry)
            return FSMDecision.SUSTAINING

        entry.last_seen_ts = ev.event_ts

        if entry.alert_id is not None:
            return FSMDecision.DEDUPED

        elapsed_ms = int((ev.event_ts - entry.first_seen_ts).total_seconds() * 1000)
        if elapsed_ms < cfg.sustain_ms:
            return FSMDecision.SUSTAINING

        return await self._fire(ev, entry)

    async def _fire(self, ev: AnomalyEvent, entry: _Entry) -> FSMDecision:
        session = self._sf()
        window_id = self._cal.is_suppressed(
            camera_id=ev.camera_id, zone_id=ev.zone_id,
            alert_type=ev.alert_type, event_ts=ev.event_ts,
        )

        row = Alert(
            alert_type=ev.alert_type,
            severity=ev.severity.value,
            state="suppressed" if window_id is not None else "active",
            camera_id=ev.camera_id,
            zone_id=ev.zone_id,
            global_track_id=ev.global_track_id,
            person_id=ev.person_id,
            triggered_at=ev.event_ts,
            suppressed_by_window_id=window_id,
            dedup_key=ev.dedup_key,
        )
        session.add(row)
        session.flush()
        entry.alert_id = row.alert_id

        if window_id is not None:
            logger.info(
                "alert suppressed alert_id=%s dedup=%s window=%s",
                row.alert_id, ev.dedup_key, window_id,
            )
            return FSMDecision.SUPPRESSED

        await publish_alert_fired(
            self._redis,
            alert_id=row.alert_id,
            alert_type=ev.alert_type,
            severity=ev.severity.value,
            camera_id=ev.camera_id,
            zone_id=ev.zone_id,
            global_track_id=ev.global_track_id,
            person_id=ev.person_id,
            triggered_at=ev.event_ts,
        )
        logger.info(
            "alert fired alert_id=%s dedup=%s type=%s",
            row.alert_id, ev.dedup_key, ev.alert_type,
        )
        return FSMDecision.FIRED
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
pytest tests/test_anomaly_fsm.py -v
```

Expected: all PASS.

- [ ] **Step 6: Run full suite**

```powershell
pytest -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```powershell
git add vms/anomaly/streams.py vms/anomaly/fsm.py tests/test_anomaly_fsm.py
git commit -m "feat(anomaly): add AlertFSM with sustain/cooldown/dedup + maintenance suppression"
```

---

## Task 7: UNKNOWN_PERSON detector

**Background:** Fires when a tracklet has a `global_track_id` (we know it's a person) but `person_id is None` (we don't know who). FSM: sustain 500 ms, cooldown 60 s/zone. Dedup key includes zone so the same unknown person re-entering a different zone fires a new alert.

**Files:**
- Create: `vms/anomaly/detectors/__init__.py`
- Create: `vms/anomaly/detectors/unknown_person.py`
- Create: `tests/test_anomaly_unknown_person.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_anomaly_unknown_person.py`:

```python
"""Tests for UnknownPersonDetector."""
from __future__ import annotations

import uuid

import pytest

from vms.anomaly.base import DetectorContext, Severity
from vms.anomaly.detectors.unknown_person import UnknownPersonDetector
from vms.inference.messages import DetectionFrame, Tracklet


def _ctx_with_tracklet(
    *, person_id_known: bool, zone_id: int | None = 1,
) -> tuple[DetectorContext, uuid.UUID]:
    gid = uuid.uuid4()
    tl = Tracklet(local_track_id=1, camera_id=4, bbox=(0, 0, 10, 10), confidence=0.9)
    frame = DetectionFrame(
        camera_id=4, seq_id=1, timestamp_ms=1_700_000_000_000,
        tracklets=(tl,), face_embeddings=(),
    )
    track_zones = {gid: zone_id} if zone_id is not None else {}
    ctx = DetectorContext(
        frame=frame, zone_lookup={}, active_track_zones=track_zones,
        head_count={}, violence_score=None,
    )
    return ctx, gid


def test_fires_when_tracklet_has_no_person_id() -> None:
    det = UnknownPersonDetector({})
    ctx, gid = _ctx_with_tracklet(person_id_known=False)
    det._gid_for_tracklet = lambda tl, ctx: gid  # type: ignore[method-assign]
    det._person_id_for = lambda gid, ctx: None    # type: ignore[method-assign]
    assert det.should_run(ctx) is True
    ev = det.evaluate(ctx)
    assert ev is not None
    assert ev.alert_type == "UNKNOWN_PERSON"
    assert ev.severity is Severity.HIGH
    assert ev.dedup_key.startswith("UNKNOWN_PERSON:")
    assert ev.global_track_id == gid


def test_does_not_fire_when_person_known() -> None:
    det = UnknownPersonDetector({})
    ctx, gid = _ctx_with_tracklet(person_id_known=True)
    det._gid_for_tracklet = lambda tl, ctx: gid  # type: ignore[method-assign]
    det._person_id_for = lambda gid, ctx: 7      # type: ignore[method-assign]
    assert det.evaluate(ctx) is None


def test_should_run_short_circuits_when_no_tracklets() -> None:
    det = UnknownPersonDetector({})
    frame = DetectionFrame(
        camera_id=4, seq_id=1, timestamp_ms=1_700_000_000_000,
        tracklets=(), face_embeddings=(),
    )
    ctx = DetectorContext(
        frame=frame, zone_lookup={}, active_track_zones={},
        head_count={}, violence_score=None,
    )
    assert det.should_run(ctx) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_anomaly_unknown_person.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `vms/anomaly/detectors/__init__.py`**

```python
"""Concrete anomaly detectors."""
```

- [ ] **Step 4: Create `vms/anomaly/detectors/unknown_person.py`**

```python
"""UNKNOWN_PERSON detector.

Fires on tracklets the IdentityEngine has flagged as belonging to a known
global_track_id but not yet mapped to a person_id (no FAISS match).
The orchestrator populates DetectorContext.active_track_zones for every
tracklet it could resolve to a gid; un-resolved tracklets are skipped here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    SeamProvider,
    Severity,
)
from vms.inference.messages import Tracklet


class UnknownPersonDetector(AnomalyDetector, SeamProvider):
    alert_type = "UNKNOWN_PERSON"
    severity = Severity.HIGH
    requires_models: tuple[str, ...] = ("face_embedder",)
    requires_tier: tuple[str, ...] = ("FULL",)

    def should_run(self, ctx: DetectorContext) -> bool:
        return len(ctx.frame.tracklets) > 0

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        for tl in ctx.frame.tracklets:
            gid = self._gid_for_tracklet(tl, ctx)
            if gid is None:
                continue
            pid = self._person_id_for(gid, ctx)
            if pid is not None:
                continue
            zone_id = ctx.active_track_zones.get(gid)
            return AnomalyEvent(
                alert_type=self.alert_type,
                severity=self.severity,
                camera_id=ctx.frame.camera_id,
                zone_id=zone_id,
                global_track_id=gid,
                person_id=None,
                event_ts=datetime.fromtimestamp(
                    ctx.frame.timestamp_ms / 1000.0, tz=timezone.utc
                ).replace(tzinfo=None),
                dedup_key=f"UNKNOWN_PERSON:cam={ctx.frame.camera_id}:zone={zone_id}",
                payload={"local_track_id": tl.local_track_id},
            )
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=500, cooldown_ms=60_000, dedup_window_ms=60_000)

    def _gid_for_tracklet(
        self, tl: Tracklet, ctx: DetectorContext
    ) -> uuid.UUID | None:
        return None  # orchestrator injects real lookup via _bind_seams
        return None

    def _person_id_for(
        self, gid: uuid.UUID, ctx: DetectorContext  # noqa: ARG002
    ) -> int | None:
        return None
```

> **Note:** the orchestrator (Task 14) replaces `_gid_for_tracklet` and `_person_id_for` with bound helpers that consult the IdentityEngine via `_bind_seams`. They are exposed as methods so tests can monkey-patch them. The defaults return `None` (safe no-op); a detector running without seam injection silently emits no events rather than returning the wrong gid.

- [ ] **Step 5: Run tests to verify they pass**

```powershell
pytest tests/test_anomaly_unknown_person.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git add vms/anomaly/detectors/__init__.py vms/anomaly/detectors/unknown_person.py tests/test_anomaly_unknown_person.py
git commit -m "feat(anomaly): add UnknownPersonDetector"
```

---

## Task 8: PERSON_LOST detector

**Background:** Fires when a previously-active `global_track_id` has not been seen for `>30 s` on **any** camera. The orchestrator passes the IdentityEngine's registry into `DetectorContext.payload` so this detector can check `last_seen_ms`. FSM: sustain 0 ms (we already waited 30 s), cooldown 120 s.

Because PERSON_LOST is a per-`gid` rule (not per-frame), it runs once per evaluation cycle on a synthetic frame. The orchestrator emits a synthetic frame every `head_count_emit_interval_s` (1 s) with `tracklets=()`; PERSON_LOST iterates over the gids from `ctx.active_track_zones`.

**Files:**
- Create: `vms/anomaly/detectors/person_lost.py`
- Create: `tests/test_anomaly_person_lost.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_anomaly_person_lost.py`:

```python
"""Tests for PersonLostDetector."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import pytest

from vms.anomaly.base import DetectorContext, Severity
from vms.anomaly.detectors.person_lost import PersonLostDetector
from vms.inference.messages import DetectionFrame


def _ctx(last_seen: dict[uuid.UUID, int]) -> DetectorContext:
    frame = DetectionFrame(
        camera_id=0, seq_id=1, timestamp_ms=int(time.time() * 1000),
        tracklets=(), face_embeddings=(),
    )
    return DetectorContext(
        frame=frame, zone_lookup={}, active_track_zones={g: 1 for g in last_seen},
        head_count={}, violence_score=None,
    ).__class__(  # rebuild with attached payload via dict trick
        frame=frame, zone_lookup={}, active_track_zones={g: 1 for g in last_seen},
        head_count={}, violence_score=None,
    )


def test_fires_for_track_unseen_longer_than_threshold() -> None:
    det = PersonLostDetector({"lost_after_s": 30})
    gid = uuid.uuid4()
    now_ms = int(time.time() * 1000)
    det._registry_last_seen = lambda ctx: {gid: now_ms - 31_000}  # type: ignore[method-assign]
    ev = det.evaluate(_ctx({gid: now_ms - 31_000}))
    assert ev is not None
    assert ev.alert_type == "PERSON_LOST"
    assert ev.global_track_id == gid


def test_does_not_fire_for_fresh_track() -> None:
    det = PersonLostDetector({"lost_after_s": 30})
    gid = uuid.uuid4()
    now_ms = int(time.time() * 1000)
    det._registry_last_seen = lambda ctx: {gid: now_ms - 5_000}  # type: ignore[method-assign]
    assert det.evaluate(_ctx({gid: now_ms - 5_000})) is None


def test_should_run_always_true() -> None:
    det = PersonLostDetector({})
    frame = DetectionFrame(
        camera_id=0, seq_id=1, timestamp_ms=1, tracklets=(), face_embeddings=(),
    )
    ctx = DetectorContext(
        frame=frame, zone_lookup={}, active_track_zones={},
        head_count={}, violence_score=None,
    )
    assert det.should_run(ctx) is True
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_anomaly_person_lost.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `vms/anomaly/detectors/person_lost.py`**

```python
"""PERSON_LOST detector.

The orchestrator injects the IdentityEngine.registry snapshot via the
_registry_last_seen() seam (overridden at wiring time). For unit tests,
the seam is monkey-patched.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    SeamProvider,
    Severity,
)


class PersonLostDetector(AnomalyDetector, SeamProvider):
    alert_type = "PERSON_LOST"
    severity = Severity.MEDIUM
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL",)

    def __init__(self, config: dict[str, object]) -> None:
        super().__init__(config)
        self._lost_after_s = int(config.get("lost_after_s", 30) or 30)

    def should_run(self, ctx: DetectorContext) -> bool:
        return True

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        now_ms = int(time.time() * 1000)
        last_seen = self._registry_last_seen(ctx)
        threshold_ms = self._lost_after_s * 1000
        for gid, last_ms in last_seen.items():
            if now_ms - last_ms > threshold_ms:
                return AnomalyEvent(
                    alert_type=self.alert_type,
                    severity=self.severity,
                    camera_id=ctx.frame.camera_id,
                    zone_id=ctx.active_track_zones.get(gid),
                    global_track_id=gid,
                    person_id=None,
                    event_ts=datetime.now(timezone.utc).replace(tzinfo=None),
                    dedup_key=f"PERSON_LOST:gid={gid}",
                    payload={"lost_for_s": (now_ms - last_ms) // 1000},
                )
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=0, cooldown_ms=120_000, dedup_window_ms=120_000)

    def _registry_last_seen(
        self, ctx: DetectorContext  # noqa: ARG002
    ) -> dict[uuid.UUID, int]:
        return {}
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_anomaly_person_lost.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add vms/anomaly/detectors/person_lost.py tests/test_anomaly_person_lost.py
git commit -m "feat(anomaly): add PersonLostDetector"
```

---

## Task 9: CROWD_DENSITY detector

**Background:** Fires when `head_count[zone_id] > zone.max_capacity`. Reads `ctx.head_count` (populated by orchestrator from `HeadCountAggregator`) and `ctx.zone_lookup` for `max_capacity`. FSM: sustain 10 s, cooldown 300 s/zone.

**Files:**
- Create: `vms/anomaly/detectors/crowd_density.py`
- Create: `tests/test_anomaly_crowd_density.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_anomaly_crowd_density.py`:

```python
"""Tests for CrowdDensityDetector."""
from __future__ import annotations

from vms.anomaly.base import DetectorContext, Severity, ZoneLookup
from vms.anomaly.detectors.crowd_density import CrowdDensityDetector
from vms.inference.messages import DetectionFrame


def _zone(zid: int, cap: int | None) -> ZoneLookup:
    return ZoneLookup(
        zone_id=zid, name=f"Z{zid}", is_restricted=False,
        max_capacity=cap, allowed_hours=None,
        loiter_threshold_s=180, polygon_json=None,
    )


def _ctx(head_count: dict[int, int], zones: dict[int, ZoneLookup]) -> DetectorContext:
    frame = DetectionFrame(
        camera_id=1, seq_id=1, timestamp_ms=1_700_000_000_000,
        tracklets=(), face_embeddings=(),
    )
    return DetectorContext(
        frame=frame, zone_lookup=zones, active_track_zones={},
        head_count=head_count, violence_score=None,
    )


def test_fires_when_count_exceeds_max_capacity() -> None:
    det = CrowdDensityDetector({})
    ctx = _ctx({3: 12}, {3: _zone(3, 10)})
    ev = det.evaluate(ctx)
    assert ev is not None
    assert ev.alert_type == "CROWD_DENSITY"
    assert ev.severity is Severity.MEDIUM
    assert ev.zone_id == 3
    assert ev.payload["count"] == 12
    assert ev.payload["max_capacity"] == 10
    assert ev.dedup_key == "CROWD_DENSITY:zone=3"


def test_does_not_fire_at_threshold() -> None:
    det = CrowdDensityDetector({})
    ctx = _ctx({3: 10}, {3: _zone(3, 10)})
    assert det.evaluate(ctx) is None


def test_skips_zones_with_no_max_capacity() -> None:
    det = CrowdDensityDetector({})
    ctx = _ctx({3: 100}, {3: _zone(3, None)})
    assert det.evaluate(ctx) is None


def test_should_run_skips_when_head_count_empty() -> None:
    det = CrowdDensityDetector({})
    ctx = _ctx({}, {})
    assert det.should_run(ctx) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_anomaly_crowd_density.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `vms/anomaly/detectors/crowd_density.py`**

```python
"""CROWD_DENSITY detector. Reads ctx.head_count + ctx.zone_lookup."""

from __future__ import annotations

from datetime import datetime, timezone

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    Severity,
)


class CrowdDensityDetector(AnomalyDetector):
    alert_type = "CROWD_DENSITY"
    severity = Severity.MEDIUM
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL", "MID")

    def should_run(self, ctx: DetectorContext) -> bool:
        return bool(ctx.head_count)

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        for zone_id, count in ctx.head_count.items():
            z = ctx.zone_lookup.get(zone_id)
            if z is None or z.max_capacity is None:
                continue
            if count > z.max_capacity:
                return AnomalyEvent(
                    alert_type=self.alert_type,
                    severity=self.severity,
                    camera_id=ctx.frame.camera_id,
                    zone_id=zone_id,
                    global_track_id=None,
                    person_id=None,
                    event_ts=datetime.fromtimestamp(
                        ctx.frame.timestamp_ms / 1000.0, tz=timezone.utc
                    ).replace(tzinfo=None),
                    dedup_key=f"CROWD_DENSITY:zone={zone_id}",
                    payload={"count": count, "max_capacity": z.max_capacity},
                )
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=10_000, cooldown_ms=300_000, dedup_window_ms=300_000)
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_anomaly_crowd_density.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add vms/anomaly/detectors/crowd_density.py tests/test_anomaly_crowd_density.py
git commit -m "feat(anomaly): add CrowdDensityDetector"
```

---

## Task 10: INTRUSION detector

**Background:** Fires when a person enters a `Zone.is_restricted=True` zone outside that zone's `allowed_hours`. `allowed_hours` JSON example: `[{"days":[1,2,3,4,5],"start":"08:00","end":"18:00"}]`. The detector parses this once per zone and caches the parsed structure. Days follow ISO weekday (1=Mon, 7=Sun).

If `allowed_hours` is NULL on a restricted zone, **any** entry triggers INTRUSION (zone is always off-limits). FSM: sustain 2 s, cooldown 60 s/zone, severity CRITICAL.

**Files:**
- Create: `vms/anomaly/detectors/intrusion.py`
- Create: `tests/test_anomaly_intrusion.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_anomaly_intrusion.py`:

```python
"""Tests for IntrusionDetector."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from vms.anomaly.base import DetectorContext, Severity, ZoneLookup
from vms.anomaly.detectors.intrusion import IntrusionDetector
from vms.inference.messages import DetectionFrame


def _zone(zid: int, allowed: list[dict[str, object]] | None,
          restricted: bool = True) -> ZoneLookup:
    return ZoneLookup(
        zone_id=zid, name=f"Z{zid}", is_restricted=restricted,
        max_capacity=None,
        allowed_hours=json.dumps(allowed) if allowed is not None else None,
        loiter_threshold_s=180, polygon_json=None,
    )


def _ctx(track_zones: dict[uuid.UUID, int], zones: dict[int, ZoneLookup],
         when: datetime) -> DetectorContext:
    ts_ms = int(when.timestamp() * 1000)
    frame = DetectionFrame(
        camera_id=1, seq_id=1, timestamp_ms=ts_ms,
        tracklets=(), face_embeddings=(),
    )
    return DetectorContext(
        frame=frame, zone_lookup=zones, active_track_zones=track_zones,
        head_count={}, violence_score=None,
    )


def test_fires_outside_allowed_hours() -> None:
    det = IntrusionDetector({})
    gid = uuid.uuid4()
    z = _zone(5, [{"days": [1, 2, 3, 4, 5], "start": "08:00", "end": "18:00"}])
    when = datetime(2026, 5, 16, 22, 30)  # Saturday 22:30
    ev = det.evaluate(_ctx({gid: 5}, {5: z}, when))
    assert ev is not None
    assert ev.severity is Severity.CRITICAL
    assert ev.zone_id == 5


def test_does_not_fire_inside_allowed_hours() -> None:
    det = IntrusionDetector({})
    gid = uuid.uuid4()
    z = _zone(5, [{"days": [1, 2, 3, 4, 5], "start": "08:00", "end": "18:00"}])
    when = datetime(2026, 5, 18, 10, 30)  # Monday 10:30
    assert det.evaluate(_ctx({gid: 5}, {5: z}, when)) is None


def test_fires_always_when_no_allowed_hours() -> None:
    det = IntrusionDetector({})
    gid = uuid.uuid4()
    z = _zone(5, None)
    when = datetime(2026, 5, 18, 10, 30)
    assert det.evaluate(_ctx({gid: 5}, {5: z}, when)) is not None


def test_skips_unrestricted_zones() -> None:
    det = IntrusionDetector({})
    gid = uuid.uuid4()
    z = _zone(5, None, restricted=False)
    when = datetime(2026, 5, 18, 10, 30)
    assert det.evaluate(_ctx({gid: 5}, {5: z}, when)) is None


def test_should_run_short_circuits_when_no_active_tracks() -> None:
    det = IntrusionDetector({})
    when = datetime(2026, 5, 18, 10, 30)
    assert det.should_run(_ctx({}, {}, when)) is False


def test_malformed_allowed_hours_treated_as_always_restricted() -> None:
    det = IntrusionDetector({})
    gid = uuid.uuid4()
    z = ZoneLookup(
        zone_id=5, name="Z5", is_restricted=True, max_capacity=None,
        allowed_hours="not valid {{", loiter_threshold_s=180, polygon_json=None,
    )
    when = datetime(2026, 5, 18, 10, 30)
    assert det.evaluate(_ctx({gid: 5}, {5: z}, when)) is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_anomaly_intrusion.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `vms/anomaly/detectors/intrusion.py`**

```python
"""INTRUSION detector — restricted zone outside allowed_hours."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, time, timezone

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    Severity,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _AllowedSlot:
    days: frozenset[int]
    start: time
    end: time


def _parse_allowed_hours(raw: str | None) -> list[_AllowedSlot] | None:
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return None
        out: list[_AllowedSlot] = []
        for item in parsed:
            days = frozenset(int(d) for d in item["days"])
            s_h, s_m = item["start"].split(":")
            e_h, e_m = item["end"].split(":")
            out.append(
                _AllowedSlot(
                    days=days,
                    start=time(int(s_h), int(s_m)),
                    end=time(int(e_h), int(e_m)),
                )
            )
        return out
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None


def _slot_covers(slot: _AllowedSlot, when: datetime) -> bool:
    if when.isoweekday() not in slot.days:
        return False
    t = when.time()
    return slot.start <= t <= slot.end


class IntrusionDetector(AnomalyDetector):
    alert_type = "INTRUSION"
    severity = Severity.CRITICAL
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL", "MID", "LOW")

    def __init__(self, config: dict[str, object]) -> None:
        super().__init__(config)
        self._slot_cache: dict[int, list[_AllowedSlot] | None] = {}

    def should_run(self, ctx: DetectorContext) -> bool:
        return len(ctx.active_track_zones) > 0

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        when = datetime.fromtimestamp(
            ctx.frame.timestamp_ms / 1000.0, tz=timezone.utc
        ).replace(tzinfo=None)

        for gid, zone_id in ctx.active_track_zones.items():
            z = ctx.zone_lookup.get(zone_id)
            if z is None or not z.is_restricted:
                continue
            slots = self._slots_for(zone_id, z.allowed_hours)
            if slots is None:
                allowed = False
            else:
                allowed = any(_slot_covers(s, when) for s in slots)
            if not allowed:
                return AnomalyEvent(
                    alert_type=self.alert_type,
                    severity=self.severity,
                    camera_id=ctx.frame.camera_id,
                    zone_id=zone_id,
                    global_track_id=gid,
                    person_id=None,
                    event_ts=when,
                    dedup_key=f"INTRUSION:zone={zone_id}:gid={gid}",
                    payload={},
                )
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=2_000, cooldown_ms=60_000, dedup_window_ms=60_000)

    def _slots_for(
        self, zone_id: int, raw: str | None
    ) -> list[_AllowedSlot] | None:
        if zone_id in self._slot_cache:
            return self._slot_cache[zone_id]
        slots = _parse_allowed_hours(raw)
        self._slot_cache[zone_id] = slots
        return slots
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_anomaly_intrusion.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add vms/anomaly/detectors/intrusion.py tests/test_anomaly_intrusion.py
git commit -m "feat(anomaly): add IntrusionDetector with allowed_hours parsing"
```

---

## Task 11: LOITERING detector

**Background:** Fires when a single tracklet has been inside one zone continuously for longer than `zone.loiter_threshold_s` (default 180 s). The detector reads `ctx.payload` extras for "entered_at per gid" — the orchestrator builds this from open `zone_presence` rows. FSM: sustain 0 (the dwell *is* the sustain), cooldown 600 s/zone, severity LOW.

**Files:**
- Create: `vms/anomaly/detectors/loitering.py`
- Create: `tests/test_anomaly_loitering.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_anomaly_loitering.py`:

```python
"""Tests for LoiteringDetector."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from vms.anomaly.base import DetectorContext, ZoneLookup
from vms.anomaly.detectors.loitering import LoiteringDetector
from vms.inference.messages import DetectionFrame


def _zone(zid: int, thresh: int = 180) -> ZoneLookup:
    return ZoneLookup(
        zone_id=zid, name=f"Z{zid}", is_restricted=False,
        max_capacity=None, allowed_hours=None,
        loiter_threshold_s=thresh, polygon_json=None,
    )


def _ctx(track_zones: dict[uuid.UUID, int], zones: dict[int, ZoneLookup],
         when: datetime) -> DetectorContext:
    ts_ms = int(when.timestamp() * 1000)
    frame = DetectionFrame(
        camera_id=1, seq_id=1, timestamp_ms=ts_ms,
        tracklets=(), face_embeddings=(),
    )
    return DetectorContext(
        frame=frame, zone_lookup=zones, active_track_zones=track_zones,
        head_count={}, violence_score=None,
    )


def test_fires_when_dwell_exceeds_threshold() -> None:
    det = LoiteringDetector({})
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    entered = now - timedelta(seconds=200)
    det._entered_at = lambda gid, zone_id, ctx: entered  # type: ignore[method-assign]
    ev = det.evaluate(_ctx({gid: 3}, {3: _zone(3, 180)}, now))
    assert ev is not None
    assert ev.alert_type == "LOITERING"
    assert ev.payload["dwell_s"] >= 200


def test_does_not_fire_under_threshold() -> None:
    det = LoiteringDetector({})
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    entered = now - timedelta(seconds=100)
    det._entered_at = lambda gid, zone_id, ctx: entered  # type: ignore[method-assign]
    assert det.evaluate(_ctx({gid: 3}, {3: _zone(3, 180)}, now)) is None


def test_skips_when_no_entered_at() -> None:
    det = LoiteringDetector({})
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    det._entered_at = lambda gid, zone_id, ctx: None  # type: ignore[method-assign]
    assert det.evaluate(_ctx({gid: 3}, {3: _zone(3, 180)}, now)) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_anomaly_loitering.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `vms/anomaly/detectors/loitering.py`**

```python
"""LOITERING detector — tracklet dwell > zone.loiter_threshold_s."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    SeamProvider,
    Severity,
)


class LoiteringDetector(AnomalyDetector, SeamProvider):
    alert_type = "LOITERING"
    severity = Severity.LOW
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL", "MID")

    def should_run(self, ctx: DetectorContext) -> bool:
        return len(ctx.active_track_zones) > 0

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        now = datetime.fromtimestamp(
            ctx.frame.timestamp_ms / 1000.0, tz=timezone.utc
        ).replace(tzinfo=None)

        for gid, zone_id in ctx.active_track_zones.items():
            z = ctx.zone_lookup.get(zone_id)
            if z is None:
                continue
            entered = self._entered_at(gid, zone_id, ctx)
            if entered is None:
                continue
            dwell_s = (now - entered).total_seconds()
            if dwell_s >= z.loiter_threshold_s:
                return AnomalyEvent(
                    alert_type=self.alert_type,
                    severity=self.severity,
                    camera_id=ctx.frame.camera_id,
                    zone_id=zone_id,
                    global_track_id=gid,
                    person_id=None,
                    event_ts=now,
                    dedup_key=f"LOITERING:zone={zone_id}:gid={gid}",
                    payload={"dwell_s": int(dwell_s)},
                )
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=0, cooldown_ms=600_000, dedup_window_ms=600_000)

    def _entered_at(
        self, gid: uuid.UUID, zone_id: int,  # noqa: ARG002
        ctx: DetectorContext,                 # noqa: ARG002
    ) -> datetime | None:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_anomaly_loitering.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add vms/anomaly/detectors/loitering.py tests/test_anomaly_loitering.py
git commit -m "feat(anomaly): add LoiteringDetector"
```

---

## Task 12: VIOLENCE detector + MoViNet ONNX wrapper in InferenceEngine

**Background:** Two parts:
1. **MoViNet wrapper** (`vms/inference/violence.py`): loads `models/movinet_a0.onnx`, accepts a `(16, H, W, 3)` clip, returns a score in `[0, 1]`. If the ONNX file is missing the wrapper logs a warning and `score()` returns `None` — InferenceEngine treats `None` as "skip violence detector". This keeps the pipeline alive on a fresh checkout.
2. **VIOLENCE detector** (`vms/anomaly/detectors/violence.py`): reads `ctx.violence_score`; if non-None and >= threshold, emits a candidate event. FSM: sustain 2 s (two consecutive clips), cooldown 30 s/zone, severity CRITICAL.

The InferenceEngine integration is in this task too: extend `DetectionFrame.violence_score`, add `_violence` model handle to `InferenceEngine`, run when YOLO sees ≥2 persons every `violence_inference_every_s` seconds, attach the score to outgoing `DetectionFrame`.

**Files:**
- Modify: `vms/inference/messages.py`
- Create: `vms/inference/violence.py`
- Modify: `vms/inference/engine.py`
- Create: `vms/anomaly/detectors/violence.py`
- Modify: `tests/test_inference_messages.py`
- Create: `tests/test_inference_violence.py`
- Modify: `tests/test_inference_engine.py`
- Create: `tests/test_anomaly_violence.py`

- [ ] **Step 1: Write the failing test for the DetectionFrame field**

Add to `tests/test_inference_messages.py`:

```python
def test_detection_frame_default_violence_score_is_none() -> None:
    from vms.inference.messages import DetectionFrame
    df = DetectionFrame(camera_id=1, seq_id=1, timestamp_ms=1,
                        tracklets=(), face_embeddings=())
    assert df.violence_score is None


def test_detection_frame_roundtrips_violence_score() -> None:
    from vms.inference.messages import DetectionFrame
    df = DetectionFrame(camera_id=1, seq_id=1, timestamp_ms=1,
                        tracklets=(), face_embeddings=(), violence_score=0.72)
    fields = df.to_redis_fields()
    df2 = DetectionFrame.from_redis_fields(fields)
    assert df2.violence_score == 0.72


def test_detection_frame_missing_violence_field_back_compat() -> None:
    """Reading a frame published before this field existed must default to None."""
    from vms.inference.messages import DetectionFrame
    fields = {
        "camera_id": "1", "seq_id": "1", "timestamp_ms": "1",
        "tracklets": "[]", "face_embeddings": "[]",
    }
    df = DetectionFrame.from_redis_fields(fields)
    assert df.violence_score is None
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_inference_messages.py -v
```

Expected: FAIL — `violence_score` field missing.

- [ ] **Step 3: Update `vms/inference/messages.py`**

Add to `DetectionFrame`:

```python
@dataclass(frozen=True)
class DetectionFrame:
    camera_id: int
    seq_id: int
    timestamp_ms: int
    tracklets: tuple[Tracklet, ...]
    face_embeddings: tuple[FaceWithEmbedding, ...]
    violence_score: float | None = None
```

In `to_redis_fields()` add:

```python
        if self.violence_score is not None:
            fields["violence_score"] = str(self.violence_score)
```

In `from_redis_fields()` parse:

```python
        violence_raw = fields.get("violence_score")
        violence_score = float(violence_raw) if violence_raw is not None else None
        return cls(
            ...,
            violence_score=violence_score,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_inference_messages.py -v
```

Expected: all PASS.

- [ ] **Step 5: Write failing test for MoViNet wrapper**

Create `tests/test_inference_violence.py`:

```python
"""Tests for the MoViNet violence wrapper."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from vms.inference.violence import ViolenceModel


def test_missing_onnx_returns_none(tmp_path: Path) -> None:
    model = ViolenceModel(str(tmp_path / "nonexistent.onnx"))
    clip = np.zeros((16, 224, 224, 3), dtype=np.uint8)
    assert model.score(clip) is None


def test_score_returns_float_when_model_available(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSession:
        def get_inputs(self):
            class I:
                name = "input"
            return [I()]
        def run(self, _outs, _inputs):
            return [np.array([[0.42]], dtype=np.float32)]

    class FakeOrt:
        InferenceSession = lambda path, providers: FakeSession()  # noqa: E731

    import vms.inference.violence as mod
    monkeypatch.setattr(mod, "ort", FakeOrt(), raising=True)
    monkeypatch.setattr(mod.os.path, "exists", lambda p: True)
    model = ViolenceModel("/fake/path.onnx")
    clip = np.zeros((16, 224, 224, 3), dtype=np.uint8)
    score = model.score(clip)
    assert score == pytest.approx(0.42, abs=1e-3)
```

- [ ] **Step 6: Run tests to verify they fail**

```powershell
pytest tests/test_inference_violence.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 7: Create `vms/inference/violence.py`**

```python
"""MoViNet-A0 violence-detection ONNX wrapper.

If the ONNX file is absent at construction time, score() permanently returns
None — the pipeline continues without violence detection. This keeps the
deployment installable on a fresh checkout before models are downloaded.
"""

from __future__ import annotations

import logging
import os

import numpy as np
import onnxruntime as ort

logger = logging.getLogger(__name__)


class ViolenceModel:
    def __init__(self, path: str) -> None:
        self._path = path
        self._session: ort.InferenceSession | None = None
        if not os.path.exists(path):
            logger.warning("violence model %s not found; violence detection disabled", path)
            return
        try:
            self._session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("violence model load failed (%s); detection disabled", exc)
            self._session = None

    def score(self, clip: np.ndarray) -> float | None:  # type: ignore[type-arg]
        if self._session is None:
            return None
        if clip.shape[0] != 16:
            return None
        x = (clip.astype(np.float32) / 255.0).transpose(0, 3, 1, 2)[np.newaxis, ...]
        name = self._session.get_inputs()[0].name
        out = self._session.run(None, {name: x})
        return float(out[0].ravel()[0])
```

- [ ] **Step 8: Run tests to verify they pass**

```powershell
pytest tests/test_inference_violence.py -v
```

Expected: all PASS.

- [ ] **Step 9: Wire MoViNet into `vms/inference/engine.py`**

In `InferenceEngine.__init__`:

```python
        from vms.inference.violence import ViolenceModel
        self._violence = ViolenceModel(get_settings().violence_model)
        self._clip_buffers: dict[int, list[np.ndarray]] = {}  # camera_id -> rolling 16 frames
        self._last_violence_ts_ms: dict[int, int] = {}
```

In `_process_one_message`, after `raw_tracklets` is computed and before `DetectionFrame` is constructed, add:

```python
        violence_score: float | None = None
        person_count = sum(1 for t in raw_tracklets)
        if person_count >= get_settings().violence_gate_min_persons:
            buf = self._clip_buffers.setdefault(pointer.cam_id, [])
            buf.append(frame_bgr.copy())
            if len(buf) > get_settings().violence_clip_frames:
                buf.pop(0)
            last_ms = self._last_violence_ts_ms.get(pointer.cam_id, 0)
            min_interval_ms = int(get_settings().violence_inference_every_s * 1000)
            if (len(buf) == get_settings().violence_clip_frames
                    and timestamp_ms - last_ms >= min_interval_ms):
                clip = np.stack(buf, axis=0)
                violence_score = self._violence.score(clip)
                self._last_violence_ts_ms[pointer.cam_id] = timestamp_ms
```

Pass `violence_score=violence_score` to `DetectionFrame(...)`.

- [ ] **Step 10: Add a regression test in `tests/test_inference_engine.py`**

```python
def test_inference_engine_disables_violence_when_model_missing(tmp_path, monkeypatch) -> None:
    from vms.inference.engine import InferenceEngine
    monkeypatch.setenv("VMS_VIOLENCE_MODEL", str(tmp_path / "no.onnx"))
    engine = InferenceEngine.__new__(InferenceEngine)  # bypass __init__ for unit
    from vms.inference.violence import ViolenceModel
    engine._violence = ViolenceModel(str(tmp_path / "no.onnx"))
    import numpy as np
    assert engine._violence.score(np.zeros((16, 224, 224, 3), dtype=np.uint8)) is None
```

- [ ] **Step 11: Write the detector test**

Create `tests/test_anomaly_violence.py`:

```python
"""Tests for ViolenceDetector."""
from __future__ import annotations

from vms.anomaly.base import DetectorContext, Severity
from vms.anomaly.detectors.violence import ViolenceDetector
from vms.inference.messages import DetectionFrame


def _ctx(score: float | None) -> DetectorContext:
    frame = DetectionFrame(
        camera_id=1, seq_id=1, timestamp_ms=1_700_000_000_000,
        tracklets=(), face_embeddings=(), violence_score=score,
    )
    return DetectorContext(
        frame=frame, zone_lookup={}, active_track_zones={},
        head_count={}, violence_score=score,
    )


def test_fires_when_score_above_threshold() -> None:
    det = ViolenceDetector({})
    ev = det.evaluate(_ctx(0.81))
    assert ev is not None
    assert ev.severity is Severity.CRITICAL
    assert ev.payload["score"] == 0.81


def test_does_not_fire_below_threshold() -> None:
    det = ViolenceDetector({})
    assert det.evaluate(_ctx(0.40)) is None


def test_should_run_skips_when_score_is_none() -> None:
    det = ViolenceDetector({})
    assert det.should_run(_ctx(None)) is False


def test_config_threshold_overrides_default() -> None:
    det = ViolenceDetector({"threshold": 0.90})
    assert det.evaluate(_ctx(0.85)) is None
```

- [ ] **Step 12: Run tests to verify they fail**

```powershell
pytest tests/test_anomaly_violence.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 13: Create `vms/anomaly/detectors/violence.py`**

```python
"""VIOLENCE detector. Reads ctx.violence_score from the InferenceEngine gated pool."""

from __future__ import annotations

from datetime import datetime, timezone

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    Severity,
)
from vms.config import get_settings


class ViolenceDetector(AnomalyDetector):
    alert_type = "VIOLENCE"
    severity = Severity.CRITICAL
    requires_models: tuple[str, ...] = ("violence",)
    requires_tier: tuple[str, ...] = ("FULL", "MID")

    def __init__(self, config: dict[str, object]) -> None:
        super().__init__(config)
        cfg_th = config.get("threshold")
        self._threshold: float = (
            float(cfg_th) if cfg_th is not None
            else get_settings().violence_threshold
        )

    def should_run(self, ctx: DetectorContext) -> bool:
        return ctx.violence_score is not None

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        score = ctx.violence_score
        if score is None or score < self._threshold:
            return None
        when = datetime.fromtimestamp(
            ctx.frame.timestamp_ms / 1000.0, tz=timezone.utc
        ).replace(tzinfo=None)
        return AnomalyEvent(
            alert_type=self.alert_type,
            severity=self.severity,
            camera_id=ctx.frame.camera_id,
            zone_id=None,
            global_track_id=None,
            person_id=None,
            event_ts=when,
            dedup_key=f"VIOLENCE:cam={ctx.frame.camera_id}",
            payload={"score": score},
        )

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=2_000, cooldown_ms=30_000, dedup_window_ms=30_000)
```

- [ ] **Step 14: Run tests to verify they pass**

```powershell
pytest tests/test_anomaly_violence.py tests/test_inference_violence.py tests/test_inference_messages.py tests/test_inference_engine.py -v
```

Expected: all PASS.

- [ ] **Step 15: Run full suite**

```powershell
pytest -v
```

Expected: all PASS.

- [ ] **Step 16: Commit**

```powershell
git add vms/inference/messages.py vms/inference/violence.py vms/inference/engine.py vms/anomaly/detectors/violence.py tests/test_inference_messages.py tests/test_inference_violence.py tests/test_inference_engine.py tests/test_anomaly_violence.py
git commit -m "feat(anomaly,inference): add MoViNet wrapper + ViolenceDetector + DetectionFrame.violence_score"
```

---

## Task 13: HeadCountAggregator (spec §N.1) — in-memory zone counts, TTL eviction

**Background:** Pure in-memory aggregator. Fed by the orchestrator: for every DetectionFrame, the orchestrator computes `(gid, zone_id)` pairs from the IdentityEngine + ZonePresenceTracker, calls `agg.on_tracking_event(gid, zone_id, ts)`. Every `head_count_emit_interval_s` (1 s) it emits `head_count_zone_<id>` stream entries and serves `/api/state/snapshot`.

**Files:**
- Create: `vms/identity/head_count.py`
- Create: `tests/test_identity_head_count.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_identity_head_count.py`:

```python
"""Tests for HeadCountAggregator."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from vms.identity.head_count import HeadCountAggregator


def test_on_event_increments_zone_count() -> None:
    agg = HeadCountAggregator()
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    agg.on_tracking_event(gid, zone_id=3, ts=now)
    snap = agg.snapshot()
    assert snap.by_zone == {3: 1}
    assert snap.plant_total == 1


def test_same_gid_moves_between_zones() -> None:
    agg = HeadCountAggregator()
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    agg.on_tracking_event(gid, zone_id=3, ts=now)
    agg.on_tracking_event(gid, zone_id=5, ts=now + timedelta(seconds=1))
    snap = agg.snapshot()
    assert snap.by_zone.get(3, 0) == 0
    assert snap.by_zone[5] == 1


def test_evict_stale_removes_old_tracks() -> None:
    agg = HeadCountAggregator()
    gid_old = uuid.uuid4()
    gid_new = uuid.uuid4()
    base = datetime(2026, 5, 15, 12, 0, 0)
    agg.on_tracking_event(gid_old, zone_id=3, ts=base)
    agg.on_tracking_event(gid_new, zone_id=3, ts=base + timedelta(seconds=20))
    agg.evict_stale(now=base + timedelta(seconds=35), ttl_s=30)
    snap = agg.snapshot()
    assert snap.by_zone[3] == 1


def test_snapshot_serialisation() -> None:
    agg = HeadCountAggregator()
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    agg.on_tracking_event(gid, zone_id=3, ts=now)
    snap = agg.snapshot()
    d = snap.to_dict()
    assert d["plant_total"] == 1
    assert d["by_zone"] == {3: 1}
    assert "ts" in d


def test_zone_none_is_ignored() -> None:
    agg = HeadCountAggregator()
    gid = uuid.uuid4()
    now = datetime(2026, 5, 15, 12, 0, 0)
    agg.on_tracking_event(gid, zone_id=None, ts=now)
    assert agg.snapshot().plant_total == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_identity_head_count.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `vms/identity/head_count.py`**

```python
"""HeadCountAggregator (spec §N.1).

In-memory aggregator subscribed (in production) to the same DetectionFrames
the orchestrator consumes. Maintains:
  - by_zone: dict[int, set[gid]]
  - last_seen: dict[gid, (zone_id, ts)]

Not thread-safe — single owner per process.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class HeadCountSnapshot:
    plant_total: int
    by_zone: dict[int, int]
    ts: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "plant_total": self.plant_total,
            "by_zone": dict(self.by_zone),
            "ts": self.ts.isoformat() + "Z",
            "schema_version": "1",
        }


@dataclass
class HeadCountAggregator:
    _by_zone: dict[int, set[uuid.UUID]] = field(
        default_factory=lambda: defaultdict(set)
    )
    _last_seen: dict[uuid.UUID, tuple[int, datetime]] = field(default_factory=dict)

    def on_tracking_event(
        self, gid: uuid.UUID, zone_id: int | None, ts: datetime
    ) -> None:
        if zone_id is None:
            prev = self._last_seen.pop(gid, None)
            if prev is not None:
                self._by_zone[prev[0]].discard(gid)
            return
        prev = self._last_seen.get(gid)
        if prev is not None and prev[0] != zone_id:
            self._by_zone[prev[0]].discard(gid)
        self._by_zone[zone_id].add(gid)
        self._last_seen[gid] = (zone_id, ts)

    def evict_stale(self, now: datetime, ttl_s: int) -> int:
        cutoff = now - timedelta(seconds=ttl_s)
        stale = [gid for gid, (_z, ts) in self._last_seen.items() if ts < cutoff]
        for gid in stale:
            zid, _ = self._last_seen.pop(gid)
            self._by_zone[zid].discard(gid)
        return len(stale)

    def snapshot(self) -> HeadCountSnapshot:
        from datetime import timezone
        non_empty = {zid: len(s) for zid, s in self._by_zone.items() if s}
        return HeadCountSnapshot(
            plant_total=sum(non_empty.values()),
            by_zone=non_empty,
            ts=datetime.now(timezone.utc).replace(tzinfo=None),
        )

    def counts_by_zone(self) -> dict[int, int]:
        return {zid: len(s) for zid, s in self._by_zone.items() if s}
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_identity_head_count.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add vms/identity/head_count.py tests/test_identity_head_count.py
git commit -m "feat(identity): add HeadCountAggregator with TTL eviction (spec §N.1)"
```

---

## Task 14: AnomalyOrchestrator — wire detections stream → detectors → FSM → alerts

**Background:** The orchestrator is the central process for Phase 2b. It consumes `detections` (separate consumer group from `DBWriter` so both can read independently), builds a `DetectorContext` per frame, runs every enabled detector inside an error-isolating try/except, pipes positive events through `AlertFSM`, and feeds `HeadCountAggregator` from the same loop. Per-detector error counters disable detectors after `anomaly_max_consecutive_errors` consecutive failures.

The orchestrator also wires the per-detector "default seam" methods to real implementations: `_gid_for_tracklet`, `_person_id_for`, `_registry_last_seen`, `_entered_at`.

**Files:**
- Create: `vms/anomaly/orchestrator.py`
- Create: `tests/test_anomaly_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_anomaly_orchestrator.py`:

```python
"""Tests for AnomalyOrchestrator."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.orm import Session

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    Severity,
)
from vms.anomaly.orchestrator import AnomalyOrchestrator
from vms.db.models import Alert, Camera, Zone
from vms.inference.messages import DetectionFrame, Tracklet


def _utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class _AlwaysFires(AnomalyDetector):
    alert_type = "UNKNOWN_PERSON"
    severity = Severity.HIGH
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL",)

    def should_run(self, ctx: DetectorContext) -> bool:
        return True

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        return AnomalyEvent(
            alert_type="UNKNOWN_PERSON",
            severity=Severity.HIGH,
            camera_id=ctx.frame.camera_id,
            zone_id=None,
            global_track_id=uuid.uuid4(),
            person_id=None,
            event_ts=_utc_naive(),
            dedup_key=f"UNKNOWN_PERSON:cam={ctx.frame.camera_id}:seq={ctx.frame.seq_id}",
        )

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=0, cooldown_ms=60_000, dedup_window_ms=60_000)


class _Raises(AnomalyDetector):
    alert_type = "INTRUSION"
    severity = Severity.CRITICAL
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL",)

    def should_run(self, ctx: DetectorContext) -> bool:
        return True

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        raise RuntimeError("intentional")

    def fsm_config(self) -> FSMConfig:
        return FSMConfig()


@pytest.mark.asyncio
async def test_process_frame_fires_one_alert(db_session: Session) -> None:
    cam = Camera(name="OrchC", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam); db_session.flush()
    client = FakeRedis(decode_responses=True)
    orch = AnomalyOrchestrator(
        redis_client=client,
        session_factory=lambda: db_session,
        detectors={"UNKNOWN_PERSON": _AlwaysFires({})},
    )
    frame = DetectionFrame(
        camera_id=cam.camera_id, seq_id=1, timestamp_ms=int(_utc_naive().timestamp() * 1000),
        tracklets=(Tracklet(local_track_id=1, camera_id=cam.camera_id,
                            bbox=(0, 0, 10, 10), confidence=0.9),),
        face_embeddings=(),
    )
    await orch.process_frame(frame)
    db_session.flush()
    assert db_session.query(Alert).filter_by(alert_type="UNKNOWN_PERSON").count() == 1


@pytest.mark.asyncio
async def test_failing_detector_does_not_kill_others(db_session: Session) -> None:
    cam = Camera(name="OrchC2", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam); db_session.flush()
    client = FakeRedis(decode_responses=True)
    orch = AnomalyOrchestrator(
        redis_client=client,
        session_factory=lambda: db_session,
        detectors={
            "INTRUSION": _Raises({}),
            "UNKNOWN_PERSON": _AlwaysFires({}),
        },
    )
    frame = DetectionFrame(
        camera_id=cam.camera_id, seq_id=1, timestamp_ms=int(_utc_naive().timestamp() * 1000),
        tracklets=(Tracklet(local_track_id=1, camera_id=cam.camera_id,
                            bbox=(0, 0, 10, 10), confidence=0.9),),
        face_embeddings=(),
    )
    await orch.process_frame(frame)
    db_session.flush()
    assert db_session.query(Alert).filter_by(alert_type="UNKNOWN_PERSON").count() == 1
    assert orch.health()["INTRUSION"]["consecutive_errors"] == 1


@pytest.mark.asyncio
async def test_detector_auto_disabled_after_max_consecutive_errors(db_session: Session) -> None:
    cam = Camera(name="OrchC3", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam); db_session.flush()
    client = FakeRedis(decode_responses=True)
    orch = AnomalyOrchestrator(
        redis_client=client,
        session_factory=lambda: db_session,
        detectors={"INTRUSION": _Raises({})},
        max_consecutive_errors=2,
    )
    frame = DetectionFrame(
        camera_id=cam.camera_id, seq_id=1, timestamp_ms=int(_utc_naive().timestamp() * 1000),
        tracklets=(), face_embeddings=(),
    )
    await orch.process_frame(frame)
    await orch.process_frame(frame)
    await orch.process_frame(frame)
    assert orch.health()["INTRUSION"]["disabled"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_anomaly_orchestrator.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `vms/anomaly/orchestrator.py`**

```python
"""AnomalyOrchestrator — consumes detections stream, runs detectors, feeds FSM."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.orm import Session

from vms.anomaly.base import AnomalyDetector, DetectorContext, FSMConfig, SeamProvider, ZoneLookup
from vms.anomaly.fsm import AlertFSM, FSMDecision
from vms.anomaly.maintenance import MaintenanceCalendar
from vms.config import get_settings
from vms.db.models import Zone, ZonePresence
from vms.identity.engine import IdentityEngine
from vms.identity.head_count import HeadCountAggregator
from vms.identity.zone_presence import ZonePresenceTracker
from vms.inference.messages import DetectionFrame
from vms.redis_client import stream_read

logger = logging.getLogger(__name__)

_DETECTIONS_STREAM = "detections"


@dataclass
class _DetectorState:
    consecutive_errors: int = 0
    total_errors: int = 0
    fires: int = 0
    suppressed: int = 0
    deduped: int = 0
    sustaining: int = 0
    disabled: bool = False


class AnomalyOrchestrator:
    """Single-process orchestrator.

    Production wiring:
      orch = AnomalyOrchestrator(
          redis_client=...,
          session_factory=SessionLocal,
          detectors=load_enabled_detectors(...).detectors,
          identity=IdentityEngine(...),
          zone_tracker=ZonePresenceTracker(),
          head_count=HeadCountAggregator(),
      )
      await orch.run()
    """

    def __init__(
        self,
        *,
        redis_client: aioredis.Redis,
        session_factory: Callable[[], Session],
        detectors: dict[str, AnomalyDetector],
        identity: IdentityEngine | None = None,
        zone_tracker: ZonePresenceTracker | None = None,
        head_count: HeadCountAggregator | None = None,
        calendar: MaintenanceCalendar | None = None,
        max_consecutive_errors: int | None = None,
    ) -> None:
        self._redis = redis_client
        self._sf = session_factory
        self._detectors = detectors
        self._identity = identity
        self._zone_tracker = zone_tracker
        self._head_count = head_count or HeadCountAggregator()
        self._cal = calendar or MaintenanceCalendar(session_factory)
        self._fsm = AlertFSM(redis_client=redis_client, calendar=self._cal,
                             session_factory=session_factory)
        self._fsm.rebuild_from_db()
        self._state: dict[str, _DetectorState] = {k: _DetectorState() for k in detectors}
        self._fsm_configs: dict[str, FSMConfig] = {
            k: d.fsm_config() for k, d in detectors.items()
        }
        self._max_errors = (
            max_consecutive_errors
            if max_consecutive_errors is not None
            else get_settings().anomaly_max_consecutive_errors
        )
        self._zone_cache: dict[int, ZoneLookup] | None = None
        self._zone_cache_expires: float = 0.0
        self._last_id = "0-0"
        self._running = False

        for det in detectors.values():
            self._bind_seams(det)

    def _bind_seams(self, det: AnomalyDetector) -> None:
        if not isinstance(det, SeamProvider):
            return
        det._gid_for_tracklet = self._gid_for_tracklet  # type: ignore[method-assign]
        det._person_id_for = self._person_id_for  # type: ignore[method-assign]
        det._registry_last_seen = self._registry_last_seen  # type: ignore[method-assign]
        det._entered_at = self._entered_at  # type: ignore[method-assign]

    def _zone_lookup(self) -> dict[int, ZoneLookup]:
        now = time.monotonic()
        if self._zone_cache is None or now >= self._zone_cache_expires:
            session = self._sf()
            rows = session.query(Zone).all()
            self._zone_cache = {
                r.zone_id: ZoneLookup(
                    zone_id=r.zone_id, name=r.name, is_restricted=r.is_restricted,
                    max_capacity=r.max_capacity, allowed_hours=r.allowed_hours,
                    loiter_threshold_s=r.loiter_threshold_s,
                    polygon_json=r.polygon_json,
                )
                for r in rows
            }
            self._zone_cache_expires = now + get_settings().zone_cache_ttl_s
        return self._zone_cache

    def _active_track_zones(self) -> dict[uuid.UUID, int]:
        if self._zone_tracker is None:
            return {}
        return {
            gid: zid for gid, zid in self._zone_tracker._current.items()  # noqa: SLF001
            if zid is not None
        }

    def _gid_for_tracklet(self, tl, ctx: DetectorContext):  # noqa: ANN001
        if self._identity is None:
            return None
        entry = self._identity._registry.get((tl.camera_id, tl.local_track_id))  # noqa: SLF001
        return entry.global_track_id if entry else None

    def _person_id_for(self, gid, ctx: DetectorContext) -> int | None:  # noqa: ANN001
        if self._identity is None:
            return None
        for entry in self._identity._registry.values():  # noqa: SLF001
            if entry.global_track_id == gid:
                return entry.person_id
        return None

    def _registry_last_seen(self, ctx: DetectorContext) -> dict[uuid.UUID, int]:
        if self._identity is None:
            return {}
        return {
            e.global_track_id: e.last_seen_ms
            for e in self._identity._registry.values()  # noqa: SLF001
        }

    def _entered_at(self, gid, zone_id: int, ctx: DetectorContext):  # noqa: ANN001
        session = self._sf()
        row = (
            session.query(ZonePresence)
            .filter_by(global_track_id=gid, zone_id=zone_id)
            .filter(ZonePresence.exited_at.is_(None))
            .order_by(ZonePresence.entered_at.desc())
            .first()
        )
        return row.entered_at if row else None

    async def process_frame(self, frame: DetectionFrame) -> None:
        ctx = DetectorContext(
            frame=frame,
            zone_lookup=self._zone_lookup(),
            active_track_zones=self._active_track_zones(),
            head_count=self._head_count.counts_by_zone(),
            violence_score=frame.violence_score,
        )

        # Feed HeadCountAggregator from this frame
        if self._identity is not None and self._zone_tracker is not None:
            now = datetime.fromtimestamp(
                frame.timestamp_ms / 1000.0, tz=timezone.utc
            ).replace(tzinfo=None)
            for gid, zid in ctx.active_track_zones.items():
                self._head_count.on_tracking_event(gid, zid, now)
            self._head_count.evict_stale(
                now, ttl_s=get_settings().head_count_track_ttl_s
            )

        for alert_type, det in self._detectors.items():
            st = self._state[alert_type]
            if st.disabled:
                continue
            try:
                if not det.should_run(ctx):
                    continue
                ev = det.evaluate(ctx)
            except Exception:  # noqa: BLE001
                st.consecutive_errors += 1
                st.total_errors += 1
                logger.exception("detector %s evaluate() raised", alert_type)
                if st.consecutive_errors >= self._max_errors:
                    st.disabled = True
                    logger.error("detector %s auto-disabled after %d errors",
                                 alert_type, st.consecutive_errors)
                continue
            st.consecutive_errors = 0
            if ev is None:
                continue
            decision = await self._fsm.process(ev, self._fsm_configs[alert_type])
            if decision is FSMDecision.FIRED:
                st.fires += 1
            elif decision is FSMDecision.SUPPRESSED:
                st.suppressed += 1
            elif decision is FSMDecision.DEDUPED:
                st.deduped += 1
            elif decision is FSMDecision.SUSTAINING:
                st.sustaining += 1

    def health(self) -> dict[str, dict[str, Any]]:
        return {
            k: {
                "consecutive_errors": v.consecutive_errors,
                "total_errors": v.total_errors,
                "fires": v.fires,
                "suppressed": v.suppressed,
                "deduped": v.deduped,
                "sustaining": v.sustaining,
                "disabled": v.disabled,
            }
            for k, v in self._state.items()
        }

    async def run(self) -> None:
        self._running = True
        _frames_since_evict = 0
        while self._running:
            messages = await stream_read(
                self._redis, _DETECTIONS_STREAM, last_id=self._last_id, count=100,
            )
            if not messages:
                await asyncio.sleep(0.05)
                continue
            for msg_id, fields in messages:
                try:
                    frame = DetectionFrame.from_redis_fields(fields)
                    await self.process_frame(frame)
                except Exception:  # noqa: BLE001
                    logger.exception("orchestrator frame handle failed msg=%s", msg_id)
                self._last_id = msg_id
                _frames_since_evict += 1
                if _frames_since_evict >= 100:
                    self._fsm.evict_closed(
                        datetime.now(timezone.utc).replace(tzinfo=None)
                    )
                    _frames_since_evict = 0

    async def stop(self) -> None:
        self._running = False
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_anomaly_orchestrator.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full suite**

```powershell
pytest -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git add vms/anomaly/orchestrator.py tests/test_anomaly_orchestrator.py
git commit -m "feat(anomaly): add AnomalyOrchestrator with error-isolated detector loop + HeadCount feed"
```

---

## Task 15: Read-only inspection APIs + CLI (no frontend = HTTP + CLI are the UI)

**Background:** With no frontend we need first-class HTTP and CLI surfaces to verify behaviour and operate the system. This task adds four read-only routes and a small CLI:

- `GET /api/state/snapshot` — full live state (head_count + active alerts + cameras), spec §N.3
- `GET /api/alerts` — list alerts with filters (state, alert_type, camera_id, from, to)
- `GET /api/anomaly-detectors` — list detector rows
- `GET /api/anomaly-detectors/health` — per-detector counters from the orchestrator process (read from a module-level shared registry)
- `GET /api/maintenance` — list windows (CRUD is deferred to Phase 3 with the dispatcher; read-only suffices for Phase 2b verification)
- CLI: `vms-cli alerts tail`, `vms-cli alerts list`, `vms-cli detectors status`, `vms-cli head-count`

All routes require auth via the existing `get_current_user` dependency.

**Files:**
- Create: `vms/api/routes/state.py`
- Create: `vms/api/routes/alerts.py`
- Create: `vms/api/routes/anomaly_detectors.py`
- Create: `vms/api/routes/maintenance.py`
- Modify: `vms/api/main.py`
- Modify: `vms/api/schemas.py`
- Modify: `vms/api/deps.py` (add `get_orchestrator_health` accessor)
- Create: `vms/cli/__init__.py`
- Create: `vms/cli/main.py`
- Modify: `pyproject.toml` (or `setup.cfg`) for `vms-cli` entry point
- Create: `tests/test_api_state.py`
- Create: `tests/test_api_alerts.py`
- Create: `tests/test_api_anomaly_detectors.py`
- Create: `tests/test_api_maintenance.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for `/api/state/snapshot`**

Create `tests/test_api_state.py`:

```python
"""Tests for GET /api/state/snapshot."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from vms.api.main import app
from vms.api.routes.state import set_head_count_aggregator
from vms.identity.head_count import HeadCountAggregator


def _auth(role: str = "manager") -> dict[str, str]:
    from vms.api.deps import create_access_token
    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


@pytest.mark.asyncio
async def test_snapshot_returns_payload_shape() -> None:
    agg = HeadCountAggregator()
    set_head_count_aggregator(agg)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/state/snapshot", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert "ts" in body
    assert "schema_version" in body
    assert body["schema_version"] == "1"
    assert "head_count" in body
    assert "active_alerts" in body
    assert "cameras" in body


@pytest.mark.asyncio
async def test_snapshot_requires_auth() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/state/snapshot")
    assert r.status_code in (401, 403)
```

- [ ] **Step 2: Write failing tests for `/api/alerts`**

Create `tests/test_api_alerts.py`:

```python
"""Tests for GET /api/alerts."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.main import app
from vms.db.models import Alert, Camera


def _auth(role: str = "manager") -> dict[str, str]:
    from vms.api.deps import create_access_token
    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


def _utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_alerts_list_returns_filtered_results(db_session: Session) -> None:
    cam = Camera(name="AC1", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    db_session.add(Alert(
        alert_type="VIOLENCE", severity="CRITICAL", state="active",
        camera_id=cam.camera_id, triggered_at=_utc_naive(), dedup_key="d1",
    ))
    db_session.add(Alert(
        alert_type="UNKNOWN_PERSON", severity="HIGH", state="resolved",
        camera_id=cam.camera_id, triggered_at=_utc_naive(), dedup_key="d2",
    ))
    db_session.flush()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/alerts?state=active", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    types = [a["alert_type"] for a in body]
    assert "VIOLENCE" in types
    assert "UNKNOWN_PERSON" not in types


@pytest.mark.asyncio
async def test_alerts_list_filter_by_alert_type(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/alerts?alert_type=VIOLENCE", headers=_auth())
    assert r.status_code == 200
```

- [ ] **Step 3: Write failing tests for `/api/anomaly-detectors`**

Create `tests/test_api_anomaly_detectors.py`:

```python
"""Tests for GET /api/anomaly-detectors and /api/anomaly-detectors/health."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.main import app


def _auth(role: str = "manager") -> dict[str, str]:
    from vms.api.deps import create_access_token
    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


@pytest.mark.asyncio
async def test_list_anomaly_detectors_returns_six_seeded(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/anomaly-detectors", headers=_auth())
    assert r.status_code == 200
    types = sorted(d["alert_type"] for d in r.json())
    assert types == ["CROWD_DENSITY", "INTRUSION", "LOITERING",
                     "PERSON_LOST", "UNKNOWN_PERSON", "VIOLENCE"]


@pytest.mark.asyncio
async def test_detector_health_returns_empty_when_unwired() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/anomaly-detectors/health", headers=_auth())
    assert r.status_code == 200
    assert isinstance(r.json(), dict)
```

- [ ] **Step 4: Write failing tests for `/api/maintenance`**

Create `tests/test_api_maintenance.py`:

```python
"""Tests for GET /api/maintenance."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.main import app
from vms.db.models import Camera, MaintenanceWindow, User


def _auth(role: str = "manager") -> dict[str, str]:
    from vms.api.deps import create_access_token
    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


@pytest.mark.asyncio
async def test_list_maintenance_windows(db_session: Session) -> None:
    u = User(username="m_op", password_hash="x", role="admin", is_active=True)
    db_session.add(u); db_session.flush()
    c = Camera(name="MC", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(c); db_session.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(MaintenanceWindow(
        name="mw1", scope_type="CAMERA", scope_id=c.camera_id,
        schedule_type="ONE_TIME",
        starts_at=now, ends_at=now + timedelta(hours=1),
        created_by=u.user_id,
    ))
    db_session.flush()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cli:
        r = await cli.get("/api/maintenance", headers=_auth())
    assert r.status_code == 200
    names = [w["name"] for w in r.json()]
    assert "mw1" in names
```

- [ ] **Step 5: Run tests to verify they fail**

```powershell
pytest tests/test_api_state.py tests/test_api_alerts.py tests/test_api_anomaly_detectors.py tests/test_api_maintenance.py -v
```

Expected: FAIL — routes missing.

- [ ] **Step 6: Add schemas to `vms/api/schemas.py`**

```python
class AlertResponse(BaseModel):
    alert_id: int
    alert_type: str
    severity: str
    state: str
    camera_id: int
    zone_id: int | None
    person_id: int | None
    triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    suppressed_by_window_id: int | None
    dedup_key: str | None

    model_config = {"from_attributes": True}


class AnomalyDetectorResponse(BaseModel):
    detector_id: int
    alert_type: str
    class_path: str
    is_enabled: bool
    config_json: str | None
    model_version: str | None

    model_config = {"from_attributes": True}


class MaintenanceWindowResponse(BaseModel):
    window_id: int
    name: str
    scope_type: str
    scope_id: int
    schedule_type: str
    starts_at: datetime | None
    ends_at: datetime | None
    cron_expr: str | None
    duration_minutes: int | None
    suppress_alert_types: str | None
    is_active: bool
    reason: str | None

    model_config = {"from_attributes": True}


class SnapshotResponse(BaseModel):
    ts: str
    schema_version: str = "1"
    head_count: dict[str, object]
    active_alerts: list[AlertResponse]
    cameras: list[dict[str, object]]
    degraded: dict[str, object] | None = None
```

Add the missing `datetime` import if needed.

- [ ] **Step 7: Add shared orchestrator-health hook in `vms/api/deps.py`**

```python
# Process-level shared state for inspection routes.
_orchestrator_health: dict[str, dict[str, object]] = {}

def set_orchestrator_health(snapshot: dict[str, dict[str, object]]) -> None:
    """Called by the orchestrator process every N seconds."""
    _orchestrator_health.clear()
    _orchestrator_health.update(snapshot)

def get_orchestrator_health() -> dict[str, dict[str, object]]:
    return dict(_orchestrator_health)
```

- [ ] **Step 8: Create `vms/api/routes/state.py`**

```python
"""GET /api/state/snapshot — spec §N.3."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.db.models import Alert, Camera
from vms.identity.head_count import HeadCountAggregator

router = APIRouter()

_agg: HeadCountAggregator | None = None


def set_head_count_aggregator(agg: HeadCountAggregator) -> None:
    """The orchestrator wires its aggregator into the API process via this hook."""
    global _agg
    _agg = agg


@router.get("/state/snapshot")
def snapshot(
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    head = _agg.snapshot().to_dict() if _agg is not None else {
        "plant_total": 0, "by_zone": {}, "ts": now, "schema_version": "1",
    }
    active = db.query(Alert).filter_by(state="active").limit(200).all()
    cams = db.query(Camera).filter_by(is_active=True).all()
    return {
        "ts": now,
        "schema_version": "1",
        "head_count": head,
        "active_alerts": [
            {
                "alert_id": a.alert_id, "alert_type": a.alert_type,
                "severity": a.severity, "state": a.state,
                "camera_id": a.camera_id, "zone_id": a.zone_id,
                "global_track_id": str(a.global_track_id) if a.global_track_id else None,
                "person_id": a.person_id,
                "triggered_at": a.triggered_at.isoformat() + "Z",
            }
            for a in active
        ],
        "cameras": [
            {
                "camera_id": c.camera_id, "name": c.name,
                "capability_tier": c.capability_tier,
                "is_active": c.is_active,
            }
            for c in cams
        ],
        "degraded": None,
    }
```

- [ ] **Step 9: Create `vms/api/routes/alerts.py`**

```python
"""GET /api/alerts — list alerts with filters."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.api.schemas import AlertResponse
from vms.db.models import Alert

router = APIRouter()


@router.get("/alerts", response_model=list[AlertResponse])
def list_alerts(
    state: str | None = Query(default=None),
    alert_type: str | None = Query(default=None),
    camera_id: int | None = Query(default=None),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[Alert]:
    q = db.query(Alert)
    if state:
        q = q.filter(Alert.state == state)
    if alert_type:
        q = q.filter(Alert.alert_type == alert_type)
    if camera_id is not None:
        q = q.filter(Alert.camera_id == camera_id)
    if from_ts:
        q = q.filter(Alert.triggered_at >= from_ts)
    if to_ts:
        q = q.filter(Alert.triggered_at <= to_ts)
    return q.order_by(Alert.triggered_at.desc()).limit(limit).all()
```

- [ ] **Step 10: Create `vms/api/routes/anomaly_detectors.py`**

```python
"""GET /api/anomaly-detectors[/health]."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db, get_orchestrator_health
from vms.api.schemas import AnomalyDetectorResponse
from vms.db.models import AnomalyDetector

router = APIRouter()


@router.get("/anomaly-detectors", response_model=list[AnomalyDetectorResponse])
def list_detectors(
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[AnomalyDetector]:
    return db.query(AnomalyDetector).order_by(AnomalyDetector.alert_type).all()


@router.get("/anomaly-detectors/health")
def detector_health(
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> dict[str, dict[str, object]]:
    return get_orchestrator_health()
```

- [ ] **Step 11: Create `vms/api/routes/maintenance.py`**

```python
"""GET /api/maintenance — list active windows."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.api.schemas import MaintenanceWindowResponse
from vms.db.models import MaintenanceWindow

router = APIRouter()


@router.get("/maintenance", response_model=list[MaintenanceWindowResponse])
def list_windows(
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[MaintenanceWindow]:
    return db.query(MaintenanceWindow).filter_by(is_active=True).all()
```

- [ ] **Step 12: Register routers in `vms/api/main.py`**

```python
from vms.api.routes import (
    alerts,
    anomaly_detectors,
    auth,
    health,
    maintenance,
    persons,
    state,
)

app = FastAPI(title="VMS API", version="0.2.0")
app.include_router(auth.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(persons.router, prefix="/api")
app.include_router(state.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(anomaly_detectors.router, prefix="/api")
app.include_router(maintenance.router, prefix="/api")
```

- [ ] **Step 13: Run API tests**

```powershell
pytest tests/test_api_state.py tests/test_api_alerts.py tests/test_api_anomaly_detectors.py tests/test_api_maintenance.py -v
```

Expected: all PASS.

- [ ] **Step 14: Write the CLI test**

Create `tests/test_cli.py`:

```python
"""Tests for vms-cli."""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from vms.cli.main import cli


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "alerts" in result.output
    assert "detectors" in result.output
    assert "head-count" in result.output


def test_cli_alerts_list_invokes_api(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = [
        {"alert_id": 1, "alert_type": "VIOLENCE", "severity": "CRITICAL",
         "state": "active", "camera_id": 5, "zone_id": None,
         "triggered_at": "2026-05-15T10:00:00Z"},
    ]

    def fake_get(url: str, headers: dict[str, str], params: dict[str, object]):
        class R:
            status_code = 200
            def json(self): return sample
        return R()

    import vms.cli.main as mod
    monkeypatch.setattr(mod.httpx, "get", fake_get, raising=True)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["alerts", "list", "--api", "http://x", "--token", "t"],
    )
    assert result.exit_code == 0
    assert "VIOLENCE" in result.output
```

- [ ] **Step 15: Run CLI test to verify it fails**

```powershell
pytest tests/test_cli.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 16: Add `click` dependency**

In `requirements.txt`:

```
click==8.1.7
httpx==0.27.2
```

(`httpx` may already be present for `AsyncClient`. If absent, install it.)

- [ ] **Step 17: Create `vms/cli/__init__.py`**

```python
"""vms-cli — inspection CLI for ops."""
```

- [ ] **Step 18: Create `vms/cli/main.py`**

```python
"""vms-cli — small click-based CLI to inspect the running VMS.

Examples:
  vms-cli alerts list --api http://localhost:8000 --token $TOK
  vms-cli alerts tail --api http://localhost:8000 --token $TOK
  vms-cli detectors status --api http://localhost:8000 --token $TOK
  vms-cli head-count --api http://localhost:8000 --token $TOK
"""

from __future__ import annotations

import json
import sys
import time

import click
import httpx


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@click.group()
def cli() -> None:
    """VMS inspection CLI."""


@cli.group()
def alerts() -> None:
    """Alert inspection."""


@alerts.command("list")
@click.option("--api", required=True)
@click.option("--token", required=True)
@click.option("--state", default=None)
@click.option("--alert-type", default=None)
@click.option("--limit", default=50, type=int)
def alerts_list(api: str, token: str, state: str | None,
                alert_type: str | None, limit: int) -> None:
    params: dict[str, object] = {"limit": limit}
    if state: params["state"] = state
    if alert_type: params["alert_type"] = alert_type
    r = httpx.get(f"{api}/api/alerts", headers=_headers(token), params=params)
    if r.status_code != 200:
        click.echo(f"error: HTTP {r.status_code}", err=True)
        sys.exit(2)
    for a in r.json():
        click.echo(json.dumps(a))


@alerts.command("tail")
@click.option("--api", required=True)
@click.option("--token", required=True)
@click.option("--interval", default=1.0, type=float)
def alerts_tail(api: str, token: str, interval: float) -> None:
    seen: set[int] = set()
    while True:
        r = httpx.get(f"{api}/api/alerts",
                      headers=_headers(token),
                      params={"state": "active", "limit": 50})
        if r.status_code == 200:
            for a in r.json():
                if a["alert_id"] not in seen:
                    seen.add(a["alert_id"])
                    click.echo(json.dumps(a))
        time.sleep(interval)


@cli.group()
def detectors() -> None:
    """Detector inspection."""


@detectors.command("status")
@click.option("--api", required=True)
@click.option("--token", required=True)
def detectors_status(api: str, token: str) -> None:
    r = httpx.get(f"{api}/api/anomaly-detectors/health", headers=_headers(token))
    click.echo(json.dumps(r.json(), indent=2))


@cli.command("head-count")
@click.option("--api", required=True)
@click.option("--token", required=True)
def head_count(api: str, token: str) -> None:
    r = httpx.get(f"{api}/api/state/snapshot", headers=_headers(token))
    body = r.json()
    click.echo(json.dumps(body.get("head_count", {}), indent=2))
```

- [ ] **Step 19: Add entry point**

If `pyproject.toml` exists, add under `[project.scripts]`:

```toml
vms-cli = "vms.cli.main:cli"
```

Otherwise add to `setup.cfg`:

```ini
[options.entry_points]
console_scripts =
    vms-cli = vms.cli.main:cli
```

- [ ] **Step 20: Run CLI test**

```powershell
pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 21: Run full suite**

```powershell
pytest -v
```

Expected: all PASS.

- [ ] **Step 22: Commit**

```powershell
git add vms/api/routes/state.py vms/api/routes/alerts.py vms/api/routes/anomaly_detectors.py vms/api/routes/maintenance.py vms/api/main.py vms/api/schemas.py vms/api/deps.py vms/cli/ pyproject.toml requirements.txt tests/test_api_state.py tests/test_api_alerts.py tests/test_api_anomaly_detectors.py tests/test_api_maintenance.py tests/test_cli.py
git commit -m "feat(api,cli): add read-only inspection routes + vms-cli for ops inspection"
```

---

## Task 16: Observability — Prometheus metrics, structured logging, end-to-end integration test, final quality gate

**Background:** Phase 2b is feature-complete after Task 15 but not observable. This task adds: (1) a Prometheus metrics endpoint so anomaly rates and detector health are scrapable; (2) structured JSON log records with `camera_id`, `seq_id`, and `alert_id` correlation fields so every alert is traceable; (3) one end-to-end integration test that drives a real `DetectionFrame` through the full stack — `AnomalyOrchestrator` → `AlertFSM` → `alerts` table + `alerts` Redis Stream — without mocking any internal boundary; (4) the final quality gate (`black`, `ruff`, `mypy --strict`, `pytest --cov`); (5) CLAUDE.md update to Phase 2b COMPLETE.

**Files:**
- Create: `vms/observability/__init__.py`
- Create: `vms/observability/metrics.py`
- Create: `vms/observability/logging.py`
- Modify: `vms/anomaly/orchestrator.py`
- Modify: `vms/api/main.py`
- Modify: `requirements.txt`
- Create: `tests/test_observability_metrics.py`
- Create: `tests/test_e2e_anomaly.py`
- Modify: `CLAUDE.md`

---

- [ ] **Step 1: Add prometheus-client dependency**

Add to `requirements.txt`:
```
prometheus-client==0.20.0
```

Install it:
```powershell
pip install prometheus-client==0.20.0
```

---

- [ ] **Step 2: Create `vms/observability/__init__.py`**

```python
"""Observability helpers: Prometheus metrics + structured log adapter."""
```

---

- [ ] **Step 3: Create `vms/observability/metrics.py`**

```python
"""Prometheus metrics registry for VMS.

Counters and gauges are registered once at import time (process-singleton).
Import this module early (before workers start) so metrics are consistent.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, REGISTRY

# ---------------------------------------------------------------------------
# Anomaly / alert metrics
# ---------------------------------------------------------------------------

alerts_fired_total = Counter(
    "vms_alerts_fired_total",
    "Total number of alert events that transitioned to FIRED state.",
    ["alert_type", "camera_id"],
)

alerts_suppressed_total = Counter(
    "vms_alerts_suppressed_total",
    "Alerts suppressed by maintenance windows.",
    ["alert_type"],
)

alerts_deduped_total = Counter(
    "vms_alerts_deduped_total",
    "Alerts skipped inside a dedup window.",
    ["alert_type"],
)

detector_errors_total = Counter(
    "vms_detector_errors_total",
    "Total detector exceptions (each increments the consecutive-error counter).",
    ["detector_name"],
)

detector_disabled_total = Counter(
    "vms_detector_disabled_total",
    "Number of times a detector was auto-disabled after consecutive errors.",
    ["detector_name"],
)

frames_processed_total = Counter(
    "vms_frames_processed_total",
    "Frames consumed by AnomalyOrchestrator.",
    ["camera_id"],
)

# ---------------------------------------------------------------------------
# Head count / zone metrics
# ---------------------------------------------------------------------------

zone_head_count = Gauge(
    "vms_zone_head_count",
    "Current number of unique tracked persons in a zone.",
    ["zone_id"],
)

# ---------------------------------------------------------------------------
# Inference metrics
# ---------------------------------------------------------------------------

inference_latency_seconds = Histogram(
    "vms_inference_latency_seconds",
    "Time from frame capture to DetectionFrame publish (seconds).",
    buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0),
)
```

---

- [ ] **Step 4: Write failing test for metrics**

Create `tests/test_observability_metrics.py`:

```python
"""Smoke-test that metrics objects exist and are incrementable."""
from __future__ import annotations


def test_alerts_fired_counter_exists_and_increments() -> None:
    from vms.observability.metrics import alerts_fired_total

    before = alerts_fired_total.labels(alert_type="INTRUSION", camera_id="1")._value.get()
    alerts_fired_total.labels(alert_type="INTRUSION", camera_id="1").inc()
    after = alerts_fired_total.labels(alert_type="INTRUSION", camera_id="1")._value.get()
    assert after == before + 1.0


def test_zone_head_count_gauge_exists() -> None:
    from vms.observability.metrics import zone_head_count

    zone_head_count.labels(zone_id="42").set(7)
    assert zone_head_count.labels(zone_id="42")._value.get() == 7.0
```

- [ ] **Step 5: Run metrics tests to verify they fail**

```powershell
pytest tests/test_observability_metrics.py -v
```

Expected: FAIL — `vms.observability.metrics` not importable.

- [ ] **Step 6: Run metrics tests to verify they pass** (after Step 3 is done)

```powershell
pytest tests/test_observability_metrics.py -v
```

Expected: PASS.

---

- [ ] **Step 7: Create `vms/observability/logging.py`**

```python
"""Structured log adapter that injects correlation fields.

Usage:
    from vms.observability.logging import get_logger
    logger = get_logger(__name__)
    logger.info("alert fired", camera_id=1, alert_id=42, seq_id=123)

The adapter converts keyword args to JSON `extra` fields, producing one-line
JSON log records when the root handler uses `logging.Formatter` with `%(message)s`.
In development (TTY / plain formatter), the extra fields are appended as k=v.
"""
from __future__ import annotations

import logging
from typing import Any, MutableMapping


class _ContextAdapter(logging.LoggerAdapter):
    """Merges per-call kwargs into the log record's extra dict."""

    def process(
        self, msg: str, kwargs: MutableMapping[str, Any]
    ) -> tuple[str, MutableMapping[str, Any]]:
        extra = dict(self.extra or {})
        # Pull caller-side kwargs that are not standard logging kwargs
        for key in list(kwargs.keys()):
            if key not in ("exc_info", "stack_info", "stacklevel"):
                extra[key] = kwargs.pop(key)
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str, **bound_fields: Any) -> _ContextAdapter:
    """Return a logger adapter with optional pre-bound correlation fields."""
    base = logging.getLogger(name)
    return _ContextAdapter(base, bound_fields)
```

---

- [ ] **Step 8: Wire metrics into `AnomalyOrchestrator`**

In `vms/anomaly/orchestrator.py`, add at the top after existing imports:

```python
from vms.observability import metrics as _m
```

In `process_frame`, increment `frames_processed_total` at the top of the method:

```python
_m.frames_processed_total.labels(camera_id=str(frame.camera_id)).inc()
```

In the per-detector error handler (`except Exception`), increment `detector_errors_total`:

```python
_m.detector_errors_total.labels(detector_name=detector.name).inc()
```

After the auto-disable branch:

```python
_m.detector_disabled_total.labels(detector_name=detector.name).inc()
```

In `AlertFSM.process` (in `vms/anomaly/fsm.py`), after persisting a FIRED alert:

```python
from vms.observability import metrics as _m
_m.alerts_fired_total.labels(alert_type=event.alert_type, camera_id=str(event.camera_id)).inc()
```

After SUPPRESSED decision:

```python
_m.alerts_suppressed_total.labels(alert_type=event.alert_type).inc()
```

After DEDUPED decision:

```python
_m.alerts_deduped_total.labels(alert_type=event.alert_type).inc()
```

---

- [ ] **Step 9: Expose Prometheus `/metrics` endpoint in `vms/api/main.py`**

Add to `vms/api/main.py`:

```python
from prometheus_client import make_asgi_app

# Mount Prometheus metrics endpoint (scrape path for Prometheus server)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

This mounts at `/metrics` (no `/api` prefix — standard Prometheus convention).

---

- [ ] **Step 10: Write the end-to-end integration test**

Create `tests/test_e2e_anomaly.py`:

```python
"""End-to-end integration test: DetectionFrame -> AnomalyOrchestrator -> Alert in DB + stream.

This test uses:
- A real PostgreSQL test DB (vms-test-db fixture from conftest.py)
- fakeredis.aioredis for the async Redis stream
- A real AnomalyOrchestrator (which internally creates AlertFSM + MaintenanceCalendar)
- A synthetic INTRUSION detector that fires deterministically

The test does NOT mock any internal anomaly boundary — it validates the full
pipeline from frame input to persisted Alert row and published stream event.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import fakeredis.aioredis
import pytest
from sqlalchemy.orm import Session

from vms.anomaly.base import AnomalyDetector, AnomalyEvent, DetectorContext, FSMConfig, Severity
from vms.anomaly.orchestrator import AnomalyOrchestrator
from vms.db.models import Alert, Camera, MaintenanceWindow, User
from vms.inference.messages import DetectionFrame, Tracklet


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_user(db_session: Session) -> int:
    user = User(
        username=f"e2e-user-{uuid.uuid4().hex[:8]}",
        password_hash="$2b$12$placeholder",
        role="admin",
    )
    db_session.add(user)
    db_session.flush()
    return user.user_id


def _seed_camera(db_session: Session) -> int:
    cam = Camera(
        name=f"e2e-cam-{uuid.uuid4().hex[:8]}",
        rtsp_url="rtsp://e2e-test",
        capability_tier="FULL",
    )
    db_session.add(cam)
    db_session.flush()
    return cam.camera_id


class _AlwaysFiresDetector(AnomalyDetector):
    """Minimal detector that fires INTRUSION on every frame with >=1 tracklet."""

    alert_type = "INTRUSION"
    severity = Severity.HIGH
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ()

    def should_run(self, ctx: DetectorContext) -> bool:
        return bool(ctx.frame.tracklets)

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        return AnomalyEvent(
            alert_type=self.alert_type,
            severity=Severity.HIGH,
            camera_id=ctx.frame.camera_id,
            zone_id=None,
            global_track_id=uuid.uuid4(),
            person_id=None,
            event_ts=_now_naive(),
            dedup_key=f"e2e:INTRUSION:cam={ctx.frame.camera_id}:{ctx.frame.seq_id}",
            payload={},
        )

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=0, cooldown_ms=0, dedup_window_ms=0)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_e2e_frame_produces_alert_in_db_and_stream(db_session: Session) -> None:
    """Full stack: synthetic frame -> orchestrator -> Alert row in DB."""
    camera_id = _seed_camera(db_session)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    orchestrator = AnomalyOrchestrator(
        redis_client=fake_redis,
        session_factory=lambda: db_session,
        detectors={"INTRUSION": _AlwaysFiresDetector({})},
    )

    frame = DetectionFrame(
        camera_id=camera_id,
        seq_id=1,
        timestamp_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        tracklets=(
            Tracklet(
                local_track_id=1,
                camera_id=camera_id,
                bbox=(10, 20, 100, 200),
                confidence=0.9,
                embedding=tuple([0.1] * 512),
            ),
        ),
        face_embeddings=(),
    )

    await orchestrator.process_frame(frame)
    db_session.flush()

    alert = db_session.query(Alert).filter_by(alert_type="INTRUSION").first()
    assert alert is not None, "Alert row must be persisted in DB"
    assert alert.state == "active"
    assert alert.camera_id == camera_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_e2e_maintenance_suppresses_alert(db_session: Session) -> None:
    """Alerts are suppressed when a ONE_TIME maintenance window covers the camera."""
    from vms.anomaly.maintenance import MaintenanceCalendar

    camera_id = _seed_camera(db_session)
    user_id = _seed_user(db_session)
    now = _now_naive()

    win = MaintenanceWindow(
        name="e2e-suppression-window",
        scope_type="CAMERA",
        scope_id=camera_id,
        schedule_type="ONE_TIME",
        starts_at=now,
        ends_at=datetime(2099, 1, 1),
        created_by=user_id,
    )
    db_session.add(win)
    db_session.flush()

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    calendar = MaintenanceCalendar(session_factory=lambda: db_session)
    calendar.refresh_now()

    orchestrator = AnomalyOrchestrator(
        redis_client=fake_redis,
        session_factory=lambda: db_session,
        detectors={"INTRUSION": _AlwaysFiresDetector({})},
        calendar=calendar,
    )

    frame = DetectionFrame(
        camera_id=camera_id,
        seq_id=2,
        timestamp_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        tracklets=(
            Tracklet(
                local_track_id=2,
                camera_id=camera_id,
                bbox=(0, 0, 50, 100),
                confidence=0.9,
                embedding=tuple([0.1] * 512),
            ),
        ),
        face_embeddings=(),
    )

    await orchestrator.process_frame(frame)
    db_session.flush()

    alert = db_session.query(Alert).filter_by(alert_type="INTRUSION", camera_id=camera_id).first()
    assert alert is None or alert.state == "suppressed", \
        "Alert must not be active when a ONE_TIME maintenance window covers the camera"
```

- [ ] **Step 11: Run E2E integration tests**

```powershell
pytest tests/test_e2e_anomaly.py -v -m integration
```

Expected: both PASS (or SKIP if DB not available in unit-test mode — integration mark).

---

- [ ] **Step 12: Final quality gate**

```powershell
black vms/ tests/
ruff check vms/ tests/
mypy vms/
pytest --cov=vms --cov-report=term-missing -v
```

Expected:
- `black`: no reformatting needed
- `ruff`: clean
- `mypy --strict`: clean
- `pytest`: all pass
- Coverage: `vms/anomaly` >= 80%, `vms/db` >= 80%, `vms/api` >= 80%

---

- [ ] **Step 13: Update CLAUDE.md — Phase 2b COMPLETE**

In `CLAUDE.md §3`, replace the Phase 2b status line:

```markdown
We are at **Phase 2b: Anomaly Framework** (not yet started — plan not written).
```

with:

```markdown
We are at **Phase 3: Profiler + Dispatcher + Audit** (not yet started — plan not written).

**Phase 2b** (Anomaly Framework) is **COMPLETE** — [N] tests passing as of commit `<hash>`. Plan: `docs/superpowers/plans/2026-05-15-vms-v2-phase2b-anomaly-framework.md`.
```

---

- [ ] **Step 14: Commit**

```powershell
git add vms/observability/ vms/anomaly/orchestrator.py vms/anomaly/fsm.py vms/api/main.py requirements.txt tests/test_observability_metrics.py tests/test_e2e_anomaly.py CLAUDE.md
git commit -m "feat(observability): add Prometheus metrics, structured logging, E2E integration test; close Phase 2b"
```

---

## Final Verification (all 16 tasks done)

```powershell
black vms/ tests/
ruff check vms/ tests/
mypy vms/
pytest --cov=vms --cov-report=term-missing -v
```

Expected outcome:
- All tests pass (target: 200+ tests, up from 159)
- `mypy --strict` clean
- `ruff` clean
- Coverage >= 80% on `vms/anomaly`, `vms/db`, `vms/api`

Then update the plan status line to `COMPLETE` and push the plan branch.

---

## Self-Review Checklist

- [x] AnomalyDetector ABC + FSMConfig → Task 3
- [x] Detector registry (load from DB) → Task 4
- [x] MaintenanceCalendar (ONE_TIME + RECURRING, TTL cache) → Task 5
- [x] AlertFSM (sustain + cooldown + dedup + suppression) → Task 6
- [x] UNKNOWN_PERSON detector → Task 7
- [x] PERSON_LOST detector → Task 8
- [x] CROWD_DENSITY detector → Task 9
- [x] INTRUSION detector (allowed_hours) → Task 10
- [x] LOITERING detector (dwell timer) → Task 11
- [x] MoViNet violence model + VIOLENCE detector → Tasks 12 + 13
- [x] HeadCountAggregator → Task 13
- [x] AnomalyOrchestrator (error isolation, auto-disable, seam injection) → Task 14
- [x] Read-only inspection APIs + vms-cli → Task 15
- [x] Prometheus metrics + structured logging + E2E integration test → Task 16
- [x] Backward compat: `DetectionFrame.violence_score` defaults to `None`
- [x] Cascading failure prevention: detector errors isolated; MoViNet absent = None score; maintenance TTL; FSM rebuilt from DB; alerts stream MAXLEN cap
- [x] All seams consistent: `_gid_for_tracklet`, `_person_id_for`, `_registry_last_seen`, `_entered_at`
- [x] TDD rhythm enforced: every task has RED → GREEN → commit
- [x] No frontend dependency: all observable via HTTP routes + CLI

---

## GSTACK REVIEW REPORT

> Reviewed 2026-05-27 by /plan-eng-review. All issues below have been applied directly to this plan file.

### Section 1 — Architecture (5 issues, all FIXED)

| # | Issue | Decision | Applied |
|---|---|---|---|
| A1 | Task 16 E2E test used completely wrong API (wrong constructor signatures for AlertFSM, AnomalyOrchestrator, MaintenanceCalendar; wrong return type for evaluate(); wrong FSMConfig fields) | Rewrote both E2E tests with correct async/await, correct constructors, correct AnomalyEvent fields | Yes |
| A2 | `FSMConfig` mixed units: `sustain_ms` but `cooldown_s`, `dedup_window_s` | Standardised all three to milliseconds: `cooldown_ms`, `dedup_window_ms`. Default values scaled ×1000. ~20 call sites updated. | Yes |
| A3 | `UNKNOWN_PERSON` `dedup_key` included full UUID gid — making per-zone dedup useless (every track got its own key, no deduplication) | Changed to `f"UNKNOWN_PERSON:cam={camera_id}:zone={zone_id}"` — one active alert per zone | Yes |
| A4 | `_gid_for_tracklet` default stub returned `next(iter(active_track_zones))` ignoring `tl` — wrong gid silently injected; misleading docstring claimed it matched orchestrator | Changed to `return None` (safe no-op). Updated docstring. | Yes |
| A5 | Seam injection used `hasattr(det, "_gid_for_tracklet")` — fragile duck-typing, not mypy-checkable | Added `@runtime_checkable class SeamProvider(Protocol)` to `base.py`. Updated `_bind_seams` to `isinstance(det, SeamProvider)`. Updated UnknownPersonDetector, PersonLostDetector, LoiteringDetector to inherit `SeamProvider`. | Yes |

### Section 2 — Code Quality (2 issues)

| # | Issue | Decision | Applied |
|---|---|---|---|
| C1 | `AlertFSM.process()` doesn't consume `cooldown_ms`/`dedup_window_ms` — fields defined but unused | Intentional: VMS uses operator-resolution model (no auto-expiry). Added clarifying comment to `process()` explaining this. Fields reserved for future time-based path. | Yes |
| C2 | Task 6 background had no pre-requisite note — implementors could run Task 6 before Task 1 migration, silently losing dedup_key writes | Added explicit prerequisite note to Task 6 background box | Yes |

### Section 3 — Tests (1 issue)

| # | Issue | Decision | Applied |
|---|---|---|---|
| T1 | `AlertFSM.evict_closed()` had no test for the full "fire → resolve → evict → re-fire" lifecycle; orchestrator `run()` never called `evict_closed()` — FSM entries accumulate forever | Added `test_evict_closed_removes_resolved_entry_and_allows_new_fire` to Task 6. Added periodic `evict_closed()` call every 100 frames in `orchestrator.run()`. | Yes |

### Section 4 — Performance (1 issue)

| # | Issue | Decision | Applied |
|---|---|---|---|
| P1 | `SELECT state FROM alerts WHERE state = 'active'` in `rebuild_from_db()` and `evict_closed()` had no index on `alerts.state` | Added `ix_alerts_state` to Task 1 migration `upgrade()` and `downgrade()` | Yes |

### NOT in scope for this review

- Frontend (Phase 4 — no plan yet)
- Alert dispatcher (Phase 3 — separate plan)
- FAISS drift reconciliation (Phase 2a, already complete)
- Camera profiler (Phase 3)

### What already exists (no changes needed)

- `MaintenanceWindow` model with all 5 CHECK constraints — already in `vms/db/models.py`
- `AnomalyDetector` registry rows — already in `vms/db/models.py`
- `Alert` model with `chk_alert_resolution_order`, `ix_alerts_alert_type`, `ix_alerts_triggered_at` — already present
