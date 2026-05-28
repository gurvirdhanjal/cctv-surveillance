"""Integration tests for vms.db.partition_manager.

Requires a real PostgreSQL instance with tracking_events partitioned.
Run only after the partitioning migration has been applied (alembic upgrade head).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from vms.db.session import engine


@pytest.fixture()
def _cleanup_partitions():
    """Drop any partitions created during a test to keep the DB clean."""
    created: list[str] = []
    yield created
    with engine.connect() as conn:
        for name in created:
            conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
        conn.commit()


@pytest.mark.integration
def test_ensure_future_partitions_creates_current_month(_cleanup_partitions: list[str]) -> None:
    from vms.db.partition_manager import ensure_future_partitions, list_partitions

    before = set(list_partitions(engine))
    ensure_future_partitions(engine, months_ahead=0)
    after = set(list_partitions(engine))

    new_partitions = after - before
    _cleanup_partitions.extend(new_partitions)

    today = datetime.now(timezone.utc)
    expected = f"tracking_events_y{today.year:04d}m{today.month:02d}"
    assert expected in after


@pytest.mark.integration
def test_ensure_future_partitions_creates_n_months_ahead(_cleanup_partitions: list[str]) -> None:
    from vms.db.partition_manager import ensure_future_partitions, list_partitions

    before = set(list_partitions(engine))
    ensure_future_partitions(engine, months_ahead=2)
    after = set(list_partitions(engine))

    new_partitions = after - before
    _cleanup_partitions.extend(new_partitions)

    # After ensure_future_partitions(months_ahead=2) there should be at least 3
    # named monthly partitions in total (current month + 2 ahead). The current-month
    # partition may already exist from the migration, so we check the total set.
    named = {p for p in after if p != "tracking_events_default"}
    assert len(named) >= 3  # current + 2 more = 3 months


@pytest.mark.integration
def test_ensure_future_partitions_is_idempotent(_cleanup_partitions: list[str]) -> None:
    from vms.db.partition_manager import ensure_future_partitions, list_partitions

    before = set(list_partitions(engine))
    ensure_future_partitions(engine, months_ahead=0)
    after_first = set(list_partitions(engine))
    ensure_future_partitions(engine, months_ahead=0)
    after_second = set(list_partitions(engine))

    new_partitions = after_first - before
    _cleanup_partitions.extend(new_partitions)

    assert after_first == after_second


@pytest.mark.integration
def test_drop_partitions_before_removes_old_partition(
    _cleanup_partitions: list[str],
) -> None:
    from vms.db.partition_manager import drop_partitions_before, list_partitions

    # Create a partition 2 years in the past
    past_year, past_month = 2020, 1
    partition_name = f"tracking_events_y{past_year:04d}m{past_month:02d}"
    with engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {partition_name} "
                f"PARTITION OF tracking_events "
                f"FOR VALUES FROM ('2020-01-01') TO ('2020-02-01')"
            )
        )
        conn.commit()

    assert partition_name in list_partitions(engine)

    # Drop partitions before Feb 2020
    drop_partitions_before(engine, datetime(2020, 2, 1, tzinfo=timezone.utc))

    assert partition_name not in list_partitions(engine)


@pytest.mark.integration
def test_drop_partitions_before_never_drops_default() -> None:
    from vms.db.partition_manager import drop_partitions_before, list_partitions

    # Use a very old cutoff to try to drop everything
    drop_partitions_before(engine, datetime(1970, 1, 1, tzinfo=timezone.utc))

    partitions = list_partitions(engine)
    assert "tracking_events_default" in partitions


@pytest.mark.integration
def test_list_partitions_returns_all_children(_cleanup_partitions: list[str]) -> None:
    from vms.db.partition_manager import ensure_future_partitions, list_partitions

    before = set(list_partitions(engine))
    ensure_future_partitions(engine, months_ahead=1)
    after = set(list_partitions(engine))

    new_partitions = after - before
    _cleanup_partitions.extend(new_partitions)

    # DEFAULT + at least 2 named partitions after ensure_future_partitions(months_ahead=1)
    assert len(after) >= 2
    assert "tracking_events_default" in after


@pytest.mark.integration
def test_list_partitions_does_not_include_parent() -> None:
    from vms.db.partition_manager import list_partitions

    partitions = list_partitions(engine)
    assert "tracking_events" not in partitions
