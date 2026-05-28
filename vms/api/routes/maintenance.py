"""GET /api/maintenance — list active windows."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.api.schemas import MaintenanceWindowResponse
from vms.db.models import MaintenanceWindow

router = APIRouter()


@router.get("/maintenance", response_model=list[MaintenanceWindowResponse])
def list_windows(
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[MaintenanceWindow]:
    return db.query(MaintenanceWindow).filter_by(is_active=True).all()
