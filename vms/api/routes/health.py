"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from vms.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")
