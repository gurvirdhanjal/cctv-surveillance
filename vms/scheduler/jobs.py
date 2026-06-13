"""Scheduler job definitions and shared helpers.

ScheduledJob is a frozen dataclass that declares every cron job.
_emit_critical_alert writes a SYSTEM_CRITICAL alert for infrastructure
failure events. These route through AlertDispatcher to Slack/email but
are filtered out of the Guard view (security operator screen).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class ScheduledJob:
    name: str
    cron: str
    handler: Callable[[], None]
    timeout_s: int
    on_failure: Literal["log", "alert"]
    audit_event_type: str


def _emit_critical_alert(*, detail: str, component: str) -> None:
    """Write a SYSTEM_CRITICAL alert for ops visibility.

    Routes through AlertDispatcher (Slack/email) via alert_routing.
    Never appears in the Guard view (filtered by alert_type).
    camera_id is intentionally NULL — system alerts have no camera.
    """
    from vms.db.models import Alert as AlertModel
    from vms.db.session import SessionLocal

    try:
        with SessionLocal() as session:
            alert = AlertModel(
                alert_type="SYSTEM_CRITICAL",
                severity="CRITICAL",
                state="active",
                camera_id=None,
                triggered_at=_utcnow(),
                dedup_key=f"scheduler:{component}:{detail[:60]}",
            )
            session.add(alert)
            session.commit()
    except Exception as exc:
        logger.error(
            "_emit_critical_alert: failed to write alert component=%s detail=%s error=%s",
            component,
            detail,
            exc,
        )


# ---------------------------------------------------------------------------
# Job registry (v1)
# ---------------------------------------------------------------------------


def _partition_create_next_month() -> None:
    from vms.db.partition_manager import ensure_future_partitions
    from vms.db.session import engine

    ensure_future_partitions(engine, months_ahead=2)


def _faiss_drift_check() -> None:
    logger.info("faiss_drift_check: placeholder — implement in Phase 3 identity hardening")


def _audit_chain_verify() -> None:
    from sqlalchemy import select

    from vms.db.models import AuditLog
    from vms.db.session import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(select(AuditLog).order_by(AuditLog.audit_id.asc())).scalars().all()
        prev = "0" * 64
        broken_at: int | None = None
        for row in rows:
            if row.prev_hash != prev:
                broken_at = row.audit_id
                break
            prev = row.row_hash

    if broken_at is not None:
        logger.error("audit_chain_verify: broken chain at audit_id=%d", broken_at)
        _emit_critical_alert(
            component="audit_chain_verify",
            detail=f"Broken chain at audit_id={broken_at}",
        )
    else:
        logger.info("audit_chain_verify: chain intact (%d rows)", len(rows))


def _worker_heartbeat_check() -> None:
    import redis as sync_redis

    from vms.config import get_settings

    s = get_settings()
    r = sync_redis.from_url(s.redis_url)  # type: ignore[no-untyped-call]

    # Count active ingestion workers by inspecting heartbeat keys.
    # Pattern: heartbeat:{worker_id}
    keys = r.keys("heartbeat:*")
    missing: list[str] = []
    for key in keys:
        ttl = r.ttl(key)
        if ttl <= 0:
            missing.append(key.decode() if isinstance(key, bytes) else key)

    if missing:
        wids = ", ".join(missing)
        logger.error("worker_heartbeat_check: workers absent: %s", wids)
        _emit_critical_alert(
            component="worker_heartbeat_check",
            detail=f"Workers absent: {wids}",
        )


JOBS: list[ScheduledJob] = [
    ScheduledJob(
        name="partition_create_next_month",
        cron="0 2 25 * *",
        handler=_partition_create_next_month,
        timeout_s=300,
        on_failure="alert",
        audit_event_type="SCHEDULER_PARTITION_CREATE",
    ),
    ScheduledJob(
        name="audit_chain_verify",
        cron="0 5 * * *",
        handler=_audit_chain_verify,
        timeout_s=600,
        on_failure="alert",
        audit_event_type="SCHEDULER_AUDIT_CHAIN_VERIFY",
    ),
    ScheduledJob(
        name="faiss_drift_check",
        cron="30 5 * * *",
        handler=_faiss_drift_check,
        timeout_s=120,
        on_failure="alert",
        audit_event_type="SCHEDULER_FAISS_DRIFT_CHECK",
    ),
    ScheduledJob(
        name="worker_heartbeat_check",
        cron="@every 10s",
        handler=_worker_heartbeat_check,
        timeout_s=15,
        on_failure="alert",
        audit_event_type="SCHEDULER_HEARTBEAT_CHECK",
    ),
]
