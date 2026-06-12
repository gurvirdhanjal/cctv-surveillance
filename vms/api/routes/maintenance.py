"""GET/POST/PATCH/DELETE/calendar /api/maintenance — maintenance window management."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from vms.api.deps import get_api_redis, get_current_user, get_db, require_role
from vms.api.schemas import (
    MaintenanceWindowCreate,
    MaintenanceWindowResponse,
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
