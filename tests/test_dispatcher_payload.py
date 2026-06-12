"""Tests for AlertPayload and config dispatcher settings."""

from __future__ import annotations

import pytest

from vms.dispatcher.payload import AlertPayload


def test_config_has_dispatcher_settings() -> None:
    """Config must declare all required dispatcher env vars."""
    import os
    os.environ.setdefault("VMS_DB_URL", "postgresql://x/y")
    os.environ.setdefault("VMS_JWT_SECRET", "test")
    from vms.config import Settings
    s = Settings()
    assert hasattr(s, "smtp_host")
    assert hasattr(s, "smtp_port")
    assert hasattr(s, "smtp_from")
    assert hasattr(s, "smtp_user")
    assert hasattr(s, "smtp_password")
    assert hasattr(s, "slack_bot_token")
    assert hasattr(s, "telegram_bot_token")
    assert hasattr(s, "webhook_secret")
    assert s.smtp_host == ""          # default is disabled
    assert s.slack_bot_token == ""
    assert s.telegram_bot_token == ""
    assert s.webhook_secret == ""


def test_alert_payload_from_stream_fields_parses_full_message() -> None:
    """from_stream_fields parses JSON and returns an AlertPayload."""
    import json
    from datetime import datetime, timezone

    from vms.dispatcher.payload import AlertPayload, from_stream_fields

    fields = {
        "payload": json.dumps({
            "alert_id": 42,
            "alert_type": "VIOLENCE",
            "severity": "CRITICAL",
            "camera_id": 7,
            "zone_id": 3,
            "global_track_id": "8f42a1b2-c3d4-e5f6-0000-000000000001",
            "person_id": None,
            "triggered_at": "2026-06-01T10:00:00.000Z",
        })
    }
    result = from_stream_fields(
        fields,
        camera_name="Loading Bay 2",
        zone_name="Loading Bay",
    )
    assert isinstance(result, AlertPayload)
    assert result.alert_id == 42
    assert result.alert_type == "VIOLENCE"
    assert result.severity == "CRITICAL"
    assert result.camera_id == 7
    assert result.camera_name == "Loading Bay 2"
    assert result.zone_id == 3
    assert result.zone_name == "Loading Bay"
    assert result.global_track_id == "8f42a1b2-c3d4-e5f6-0000-000000000001"
    assert result.person_id is None
    assert isinstance(result.triggered_at, datetime)


def test_alert_payload_from_stream_fields_handles_null_zone() -> None:
    """from_stream_fields handles zone_id=None gracefully."""
    import json
    from vms.dispatcher.payload import from_stream_fields

    fields = {
        "payload": json.dumps({
            "alert_id": 1,
            "alert_type": "INTRUSION",
            "severity": "HIGH",
            "camera_id": 2,
            "zone_id": None,
            "global_track_id": None,
            "person_id": None,
            "triggered_at": "2026-06-01T10:00:00.000Z",
        })
    }
    result = from_stream_fields(fields, camera_name="Gate 1", zone_name=None)
    assert result.zone_id is None
    assert result.zone_name is None


def test_alert_payload_from_stream_fields_raises_on_missing_payload_key() -> None:
    """from_stream_fields raises ValueError if 'payload' key is absent."""
    import pytest
    from vms.dispatcher.payload import from_stream_fields

    with pytest.raises(ValueError, match="missing 'payload'"):
        from_stream_fields({}, camera_name="x", zone_name=None)
