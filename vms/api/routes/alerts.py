"""GET/PATCH /api/alerts — list and update alerts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.api.schemas import AlertResponse
from vms.db.models import Alert

router = APIRouter()

# Frontend uses OPEN/ACKNOWLEDGED/RESOLVED; DB stores active/acknowledged/resolved
_FE_TO_DB_STATE: dict[str, str] = {
    "OPEN": "active",
    "ACKNOWLEDGED": "acknowledged",
    "RESOLVED": "resolved",
}


class AlertPatch(BaseModel):
    state: str


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
    q = db.query(Alert).filter(Alert.alert_type != "SYSTEM_CRITICAL")
    if state:
        db_state = _FE_TO_DB_STATE.get(state.upper(), state.lower())
        q = q.filter(Alert.state == db_state)
    if alert_type:
        q = q.filter(Alert.alert_type == alert_type)
    if camera_id is not None:
        q = q.filter(Alert.camera_id == camera_id)
    if from_ts:
        q = q.filter(Alert.triggered_at >= from_ts)
    if to_ts:
        q = q.filter(Alert.triggered_at <= to_ts)
    return q.order_by(Alert.triggered_at.desc()).limit(limit).all()


@router.patch("/alerts/{alert_id}", response_model=AlertResponse)
def patch_alert(
    alert_id: int,
    body: AlertPatch,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Alert:
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    new_state = _FE_TO_DB_STATE.get(body.state.upper())
    if new_state is None:
        raise HTTPException(status_code=400, detail=f"Invalid state: {body.state}")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    alert.state = new_state
    if new_state == "acknowledged" and alert.acknowledged_at is None:
        alert.acknowledged_at = now
        alert.acknowledged_by = user.get("user_id")
    elif new_state == "resolved" and alert.resolved_at is None:
        alert.resolved_at = now

    db.commit()
    db.refresh(alert)
    return alert
