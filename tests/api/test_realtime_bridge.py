"""Tests for the Redis → Socket.io bridge — §10 event shapes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from vms.api.realtime.bridge import _emit_alert
from vms.api.realtime.server import sio


async def test_alert_stream_event_emits_alert_fired() -> None:
    event = {
        "alert_id": "42",
        "alert_type": "INTRUSION",
        "severity": "HIGH",
        "camera_id": "5",
        "zone_id": "3",
        "global_track_id": "gid_abc",
        "snapshot_url": "/media/snap.jpg",
        "ts": "2026-06-24T10:00:00",
    }
    with patch.object(sio, "emit", new_callable=AsyncMock) as mock_emit:
        await _emit_alert(event)
    mock_emit.assert_called_once()
    event_name, payload = mock_emit.call_args[0]
    assert event_name == "alert_fired"
    assert payload["alert_id"] == 42
    assert payload["alert_type"] == "INTRUSION"
    assert payload["severity"] == "HIGH"
    assert payload["camera_id"] == 5
    assert payload["zone_id"] == 3
    assert payload["global_track_id"] == "gid_abc"
    assert payload["snapshot_url"] == "/media/snap.jpg"


async def test_alert_stream_event_none_camera_stays_none() -> None:
    event = {
        "alert_id": "1",
        "alert_type": "SYSTEM_CRITICAL",
        "severity": "CRITICAL",
        "ts": "2026-06-24T10:00:00",
    }
    with patch.object(sio, "emit", new_callable=AsyncMock) as mock_emit:
        await _emit_alert(event)
    _, payload = mock_emit.call_args[0]
    assert payload["camera_id"] is None
    assert payload["zone_id"] is None
    assert payload["global_track_id"] is None


async def test_alert_fired_payload_has_all_spec_fields() -> None:
    event = {"alert_id": "1", "alert_type": "X", "severity": "LOW", "ts": "t"}
    with patch.object(sio, "emit", new_callable=AsyncMock) as mock_emit:
        await _emit_alert(event)
    _, payload = mock_emit.call_args[0]
    required = {
        "alert_id",
        "alert_type",
        "severity",
        "camera_id",
        "zone_id",
        "global_track_id",
        "snapshot_url",
        "ts",
    }
    assert required.issubset(payload.keys())
