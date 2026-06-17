"""camera_shutter_and_overrides

Revision ID: bda2a93aaa9f
Revises: 942aa02e2872
Create Date: 2026-06-06

Adds:
  - cameras.shutter_type (new) — rolling/global/unknown, NOT NULL, default 'unknown'
  - cameras.model_overrides (Phase 3 addition) — nullable Text, may already exist on some DBs
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bda2a93aaa9f"
down_revision: Union[str, None] = "942aa02e2872"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cameras",
        sa.Column(
            "shutter_type",
            sa.String(10),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.create_check_constraint(
        "chk_camera_shutter",
        "cameras",
        "shutter_type IN ('rolling', 'global', 'unknown')",
    )
    # model_overrides: Phase 3 addition — may be absent from older test DBs.
    # Use ADD COLUMN IF NOT EXISTS to be safe across environments.
    op.execute(
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS model_overrides TEXT"
    )


def downgrade() -> None:
    op.drop_constraint("chk_camera_shutter", "cameras", type_="check")
    op.drop_column("cameras", "shutter_type")
