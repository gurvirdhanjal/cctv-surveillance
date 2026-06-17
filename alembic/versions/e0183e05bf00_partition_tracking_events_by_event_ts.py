"""partition_tracking_events_by_event_ts

Converts tracking_events from a plain heap table to a PostgreSQL declarative
range-partitioned table (PARTITION BY RANGE (event_ts)).

Primary key changes from (event_id) to (event_id, event_ts) — required by
PostgreSQL partitioning, which mandates the partition key appear in every
unique constraint on the parent.

The existing unique constraint uq_tracking_idem(camera_id, local_track_id,
event_ts) already includes event_ts, so it remains valid without change.

No application data is lost. The upgrade runs on an empty table in dev/test.
For a production deployment with live data, schedule this during a maintenance
window; the INSERT from tracking_events_old may take several minutes on large
tables.

Revision ID: e0183e05bf00
Revises: 4d08355b1fef
Create Date: 2026-05-28
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "e0183e05bf00"
down_revision: Union[str, None] = "4d08355b1fef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _current_month_bounds() -> tuple[str, str]:
    """Return (start, end) ISO date strings for the current UTC month."""
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1)
    else:
        end = datetime(now.year, now.month + 1, 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Rename old table to preserve data during reconstruction.
    conn.execute(text("ALTER TABLE tracking_events RENAME TO tracking_events_old"))

    # 2. Rename the old autoincrement sequence so the new BIGSERIAL can claim
    #    the canonical name tracking_events_event_id_seq.
    conn.execute(
        text(
            "ALTER SEQUENCE IF EXISTS tracking_events_event_id_seq "
            "RENAME TO tracking_events_old_event_id_seq"
        )
    )

    # 3. Drop constraints/indexes from the old table that have schema-wide names
    #    (unique constraints are backed by indexes in PostgreSQL's global namespace).
    conn.execute(
        text("ALTER TABLE tracking_events_old DROP CONSTRAINT IF EXISTS uq_tracking_idem")
    )
    conn.execute(
        text("ALTER TABLE tracking_events_old DROP CONSTRAINT IF EXISTS chk_bbox_valid")
    )
    conn.execute(
        text("DROP INDEX IF EXISTS ix_tracking_events_global_track_id")
    )
    conn.execute(text("DROP INDEX IF EXISTS ix_tracking_events_person_id"))
    conn.execute(text("DROP INDEX IF EXISTS ix_tracking_events_camera_id"))
    conn.execute(text("DROP INDEX IF EXISTS ix_tracking_events_event_ts"))

    # 5. Create the new partitioned table.
    conn.execute(
        text(
            """
            CREATE TABLE tracking_events (
                event_id        BIGSERIAL NOT NULL,
                camera_id       INTEGER NOT NULL,
                local_track_id  VARCHAR(50) NOT NULL,
                global_track_id UUID NOT NULL,
                person_id       INTEGER,
                zone_id         INTEGER,
                event_ts        TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                ingest_ts       TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                bbox_x1         INTEGER NOT NULL,
                bbox_y1         INTEGER NOT NULL,
                bbox_x2         INTEGER NOT NULL,
                bbox_y2         INTEGER NOT NULL,
                floor_x         DOUBLE PRECISION,
                floor_y         DOUBLE PRECISION,
                seq_id          BIGINT NOT NULL,
                CONSTRAINT pk_tracking_events PRIMARY KEY (event_id, event_ts),
                CONSTRAINT chk_bbox_valid
                    CHECK (bbox_x2 > bbox_x1 AND bbox_y2 > bbox_y1),
                CONSTRAINT uq_tracking_idem
                    UNIQUE (camera_id, local_track_id, event_ts),
                CONSTRAINT fk_tracking_events_camera_id
                    FOREIGN KEY (camera_id)
                    REFERENCES cameras(camera_id) ON DELETE NO ACTION,
                CONSTRAINT fk_tracking_events_person_id
                    FOREIGN KEY (person_id)
                    REFERENCES persons(person_id) ON DELETE SET NULL
            ) PARTITION BY RANGE (event_ts)
            """
        )
    )

    # 6. DEFAULT partition — catches event_ts values outside named partitions.
    conn.execute(
        text(
            "CREATE TABLE tracking_events_default "
            "PARTITION OF tracking_events DEFAULT"
        )
    )

    # 7. Current-month named partition for the deploy date.
    start, end = _current_month_bounds()
    now = datetime.now(timezone.utc)
    partition_name = f"tracking_events_y{now.year:04d}m{now.month:02d}"
    conn.execute(
        text(
            f"CREATE TABLE {partition_name} "
            f"PARTITION OF tracking_events "
            f"FOR VALUES FROM ('{start}') TO ('{end}')"
        )
    )

    # 8. Copy existing data from old table (no-op on empty DB).
    conn.execute(text("INSERT INTO tracking_events SELECT * FROM tracking_events_old"))

    # 9. Advance the new sequence past the highest copied event_id.
    conn.execute(
        text(
            "SELECT setval('tracking_events_event_id_seq', "
            "COALESCE((SELECT MAX(event_id) FROM tracking_events), 0) + 1, false)"
        )
    )

    # 10. Recreate indexes on the parent (propagate to all child partitions).
    for idx, col in [
        ("ix_tracking_events_global_track_id", "global_track_id"),
        ("ix_tracking_events_person_id", "person_id"),
        ("ix_tracking_events_camera_id", "camera_id"),
        ("ix_tracking_events_event_ts", "event_ts"),
    ]:
        conn.execute(
            text(f"CREATE INDEX {idx} ON tracking_events ({col})")
        )

    # 11. Drop the old table (and its renamed sequence drops with it).
    conn.execute(text("DROP TABLE tracking_events_old"))


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Release schema-wide constraint names from the partitioned table so
    #    tracking_events_restored can claim the canonical names.
    conn.execute(
        text(
            "ALTER TABLE tracking_events DROP CONSTRAINT IF EXISTS uq_tracking_idem"
        )
    )
    conn.execute(
        text(
            "ALTER TABLE tracking_events DROP CONSTRAINT IF EXISTS chk_bbox_valid"
        )
    )
    conn.execute(text("DROP INDEX IF EXISTS ix_tracking_events_global_track_id"))
    conn.execute(text("DROP INDEX IF EXISTS ix_tracking_events_person_id"))
    conn.execute(text("DROP INDEX IF EXISTS ix_tracking_events_camera_id"))
    conn.execute(text("DROP INDEX IF EXISTS ix_tracking_events_event_ts"))

    # 3. Create a plain (non-partitioned) replacement table.
    conn.execute(
        text(
            """
            CREATE TABLE tracking_events_restored (
                event_id        BIGINT NOT NULL,
                camera_id       INTEGER NOT NULL,
                local_track_id  VARCHAR(50) NOT NULL,
                global_track_id UUID NOT NULL,
                person_id       INTEGER,
                zone_id         INTEGER,
                event_ts        TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                ingest_ts       TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                bbox_x1         INTEGER NOT NULL,
                bbox_y1         INTEGER NOT NULL,
                bbox_x2         INTEGER NOT NULL,
                bbox_y2         INTEGER NOT NULL,
                floor_x         DOUBLE PRECISION,
                floor_y         DOUBLE PRECISION,
                seq_id          BIGINT NOT NULL,
                CONSTRAINT tracking_events_pkey PRIMARY KEY (event_id),
                CONSTRAINT chk_bbox_valid
                    CHECK (bbox_x2 > bbox_x1 AND bbox_y2 > bbox_y1),
                CONSTRAINT uq_tracking_idem
                    UNIQUE (camera_id, local_track_id, event_ts)
            )
            """
        )
    )

    # 4. Copy data from all partitions through the parent table.
    conn.execute(
        text("INSERT INTO tracking_events_restored SELECT * FROM tracking_events")
    )

    # 5. Drop the partitioned table (CASCADE drops all child partitions and
    #    the tracking_events_event_id_seq sequence).
    conn.execute(text("DROP TABLE tracking_events CASCADE"))

    # 6. Rename restored table to canonical name.
    conn.execute(
        text("ALTER TABLE tracking_events_restored RENAME TO tracking_events")
    )

    # 7. Restore foreign key constraints.
    conn.execute(
        text(
            "ALTER TABLE tracking_events ADD CONSTRAINT fk_tracking_events_camera_id "
            "FOREIGN KEY (camera_id) REFERENCES cameras(camera_id) ON DELETE NO ACTION"
        )
    )
    conn.execute(
        text(
            "ALTER TABLE tracking_events ADD CONSTRAINT fk_tracking_events_person_id "
            "FOREIGN KEY (person_id) REFERENCES persons(person_id) ON DELETE SET NULL"
        )
    )

    # 8. Restore indexes.
    for idx, col in [
        ("ix_tracking_events_global_track_id", "global_track_id"),
        ("ix_tracking_events_person_id", "person_id"),
        ("ix_tracking_events_camera_id", "camera_id"),
        ("ix_tracking_events_event_ts", "event_ts"),
    ]:
        conn.execute(
            text(f"CREATE INDEX {idx} ON tracking_events ({col})")
        )

    # 9. Restore the autoincrement sequence (was dropped by CASCADE).
    conn.execute(text("CREATE SEQUENCE tracking_events_event_id_seq AS BIGINT"))
    conn.execute(
        text(
            "SELECT setval('tracking_events_event_id_seq', "
            "COALESCE((SELECT MAX(event_id) FROM tracking_events), 0) + 1, false)"
        )
    )
    conn.execute(
        text(
            "ALTER TABLE tracking_events ALTER COLUMN event_id "
            "SET DEFAULT nextval('tracking_events_event_id_seq')"
        )
    )
    conn.execute(
        text(
            "ALTER SEQUENCE tracking_events_event_id_seq "
            "OWNED BY tracking_events.event_id"
        )
    )
