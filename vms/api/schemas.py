"""Pydantic request/response schemas for the VMS API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PersonCreate(BaseModel):
    name: str = Field(..., max_length=200)
    employee_id: str = Field(..., max_length=50)


class PersonResponse(BaseModel):
    person_id: int
    name: str
    employee_id: str
    is_active: bool

    model_config = {"from_attributes": True}


class EmbeddingCreate(BaseModel):
    embedding: list[float] = Field(..., min_length=512, max_length=512)
    quality_score: float = Field(..., ge=0.0, le=1.0)


class EmbeddingResponse(BaseModel):
    embedding_id: int
    person_id: int
    quality_score: float

    model_config = {"from_attributes": True}


class PurgeRequest(BaseModel):
    confirmation_name: str = Field(..., description="Must match person.name exactly")
    reason: str = Field(..., min_length=10, max_length=500)


class HealthResponse(BaseModel):
    status: str
    version: str
