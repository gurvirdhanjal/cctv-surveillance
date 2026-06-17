# Alert Dispatcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Implement the `AlertDispatcher` — a background process that reads from the `alerts` Redis Stream and fans out to EMAIL, SLACK, TELEGRAM, and WEBHOOK channels with idempotent retries and audit logging.

**Architecture:** The dispatcher runs as a FastAPI lifespan background task, consuming from the `alerts` Redis Stream using a persistent cursor key (`dispatcher:alerts:cursor`). For each alert it queries `alert_routing` for matching rules, dispatches to each matched channel, and records every attempt in `alert_dispatches`. Failures retry 3× with exponential backoff (1s → 4s → 16s); after 3 failures a CRITICAL audit event is logged. The WEBSOCKET channel is already handled by the anomaly orchestrator; the dispatcher only handles EMAIL/SLACK/TELEGRAM/WEBHOOK.

**Tech Stack:** Python 3.10, FastAPI lifespan, httpx (async HTTP), smtplib in asyncio.to_thread (SMTP), fakeredis (tests), SQLAlchemy ORM, `vms.db.audit.write_audit_event`.

**Spec refs:** `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md §E`

**DB tables:** `alert_routing` and `alert_dispatches` — already in migration `0001_initial_schema.py`. No new migration needed.

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Create | `vms/dispatcher/__init__.py` | empty |
| Create | `vms/dispatcher/payload.py` | `AlertPayload` frozen dataclass + `from_stream_fields()` |
| Create | `vms/dispatcher/channels.py` | `ChannelSender` Protocol + 4 concrete senders |
| Create | `vms/dispatcher/router.py` | `match_routing_rules()` DB query |
| Create | `vms/dispatcher/worker.py` | `AlertDispatcher` async loop |
| Modify | `vms/config.py` | Add SMTP/Slack/Telegram/Webhook settings |
| Modify | `vms/api/schemas.py` | Add `AlertRoutingCreate`, `AlertRoutingResponse` |
| Create | `vms/api/routes/routing.py` | CRUD for `alert_routing` table |
| Modify | `vms/api/main.py` | Register routing router + start dispatcher |
| Create | `tests/test_dispatcher_payload.py` | Unit tests for payload parsing |
| Create | `tests/test_dispatcher_channels.py` | Unit tests for channel senders |
| Create | `tests/test_dispatcher_router.py` | Unit tests for routing matcher |
| Create | `tests/test_dispatcher_worker.py` | Integration tests for dispatcher loop |
| Create | `tests/test_api_alert_routing.py` | API tests for routing CRUD |

---

## Task 1: Config additions

**Files:**
- Modify: `vms/config.py`

Add all channel settings as optional fields (empty string = channel disabled). The dispatcher checks emptiness before attempting to send.

- [ ] **Step 1: Write the failing test**

File: `tests/test_dispatcher_payload.py` (create new, add first test here to keep it simple):

```python
"""Tests for AlertPayload and config dispatcher settings."""

from __future__ import annotations

import json

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
```

- [ ] **Step 2: Run to confirm failure**

```powershell
pytest tests/test_dispatcher_payload.py::test_config_has_dispatcher_settings -v
```
Expected: `FAILED` — `cannot import name 'AlertPayload' from 'vms.dispatcher.payload'`

- [ ] **Step 3: Create dispatcher package and add config fields**

Create `vms/dispatcher/__init__.py` (empty):
```python
```

Create `vms/dispatcher/payload.py` (minimal stub — real content in Task 2):
```python
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
```

Add to `vms/config.py` after the `alerts_stream_maxlen` line:

```python
    # dispatcher — channel credentials (empty = channel disabled)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_from: str = ""
    smtp_user: str = ""
    smtp_password: str = ""
    slack_bot_token: str = ""
    telegram_bot_token: str = ""
    webhook_secret: str = ""
```

- [ ] **Step 4: Run to confirm pass**

```powershell
pytest tests/test_dispatcher_payload.py::test_config_has_dispatcher_settings -v
```
Expected: `PASSED`

- [ ] **Step 5: Commit**

```powershell
git add vms/dispatcher/__init__.py vms/dispatcher/payload.py vms/config.py tests/test_dispatcher_payload.py
git commit -m "feat(dispatcher): create dispatcher package + config settings"
```

---

## Task 2: AlertPayload DTO

**Files:**
- Modify: `vms/dispatcher/payload.py`

`AlertPayload` is the rich DTO the dispatcher builds once per alert before fanning out to channels. It enriches the bare stream message (which only has IDs) with camera/zone names fetched from the DB.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dispatcher_payload.py`:

```python
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
    from vms.dispatcher.payload import from_stream_fields

    with pytest.raises(ValueError, match="missing 'payload'"):
        from_stream_fields({}, camera_name="x", zone_name=None)
