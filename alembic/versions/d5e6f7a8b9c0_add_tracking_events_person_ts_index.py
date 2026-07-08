"""add_tracking_events_person_ts_index

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-07-08

Composite (person_id, event_ts) index on tracking_events for the persons detail
last-seen lookup and the person timeline endpoint (Phase 4P Tasks 1/1b).
Created on the partitioned parent, so PostgreSQL cascades it to every partition.
"""

from __future__ import annotations

from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_tracking_events_person_ts",
        "tracking_events",
        ["person_id", "event_ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_tracking_events_person_ts", table_name="tracking_events")
