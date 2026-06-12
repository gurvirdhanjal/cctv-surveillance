"""GET/PATCH /api/anomaly-detectors[/health]."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from vms.api.deps import (
    get_api_redis,
    get_current_user,
    get_db,
    get_orchestrator_health,
    require_role,
)
from vms.api.schemas import AnomalyDetectorResponse, AnomalyDetectorUpdate
from vms.db.audit import write_audit_event
from vms.db.models import AnomalyDetector
from vms.db.models import User as DBUser

router = APIRouter()


@router.get("/anomaly-detectors", response_model=list[AnomalyDetectorResponse])
def list_detectors(
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[AnomalyDetector]:
    return db.query(AnomalyDetector).order_by(AnomalyDetector.alert_type).all()


@router.get("/anomaly-detectors/health")
def detector_health(
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> dict[str, dict[str, object]]:
    return get_orchestrator_health()


@router.patch("/anomaly-detectors/{detector_id}", response_model=AnomalyDetectorResponse)
async def update_detector(
    detector_id: int,
    body: AnomalyDetectorUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = require_role("admin", "manager"),  # noqa: B008
) -> AnomalyDetector:
    detector = db.get(AnomalyDetector, detector_id)
    if detector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detector not found")

    updates = body.model_dump(exclude_unset=True)
    if "is_enabled" in updates:
        detector.is_enabled = updates["is_enabled"]
    if "config_json" in updates:
        detector.config_json = (
            json.dumps(updates["config_json"]) if updates["config_json"] is not None else None
        )
    detector.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(detector)

    try:
        actor_id: int | None = int(user["sub"])
    except (ValueError, KeyError):
        actor_id = None
    if actor_id is not None and db.get(DBUser, actor_id) is None:
        actor_id = None

    write_audit_event(
        db,
        event_type="DETECTOR_CONFIG_UPDATED",
        actor_user_id=actor_id,
        target_type="anomaly_detector",
        target_id=str(detector_id),
        payload=json.dumps({"detector_id": detector_id, "updates": updates}),
    )

    redis_client = get_api_redis()
    await redis_client.publish(
        f"detector_config_changed:{detector_id}",
        json.dumps({"detector_id": detector_id}),
    )

    return detector
