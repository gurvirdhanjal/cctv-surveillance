"""Person enrollment and search endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.api.schemas import (
    EmbeddingCreate,
    EmbeddingResponse,
    PersonCreate,
    PersonResponse,
    PurgeRequest,
)
from vms.db.audit import write_audit_event
from vms.db.models import Person, PersonEmbedding
from vms.db.models import User as DBUser

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


@router.delete("/persons/{person_id}")
def purge_person(
    person_id: int,
    body: PurgeRequest,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Response:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    if person.name != body.confirmation_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="confirmation_name does not match person.name",
        )

    person.is_active = False
    person.purged_at = datetime.utcnow()
    person.thumbnail_path = None

    blank: list[float] = np.zeros(512, dtype=np.float32).tolist()
    for emb in db.query(PersonEmbedding).filter_by(person_id=person_id).all():
        emb.embedding = blank
        emb.quality_score = 0.0

    # Resolve actor_user_id only when the user exists in DB — handles deleted-user edge case
    actor_id: int | None = int(user["sub"])
    if db.get(DBUser, actor_id) is None:
        actor_id = None

    # write_audit_event calls session.commit() internally -- do not commit separately
    write_audit_event(
        db,
        event_type="PERSON_PURGED",
        actor_user_id=actor_id,
        target_type="person",
        target_id=str(person_id),
        payload=body.reason,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
