"""Tests for the AlertDispatcher worker."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from sqlalchemy.orm import Session

from vms.db.models import Alert, AlertDispatch, AlertRouting, Camera

_TS = datetime(2026, 6, 1, 10, 0, 0)


def _seed_camera(db: Session) -> Camera:
    cam = Camera(name="Gate 1", rtsp_url="rtsp://x/1", capability_tier="FULL")
    db.add(cam)
    db.flush()
    return cam


def _seed_alert(db: Session, camera_id: int) -> Alert:
    alert = Alert(
        alert_type="VIOLENCE",
        severity="CRITICAL",
        camera_id=camera_id,
        triggered_at=_TS,
    )
    db.add(alert)
    db.flush()
    return alert


def _seed_routing(db: Session) -> AlertRouting:
    r = AlertRouting(
        channel="WEBHOOK",
        target="https://example.com/hook",
        is_active=True,
    )
    db.add(r)
    db.flush()
    return r


async def _publish_alert(
    redis: fakeredis.aioredis.FakeRedis, camera_id: int, alert_id: int
) -> None:
    payload = json.dumps(
        {
            "alert_id": alert_id,
            "alert_type": "VIOLENCE",
            "severity": "CRITICAL",
            "camera_id": camera_id,
            "zone_id": None,
            "global_track_id": None,
            "person_id": None,
            "triggered_at": "2026-06-01T10:00:00.000Z",
        }
    )
    await redis.xadd("alerts", {"payload": payload})


@pytest.mark.integration
async def test_dispatcher_dispatches_to_webhook_and_records_success(
    db_session: Session,
) -> None:
    """Worker reads stream, dispatches to webhook, records AlertDispatch(success=True)."""
    from vms.dispatcher.worker import AlertDispatcher

    cam = _seed_camera(db_session)
    alert = _seed_alert(db_session, cam.camera_id)
    _seed_routing(db_session)
    db_session.commit()

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await _publish_alert(redis, cam.camera_id, alert.alert_id)

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=None)

    dispatcher = AlertDispatcher(
        redis=redis,
        db_session_factory=lambda: db_session,
        senders={"WEBHOOK": mock_sender},
    )

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
    alert = _seed_alert(db_session, cam.camera_id)
    _seed_routing(db_session)
    db_session.commit()

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await _publish_alert(redis, cam.camera_id, alert.alert_id)

    call_count = 0

    async def flaky_send(payload, target):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ChannelError("transient error")

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(side_effect=flaky_send)

    dispatcher = AlertDispatcher(
        redis=redis,
        db_session_factory=lambda: db_session,
        senders={"WEBHOOK": mock_sender},
        retry_delays=(0, 0),
    )

    await dispatcher._process_once()

    dispatches = db_session.query(AlertDispatch).order_by(AlertDispatch.attempt_n).all()
    assert len(dispatches) == 2
    assert dispatches[0].success is False
    assert dispatches[0].attempt_n == 1
    assert dispatches[1].success is True
    assert dispatches[1].attempt_n == 2


@pytest.mark.integration
async def test_dispatcher_records_dead_letter_after_three_failures(
    db_session: Session,
) -> None:
    """After max_attempts failures dispatcher marks all as failed — value read from settings."""
    from vms.dispatcher.channels import ChannelError
    from vms.dispatcher.worker import AlertDispatcher

    cam = _seed_camera(db_session)
    alert = _seed_alert(db_session, cam.camera_id)
    _seed_routing(db_session)
    db_session.commit()

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await _publish_alert(redis, cam.camera_id, alert.alert_id)

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(side_effect=ChannelError("always fails"))

    # Patch settings to confirm max_attempts and retry_delays are read from config,
    # not from hardcoded constants. Use max_attempts=2 so the test is unambiguous.
    mock_settings = MagicMock()
    mock_settings.alert_dispatcher_max_attempts = 2
    mock_settings.alert_dispatcher_retry_delays_s = (0,)

    with patch("vms.dispatcher.worker.get_settings", return_value=mock_settings):
        dispatcher = AlertDispatcher(
            redis=redis,
            db_session_factory=lambda: db_session,
            senders={"WEBHOOK": mock_sender},
        )

    await dispatcher._process_once()

    dispatches = db_session.query(AlertDispatch).all()
    assert len(dispatches) == 2
    assert all(d.success is False for d in dispatches)
    assert mock_sender.send.await_count == 2


@pytest.mark.integration
async def test_dispatcher_skips_already_dispatched_alert(
    db_session: Session,
) -> None:
    """Dispatcher skips dispatch if success=True row already exists for (alert_id, channel)."""
    from vms.dispatcher.worker import AlertDispatcher

    cam = _seed_camera(db_session)
    alert = _seed_alert(db_session, cam.camera_id)
    _seed_routing(db_session)

    existing = AlertDispatch(
        alert_id=alert.alert_id,
        channel="WEBHOOK",
        target="https://example.com/hook",
        attempt_n=1,
        dispatched_at=_TS,
        success=True,
        error=None,
        response_code=None,
    )
    db_session.add(existing)
    db_session.commit()

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await _publish_alert(redis, cam.camera_id, alert.alert_id)

    send_calls: list[object] = []

    class SpySender:
        async def send(self, payload: object, target: str) -> None:  # type: ignore[no-untyped-def]
            send_calls.append(target)

    dispatcher = AlertDispatcher(
        redis=redis,
        db_session_factory=lambda: db_session,
        senders={"WEBHOOK": SpySender()},  # type: ignore[arg-type]
    )
    await dispatcher._process_once()

    assert send_calls == [], "Should not re-dispatch already-dispatched alert"


@pytest.mark.integration
async def test_dispatcher_writes_dead_alert_to_stream_after_max_retries(
    db_session: Session,
) -> None:
    """After all retry attempts fail, alert_id is published to dead_alerts stream."""
    from vms.dispatcher.channels import ChannelError
    from vms.dispatcher.worker import AlertDispatcher

    cam = _seed_camera(db_session)
    alert = _seed_alert(db_session, cam.camera_id)
    _seed_routing(db_session)
    db_session.commit()

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await _publish_alert(redis, cam.camera_id, alert.alert_id)

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(side_effect=ChannelError("always fails"))

    dispatcher = AlertDispatcher(
        redis=redis,
        db_session_factory=lambda: db_session,
        senders={"WEBHOOK": mock_sender},
        retry_delays=(0,),
        max_attempts=1,
    )
    await dispatcher._process_once()

    messages = await redis.xread({"dead_alerts": "0-0"}, count=10)
    assert messages, "Expected an entry in dead_alerts stream"
    _, entries = messages[0]
    _, fields = entries[0]
    assert str(alert.alert_id) == fields["alert_id"]
    assert fields["channel"] == "WEBHOOK"
