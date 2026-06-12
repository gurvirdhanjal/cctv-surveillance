"""GET/POST/PATCH/DELETE /api/alert-routing — routing rule management."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db, require_role
from vms.api.schemas import AlertRoutingCreate, AlertRoutingResponse, AlertRoutingUpdate
from vms.db.audit import write_audit_event
from vms.db.models import AlertRouting
from vms.db.models import User as DBUser

router = APIRouter()


@router.get("/alert-routing", response_model=list[AlertRoutingResponse])
def list_routing_rules(
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[AlertRouting]:
    return db.query(AlertRouting).filter(AlertRouting.is_active.is_(True)).all()


@router.post("/alert-routing", response_model=AlertRoutingResponse, status_code=201)
def create_routing_rule(
    body: AlertRoutingCreate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = require_role("admin", "super_admin"),  # noqa: B008
) -> AlertRouting:
    rule = AlertRouting(
        alert_type=body.alert_type,
        severity=body.severity,
        zone_id=body.zone_id,
        channel=body.channel,
        target=body.target,
        is_active=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/alert-routing/{routing_id}", response_model=AlertRoutingResponse)
def update_routing_rule(
    routing_id: int,
    body: AlertRoutingUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = require_role("admin", "super_admin"),  # noqa: B008
) -> AlertRouting:
    rule = db.get(AlertRouting, routing_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing rule not found")
    before = {
        "alert_type": rule.alert_type,
        "severity": rule.severity,
        "zone_id": rule.zone_id,
        "channel": rule.channel,
        "target": rule.target,
        "is_active": rule.is_active,
    }
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    try:
        actor_id: int | None = int(_user["sub"])
    except (ValueError, KeyError):
        actor_id = None
    if actor_id is not None and db.get(DBUser, actor_id) is None:
        actor_id = None
    write_audit_event(
        db,
        event_type="ROUTING_RULE_UPDATED",
        actor_user_id=actor_id,
        target_type="alert_routing",
        target_id=str(routing_id),
        payload=json.dumps({"routing_id": routing_id, "from": before, "to": updates}),
    )
    return rule


@router.delete("/alert-routing/{routing_id}", status_code=204, response_class=Response)
def delete_routing_rule(
    routing_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = require_role("admin", "super_admin"),  # noqa: B008
) -> Response:
    rule = db.get(AlertRouting, routing_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing rule not found")
    rule.is_active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