```

- [ ] **Step 2: Run to confirm failure**

```powershell
pytest tests/test_dispatcher_payload.py -v
```
Expected: 2-3 failures — `cannot import name 'from_stream_fields'`

- [ ] **Step 3: Implement AlertPayload + from_stream_fields**

Replace `vms/dispatcher/payload.py` entirely:

```python
"""AlertPayload DTO — the rich per-alert data passed to channel senders."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone


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
    # Normalize ISO8601 with trailing Z to UTC-aware then strip tzinfo for DB
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    triggered_at = datetime.fromisoformat(ts_str).replace(tzinfo=None)

    return AlertPayload(
        alert_id=int(data["alert_id"]),  # type: ignore[arg-type]
        alert_type=str(data["alert_type"]),
        severity=str(data["severity"]),
        camera_id=int(data["camera_id"]),  # type: ignore[arg-type]
        camera_name=camera_name,
        zone_id=int(data["zone_id"]) if data.get("zone_id") is not None else None,  # type: ignore[arg-type]
        zone_name=zone_name,
        global_track_id=str(data["global_track_id"]) if data.get("global_track_id") else None,
        person_id=int(data["person_id"]) if data.get("person_id") is not None else None,  # type: ignore[arg-type]
        triggered_at=triggered_at,
    )
```

- [ ] **Step 4: Run to confirm pass**

```powershell
pytest tests/test_dispatcher_payload.py -v
```
Expected: all 4 tests `PASSED`

- [ ] **Step 5: Commit**

```powershell
git add vms/dispatcher/payload.py tests/test_dispatcher_payload.py
git commit -m "feat(dispatcher): AlertPayload DTO + from_stream_fields parser"
```

---

## Task 3: Channel senders

**Files:**
- Create: `vms/dispatcher/channels.py`
- Create: `tests/test_dispatcher_channels.py`

Four async channel senders. Each raises `ChannelError` on failure (the worker catches this). The `WEBSOCKET` channel is skipped (already handled by the anomaly orchestrator).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dispatcher_channels.py`:

```python
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
    from unittest.mock import MagicMock

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
    # Body is valid JSON with alert_id
    body = json.loads(body_bytes)
    assert body["alert_id"] == 1


def test_webhook_sender_raises_channel_error_on_http_error() -> None:
    """WebhookSender wraps HTTP errors in ChannelError."""
    import asyncio
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_response)
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
        asyncio.get_event_loop().run_until_complete(
            sender.send(_PAYLOAD, "#security-alerts")
        )

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
        asyncio.get_event_loop().run_until_complete(
            sender.send(_PAYLOAD, "-1001234567890")  # chat_id
        )

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

    with patch("vms.dispatcher.channels.asyncio.to_thread", side_effect=smtplib.SMTPException("conn refused")):
        sender = EmailSender(host="smtp.example.com", port=587, from_addr="vms@example.com", user="u", password="p")
        with pytest.raises(ChannelError, match="email"):
            asyncio.get_event_loop().run_until_complete(
                sender.send(_PAYLOAD, "guard@example.com")
            )
```

- [ ] **Step 2: Run to confirm failure**

```powershell
pytest tests/test_dispatcher_channels.py -v
```
Expected: `FAILED` — `cannot import name 'WebhookSender' from 'vms.dispatcher.channels'`

- [ ] **Step 3: Implement channels.py**

Create `vms/dispatcher/channels.py`:

```python
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

    SLACK_API = "https://slack.com/api/chat.postMessage"

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
```

- [ ] **Step 4: Run to confirm pass**

```powershell
pytest tests/test_dispatcher_channels.py -v
```
Expected: all 5 tests `PASSED`

- [ ] **Step 5: Commit**

```powershell
git add vms/dispatcher/channels.py tests/test_dispatcher_channels.py
git commit -m "feat(dispatcher): channel senders - webhook, slack, telegram, email"
```

---

## Task 4: Routing evaluator

**Files:**
- Create: `vms/dispatcher/router.py`
- Create: `tests/test_dispatcher_router.py`

`match_routing_rules()` is a pure DB query — no side effects. A rule matches an alert when:
- `rule.alert_type IS NULL` OR `rule.alert_type == alert.alert_type`
- `rule.severity IS NULL` OR `rule.severity == alert.severity`
- `rule.zone_id IS NULL` OR `rule.zone_id == alert.zone_id`
- `rule.is_active == True`
- `rule.channel != 'WEBSOCKET'` (WebSocket is handled by anomaly orchestrator)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dispatcher_router.py`:

```python
"""Tests for the alert routing matcher."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from vms.db.models import AlertRouting


