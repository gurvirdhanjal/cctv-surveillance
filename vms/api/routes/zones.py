"""GET/POST/PATCH/DELETE /api/zones — zone management."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db, require_role
from vms.api.schemas import ZoneCreate, ZoneResponse, ZoneUpdate
from vms.db.models import Zone

router = APIRouter()


def _to_response(z: Zone) -> ZoneResponse:
    polygon: list[tuple[float, float]] | None = None
    if z.polygon_json:
        raw = json.loads(z.polygon_json)
        polygon = [tuple(pt) for pt in raw]
    return ZoneResponse(
        zone_id=z.zone_id,
        name=z.name,
        polygon=polygon,
        allowed_hours=z.allowed_hours,
        max_capacity=z.max_capacity,
        loiter_threshold_s=z.loiter_threshold_s,
        floor_plan_id=z.floor_plan_id,
        is_active=z.is_active,
    )


@router.get("/zones", response_model=list[ZoneResponse])
def list_zones(
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[ZoneResponse]:
    zones = db.query(Zone).filter(Zone.is_active.is_(True)).order_by(Zone.name).all()
    return [_to_response(z) for z in zones]


@router.post("/zones", response_model=ZoneResponse, status_code=status.HTTP_201_CREATED)
def create_zone(
    body: ZoneCreate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = require_role("admin"),  # noqa: B008
) -> ZoneResponse:
    z = Zone(
        name=body.name,
        polygon_json=json.dumps([list(pt) for pt in body.polygon]),
        allowed_hours=body.allowed_hours,
        max_capacity=body.max_capacity,
        loiter_threshold_s=body.loiter_threshold_s,
        floor_plan_id=body.floor_plan_id,
        is_active=True,
    )
    db.add(z)
    db.commit()
    db.refresh(z)
    return _to_response(z)


@router.patch("/zones/{zone_id}", response_model=ZoneResponse)
def update_zone(
    zone_id: int,
    body: ZoneUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = require_role("admin"),  # noqa: B008
) -> ZoneResponse:
    z = db.get(Zone, zone_id)
    if z is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    updates = body.model_dump(exclude_unset=True)
    if "polygon" in updates:
        z.polygon_json = json.dumps([list(pt) for pt in updates.pop("polygon")])
    for field, value in updates.items():
        setattr(z, field, value)
    db.commit()
    db.refresh(z)
    return _to_response(z)


@router.delete("/zones/{zone_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_zone(
    zone_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = require_role("admin"),  # noqa: B008
) -> Response:
    z = db.get(Zone, zone_id)
    if z is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    z.is_active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
