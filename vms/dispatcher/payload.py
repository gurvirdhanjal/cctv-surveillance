"""AlertPayload DTO — the rich per-alert data passed to channel senders."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AlertPayload:
    alert_id: int
    alert_type: str
    severity: str
    # camera_id is None for SYSTEM_CRITICAL alerts
    camera_id: int | None
    camera_name: str
    zone_id: int | None
    zone_name: str | None
    global_track_id: str | None
    person_id: int | None
    triggered_at: datetime
    schema_version: str = "1"

    def to_webhook_dict(self) -> dict[str, object]:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "triggered_at": self.triggered_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "global_track_id": self.global_track_id,
            "person_id": self.person_id,
            "schema_version": self.schema_version,
        }


def from_stream_fields(
    fields: dict[str, str],
    *,
    camera_name: str,
    zone_name: str | None,
) -> AlertPayload:
    """Parse a Redis stream message into an AlertPayload.

    The anomaly orchestrator publishes alerts as {"payload": json_string}.
    camera_name and zone_name are enriched by the caller from a DB lookup.
    """
    if "payload" not in fields:
        raise ValueError("Stream message missing 'payload' key")
    data: dict[str, object] = json.loads(fields["payload"])

    ts_str = str(data["triggered_at"])
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    triggered_at = datetime.fromisoformat(ts_str).replace(tzinfo=None)

    return AlertPayload(
        alert_id=int(data["alert_id"]),  # type: ignore[call-overload]
        alert_type=str(data["alert_type"]),
        severity=str(data["severity"]),
        camera_id=int(data["camera_id"]),  # type: ignore[call-overload]
        camera_name=camera_name,
        zone_id=int(data["zone_id"]) if data.get("zone_id") is not None else None,  # type: ignore[call-overload]
        zone_name=zone_name,
        global_track_id=str(data["global_track_id"]) if data.get("global_track_id") else None,
        person_id=int(data["person_id"]) if data.get("person_id") is not None else None,  # type: ignore[call-overload]
        triggered_at=triggered_at,
    )
