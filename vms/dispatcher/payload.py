"""AlertPayload DTO — populated when Task 2 is complete."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AlertPayload:
    alert_id: int
    alert_type: str
    severity: str
    camera_id: int
    camera_name: str
    zone_id: int | None
    zone_name: str | None
    global_track_id: str | None
    person_id: int | None
    triggered_at: datetime
    schema_version: str = "1"