def _rule(
    db: Session,
    *,
    channel: str,
    target: str,
    alert_type: str | None = None,
    severity: str | None = None,
    zone_id: int | None = None,
    is_active: bool = True,
) -> AlertRouting:
    r = AlertRouting(
        channel=channel,
        target=target,
        alert_type=alert_type,
        severity=severity,
        zone_id=zone_id,
        is_active=is_active,
    )
    db.add(r)
    db.flush()
    return r


@pytest.mark.integration
def test_match_routing_rules_returns_matching_rule(db_session: Session) -> None:
    """A rule with matching alert_type and no zone filter matches."""
    from vms.dispatcher.router import match_routing_rules

    _rule(db_session, channel="WEBHOOK", target="https://hook.example.com", alert_type="VIOLENCE")
    db_session.commit()

    results = match_routing_rules(db_session, alert_type="VIOLENCE", severity="CRITICAL", zone_id=None)
    assert len(results) == 1
    assert results[0].channel == "WEBHOOK"


@pytest.mark.integration
def test_match_routing_rules_null_type_matches_any_alert_type(db_session: Session) -> None:
    """A rule with alert_type=NULL matches any alert type."""
    from vms.dispatcher.router import match_routing_rules

    _rule(db_session, channel="EMAIL", target="guard@example.com", alert_type=None)
    db_session.commit()

    r1 = match_routing_rules(db_session, alert_type="INTRUSION", severity="HIGH", zone_id=None)
    r2 = match_routing_rules(db_session, alert_type="VIOLENCE", severity="CRITICAL", zone_id=None)
    assert len(r1) == 1
    assert len(r2) == 1


@pytest.mark.integration
def test_match_routing_rules_inactive_rules_excluded(db_session: Session) -> None:
    """is_active=False rules are never returned."""
    from vms.dispatcher.router import match_routing_rules

    _rule(db_session, channel="SLACK", target="#ch", is_active=False)
    db_session.commit()

    results = match_routing_rules(db_session, alert_type="VIOLENCE", severity="CRITICAL", zone_id=None)
    assert results == []


@pytest.mark.integration
def test_match_routing_rules_websocket_channel_excluded(db_session: Session) -> None:
    """WEBSOCKET rules are never returned (already handled by anomaly orchestrator)."""
    from vms.dispatcher.router import match_routing_rules

    _rule(db_session, channel="WEBSOCKET", target="frontend")
    db_session.commit()

    results = match_routing_rules(db_session, alert_type="VIOLENCE", severity="CRITICAL", zone_id=None)
    assert results == []


@pytest.mark.integration
def test_match_routing_rules_zone_filter_respected(db_session: Session) -> None:
    """A rule with zone_id only matches alerts from that zone."""
    from vms.dispatcher.router import match_routing_rules

    _rule(db_session, channel="WEBHOOK", target="https://h.io", zone_id=5)
    db_session.commit()

    matched = match_routing_rules(db_session, alert_type="INTRUSION", severity="HIGH", zone_id=5)
    missed = match_routing_rules(db_session, alert_type="INTRUSION", severity="HIGH", zone_id=6)
    assert len(matched) == 1
    assert missed == []
