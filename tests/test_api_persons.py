"""Tests for person enrollment and search endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token
from vms.api.main import app
from vms.db.models import Person


def _auth_headers(role: str = "admin") -> dict[str, str]:
    token = create_access_token(user_id=1, role=role)
    return {"Authorization": f"Bearer {token}"}


def _auth_headers_role(role: str) -> dict[str, str]:
    from vms.api.deps import create_access_token

    token = create_access_token(user_id=99, role=role)
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


async def test_purge_person_returns_204(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/persons",
            json={"name": "Purge Target", "employee_id": "E_PURGE_01"},
            headers=_auth_headers(role="admin"),
        )
        person_id = create_resp.json()["person_id"]
        # httpx.delete() does not accept json=; use request() for DELETE with body
        resp = await client.request(
            "DELETE",
            f"/api/persons/{person_id}",
            json={
                "confirmation_name": "Purge Target",
                "reason": "GDPR erasure request from subject",
            },
            headers=_auth_headers(role="admin"),
        )
    assert resp.status_code == 204


async def test_purge_person_requires_admin_role() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.request(
            "DELETE",
            "/api/persons/1",
            json={"confirmation_name": "Anyone", "reason": "test reason here please"},
            headers=_auth_headers(role="guard"),
        )
    assert resp.status_code == 403


async def test_purge_person_rejects_wrong_confirmation(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/persons",
            json={"name": "Real Name", "employee_id": "E_PURGE_02"},
            headers=_auth_headers(role="admin"),
        )
        person_id = create_resp.json()["person_id"]
        resp = await client.request(
            "DELETE",
            f"/api/persons/{person_id}",
            json={"confirmation_name": "Wrong Name", "reason": "test reason here please"},
            headers=_auth_headers(role="admin"),
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_person_guard_role_returns_403() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/persons",
            json={"name": "Bob", "employee_id": "E999"},
            headers=_auth_headers_role("guard"),
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_add_embedding_guard_role_returns_403(db_session: Session) -> None:
    person = Person(name="Alice", employee_id="EA1")
    db_session.add(person)
    db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/persons/{person.person_id}/embeddings",
            json={"embedding": [0.0] * 512, "quality_score": 0.9},
            headers=_auth_headers_role("guard"),
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_search_excludes_purged_persons(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp1 = await client.post(
            "/api/persons",
            json={"name": "ActiveAlice", "employee_id": "AA1"},
            headers=_auth_headers_role("manager"),
        )
        assert create_resp1.status_code == 201

        create_resp2 = await client.post(
            "/api/persons",
            json={"name": "ActiveAlice", "employee_id": "AA2"},
            headers=_auth_headers_role("manager"),
        )
        person_id2 = create_resp2.json()["person_id"]

        purge_resp = await client.request(
            "DELETE",
            f"/api/persons/{person_id2}",
            json={"confirmation_name": "ActiveAlice", "reason": "test purge"},
            headers=_auth_headers_role("admin"),
        )
        assert purge_resp.status_code == 204

        response = await client.get(
            "/api/persons/search?q=ActiveAlice",
            headers=_auth_headers_role("manager"),
        )
    assert response.status_code == 200
    results = response.json()
    ids = [r["employee_id"] for r in results]
    assert "AA1" in ids
    assert "AA2" not in ids


@pytest.mark.asyncio
async def test_add_embedding_publishes_faiss_add() -> None:
    with patch("vms.api.routes.persons.faiss_dirty.publish_add", new_callable=AsyncMock) as mock_pub:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_resp = await client.post(
                "/api/persons",
                json={"name": "FaissTest", "employee_id": "FT_FAISS1"},
                headers=_auth_headers("admin"),
            )
            assert create_resp.status_code == 201
            person_id = create_resp.json()["person_id"]
            response = await client.post(
                f"/api/persons/{person_id}/embeddings",
                json={"embedding": [0.1] * 512, "quality_score": 0.85},
                headers=_auth_headers("admin"),
            )
        assert response.status_code == 201
        mock_pub.assert_called_once()


@pytest.mark.asyncio
async def test_purge_publishes_faiss_remove() -> None:
    with patch("vms.api.routes.persons.faiss_dirty.publish_remove", new_callable=AsyncMock) as mock_pub:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_resp = await client.post(
                "/api/persons",
                json={"name": "PurgeMe", "employee_id": "FT_PURGE1"},
                headers=_auth_headers("admin"),
            )
            assert create_resp.status_code == 201
            person_id = create_resp.json()["person_id"]
            emb_resp = await client.post(
                f"/api/persons/{person_id}/embeddings",
                json={"embedding": [0.0] * 512, "quality_score": 0.9},
                headers=_auth_headers("admin"),
            )
            assert emb_resp.status_code == 201
            response = await client.request(
                "DELETE",
                f"/api/persons/{person_id}",
                json={"confirmation_name": "PurgeMe", "reason": "GDPR erasure request"},
                headers=_auth_headers("admin"),
            )
        assert response.status_code == 204
        mock_pub.assert_called_once()
