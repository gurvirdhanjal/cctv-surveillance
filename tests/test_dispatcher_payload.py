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
