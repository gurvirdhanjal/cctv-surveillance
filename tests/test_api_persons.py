"""Tests for person enrollment and search endpoints."""

from __future__ import annotations

import numpy as np
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token
from vms.api.main import app


def _auth_headers(role: str = "admin") -> dict[str, str]:
    token = create_access_token(user_id=1, role=role)
    return {"Authorization": f"Bearer {token}"}


async def test_create_person_returns_201(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/persons",
            json={"name": "Alice Tester", "employee_id": "E001"},
            headers=_auth_headers(),
        )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Alice Tester"
    assert "person_id" in body


async def test_create_person_requires_auth() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/persons",
            json={"name": "No Auth", "employee_id": "E999"},
        )
    assert response.status_code == 401


async def test_search_persons_returns_matching_results(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/persons",
            json={"name": "Bob Search", "employee_id": "E002"},
            headers=_auth_headers(),
        )
        response = await client.get(
            "/api/persons/search?q=Bob",
            headers=_auth_headers(),
        )
    assert response.status_code == 200
    results = response.json()
    assert any("Bob" in p["name"] for p in results)


async def test_add_embedding_to_existing_person(db_session: Session) -> None:
    embedding = [float(x) for x in np.random.randn(512).astype(np.float32)]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/persons",
            json={"name": "Carol Embed", "employee_id": "E003"},
            headers=_auth_headers(),
        )
        person_id = create_resp.json()["person_id"]
        embed_resp = await client.post(
            f"/api/persons/{person_id}/embeddings",
            json={"embedding": embedding, "quality_score": 0.85},
            headers=_auth_headers(),
        )
    assert embed_resp.status_code == 201
