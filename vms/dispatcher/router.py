"""Routing rule evaluator — matches alert attributes against alert_routing table."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from vms.db.models import AlertRouting


def match_routing_rules(
    db: Session,
    *,
    alert_type: str,
    severity: str,
    zone_id: int | None,
) -> list[AlertRouting]:
    """Return all active routing rules that match the given alert attributes.

    Rules with NULL fields are treated as wildcards:
      - alert_type=NULL  -> match any alert_type
      - severity=NULL    -> match any severity
      - zone_id=NULL     -> match any zone

    The WEBSOCKET channel is excluded — it is already handled by the anomaly orchestrator.
    """
    q = (
        db.query(AlertRouting)
        .filter(AlertRouting.is_active.is_(True))
        .filter(AlertRouting.channel != "WEBSOCKET")
        .filter(or_(AlertRouting.alert_type.is_(None), AlertRouting.alert_type == alert_type))
        .filter(or_(AlertRouting.severity.is_(None), AlertRouting.severity == severity))
    )
    if zone_id is None:
        q = q.filter(AlertRouting.zone_id.is_(None))
    else:
        q = q.filter(or_(AlertRouting.zone_id.is_(None), AlertRouting.zone_id == zone_id))
    return q.all()
