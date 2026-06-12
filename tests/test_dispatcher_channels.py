"""Unit tests for channel senders."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vms.dispatcher.channels import (
    ChannelError,
    EmailSender,
    SlackSender,
    TelegramSender,
    WebhookSender,
)
from vms.dispatcher.payload import AlertPayload

_PAYLOAD = AlertPayload(
    alert_id=1,
    alert_type="VIOLENCE",
    severity="CRITICAL",
    camera_id=7,
    camera_name="Loading Bay",
    zone_id=3,
    zone_name="Dock",
    global_track_id="abc",
    person_id=None,
    triggered_at=datetime(2026, 6, 1, 10, 0, 0),
)


def test_webhook_sender_posts_with_hmac_signature() -> None:
    """WebhookSender POSTs JSON with X-VMS-Signature header."""
    import asyncio

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("vms.dispatcher.channels.httpx.AsyncClient", return_value=mock_client):
        sender = WebhookSender(secret="mysecret")
        asyncio.get_event_loop().run_until_complete(
            sender.send(_PAYLOAD, "https://example.com/webhook")
        )

    call_kwargs = mock_client.post.call_args
    headers = call_kwargs.kwargs["headers"]
    body_bytes = call_kwargs.kwargs["content"]

    sig_header = headers["X-VMS-Signature"]
    assert sig_header.startswith("sha256=")
    expected_sig = hmac.new(b"mysecret", body_bytes, hashlib.sha256).hexdigest()
    assert sig_header == f"sha256={expected_sig}"
    body = json.loads(body_bytes)
    assert body["alert_id"] == 1


def test_webhook_sender_raises_channel_error_on_http_error() -> None:
    """WebhookSender wraps HTTP errors in ChannelError."""
    import asyncio

    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )
    )

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("vms.dispatcher.channels.httpx.AsyncClient", return_value=mock_client):
        sender = WebhookSender(secret="s")
        with pytest.raises(ChannelError, match="webhook"):
            asyncio.get_event_loop().run_until_complete(
                sender.send(_PAYLOAD, "https://example.com/webhook")
            )


def test_slack_sender_posts_to_channel() -> None:
    """SlackSender calls Slack Web API with bearer token."""
    import asyncio

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"ok": True})
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("vms.dispatcher.channels.httpx.AsyncClient", return_value=mock_client):
        sender = SlackSender(token="xoxb-test-token")
        asyncio.get_event_loop().run_until_complete(sender.send(_PAYLOAD, "#security-alerts"))

    call_kwargs = mock_client.post.call_args
    assert "api.slack.com" in call_kwargs.args[0]
    headers = call_kwargs.kwargs["headers"]
    assert headers["Authorization"] == "Bearer xoxb-test-token"
    body = call_kwargs.kwargs["json"]
    assert body["channel"] == "#security-alerts"
    assert "VIOLENCE" in body["text"]


def test_telegram_sender_sends_message() -> None:
    """TelegramSender calls Telegram Bot API."""
    import asyncio

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("vms.dispatcher.channels.httpx.AsyncClient", return_value=mock_client):
        sender = TelegramSender(token="bot123:ABC")
        asyncio.get_event_loop().run_until_complete(sender.send(_PAYLOAD, "-1001234567890"))

    call_kwargs = mock_client.post.call_args
    assert "bot123:ABC" in call_kwargs.args[0]
    assert "sendMessage" in call_kwargs.args[0]
    body = call_kwargs.kwargs["json"]
    assert body["chat_id"] == "-1001234567890"
    assert "VIOLENCE" in body["text"]


def test_email_sender_raises_channel_error_on_smtp_failure() -> None:
    """EmailSender wraps SMTP errors in ChannelError."""
    import asyncio
    import smtplib

    with patch(
        "vms.dispatcher.channels.asyncio.to_thread",
        side_effect=smtplib.SMTPException("conn refused"),
    ):
        sender = EmailSender(
            host="smtp.example.com", port=587, from_addr="vms@example.com", user="u", password="p"
        )
        with pytest.raises(ChannelError, match="email"):
            asyncio.get_event_loop().run_until_complete(sender.send(_PAYLOAD, "guard@example.com"))
