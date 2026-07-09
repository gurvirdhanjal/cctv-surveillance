"""GET /api/analytics/* — KPI + head-count series (Phase 4P Tasks 3-4)."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vms.api.deps import get_api_redis, get_current_user, get_db
from vms.api.routes.state import get_head_count_aggregator
from vms.api.schemas import (
    FloorPosition,
    FloorPositionsResponse,
    HeadCountPoint,
    HeadCountSeriesResponse,
    HeatmapCell,
    HeatmapResponse,
    KpiResponse,
)
from vms.config import get_settings
from vms.db.models import (
    Alert,
    AnalyticsHeadCountHourly,
    Camera,
    CameraStatusEvent,
    FloorPlan,
    TrackingEvent,
    UserCameraPermission,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_MANAGER_ROLES = {"manager", "admin"}


def _require_manager(user: dict[str, Any]) -> None:
    if user.get("role") not in _MANAGER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager role required")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _camera_uptime_pct(db: Session, window_from: datetime, window_to: datetime) -> float:
    """Mean per-camera uptime over the window from camera_status_events.

    A camera with no transition history counts as fully online; the status at
    window start comes from its latest event at or before the window.
    """
    cam_ids = list(db.execute(select(Camera.camera_id)).scalars().all())
    if not cam_ids:
        return 100.0
    events = db.execute(
        select(CameraStatusEvent.camera_id, CameraStatusEvent.status, CameraStatusEvent.at)
        .where(CameraStatusEvent.at <= window_to)
        .order_by(CameraStatusEvent.camera_id, CameraStatusEvent.at, CameraStatusEvent.id)
    ).all()
    by_cam: dict[int, list[tuple[str, datetime]]] = defaultdict(list)
    for cam_id, event_status, at in events:
        by_cam[cam_id].append((event_status, at))

    window_s = (window_to - window_from).total_seconds()
    uptime_sum = 0.0
    for cam_id in cam_ids:
        current = "online"
        cursor = window_from
        offline_s = 0.0
        for event_status, at in by_cam.get(cam_id, []):
            if at <= window_from:
                current = event_status
                continue
            if current == "offline":
                offline_s += (at - cursor).total_seconds()
            current = event_status
            cursor = at
        if current == "offline":
            offline_s += (window_to - cursor).total_seconds()
        uptime_sum += max(0.0, 1.0 - offline_s / window_s)
    return round(100.0 * uptime_sum / len(cam_ids), 2)


@router.get("/analytics/kpi", response_model=KpiResponse)
async def analytics_kpi(
    from_ts: datetime | None = Query(default=None, alias="from"),  # noqa: B008
    to_ts: datetime | None = Query(default=None, alias="to"),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> KpiResponse:
    _require_manager(user)
    now = _utcnow()
    window_to = to_ts if to_ts is not None else now
    window_from = from_ts if from_ts is not None else window_to - timedelta(hours=24)
    if window_from >= window_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'from' must be earlier than 'to'",
        )

    cache_key = f"analytics:kpi:{window_from.isoformat()}:{window_to.isoformat()}"
    redis = None
    try:
        redis = get_api_redis()
        cached = await redis.get(cache_key)
        if cached:
            return KpiResponse.model_validate_json(cached)
    except Exception:
        logger.warning("analytics_kpi: redis cache unavailable; computing uncached")
        redis = None

    peak_row = db.execute(
        select(
            AnalyticsHeadCountHourly.count.label("peak_count"),
            AnalyticsHeadCountHourly.bucket_start,
        )
        .where(
            AnalyticsHeadCountHourly.zone_id.is_(None),
            AnalyticsHeadCountHourly.bucket_start >= window_from,
            AnalyticsHeadCountHourly.bucket_start < window_to,
        )
        .order_by(AnalyticsHeadCountHourly.count.desc())
        .limit(1)
    ).first()
    peak, peak_at = (peak_row.peak_count, peak_row.bucket_start) if peak_row else (0, None)
    # Live top-up: the open hour is not rolled up yet — consult the in-process aggregator
    if window_to >= now:
        agg = get_head_count_aggregator()
        if agg is not None:
            snap = agg.snapshot()
            if snap.plant_total > peak:
                peak = snap.plant_total
                peak_at = snap.ts

    spans = (
        select(
            func.min(TrackingEvent.event_ts).label("from_ts"),
            func.max(TrackingEvent.event_ts).label("to_ts"),
        )
        .where(TrackingEvent.event_ts >= window_from, TrackingEvent.event_ts <= window_to)
        .group_by(TrackingEvent.global_track_id)
        .subquery()
    )
    avg_dwell_s = db.execute(
        select(func.avg(func.extract("epoch", spans.c.to_ts - spans.c.from_ts)))
    ).scalar()
    avg_dwell_minutes = round(float(avg_dwell_s or 0.0) / 60.0, 2)

    unknown_person_events: int = db.execute(
        select(func.count())
        .select_from(Alert)
        .where(
            Alert.alert_type == "UNKNOWN_PERSON",
            Alert.triggered_at >= window_from,
            Alert.triggered_at <= window_to,
        )
    ).scalar_one()

    severity_rows = db.execute(
        select(Alert.severity, func.count())
        .where(Alert.state.in_(("active", "acknowledged")))
        .group_by(Alert.severity)
    ).all()
    alerts_by_severity = {severity: count for severity, count in severity_rows}

    response = KpiResponse(
        head_count_peak=peak,
        head_count_peak_at=peak_at,
        avg_dwell_minutes=avg_dwell_minutes,
        unknown_person_events=unknown_person_events,
        camera_uptime_pct=_camera_uptime_pct(db, window_from, window_to),
        open_alerts=sum(alerts_by_severity.values()),
        alerts_by_severity=alerts_by_severity,
    )
    if redis is not None:
        try:
            await redis.set(
                cache_key, response.model_dump_json(), ex=get_settings().analytics_cache_ttl_s
            )
        except Exception:
            logger.warning("analytics_kpi: failed to cache result")
    return response


def _plan_camera_ids(db: Session, floor_plan_id: int, user: dict[str, Any]) -> list[int]:
    """Plan's cameras, intersected with the user's camera scope (404 unknown plan)."""
    if db.get(FloorPlan, floor_plan_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found")
    camera_ids = set(
        db.execute(select(Camera.camera_id).where(Camera.floor_plan_id == floor_plan_id)).scalars()
    )
    if user.get("role") != "admin":
        perm_camera_ids = set(
            db.execute(
                select(UserCameraPermission.camera_id).where(
                    UserCameraPermission.user_id == int(user["sub"])
                )
            ).scalars()
        )
        # Zero rows = camera scoping not configured for this user -> unrestricted
        if perm_camera_ids:
            camera_ids &= perm_camera_ids
    return sorted(camera_ids)


@router.get("/analytics/heatmap", response_model=HeatmapResponse)
async def floor_heatmap(
    floor_plan_id: int,
    from_ts: datetime = Query(alias="from"),  # noqa: B008
    to_ts: datetime = Query(alias="to"),  # noqa: B008
    bucket_m: float = Query(default=1.0),
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> HeatmapResponse:
    _require_manager(user)
    settings = get_settings()
    if bucket_m <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="bucket_m must be > 0"
        )
    if from_ts >= to_ts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'from' must be earlier than 'to'",
        )
    if (to_ts - from_ts).total_seconds() > settings.heatmap_max_window_h * 3600:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"window must be <= {settings.heatmap_max_window_h}h",
        )

    plan = db.get(FloorPlan, floor_plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found")
    bin_px = bucket_m / plan.scale_m_per_px

    cache_key = (
        f"analytics:heatmap:{floor_plan_id}:{user['sub']}:"
        f"{from_ts.isoformat()}:{to_ts.isoformat()}:{bucket_m}"
    )
    redis = None
    try:
        redis = get_api_redis()
        cached = await redis.get(cache_key)
        if cached:
            return HeatmapResponse.model_validate_json(cached)
    except Exception:
        logger.warning("floor_heatmap: redis cache unavailable; computing uncached")
        redis = None

    camera_ids = _plan_camera_ids(db, floor_plan_id, user)
    cells: list[HeatmapCell] = []
    if camera_ids:
        cell_x = func.floor(TrackingEvent.floor_x / bin_px)
        cell_y = func.floor(TrackingEvent.floor_y / bin_px)
        rows = db.execute(
            select(cell_x, cell_y, func.count())
            .where(
                TrackingEvent.camera_id.in_(camera_ids),
                TrackingEvent.floor_x.isnot(None),
                TrackingEvent.event_ts >= from_ts,
                TrackingEvent.event_ts <= to_ts,
            )
            .group_by(cell_x, cell_y)
        ).all()
        cells = [HeatmapCell(x=int(x), y=int(y), count=count) for x, y, count in rows]

    response = HeatmapResponse(bucket_m=bucket_m, bin_px=bin_px, cells=cells)
    if redis is not None:
        try:
            await redis.set(
                cache_key, response.model_dump_json(), ex=settings.analytics_cache_ttl_s
            )
        except Exception:
            logger.warning("floor_heatmap: failed to cache result")
    return response


@router.get("/live/floor-positions", response_model=FloorPositionsResponse)
def live_floor_positions(
    floor_plan_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> FloorPositionsResponse:
    settings = get_settings()
    camera_ids = _plan_camera_ids(db, floor_plan_id, user)
    if not camera_ids:
        return FloorPositionsResponse(positions=[])

    since = _utcnow() - timedelta(seconds=settings.live_positions_window_s)
    rows = (
        db.execute(
            select(TrackingEvent)
            .where(
                TrackingEvent.camera_id.in_(camera_ids),
                TrackingEvent.floor_x.isnot(None),
                TrackingEvent.event_ts >= since,
            )
            .distinct(TrackingEvent.global_track_id)
            .order_by(TrackingEvent.global_track_id, TrackingEvent.event_ts.desc())
        )
        .scalars()
        .all()
    )
    positions = [
        FloorPosition(
            global_track_id=str(r.global_track_id),
            camera_id=r.camera_id,
            person_id=r.person_id,
            floor_x=r.floor_x if r.floor_x is not None else 0.0,
            floor_y=r.floor_y if r.floor_y is not None else 0.0,
            ts=r.event_ts,
        )
        for r in rows
    ]
    return FloorPositionsResponse(positions=positions)


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
