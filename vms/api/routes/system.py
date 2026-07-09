"""GET /api/system/metrics (Phase 4P Task 5, spec §8.4)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from vms.api.deps import get_api_redis, get_current_user
from vms.config import get_settings
from vms.scheduler.system_metrics import METRICS_KEY

router = APIRouter()

_UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="metrics unavailable"
)


@router.get("/system/metrics")
async def system_metrics(
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    try:
        raw = await get_api_redis().get(METRICS_KEY)
    except Exception as exc:
        raise _UNAVAILABLE from exc
    if not raw:
        raise _UNAVAILABLE

    payload: dict[str, Any] = json.loads(raw)
    sampled_at = datetime.fromisoformat(payload["ts"])
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    max_age_s = 3 * get_settings().metrics_sample_interval_s
    if (now - sampled_at).total_seconds() > max_age_s:
        raise _UNAVAILABLE
    return payload
