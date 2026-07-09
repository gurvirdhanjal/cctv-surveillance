"""Head-count hourly rollup (Phase 4P Task 4).

Aggregates tracking_events into analytics_head_count_hourly. Dedup mirrors
HeadCountAggregator (spec §N.1): identified persons dedup by person_id across
tracks; unknowns dedup per-track by global_track_id.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from vms.config import get_settings
from vms.db.models import AnalyticsHeadCountHourly, TrackingEvent

# 'p<person_id>' for identified persons, 'g<gid>' for unknowns — one head each.
_HEAD_KEY = text("COALESCE('p' || person_id::text, 'g' || global_track_id::text)")


def _upsert(session: Session, bucket_start: datetime, zone_id: int | None, count: int) -> None:
    stmt = pg_insert(AnalyticsHeadCountHourly).values(
        bucket_start=bucket_start, zone_id=zone_id, count=count
    )
    session.execute(
        stmt.on_conflict_do_update(
            constraint="uq_head_count_bucket_zone",
            set_={"count": stmt.excluded.count},
        )
    )


def rollup_head_count_hour(session: Session, bucket_start: datetime) -> None:
    """Aggregate one closed hour idempotently (ON CONFLICT DO UPDATE).

    Always writes the plant-total row (zone_id NULL), even when 0 — its presence
    marks the hour as processed for backfill. Zone rows only for zones seen.
    """
    bucket_end = bucket_start + timedelta(hours=1)
    window = (TrackingEvent.event_ts >= bucket_start) & (TrackingEvent.event_ts < bucket_end)

    plant: int = session.execute(
        select(func.count(func.distinct(_HEAD_KEY))).select_from(TrackingEvent).where(window)
    ).scalar_one()
    _upsert(session, bucket_start, None, plant)

    zone_rows = session.execute(
        select(TrackingEvent.zone_id, func.count(func.distinct(_HEAD_KEY)))
        .where(window, TrackingEvent.zone_id.isnot(None))
        .group_by(TrackingEvent.zone_id)
    ).all()
    for zone_id, count in zone_rows:
        _upsert(session, bucket_start, zone_id, count)


def backfill_missed_hours(session: Session, *, now: datetime | None = None) -> int:
    """Roll up every missed closed hour, bounded by VMS_ROLLUP_BACKFILL_MAX_HOURS.

    Returns the number of hours rolled up. Resumes after the latest plant-total
    row; an empty table starts at the bound. Caller owns the commit.
    """
    settings = get_settings()
    if now is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
    last_closed = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    earliest = last_closed - timedelta(hours=settings.rollup_backfill_max_hours - 1)

    latest: datetime | None = session.execute(
        select(func.max(AnalyticsHeadCountHourly.bucket_start)).where(
            AnalyticsHeadCountHourly.zone_id.is_(None)
        )
    ).scalar_one_or_none()

    start = earliest if latest is None else max(latest + timedelta(hours=1), earliest)
    done = 0
    bucket = start
    while bucket <= last_closed:
        rollup_head_count_hour(session, bucket)
        done += 1
        bucket += timedelta(hours=1)
    return done
