"""GET/POST/PATCH/DELETE/calendar /api/maintenance — maintenance window management."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from vms.api.deps import get_api_redis, get_current_user, get_db, require_role
from vms.api.schemas import (
    MaintenanceWindowCreate,
    MaintenanceWindowPatchResponse,
    MaintenanceWindowResponse,
    MaintenanceWindowUpdate,
    validate_window_coherence,
)
from vms.db.audit import write_audit_event
from vms.db.models import MaintenanceWindow

router = APIRouter()

_MW_CHANGED_CHANNEL = "maintenance_window_changed"


async def _publish_mw_changed() -> None:
    """Signal orchestrator to reload active maintenance windows (cross-process).

    30s TTL is the correctness backstop until the orchestrator subscribes.
    """
    redis_client = get_api_redis()
    await redis_client.publish(_MW_CHANGED_CHANNEL, "{}")


def _serialize_suppress_types(types: list[str] | None) -> str | None:
    return json.dumps(types) if types is not None else None


@router.get("/maintenance", response_model=list[MaintenanceWindowResponse])
def list_windows(
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[MaintenanceWindow]:
    return db.query(MaintenanceWindow).filter_by(is_active=True).all()


@router.post("/maintenance", response_model=MaintenanceWindowResponse, status_code=201)
async def create_window(
    body: MaintenanceWindowCreate,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = require_role("admin", "manager"),  # noqa: B008
) -> MaintenanceWindow:
    window = MaintenanceWindow(
        name=body.name,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        schedule_type=body.schedule_type,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        cron_expr=body.cron_expr,
        duration_minutes=body.duration_minutes,
        suppress_alert_types=_serialize_suppress_types(body.suppress_alert_types),
        is_active=True,
        reason=body.reason,
        created_by=int(user["sub"]),
    )
    db.add(window)
    db.commit()
    db.refresh(window)

    write_audit_event(
        db,
        event_type="MAINTENANCE_WINDOW_CREATED",
        actor_user_id=int(user["sub"]),
        target_type="maintenance_window",
        target_id=str(window.window_id),
        payload=json.dumps(
            {
                "window_id": window.window_id,
                "name": window.name,
                "scope_type": window.scope_type,
                "scope_id": window.scope_id,
                "schedule_type": window.schedule_type,
            }
        ),
    )

    await _publish_mw_changed()
    return window


@router.patch("/maintenance/{window_id}", response_model=MaintenanceWindowPatchResponse)
async def update_window(
    window_id: int,
    body: MaintenanceWindowUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = require_role("admin", "manager"),  # noqa: B008
) -> MaintenanceWindowPatchResponse:
    window = db.get(MaintenanceWindow, window_id)
    if window is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Window not found")

    updates = body.model_dump(exclude_unset=True)
    before: dict[str, Any] = {k: getattr(window, k) for k in updates}

    # Merge patch fields onto existing row values for cross-field coherence check.
    merged_schedule = updates.get("schedule_type", window.schedule_type)
    merged_starts = updates.get("starts_at", window.starts_at)
    merged_ends = updates.get("ends_at", window.ends_at)
    merged_cron = updates.get("cron_expr", window.cron_expr)
    merged_dur = updates.get("duration_minutes", window.duration_minutes)
    try:
        validate_window_coherence(
            schedule_type=merged_schedule,
            starts_at=merged_starts,
            ends_at=merged_ends,
            cron_expr=merged_cron,
            duration_minutes=merged_dur,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    for field, value in updates.items():
        if field == "suppress_alert_types":
            setattr(window, field, _serialize_suppress_types(value))
        else:
            setattr(window, field, value)

    db.commit()
    db.refresh(window)

    actor_id = int(user["sub"])
    write_audit_event(
        db,
        event_type="MAINTENANCE_WINDOW_UPDATED",
        actor_user_id=actor_id,
        target_type="maintenance_window",
        target_id=str(window_id),
        payload=json.dumps(
            {"changed_fields": {k: {"from": before[k], "to": updates[k]} for k in updates}},
            default=str,
        ),
    )

    await _publish_mw_changed()

    # Non-blocking warning: operator patched an actively-suppressing window.
    warning: str | None = None
    non_reason_fields = {k for k in updates if k not in {"reason", "is_active"}}
    if window.is_active and non_reason_fields:
        warning = "window is currently active — changes take effect immediately"

    resp = MaintenanceWindowPatchResponse.model_validate(window)
    resp.warning = warning
    return resp


@router.delete("/maintenance/{window_id}", status_code=204, response_class=Response)
async def delete_window(
    window_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = require_role("admin", "manager"),  # noqa: B008
) -> Response:
    window = db.get(MaintenanceWindow, window_id)
    if window is None or not window.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Window not found")

    window.is_active = False
    db.commit()

    write_audit_event(
        db,
        event_type="MAINTENANCE_WINDOW_CANCELLED",
        actor_user_id=int(user["sub"]),
        target_type="maintenance_window",
        target_id=str(window_id),
        payload=json.dumps(
            {"window_id": window_id, "name": window.name, "reason": "operator_delete"}
        ),
    )

    await _publish_mw_changed()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
