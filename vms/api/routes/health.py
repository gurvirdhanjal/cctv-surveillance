"""Health check and readiness probe endpoints."""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from vms.api.deps import get_api_redis, get_db
from vms.api.schemas import HealthResponse, ReadinessResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")


@router.get("/ready", response_model=ReadinessResponse)
async def ready(
    db: Session = Depends(get_db),  # noqa: B008
    redis: aioredis.Redis = Depends(get_api_redis),  # noqa: B008
) -> Any:
    db_status = "ok"
    redis_status = "ok"

    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "fail"

    try:
        await redis.ping()
    except Exception:
        redis_status = "fail"

    response = ReadinessResponse(db=db_status, redis=redis_status)
    status_code = 200 if db_status == "ok" and redis_status == "ok" else 503
    return JSONResponse(status_code=status_code, content=response.model_dump())
