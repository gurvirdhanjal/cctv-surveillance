"""BLE badge event DTOs."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class BleEvent:
    """One RSSI reading from a BLE reader for one badge."""

    badge_id: str  # Bluetooth MAC address of employee badge
    reader_id: str  # MAC address or name of the fixed BLE reader
    rssi: int  # signal strength dBm (e.g. -65)
    timestamp_ms: int  # UTC epoch milliseconds

    def to_redis_fields(self) -> dict[str, str]:
        return {
            "badge_id": self.badge_id,
            "reader_id": self.reader_id,
            "rssi": str(self.rssi),
            "timestamp_ms": str(self.timestamp_ms),
        }

    @classmethod
    def from_redis_fields(cls, fields: dict[str, str]) -> BleEvent:
        return cls(
            badge_id=fields["badge_id"],
            reader_id=fields["reader_id"],
            rssi=int(fields["rssi"]),
            timestamp_ms=int(fields["timestamp_ms"]),
        )

    @classmethod
    def from_mqtt_payload(cls, payload: str, timestamp_ms: int) -> BleEvent:
        """Parse JSON MQTT payload: {"badge_id":"AA:BB:..","reader_id":"..","rssi":-65}."""
        data: dict[str, object] = json.loads(payload)
        return cls(
            badge_id=str(data["badge_id"]),
            reader_id=str(data["reader_id"]),
            rssi=int(str(data["rssi"])),
            timestamp_ms=timestamp_ms,
        )
