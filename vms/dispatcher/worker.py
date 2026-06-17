"""AlertDispatcher — reads the alerts Redis Stream and fans out to channels."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from vms.config import get_settings
from vms.db.audit import write_audit_event
from vms.db.models import AlertDispatch, AlertRouting, Camera, Zone
from vms.dispatcher.channels import ChannelError, ChannelSender
from vms.dispatcher.payload import AlertPayload, from_stream_fields
from vms.dispatcher.router import match_routing_rules
from vms.redis_client import stream_read

logger = logging.getLogger(__name__)

_CURSOR_KEY = "dispatcher:alerts:cursor"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AlertDispatcher:
    """Reads from the 'alerts' stream and dispatches to configured channel senders."""

    def __init__(
        self,
        redis: Any,
        db_session_factory: Callable[[], Session],
        senders: dict[str, ChannelSender],
        retry_delays: tuple[int, ...] | None = None,
        max_attempts: int | None = None,
    ) -> None:
        s = get_settings()
        self._redis = redis
        self._db_factory = db_session_factory
        self._senders = senders
        self._retry_delays = (
            retry_delays if retry_delays is not None else s.alert_dispatcher_retry_delays_s
        )
        self._max_attempts = (
            max_attempts if max_attempts is not None else s.alert_dispatcher_max_attempts
        )

    @classmethod
    def from_settings(
        cls,
        redis: Any,
        db_session_factory: Callable[[], Session],
    ) -> AlertDispatcher:
        """Build a dispatcher with senders configured from VMS_* env vars."""
        from vms.dispatcher.channels import (
            EmailSender,
            SlackSender,
            TelegramSender,
            WebhookSender,
        )

        cfg = get_settings()
        senders: dict[str, ChannelSender] = {}
        if cfg.webhook_secret:
            senders["WEBHOOK"] = WebhookSender(secret=cfg.webhook_secret)
        if cfg.slack_bot_token:
            senders["SLACK"] = SlackSender(token=cfg.slack_bot_token)
        if cfg.telegram_bot_token:
            senders["TELEGRAM"] = TelegramSender(token=cfg.telegram_bot_token)
        if cfg.smtp_host:
            senders["EMAIL"] = EmailSender(
                host=cfg.smtp_host,
                port=cfg.smtp_port,
                from_addr=cfg.smtp_from,
                user=cfg.smtp_user,
                password=cfg.smtp_password,
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
            # camera_id is None for SYSTEM_CRITICAL alerts
            camera_id: int | None = int(raw["camera_id"]) if raw.get("camera_id") is not None else None
            zone_id: int | None = int(raw["zone_id"]) if raw.get("zone_id") is not None else None

            cam = db.get(Camera, camera_id) if camera_id is not None else None
            camera_name = cam.name if cam else (f"camera_{camera_id}" if camera_id else "system")

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
        """Attempt dispatch up to max_attempts times with exponential backoff."""
        already = (
            db.query(AlertDispatch)
            .filter_by(alert_id=payload.alert_id, channel=rule.channel, success=True)
            .first()
        )
        if already is not None:
            logger.debug(
                "alert_id=%d channel=%s already dispatched (dispatch_id=%d); skipping",
                payload.alert_id,
                rule.channel,
                already.dispatch_id,
            )
            return

        last_error: str | None = None

        for attempt in range(1, self._max_attempts + 1):
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
                    self._max_attempts,
                    payload.alert_id,
                    rule.channel,
                    last_error,
                )

        logger.error(
            "Dead letter: alert_id=%d channel=%s target=%s after %d attempts. Last error: %s",
            payload.alert_id,
            rule.channel,
            rule.target,
            self._max_attempts,
            last_error,
        )
        write_audit_event(
            db,
            event_type="ALERT_DISPATCH_DEAD_LETTER",
            target_type="alert",
            target_id=str(payload.alert_id),
            payload=json.dumps({"channel": rule.channel, "last_error": last_error}),
        )
        s = get_settings()
        await self._redis.xadd(
            "dead_alerts",
            {"alert_id": str(payload.alert_id), "channel": rule.channel},
            maxlen=s.dead_alerts_stream_maxlen,
        )