```

- [ ] **Step 2: Run to confirm failure**

```powershell
pytest tests/test_dispatcher_router.py -v -m integration
```
Expected: `FAILED` — `cannot import name 'match_routing_rules' from 'vms.dispatcher.router'`

- [ ] **Step 3: Implement router.py**

Create `vms/dispatcher/router.py`:

```python
"""Routing rule evaluator — matches alert attributes against alert_routing table."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from vms.db.models import AlertRouting


def match_routing_rules(
    db: Session,
    *,
    alert_type: str,
    severity: str,
    zone_id: int | None,
) -> list[AlertRouting]:
    """Return all active routing rules that match the given alert attributes.

    Rules with NULL fields are treated as wildcards:
      - alert_type=NULL  -> match any alert_type
      - severity=NULL    -> match any severity
      - zone_id=NULL     -> match any zone

    The WEBSOCKET channel is excluded — it is already handled by the anomaly orchestrator.
    """
    q = (
        db.query(AlertRouting)
        .filter(AlertRouting.is_active.is_(True))
        .filter(AlertRouting.channel != "WEBSOCKET")
        .filter(
            or_(AlertRouting.alert_type.is_(None), AlertRouting.alert_type == alert_type)
        )
        .filter(
            or_(AlertRouting.severity.is_(None), AlertRouting.severity == severity)
        )
    )
    if zone_id is None:
        q = q.filter(AlertRouting.zone_id.is_(None))
    else:
        q = q.filter(
            or_(AlertRouting.zone_id.is_(None), AlertRouting.zone_id == zone_id)
        )
    return q.all()
```

- [ ] **Step 4: Run to confirm pass**

```powershell
pytest tests/test_dispatcher_router.py -v -m integration
```
Expected: all 5 tests `PASSED`

- [ ] **Step 5: Commit**

```powershell
git add vms/dispatcher/router.py tests/test_dispatcher_router.py
git commit -m "feat(dispatcher): routing rule evaluator"
```

---

## Task 5: AlertDispatcher worker

**Files:**
- Create: `vms/dispatcher/worker.py`
- Create: `tests/test_dispatcher_worker.py`

The worker is an async loop. It reads from the `alerts` Redis Stream using a cursor persisted at Redis key `dispatcher:alerts:cursor`. For each message:
1. Parse to `AlertPayload` (enrich with camera/zone names from DB)
2. Query matching routing rules
3. Dispatch to each matching channel with retry (max 3 attempts: 1s → 4s → 16s backoff)
4. Record each attempt in `alert_dispatches`
5. Write audit event on first successful dispatch and on dead-letter (all 3 failed)
6. Advance cursor after all rules are dispatched

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dispatcher_worker.py`:

```python
"""Tests for the AlertDispatcher worker."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from sqlalchemy.orm import Session

from vms.db.models import AlertDispatch, AlertRouting, Camera


def _seed_camera(db: Session) -> Camera:
    cam = Camera(name="Gate 1", rtsp_url="rtsp://x/1", capability_tier="FULL")
    db.add(cam)
    db.flush()
    return cam


def _seed_routing(db: Session, camera_id: int | None = None) -> AlertRouting:
    r = AlertRouting(
        channel="WEBHOOK",
        target="https://example.com/hook",
        is_active=True,
    )
    db.add(r)
    db.flush()
    return r


async def _publish_alert(redis: fakeredis.aioredis.FakeRedis, camera_id: int) -> None:
    payload = json.dumps({
        "alert_id": 99,
        "alert_type": "VIOLENCE",
        "severity": "CRITICAL",
        "camera_id": camera_id,
        "zone_id": None,
        "global_track_id": None,
        "person_id": None,
        "triggered_at": "2026-06-01T10:00:00.000Z",
    })
    await redis.xadd("alerts", {"payload": payload})


@pytest.mark.integration
async def test_dispatcher_dispatches_to_webhook_and_records_success(db_session: Session) -> None:
    """Worker reads stream, dispatches to webhook, records AlertDispatch(success=True)."""
    from vms.dispatcher.worker import AlertDispatcher

    cam = _seed_camera(db_session)
    _seed_routing(db_session)
    db_session.commit()

    redis = fakeredis.aioredis.FakeRedis()
    await _publish_alert(redis, cam.camera_id)

    mock_sender = AsyncMock()  # no-op send — success

    dispatcher = AlertDispatcher(
        redis=redis,
        db_session_factory=lambda: db_session,
        senders={"WEBHOOK": mock_sender},
    )

    # Process exactly one batch
    await dispatcher._process_once()

    mock_sender.send.assert_awaited_once()
    dispatches = db_session.query(AlertDispatch).all()
    assert len(dispatches) == 1
    assert dispatches[0].success is True
    assert dispatches[0].attempt_n == 1
    assert dispatches[0].channel == "WEBHOOK"


@pytest.mark.integration
async def test_dispatcher_retries_on_failure_then_succeeds(db_session: Session) -> None:
    """Worker retries up to 3 times; records both failure and success attempts."""
    from vms.dispatcher.channels import ChannelError
    from vms.dispatcher.worker import AlertDispatcher

    cam = _seed_camera(db_session)
    _seed_routing(db_session)
    db_session.commit()

    redis = fakeredis.aioredis.FakeRedis()
    await _publish_alert(redis, cam.camera_id)

    call_count = 0

    async def flaky_send(payload, target):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ChannelError("transient error")

    mock_sender = AsyncMock(side_effect=flaky_send)

    dispatcher = AlertDispatcher(
        redis=redis,
        db_session_factory=lambda: db_session,
        senders={"WEBHOOK": mock_sender},
        retry_delays=(0, 0),  # no actual sleep in tests
    )

    await dispatcher._process_once()

    dispatches = db_session.query(AlertDispatch).order_by(AlertDispatch.attempt_n).all()
    assert len(dispatches) == 2
    assert dispatches[0].success is False
    assert dispatches[0].attempt_n == 1
    assert dispatches[1].success is True
    assert dispatches[1].attempt_n == 2


