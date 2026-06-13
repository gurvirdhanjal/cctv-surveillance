"""system_critical_alert_type

Revision ID: f1a2b3c4d5e6
Revises: bda2a93aaa9f
Create Date: 2026-06-13

Adds:
  - alerts.alert_type CHECK: adds PPE_VIOLATION and SYSTEM_CRITICAL
  - alerts.camera_id: make nullable (was NOT NULL)
  - alerts.chk_alert_camera_id_required: enforces camera_id IS NOT NULL for
    all non-SYSTEM_CRITICAL alert types

SYSTEM_CRITICAL alerts are emitted by the scheduler process for infrastructure
failure events. They intentionally have no camera_id (camera_id=None).
All security alert types (UNKNOWN_PERSON, INTRUSION, etc.) still require a
camera_id — enforced by chk_alert_camera_id_required.

downgrade() note: restoring camera_id NOT NULL will fail if any SYSTEM_CRITICAL
rows exist in the alerts table. Drain or delete them before downgrading.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "bda2a93aaa9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_ALERT_TYPES = (
    "alert_type IN ('UNKNOWN_PERSON','PERSON_LOST','CROWD_DENSITY',"
    "'INTRUSION','VIOLENCE','LOITERING')"
)
_NEW_ALERT_TYPES = (
    "alert_type IN ('UNKNOWN_PERSON','PERSON_LOST','CROWD_DENSITY',"
    "'INTRUSION','VIOLENCE','LOITERING','PPE_VIOLATION','SYSTEM_CRITICAL')"
)
_CAMERA_ID_REQUIRED = (
    "alert_type = 'SYSTEM_CRITICAL' OR camera_id IS NOT NULL"
)


def upgrade() -> None:
    # 1. Expand alert_type CHECK constraint.
    op.drop_constraint("chk_alert_type", "alerts", type_="check")
    op.create_check_constraint("chk_alert_type", "alerts", _NEW_ALERT_TYPES)

    # 2. Make camera_id nullable so SYSTEM_CRITICAL rows can omit it.
    op.alter_column("alerts", "camera_id", existing_type=sa.Integer(), nullable=True)

    # 3. Partial CHECK: all non-SYSTEM_CRITICAL alerts must still have a camera_id.
    op.create_check_constraint("chk_alert_camera_id_required", "alerts", _CAMERA_ID_REQUIRED)


def downgrade() -> None:
    # Remove the partial check first.
    op.drop_constraint("chk_alert_camera_id_required", "alerts", type_="check")

    # Restore camera_id NOT NULL.
    # WARNING: this will fail if SYSTEM_CRITICAL rows with camera_id=NULL exist.
    # Delete or update them before running this downgrade.
    op.alter_column("alerts", "camera_id", existing_type=sa.Integer(), nullable=False)

    # Restore the narrow alert_type constraint.
    op.drop_constraint("chk_alert_type", "alerts", type_="check")
    op.create_check_constraint("chk_alert_type", "alerts", _OLD_ALERT_TYPES)
