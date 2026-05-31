"""phase2d_ble_badge_resolved_via

Revision ID: 942aa02e2872
Revises: bc0e96331eb1
Create Date: 2026-06-01 00:56:40.515153

Adds:
  - persons.badge_id (nullable, unique) — BLE badge MAC address
  - ble_events table                    — BLE badge detection log
  - tracking_events.resolved_via        — how person_id was resolved (face/body/ble/unknown)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "942aa02e2872"
down_revision: Union[str, None] = "bc0e96331eb1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # badge_id on persons
    op.add_column("persons", sa.Column("badge_id", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_persons_badge_id", "persons", ["badge_id"])
    op.create_index("ix_persons_badge_id", "persons", ["badge_id"])

    # ble_events table
    op.create_table(
        "ble_events",
        sa.Column("event_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "person_id",
            sa.Integer,
            sa.ForeignKey("persons.person_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("badge_id", sa.String(64), nullable=False),
        sa.Column(
            "zone_id",
            sa.Integer,
            sa.ForeignKey("zones.zone_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rssi", sa.Integer, nullable=True),
        sa.Column("reader_id", sa.String(64), nullable=False),
        sa.Column("event_ts", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_ble_events_person_id", "ble_events", ["person_id"])
    op.create_index("ix_ble_events_badge_id", "ble_events", ["badge_id"])
    op.create_index("ix_ble_events_event_ts", "ble_events", ["event_ts"])

    # resolved_via on tracking_events (partitioned table — PostgreSQL propagates to partitions)
    op.add_column("tracking_events", sa.Column("resolved_via", sa.String(16), nullable=True))
    op.create_check_constraint(
        "chk_tracking_resolved_via",
        "tracking_events",
        "resolved_via IN ('face','body','ble','unknown')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_tracking_resolved_via", "tracking_events", type_="check")
    op.drop_column("tracking_events", "resolved_via")

    op.drop_index("ix_ble_events_event_ts", table_name="ble_events")
    op.drop_index("ix_ble_events_badge_id", table_name="ble_events")
    op.drop_index("ix_ble_events_person_id", table_name="ble_events")
    op.drop_table("ble_events")

    op.drop_index("ix_persons_badge_id", table_name="persons")
    op.drop_constraint("uq_persons_badge_id", "persons", type_="unique")
    op.drop_column("persons", "badge_id")
