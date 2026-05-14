"""Person enrollment and search endpoints."""

from __future__ import annotations

from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.api.schemas import EmbeddingCreate, EmbeddingResponse, PersonCreate, PersonResponse
from vms.db.models import Person, PersonEmbedding

router = APIRouter()


@router.post("/persons", response_model=PersonResponse, status_code=status.HTTP_201_CREATED)
def create_person(
    body: PersonCreate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Person:
    person = Person(
        name=body.name,
        employee_id=body.employee_id,
    )
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.post(
    "/persons/{person_id}/embeddings",
    response_model=EmbeddingResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_embedding(
    person_id: int,
    body: EmbeddingCreate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> PersonEmbedding:
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    emb_array = np.array(body.embedding, dtype=np.float32)
    record = PersonEmbedding(
        person_id=person_id,
        embedding=emb_array,
        quality_score=body.quality_score,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/persons/search", response_model=list[PersonResponse])
def search_persons(
    q: str,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[Person]:
    return (
        db.query(Person)
        .filter(Person.name.ilike(f"%{q}%") | Person.employee_id.ilike(f"%{q}%"))
        .limit(50)
        .all()
    )
