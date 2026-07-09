"""GET /api/analytics/* — KPI + head-count series (Phase 4P Tasks 3-4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.api.schemas import HeadCountPoint, HeadCountSeriesResponse
from vms.db.models import AnalyticsHeadCountHourly

router = APIRouter()

_MANAGER_ROLES = {"manager", "admin"}


def _require_manager(user: dict[str, Any]) -> None:
    if user.get("role") not in _MANAGER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager role required")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("/analytics/head-count", response_model=HeadCountSeriesResponse)
def head_count_series(
    days: int = Query(default=7, ge=1, le=90),
    bucket: str = Query(default="hour", pattern="^(hour|day)$"),
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> HeadCountSeriesResponse:
    _require_manager(user)
    window_from = _utcnow() - timedelta(days=days)

    rows = db.execute(
        select(
            AnalyticsHeadCountHourly.bucket_start,
            AnalyticsHeadCountHourly.zone_id,
            AnalyticsHeadCountHourly.count,
        )
        .where(AnalyticsHeadCountHourly.bucket_start >= window_from)
        .order_by(AnalyticsHeadCountHourly.bucket_start)
    ).all()

    points: dict[datetime, HeadCountPoint] = {}
    for bucket_start, zone_id, count in rows:
        ts = bucket_start if bucket == "hour" else bucket_start.replace(hour=0)
        point = points.get(ts)
        if point is None:
            point = HeadCountPoint(ts=ts, plant_total=0, by_zone={})
            points[ts] = point
        if zone_id is None:
            point.plant_total += count
        else:
            point.by_zone[zone_id] = point.by_zone.get(zone_id, 0) + count

    return HeadCountSeriesResponse(series=[points[ts] for ts in sorted(points)])
