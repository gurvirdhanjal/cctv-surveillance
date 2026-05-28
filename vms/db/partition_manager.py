"""Utilities for managing monthly range partitions on the tracking_events table."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import Engine, text


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    """Return (start, end) ISO date strings for the given year/month."""
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    """Add *delta* months to (year, month), returning a new (year, month) pair."""
    total = (month - 1) + delta
    return year + total // 12, total % 12 + 1


def ensure_future_partitions(engine: Engine, months_ahead: int = 3) -> None:
    """Create monthly partitions for the current month through months_ahead months later.

    Uses CREATE TABLE IF NOT EXISTS so it is safe to call repeatedly.
    Does nothing if tracking_events is not yet a partitioned table (relkind != 'p'),
    which can happen before the partitioning migration has been applied.
    """
    now = datetime.now(timezone.utc)
    with engine.connect() as conn:
        # Guard: skip gracefully when the table is absent or not yet partitioned.
        relkind = conn.execute(
            text(
                "SELECT relkind FROM pg_class "
                "WHERE relname = 'tracking_events' AND relkind = 'p'"
            )
        ).scalar()
        if relkind is None:
            return

        for delta in range(months_ahead + 1):
            year, month = _add_months(now.year, now.month, delta)
            partition_name = f"tracking_events_y{year:04d}m{month:02d}"
            start, end = _month_bounds(year, month)
            conn.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {partition_name} "
                    f"PARTITION OF tracking_events "
                    f"FOR VALUES FROM ('{start}') TO ('{end}')"
                )
            )
        conn.commit()


def drop_partitions_before(engine: Engine, cutoff: datetime) -> None:
    """Drop all named monthly partitions whose upper bound is <= *cutoff*.

    The DEFAULT partition (tracking_events_default) is never dropped.
    """
    cutoff_naive = cutoff.replace(tzinfo=None)
    with engine.connect() as conn:
        for name in list_partitions(engine):
            if name == "tracking_events_default":
                continue
            m = re.fullmatch(r"tracking_events_y(\d{4})m(\d{2})", name)
            if not m:
                continue
            year, month = int(m.group(1)), int(m.group(2))
            _, end_str = _month_bounds(year, month)
            partition_end = datetime.strptime(end_str, "%Y-%m-%d")
            if partition_end <= cutoff_naive:
                conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
        conn.commit()


def list_partitions(engine: Engine) -> list[str]:
    """Return the names of all child partitions of tracking_events."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
                SELECT c.relname
                FROM   pg_inherits  i
                JOIN   pg_class     c ON c.oid = i.inhrelid
                JOIN   pg_class     p ON p.oid = i.inhparent
                WHERE  p.relname = 'tracking_events'
                ORDER  BY c.relname
                """)).fetchall()
    return [row[0] for row in rows]
