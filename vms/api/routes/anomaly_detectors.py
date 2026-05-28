"""GET /api/anomaly-detectors[/health]."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db, get_orchestrator_health
from vms.api.schemas import AnomalyDetectorResponse
from vms.db.models import AnomalyDetector

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
