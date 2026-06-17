"""add_row_hash_version_to_audit_log

Revision ID: a1b2c3d4e5f6
Revises: 5b4fe0f76497
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "5b4fe0f76497"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_log",
        sa.Column(
            "row_hash_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("audit_log", "row_hash_version")
