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
from vms.db.models import AlertDispatch, AlertRouting, Camera, Zone
from vms.dispatcher.channels import ChannelError, ChannelSender
from vms.dispatcher.payload import AlertPayload, from_stream_fields
from vms.dispatcher.router import match_routing_rules
from vms.redis_client import stream_read

logger = logging.getLogger(__name__)

_CURSOR_KEY = "dispatcher:alerts:cursor"
_DEFAULT_RETRY_DELAYS: tuple[int, ...] = (1, 4, 16)
_MAX_ATTEMPTS = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AlertDispatcher:
    """Reads from the 'alerts' stream and dispatches to configured channel senders."""

    def __init__(
        self,
        redis: Any,
        db_session_factory: Callable[[], Session],
        senders: dict[str, ChannelSender],
        retry_delays: tuple[int, ...] = _DEFAULT_RETRY_DELAYS,
    ) -> None:
        self._redis = redis
        self._db_factory = db_session_factory
        self._senders = senders
        self._retry_delays = retry_delays

    @classmethod
    def from_settings(
        cls,
        redis: Any,
        db_session_factory: Callable[[], Session],
    ) -> AlertDispatcher:
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
            raw = json.loads(fields.get("payload", "{}"))
            camera_id: int = int(raw.get("camera_id", 0))
            zone_id: int | None = int(raw["zone_id"]) if raw.get("zone_id") is not None else None

            cam = db.get(Camera, camera_id)
            camera_name = cam.name if cam else f"camera_{camera_id}"

            zone_name: str | None = None
            if zone_id is not None:
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
                        rule.channel,
                        rule.routing_id,
                    )
                    continue
                await self._dispatch_with_retry(db, payload, sender, rule)
            db.commit()

        except Exception:
            logger.exception("Failed to handle alert message; skipping")
            db.rollback()

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
                delay = self._retry_delays[attempt - 2]
                if delay > 0:
                    await asyncio.sleep(delay)

            try:
                await sender.send(payload, rule.target)
                dispatch = AlertDispatch(
                    alert_id=payload.alert_id,
                    channel=rule.channel,
                    target=rule.target,
                    attempt_n=attempt,
                    dispatched_at=_utcnow(),
                    success=True,
                    error=None,
                    response_code=None,
                )
                db.add(dispatch)
                db.flush()
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
                dispatch = AlertDispatch(
                    alert_id=payload.alert_id,
                    channel=rule.channel,
                    target=rule.target,
                    attempt_n=attempt,
                    dispatched_at=_utcnow(),
                    success=False,
                    error=last_error[:500],
                    response_code=None,
                )
                db.add(dispatch)
                db.flush()
                logger.warning(
                    "Dispatch failed (attempt %d/%d) alert=%d channel=%s: %s",
                    attempt,
                    _MAX_ATTEMPTS,
                    payload.alert_id,
                    rule.channel,
                    last_error,
                )

        logger.error(
            "Dead letter: alert_id=%d channel=%s target=%s after %d attempts. Last error: %s",
            payload.alert_id,
            rule.channel,
            rule.target,
            _MAX_ATTEMPTS,
            last_error,
        )
        write_audit_event(
            db,
            event_type="ALERT_DISPATCH_DEAD_LETTER",
            target_type="alert",
            target_id=str(payload.alert_id),
            payload=json.dumps({"channel": rule.channel, "last_error": last_error}),
        )
