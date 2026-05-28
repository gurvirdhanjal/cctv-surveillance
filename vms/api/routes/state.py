"""GET /api/state/snapshot — spec §N.3."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.db.models import Alert, Camera
from vms.identity.head_count import HeadCountAggregator

router = APIRouter()

_agg: HeadCountAggregator | None = None


def set_head_count_aggregator(agg: HeadCountAggregator) -> None:
    """The orchestrator wires its aggregator into the API process via this hook."""
    global _agg
    _agg = agg


@router.get("/state/snapshot")
def snapshot(
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    head: dict[str, Any] = (
        _agg.snapshot().to_dict()
        if _agg is not None
        else {"plant_total": 0, "by_zone": {}, "ts": now, "schema_version": "1"}
    )
    active = db.query(Alert).filter_by(state="active").limit(200).all()
    cams = db.query(Camera).filter_by(is_active=True).all()
    return {
        "ts": now,
        "schema_version": "1",
        "head_count": head,
        "active_alerts": [
            {
                "alert_id": a.alert_id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "state": a.state,
                "camera_id": a.camera_id,
                "zone_id": a.zone_id,
                "global_track_id": str(a.global_track_id) if a.global_track_id else None,
                "person_id": a.person_id,
                "triggered_at": a.triggered_at.isoformat() + "Z",
            }
            for a in active
        ],
        "cameras": [
            {
                "camera_id": c.camera_id,
                "name": c.name,
                "capability_tier": c.capability_tier,
                "is_active": c.is_active,
            }
            for c in cams
        ],
        "degraded": None,
    }
