"""GET /api/audit/verify and GET /api/audit/export."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from vms.api.deps import get_db, require_role
from vms.api.schemas import AuditVerifyResponse
from vms.db.audit import compute_row_hash
from vms.db.models import AuditLog

_log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/audit/verify", response_model=AuditVerifyResponse)
def verify_audit_chain(
    from_dt: datetime = Query(..., alias="from"),  # noqa: B008
    to_dt: datetime = Query(..., alias="to"),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = require_role("admin", "manager"),  # noqa: B008
) -> AuditVerifyResponse:
    if to_dt <= from_dt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="to must be after from",
        )

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.event_ts >= from_dt, AuditLog.event_ts < to_dt)
        .order_by(AuditLog.audit_id.asc())
        .yield_per(1000)
    )

    rows_checked = 0
    prev_row_hash: str | None = None

    for row in rows:
        expected = compute_row_hash(
            audit_id=row.audit_id,
            event_type=row.event_type,
            actor_user_id=row.actor_user_id,
            target_type=row.target_type,
            target_id=row.target_id,
            payload=row.payload,
            prev_hash=row.prev_hash,
            event_ts=row.event_ts,
        )
        if row.row_hash != expected:
            return AuditVerifyResponse(rows_checked=rows_checked, broken_chain_at=row.event_ts)

        if prev_row_hash is not None and row.prev_hash != prev_row_hash:
            return AuditVerifyResponse(rows_checked=rows_checked, broken_chain_at=row.event_ts)

        prev_row_hash = row.row_hash
        rows_checked += 1

    _log.info(
        "audit chain verified: %d rows checked, broken_chain_at=%s",
        rows_checked,
        None,
    )
    return AuditVerifyResponse(rows_checked=rows_checked, broken_chain_at=None)
