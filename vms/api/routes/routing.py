"""GET/POST/DELETE /api/alert-routing — routing rule management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db, require_role
from vms.api.schemas import AlertRoutingCreate, AlertRoutingResponse
from vms.db.models import AlertRouting

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