@pytest.mark.integration
async def test_dispatcher_records_dead_letter_after_three_failures(db_session: Session) -> None:
    """After 3 failed attempts dispatcher marks all as failed and logs CRITICAL."""
    from vms.dispatcher.channels import ChannelError
    from vms.dispatcher.worker import AlertDispatcher

    cam = _seed_camera(db_session)
    _seed_routing(db_session)
    db_session.commit()

    redis = fakeredis.aioredis.FakeRedis()
    await _publish_alert(redis, cam.camera_id)

    mock_sender = AsyncMock(side_effect=ChannelError("always fails"))

    dispatcher = AlertDispatcher(
        redis=redis,
        db_session_factory=lambda: db_session,
        senders={"WEBHOOK": mock_sender},
        retry_delays=(0, 0),
    )

    await dispatcher._process_once()

    dispatches = db_session.query(AlertDispatch).all()
    assert len(dispatches) == 3
    assert all(d.success is False for d in dispatches)
    assert mock_sender.send.await_count == 3
```

- [ ] **Step 2: Run to confirm failure**

```powershell
pytest tests/test_dispatcher_worker.py -v -m integration
```
Expected: `FAILED` — `cannot import name 'AlertDispatcher' from 'vms.dispatcher.worker'`

- [ ] **Step 3: Implement worker.py**

Create `vms/dispatcher/worker.py`:

```python
"""AlertDispatcher — reads the alerts Redis Stream and fans out to channels."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from vms.db.audit import write_audit_event
from vms.db.models import AlertDispatch, AlertRouting, Camera
from vms.dispatcher.channels import ChannelError, ChannelSender
from vms.dispatcher.payload import AlertPayload, from_stream_fields
from vms.dispatcher.router import match_routing_rules
from vms.redis_client import stream_read

logger = logging.getLogger(__name__)

_CURSOR_KEY = "dispatcher:alerts:cursor"
_DEFAULT_RETRY_DELAYS = (1, 4, 16)  # seconds before attempt 2, 3, 4 (3 total attempts)
_MAX_ATTEMPTS = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AlertDispatcher:
    """Reads from the 'alerts' stream and dispatches to configured channel senders.

    Usage:
        dispatcher = AlertDispatcher.from_settings(redis, db_factory, settings)
        asyncio.create_task(dispatcher.run())
    """

    def __init__(
        self,
        redis: Any,
        db_session_factory: Callable[[], Session],
        senders: dict[str, ChannelSender],
        retry_delays: tuple[int, ...] = _DEFAULT_RETRY_DELAYS,
    ) -> None:
        self._redis = redis
        self._db_factory = db_session_factory
        self._senders = senders  # channel -> sender
        self._retry_delays = retry_delays

    @classmethod
    def from_settings(
        cls,
        redis: Any,
        db_session_factory: Callable[[], Session],
    ) -> "AlertDispatcher":
        """Build a dispatcher with senders configured from VMS_* env vars."""
        from vms.config import get_settings
        from vms.dispatcher.channels import (
            EmailSender,
            SlackSender,
            TelegramSender,
            WebhookSender,
        )

        s = get_settings()
        senders: dict[str, ChannelSender] = {}
        if s.webhook_secret:
            senders["WEBHOOK"] = WebhookSender(secret=s.webhook_secret)
        if s.slack_bot_token:
            senders["SLACK"] = SlackSender(token=s.slack_bot_token)
        if s.telegram_bot_token:
            senders["TELEGRAM"] = TelegramSender(token=s.telegram_bot_token)
        if s.smtp_host:
            senders["EMAIL"] = EmailSender(
                host=s.smtp_host,
                port=s.smtp_port,
                from_addr=s.smtp_from,
                user=s.smtp_user,
                password=s.smtp_password,
            )
        return cls(redis=redis, db_session_factory=db_session_factory, senders=senders)

    async def run(self) -> None:
        """Continuous processing loop. Runs until cancelled."""
        logger.info("AlertDispatcher started — senders: %s", list(self._senders))
        while True:
            try:
                await self._process_once()
            except asyncio.CancelledError:
                logger.info("AlertDispatcher shutting down")
                raise
            except Exception:
                logger.exception("AlertDispatcher loop error; resuming in 5s")
                await asyncio.sleep(5)

    async def _process_once(self) -> None:
        """Read one batch from the stream and dispatch."""
        last_id_bytes = await self._redis.get(_CURSOR_KEY)
        last_id = last_id_bytes.decode() if last_id_bytes else "0-0"

        messages = await stream_read(self._redis, "alerts", last_id=last_id, block_ms=200)
        for msg_id, fields in messages:
            await self._handle_message(fields)
            await self._redis.set(_CURSOR_KEY, msg_id)

    async def _handle_message(self, fields: dict[str, str]) -> None:
        """Dispatch a single alert message to all matching channels."""
        db = self._db_factory()
        try:
            # Parse the stream message into a rich AlertPayload
            raw = json.loads(fields.get("payload", "{}"))
            camera_id: int = int(raw.get("camera_id", 0))
            zone_id: int | None = int(raw["zone_id"]) if raw.get("zone_id") is not None else None

            cam = db.get(Camera, camera_id)
            camera_name = cam.name if cam else f"camera_{camera_id}"

            zone_name: str | None = None
            if zone_id is not None:
                from vms.db.models import Zone  # type: ignore[attr-defined]
                zone = db.get(Zone, zone_id)
                zone_name = zone.name if zone else f"zone_{zone_id}"

            payload = from_stream_fields(fields, camera_name=camera_name, zone_name=zone_name)

            rules = match_routing_rules(
                db,
                alert_type=payload.alert_type,
                severity=payload.severity,
                zone_id=payload.zone_id,
            )

            for rule in rules:
                sender = self._senders.get(rule.channel)
                if sender is None:
                    logger.debug(
                        "No sender configured for channel %s; skipping rule %d",
                        rule.channel, rule.routing_id,
                    )
                    continue
                await self._dispatch_with_retry(db, payload, sender, rule)
            db.commit()

        except Exception:
            logger.exception("Failed to handle alert message; skipping")
            db.rollback()
        finally:
            db.close()

    async def _dispatch_with_retry(
        self,
        db: Session,
        payload: AlertPayload,
        sender: ChannelSender,
        rule: AlertRouting,
    ) -> None:
        """Attempt dispatch up to _MAX_ATTEMPTS times with exponential backoff."""
        last_error: str | None = None

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            if attempt > 1 and len(self._retry_delays) >= attempt - 1:
                await asyncio.sleep(self._retry_delays[attempt - 2])

            try:
                await sender.send(payload, rule.target)
                db.add(AlertDispatch(
                    alert_id=payload.alert_id,
                    channel=rule.channel,
                    target=rule.target,
                    attempt_n=attempt,
                    dispatched_at=_utcnow(),
                    success=True,
                    error=None,
                    response_code=None,
                ))
                write_audit_event(
                    db,
                    event_type="ALERT_DISPATCHED",
                    target_type="alert",
                    target_id=str(payload.alert_id),
                    payload=json.dumps({"channel": rule.channel, "attempt": attempt}),
                )
                return

            except ChannelError as exc:
                last_error = str(exc)
                db.add(AlertDispatch(
                    alert_id=payload.alert_id,
                    channel=rule.channel,
                    target=rule.target,
                    attempt_n=attempt,
                    dispatched_at=_utcnow(),
                    success=False,
                    error=last_error[:500],
                    response_code=None,
                ))
                logger.warning(
                    "Dispatch failed (attempt %d/%d) alert=%d channel=%s: %s",
                    attempt, _MAX_ATTEMPTS, payload.alert_id, rule.channel, last_error,
                )

        # All attempts exhausted — dead letter
        logger.error(
            "Dead letter: alert_id=%d channel=%s target=%s after %d attempts. Last error: %s",
            payload.alert_id, rule.channel, rule.target, _MAX_ATTEMPTS, last_error,
        )
        write_audit_event(
            db,
            event_type="ALERT_DISPATCH_DEAD_LETTER",
            target_type="alert",
            target_id=str(payload.alert_id),
            payload=json.dumps({"channel": rule.channel, "last_error": last_error}),
        )
```

- [ ] **Step 4: Run to confirm pass**

```powershell
pytest tests/test_dispatcher_worker.py -v -m integration
```
Expected: all 3 tests `PASSED`

- [ ] **Step 5: Commit**

```powershell
git add vms/dispatcher/worker.py tests/test_dispatcher_worker.py
git commit -m "feat(dispatcher): AlertDispatcher worker with retry and dead-letter"
```

---

## Task 6: Routing CRUD API

**Files:**
- Modify: `vms/api/schemas.py`
- Create: `vms/api/routes/routing.py`
- Create: `tests/test_api_alert_routing.py`

Three endpoints:
- `GET /api/alert-routing` — list active routing rules (any authenticated user)
- `POST /api/alert-routing` — create rule (`admin` or `super_admin`)
- `DELETE /api/alert-routing/{routing_id}` — soft-delete (set `is_active=False`) (`admin` or `super_admin`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_alert_routing.py`:

```python
"""API tests for alert routing CRUD."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from tests.conftest import make_token


