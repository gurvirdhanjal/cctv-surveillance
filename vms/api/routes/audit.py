"""GET /api/audit/verify and GET /api/audit/export."""

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from vms.api.deps import get_db, require_role
from vms.api.schemas import AuditVerifyResponse
from vms.config import get_settings
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


def _build_audit_pdf(rows: list[AuditLog], from_dt: datetime, to_dt: datetime) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()

    elements: list[Any] = [
        Paragraph(
            f"VMS Audit Log — {from_dt.date()} to {to_dt.date()}",
            styles["Title"],
        )
    ]

    header = ["audit_id", "event_ts (UTC)", "event_type", "actor", "target", "hash (first 16)"]
    data: list[list[str]] = [header]
    for row in rows:
        data.append(
            [
                str(row.audit_id),
                row.event_ts.isoformat(),
                row.event_type,
                str(row.actor_user_id) if row.actor_user_id is not None else "system",
                f"{row.target_type}:{row.target_id}" if row.target_type else "",
                row.row_hash[:16],
            ]
        )

    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)
    buf.seek(0)
    return buf.read()


@router.get("/audit/export")
def export_audit_log(
    from_dt: datetime = Query(..., alias="from"),  # noqa: B008
    to_dt: datetime = Query(..., alias="to"),  # noqa: B008
    fmt: str = Query("pdf", alias="format"),
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = require_role("admin"),  # noqa: B008
) -> Response:
    if to_dt <= from_dt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="to must be after from",
        )
    if fmt != "pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only format=pdf is supported",
        )

    max_rows = get_settings().audit_export_max_rows
    rows: list[AuditLog] = (
        db.query(AuditLog)
        .filter(AuditLog.event_ts >= from_dt, AuditLog.event_ts < to_dt)
        .order_by(AuditLog.audit_id.asc())
        .limit(max_rows + 1)
        .all()
    )
    if len(rows) > max_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Date range contains more than {max_rows} audit rows. Use a narrower range.",
        )

    pdf_bytes = _build_audit_pdf(rows, from_dt, to_dt)
    filename = f"audit-{from_dt.date()}--{to_dt.date()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
