"""Channel sender implementations for the AlertDispatcher.

Each sender raises ChannelError on failure — the worker handles retries.
The WEBSOCKET channel is handled by the anomaly orchestrator; skip it here.
"""

from __future__ import annotations

import asyncio
import email.mime.text as mime_text
import hashlib
import hmac
import json
import logging
import smtplib
from typing import Protocol, runtime_checkable

import httpx

from vms.dispatcher.payload import AlertPayload

logger = logging.getLogger(__name__)


class ChannelError(Exception):
    """Raised by a sender when delivery fails (retryable)."""


@runtime_checkable
class ChannelSender(Protocol):
    async def send(self, payload: AlertPayload, target: str) -> None:
        """Deliver the alert to the given target. Raises ChannelError on failure."""
        ...


class WebhookSender:
    """POST JSON payload to a URL signed with HMAC-SHA256."""

    def __init__(self, secret: str) -> None:
        self._secret = secret.encode()

    async def send(self, payload: AlertPayload, target: str) -> None:
        body = json.dumps(payload.to_webhook_dict(), default=str).encode()
        sig = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    target,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-VMS-Signature": f"sha256={sig}",
                    },
                )
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ChannelError(f"webhook POST failed: {exc}") from exc


class SlackSender:
    """Post to a Slack channel via the Web API."""

    SLACK_API = "https://api.slack.com/api/chat.postMessage"

    def __init__(self, token: str) -> None:
        self._token = token

    async def send(self, payload: AlertPayload, target: str) -> None:
        text = (
            f"[{payload.severity}] {payload.alert_type} on {payload.camera_name}"
            + (f" / {payload.zone_name}" if payload.zone_name else "")
            + f" at {payload.triggered_at.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            + f"  (alert_id={payload.alert_id})"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self.SLACK_API,
                    json={"channel": target, "text": text},
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    raise ChannelError(f"Slack error: {data.get('error', 'unknown')}")
        except httpx.HTTPError as exc:
            raise ChannelError(f"slack POST failed: {exc}") from exc


class TelegramSender:
    """Send a Telegram message via the Bot API."""

    def __init__(self, token: str) -> None:
        self._token = token

    async def send(self, payload: AlertPayload, target: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        text = (
            f"[{payload.severity}] {payload.alert_type}\n"
            f"Camera: {payload.camera_name}"
            + (f"\nZone: {payload.zone_name}" if payload.zone_name else "")
            + f"\nTime: {payload.triggered_at.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            + f"\nAlert ID: {payload.alert_id}"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json={"chat_id": target, "text": text},
                )
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ChannelError(f"telegram sendMessage failed: {exc}") from exc


class EmailSender:
    """Send an alert email via SMTP (runs in a thread to avoid blocking)."""

    def __init__(self, host: str, port: int, from_addr: str, user: str, password: str) -> None:
        self._host = host
        self._port = port
        self._from = from_addr
        self._user = user
        self._password = password

    async def send(self, payload: AlertPayload, target: str) -> None:
        subject = f"[VMS {payload.severity}] {payload.alert_type} — {payload.camera_name}"
        body = (
            f"Alert type : {payload.alert_type}\n"
            f"Severity   : {payload.severity}\n"
            f"Camera     : {payload.camera_name} (id={payload.camera_id})\n"
            f"Zone       : {payload.zone_name or 'N/A'}\n"
            f"Time (UTC) : {payload.triggered_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Alert ID   : {payload.alert_id}\n"
        )
        msg = mime_text.MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = target

        def _send_sync() -> None:
            with smtplib.SMTP(self._host, self._port) as smtp:
                smtp.starttls()
                smtp.login(self._user, self._password)
                smtp.send_message(msg)

        try:
            await asyncio.to_thread(_send_sync)
        except Exception as exc:
            raise ChannelError(f"email SMTP failed: {exc}") from exc
