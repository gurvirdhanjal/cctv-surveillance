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

    def _gid_for_tracklet(self, tl: Any, ctx: DetectorContext) -> uuid.UUID | None:
        return None

    def _person_id_for(self, gid: uuid.UUID, ctx: DetectorContext) -> int | None:
        return None

    def _registry_last_seen(self, ctx: DetectorContext) -> dict[uuid.UUID, int]:
        return {}

    def _entered_at(self, gid: uuid.UUID, zone_id: int, ctx: DetectorContext) -> datetime | None:
        return None
