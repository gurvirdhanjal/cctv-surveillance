"""Audit log writer — enforces hash-chain linkage.

Only public API: write_audit_event() and compute_row_hash().
Never construct AuditLog ORM objects directly; always go through write_audit_event().
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from vms.db.models import AuditLog

_ZERO_HASH = "0" * 64
ROW_HASH_VERSION = 1  # bump when compute_row_hash algorithm changes


def compute_row_hash(
    *,
    audit_id: int,
    event_type: str,
    actor_user_id: int | None,
    target_type: str | None,
    target_id: str | None,
    payload: str | None,
    prev_hash: str,
    event_ts: datetime,
) -> str:
    """Return a deterministic SHA-256 hex digest for an audit row."""
    parts = "|".join(
        [
            str(ROW_HASH_VERSION),
            str(audit_id),
            event_type,
            str(actor_user_id) if actor_user_id is not None else "",
            target_type or "",
            target_id or "",
            payload or "",
            prev_hash,
            event_ts.isoformat(),
        ]
    )
    return hashlib.sha256(parts.encode()).hexdigest()


def write_audit_event(
    session: Session,
    *,
    event_type: str,
    actor_user_id: int | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    payload: str | None = None,
) -> AuditLog:
    """Write a single audit event, linking it into the hash chain.

    Reads the most recent row's hash as prev_hash, computes this row's hash,
    inserts, and returns the persisted AuditLog row.
    """
    last = session.execute(
        select(AuditLog)
        .order_by(AuditLog.audit_id.desc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()

    prev_hash = last.row_hash if last is not None else _ZERO_HASH
    event_ts = datetime.now(timezone.utc).replace(tzinfo=None)

    row = AuditLog(
        event_type=event_type,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
        prev_hash=prev_hash,
        row_hash="",  # placeholder; set below after flush gives us audit_id
        event_ts=event_ts,
    )
    session.add(row)
    session.flush()  # populates audit_id without committing

    row.row_hash = compute_row_hash(
        audit_id=row.audit_id,
        event_type=row.event_type,
        actor_user_id=row.actor_user_id,
        target_type=row.target_type,
        target_id=row.target_id,
        payload=row.payload,
        prev_hash=row.prev_hash,
        event_ts=row.event_ts,
    )
    session.commit()
    return row
