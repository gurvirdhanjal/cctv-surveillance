"""add_zone_is_active_floor_plan_id

Revision ID: a0ae6d1f0eec
Revises: b2c3d4e5f6a7
Create Date: 2026-06-24 02:39:40.534125

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a0ae6d1f0eec"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # is_active: server_default backfills existing rows; drop default after to keep schema clean
    op.add_column(
        "zones",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("zones", "is_active", server_default=None)

    # floor_plan_id: plain nullable int, no FK (no floor_plans table yet)
    op.add_column(
        "zones",
        sa.Column("floor_plan_id", sa.Integer(), nullable=True),
    )

    op.create_check_constraint(
        "chk_zone_nonneg",
        "zones",
        "(max_capacity IS NULL OR max_capacity >= 0) AND loiter_threshold_s >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("chk_zone_nonneg", "zones", type_="check")
    op.drop_column("zones", "floor_plan_id")
    op.drop_column("zones", "is_active")
