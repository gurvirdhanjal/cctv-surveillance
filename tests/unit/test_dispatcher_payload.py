"""Tests for AlertPayload and config dispatcher settings.

Note: Run with pytest tests/unit/ to avoid DB fixture issues.
"""

from __future__ import annotations

from datetime import datetime


def test_alertpayload_structure() -> None:
    """AlertPayload must have all required fields."""
    from vms.dispatcher.payload import AlertPayload

    payload = AlertPayload(
        alert_id=1,
        alert_type="INTRUSION",
        severity="HIGH",
        camera_id=1,
        camera_name="Entrance",
        zone_id=1,
        zone_name="Zone A",
        global_track_id="gid123",
        person_id=1,
        triggered_at=datetime(2026, 1, 1),
    )
    assert payload.alert_id == 1
    assert payload.alert_type == "INTRUSION"
    assert payload.severity == "HIGH"
    assert payload.schema_version == "1"