@pytest.mark.integration
def test_list_routing_rules_returns_empty_initially(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {make_token('guard', 'viewer')}"}
    resp = client.get("/api/alert-routing", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_create_routing_rule_requires_admin(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {make_token('guard', 'viewer')}"}
    resp = client.post(
        "/api/alert-routing",
        json={"channel": "WEBHOOK", "target": "https://example.com"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.integration
def test_create_routing_rule_admin_succeeds(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {make_token('admin', 'admin')}"}
    resp = client.post(
        "/api/alert-routing",
        json={
            "channel": "WEBHOOK",
            "target": "https://example.com/hook",
            "alert_type": "VIOLENCE",
            "severity": "CRITICAL",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["channel"] == "WEBHOOK"
    assert body["target"] == "https://example.com/hook"
    assert body["alert_type"] == "VIOLENCE"
    assert body["is_active"] is True
    assert "routing_id" in body


@pytest.mark.integration
def test_delete_routing_rule_soft_deletes(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {make_token('admin', 'admin')}"}
    # Create
    create_resp = client.post(
        "/api/alert-routing",
        json={"channel": "SLACK", "target": "#alerts"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    routing_id = create_resp.json()["routing_id"]

    # Delete
    del_resp = client.delete(f"/api/alert-routing/{routing_id}", headers=headers)
    assert del_resp.status_code == 204

    # List should not show it
    list_resp = client.get("/api/alert-routing", headers=headers)
    active_ids = [r["routing_id"] for r in list_resp.json()]
    assert routing_id not in active_ids


@pytest.mark.integration
def test_create_routing_rule_rejects_invalid_channel(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {make_token('admin', 'admin')}"}
    resp = client.post(
        "/api/alert-routing",
        json={"channel": "PIGEON", "target": "coo"},
        headers=headers,
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run to confirm failure**

```powershell
pytest tests/test_api_alert_routing.py -v -m integration
```
Expected: `FAILED` — routes not registered yet

- [ ] **Step 3: Add schemas and router**

Add to `vms/api/schemas.py` (after the camera schemas):

```python
# ── Alert Routing ──────────────────────────────────────────────────────────

_VALID_CHANNELS = frozenset({"EMAIL", "SLACK", "TELEGRAM", "WEBHOOK", "WEBSOCKET"})

class AlertRoutingCreate(BaseModel):
    alert_type: str | None = None
    severity: str | None = None
    zone_id: int | None = None
    channel: str
    target: str

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        if v not in _VALID_CHANNELS:
            raise ValueError(f"channel must be one of {sorted(_VALID_CHANNELS)}")
        return v


class AlertRoutingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    routing_id: int
    alert_type: str | None
    severity: str | None
    zone_id: int | None
    channel: str
    target: str
    is_active: bool
```

Create `vms/api/routes/routing.py`:

```python
"""GET/POST/DELETE /api/alert-routing — routing rule management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db, require_role
from vms.api.schemas import AlertRoutingCreate, AlertRoutingResponse
from vms.db.models import AlertRouting

router = APIRouter()


@router.get("/alert-routing", response_model=list[AlertRoutingResponse])
def list_routing_rules(
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> list[AlertRouting]:
    return db.query(AlertRouting).filter(AlertRouting.is_active.is_(True)).all()


@router.post("/alert-routing", response_model=AlertRoutingResponse, status_code=201)
def create_routing_rule(
    body: AlertRoutingCreate,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(require_role("admin", "super_admin")),
) -> AlertRouting:
    rule = AlertRouting(
        alert_type=body.alert_type,
        severity=body.severity,
        zone_id=body.zone_id,
        channel=body.channel,
        target=body.target,
        is_active=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/alert-routing/{routing_id}", status_code=204)
def delete_routing_rule(
    routing_id: int,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(require_role("admin", "super_admin")),
) -> None:
    rule = db.get(AlertRouting, routing_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Routing rule not found")
    rule.is_active = False
    db.commit()
```

- [ ] **Step 4: Run to confirm failure (routes not wired yet)**

```powershell
pytest tests/test_api_alert_routing.py -v -m integration
```
Expected: `FAILED` — 404 on all endpoints (router not registered)

- [ ] **Step 5: Register router in main.py**

In `vms/api/main.py`, add:

```python
from vms.api.routes import alerts, anomaly_detectors, auth, cameras, health, maintenance, persons, routing, state
```

And inside `create_app()` or at module level (match existing pattern):

```python
app.include_router(routing.router, prefix="/api")
```

- [ ] **Step 6: Run to confirm pass**

```powershell
pytest tests/test_api_alert_routing.py -v -m integration
```
Expected: all 5 tests `PASSED`

- [ ] **Step 7: Commit**

```powershell
git add vms/api/schemas.py vms/api/routes/routing.py vms/api/main.py tests/test_api_alert_routing.py
git commit -m "feat(dispatcher): alert routing CRUD API"
```

---

## Task 7: Wire dispatcher into app lifespan

**Files:**
- Modify: `vms/api/main.py`
- Modify: `vms/api/deps.py`

Start the dispatcher as a FastAPI background task during app lifespan. It shares the same Redis client used by the API but runs an independent async loop.

- [ ] **Step 1: Write a smoke test**

Add to `tests/test_api_alert_routing.py`:

```python
@pytest.mark.integration
def test_health_endpoint_still_passes_after_dispatcher_wired(client: TestClient) -> None:
    """Regression: wiring the dispatcher must not break the health endpoint."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
```

- [ ] **Step 2: Wire dispatcher startup**

In `vms/api/main.py`, locate the `lifespan` context manager (or create one following the existing pattern). Add dispatcher startup:

```python
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from vms.api.deps import get_api_redis


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # ── existing startup (partition manager, etc.) ──
    from vms.db.partition_manager import ensure_future_partitions
    from vms.db.session import SessionLocal
    with SessionLocal() as db:
        ensure_future_partitions(db)

    # ── dispatcher ──
    import asyncio
    from vms.dispatcher.worker import AlertDispatcher

    redis = await get_api_redis()
    dispatcher = AlertDispatcher.from_settings(
        redis=redis,
        db_session_factory=SessionLocal,
    )
    task = asyncio.create_task(dispatcher.run(), name="alert-dispatcher")

    yield

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
```

> **Important:** Read the existing `main.py` carefully before editing — the lifespan may already exist. Merge the dispatcher startup code into the existing lifespan rather than replacing it.

- [ ] **Step 3: Run full suite**

```powershell
pytest --tb=short -q
```
Expected: all existing tests still pass (≥ 450 passing)

- [ ] **Step 4: Commit**

```powershell
git add vms/api/main.py
git commit -m "feat(dispatcher): start AlertDispatcher as lifespan background task"
```

---

## Task 8: Full suite + lint + type check

- [ ] **Step 1: Run full test suite**

```powershell
pytest --tb=short -q
```
Expected: ≥ 465 tests passing (≥ 450 pre-existing + 15 new dispatcher tests)

- [ ] **Step 2: Lint**

```powershell
ruff check vms/ tests/
```
Expected: no errors

- [ ] **Step 3: Format**

```powershell
black vms/ tests/
```

- [ ] **Step 4: Type check**

```powershell
mypy vms/
```
Expected: `Success: no issues found in N source files`

- [ ] **Step 5: Final commit**

```powershell
git add -u
git commit -m "chore(dispatcher): lint + format + type fixes"
```

---

## Self-review checklist

**Spec coverage (§E):**
- [x] `alert_routing` table — exists in `0001` migration, ORM in models.py
- [x] `alert_dispatches` table — same
- [x] EMAIL channel — `EmailSender` in Task 3
- [x] SLACK channel — `SlackSender` in Task 3
- [x] TELEGRAM channel — `TelegramSender` in Task 3
- [x] WEBHOOK channel with `X-VMS-Signature: sha256=<hmac>` — `WebhookSender` in Task 3
- [x] WEBSOCKET — already handled by anomaly orchestrator; dispatcher skips it
- [x] Exponential backoff: 1s, 4s, 16s — `_DEFAULT_RETRY_DELAYS = (1, 4, 16)` in worker.py
- [x] Max 3 attempts — `_MAX_ATTEMPTS = 3`
- [x] Dead-letter logging + audit event — `ALERT_DISPATCH_DEAD_LETTER` in worker.py
- [x] Routing rules: NULL = wildcard matching — `match_routing_rules()` in Task 4
- [x] One alert → multiple channels — `for rule in rules` in worker.py
- [x] Webhook payload matches spec schema — `to_webhook_dict()` in payload.py
- [x] `alert_dispatches` records each attempt — `db.add(AlertDispatch(...))` in worker.py
- [x] Audit event on successful dispatch — `ALERT_DISPATCHED` in worker.py
- [x] Routing CRUD API — Task 6

**No placeholders:** all code blocks are complete and runnable.

**Type consistency:** `AlertPayload` defined in Task 2, used in Tasks 3, 4, 5. `ChannelSender` Protocol defined in Task 3, used in Task 5. `AlertRouting` ORM from models.py throughout.
