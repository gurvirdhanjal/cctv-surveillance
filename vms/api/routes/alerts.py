"""GET /api/alerts — list alerts with filters."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.api.schemas import AlertResponse
from vms.db.models import Alert

router = APIRouter()


@router.get("/alerts", response_model=list[AlertResponse])
def list_alerts(
    state: str | None = Query(default=None),
    alert_type: str | None = Query(default=None),
    camera_id: int | None = Query(default=None),
    from_ts: datetime | None = Query(default=None, alias="from"),  # noqa: B008
    to_ts: datetime | None = Query(default=None, alias="to"),  # noqa: B008
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[Alert]:
    # SYSTEM_CRITICAL alerts are ops/scheduler events, not security events — excluded from guard view
    q = db.query(Alert).filter(Alert.alert_type != "SYSTEM_CRITICAL")
    if state:
        q = q.filter(Alert.state == state)
    if alert_type:
        q = q.filter(Alert.alert_type == alert_type)
    if camera_id is not None:
        q = q.filter(Alert.camera_id == camera_id)
    if from_ts:
        q = q.filter(Alert.triggered_at >= from_ts)
    if to_ts:
        q = q.filter(Alert.triggered_at <= to_ts)
    return q.order_by(Alert.triggered_at.desc()).limit(limit).all()
