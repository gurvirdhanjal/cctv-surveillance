"""phase2b_anomaly_framework

Adds:
  - alerts.dedup_key  (String 100, nullable)
  - alerts.ix_alerts_state index
  - alerts.ix_alerts_dedup_key_active partial index (where state='active')
  - alerts CHECK constraints: chk_alert_state, chk_alert_type
  - 6 default rows seeded in anomaly_detectors

Revision ID: bc0e96331eb1
Revises: e0183e05bf00
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bc0e96331eb1"
down_revision: Union[str, None] = "e0183e05bf00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DETECTORS = [
    ("UNKNOWN_PERSON", "vms.anomaly.detectors.unknown_person.UnknownPersonDetector"),
    ("PERSON_LOST", "vms.anomaly.detectors.person_lost.PersonLostDetector"),
    ("CROWD_DENSITY", "vms.anomaly.detectors.crowd_density.CrowdDensityDetector"),
    ("INTRUSION", "vms.anomaly.detectors.intrusion.IntrusionDetector"),
    ("VIOLENCE", "vms.anomaly.detectors.violence.ViolenceDetector"),
    ("LOITERING", "vms.anomaly.detectors.loitering.LoiteringDetector"),
]


def upgrade() -> None:
    op.add_column("alerts", sa.Column("dedup_key", sa.String(length=100), nullable=True))
    op.create_index("ix_alerts_state", "alerts", ["state"])
    op.create_index(
        "ix_alerts_dedup_key_active",
        "alerts",
        ["dedup_key"],
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_check_constraint(
        "chk_alert_state",
        "alerts",
        "state IN ('active', 'acknowledged', 'resolved', 'suppressed')",
    )
    op.create_check_constraint(
        "chk_alert_type",
        "alerts",
        "alert_type IN ('UNKNOWN_PERSON','PERSON_LOST','CROWD_DENSITY',"
        "'INTRUSION','VIOLENCE','LOITERING')",
    )

    detectors_table = sa.table(
        "anomaly_detectors",
        sa.column("alert_type", sa.String),
        sa.column("class_path", sa.String),
        sa.column("is_enabled", sa.Boolean),
    )
    op.bulk_insert(
        detectors_table,
        [{"alert_type": at, "class_path": cp, "is_enabled": True} for at, cp in _DETECTORS],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM anomaly_detectors WHERE alert_type IN ("
        "'UNKNOWN_PERSON','PERSON_LOST','CROWD_DENSITY',"
        "'INTRUSION','VIOLENCE','LOITERING')"
    )
    op.drop_constraint("chk_alert_type", "alerts", type_="check")
    op.drop_constraint("chk_alert_state", "alerts", type_="check")
    op.drop_index("ix_alerts_dedup_key_active", table_name="alerts")
    op.drop_index("ix_alerts_state", table_name="alerts")
    op.drop_column("alerts", "dedup_key")
