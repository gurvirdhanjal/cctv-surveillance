"""Tests for person enrollment and search endpoints."""

from __future__ import annotations

import json
import pathlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token
from vms.api.main import app
from vms.db.models import (
    AuditLog,
    Camera,
    Person,
    PersonClipEmbedding,
    TrackingEvent,
)


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
    with patch(
        "vms.api.routes.persons.faiss_dirty.publish_add", new_callable=AsyncMock
    ) as mock_pub:
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
async def test_purge_audit_payload_is_json_with_required_keys() -> None:
    from vms.db.session import SessionLocal

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/persons",
            json={"name": "AuditPayloadTest", "employee_id": "E_APT_99"},
            headers=_auth_headers(role="admin"),
        )
        assert create_resp.status_code == 201
        person_id = create_resp.json()["person_id"]
        resp = await client.request(
            "DELETE",
            f"/api/persons/{person_id}",
            json={"confirmation_name": "AuditPayloadTest", "reason": "GDPR audit payload test"},
            headers=_auth_headers(role="admin"),
        )
    assert resp.status_code == 204

    with SessionLocal() as sess:
        audit = sess.execute(
            select(AuditLog)
            .where(AuditLog.event_type == "PERSON_PURGED")
            .where(AuditLog.target_id == str(person_id))
            .order_by(AuditLog.audit_id.desc())
            .limit(1)
        ).scalar_one_or_none()

    assert audit is not None
    assert audit.payload is not None
    payload = json.loads(audit.payload)
    assert payload["reason"] == "GDPR audit payload test"
    assert isinstance(payload["embeddings_blanked"], int)


@pytest.mark.asyncio
async def test_purge_person_deletes_thumbnail_file(tmp_path: pathlib.Path) -> None:
    from unittest.mock import patch

    from vms.db.session import SessionLocal
    from vms.storage.backends import LocalStorageBackend

    key = "thumbnails/2026/05/28/person_thumb.jpg"
    local = LocalStorageBackend(str(tmp_path))
    local.write(key, b"fake-jpeg-data")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/persons",
            json={"name": "ThumbDeleteTest", "employee_id": "E_THUMB_99"},
            headers=_auth_headers(role="admin"),
        )
        assert create_resp.status_code == 201
        person_id = create_resp.json()["person_id"]

    with SessionLocal() as sess:
        p = sess.get(Person, person_id)
        assert p is not None
        p.thumbnail_path = key
        sess.commit()

    with patch("vms.api.routes.persons.get_storage", return_value=local):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.request(
                "DELETE",
                f"/api/persons/{person_id}",
                json={
                    "confirmation_name": "ThumbDeleteTest",
                    "reason": "Testing thumbnail deletion",
                },
                headers=_auth_headers(role="admin"),
            )
    assert resp.status_code == 204
    assert not local.exists(key)


@pytest.mark.asyncio
async def test_purge_person_deletes_clip_embeddings(tmp_path: pathlib.Path) -> None:
    from unittest.mock import patch

    from vms.db.session import SessionLocal
    from vms.storage.backends import LocalStorageBackend

    snap_key = "snapshots/2026/05/28/clip_snapshot.jpg"
    local = LocalStorageBackend(str(tmp_path))
    local.write(snap_key, b"fake-clip-snapshot")

    gid = uuid.uuid4()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/persons",
            json={"name": "ClipDeleteTest", "employee_id": "E_CLIP_99"},
            headers=_auth_headers(role="admin"),
        )
        assert create_resp.status_code == 201
        person_id = create_resp.json()["person_id"]

    with SessionLocal() as sess:
        cam = Camera(name="test-cam-clip", rtsp_url="rtsp://localhost/clip", capability_tier="FULL")
        sess.add(cam)
        sess.flush()
        te = TrackingEvent(
            camera_id=cam.camera_id,
            local_track_id="lt-clip-99",
            global_track_id=gid,
            person_id=person_id,
            event_ts=now,
            ingest_ts=now,
            bbox_x1=0,
            bbox_y1=0,
            bbox_x2=10,
            bbox_y2=10,
            seq_id=1,
        )
        sess.add(te)
        clip = PersonClipEmbedding(
            global_track_id=gid,
            camera_id=cam.camera_id,
            event_ts=now,
            embedding=[0.0] * 512,
            snapshot_path=snap_key,
        )
        sess.add(clip)
        sess.commit()
        clip_id = clip.clip_emb_id

    with patch("vms.api.routes.persons.get_storage", return_value=local):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.request(
                "DELETE",
                f"/api/persons/{person_id}",
                json={
                    "confirmation_name": "ClipDeleteTest",
                    "reason": "Testing CLIP embedding deletion",
                },
                headers=_auth_headers(role="admin"),
            )
    assert resp.status_code == 204
    assert not local.exists(snap_key)

    with SessionLocal() as sess:
        deleted = sess.get(PersonClipEmbedding, clip_id)
    assert deleted is None


@pytest.mark.asyncio
async def test_purge_calls_storage_delete_for_thumbnail(db_session: Session) -> None:
    from unittest.mock import MagicMock, patch

    mock_storage = MagicMock()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/persons",
            json={"name": "StorageThumbTest", "employee_id": "E_ST_01"},
            headers=_auth_headers(role="admin"),
        )
        assert create_resp.status_code == 201
        person_id = create_resp.json()["person_id"]

    from vms.db.session import SessionLocal

    with SessionLocal() as sess:
        p = sess.get(Person, person_id)
        assert p is not None
        p.thumbnail_path = "thumbnails/2026/05/28/face.jpg"
        sess.commit()

    with patch("vms.api.routes.persons.get_storage", return_value=mock_storage):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.request(
                "DELETE",
                f"/api/persons/{person_id}",
                json={"confirmation_name": "StorageThumbTest", "reason": "storage test"},
                headers=_auth_headers(role="admin"),
            )
    assert resp.status_code == 204
    mock_storage.delete.assert_called_with("thumbnails/2026/05/28/face.jpg")


# ---------------------------------------------------------------------------
# P0 — GET /api/persons list
# ---------------------------------------------------------------------------


async def test_list_persons_requires_auth() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/persons")
    assert response.status_code == 401


async def test_list_persons_rejects_guard() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/persons", headers=_auth_headers_role("guard"))
    assert response.status_code == 403


async def test_list_persons_returns_paginated(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/persons",
            json={"name": "Zara Patel", "employee_id": "E_LP_01"},
            headers=_auth_headers(),
        )
        await client.post(
            "/api/persons",
            json={"name": "Aaron Khan", "employee_id": "E_LP_02"},
            headers=_auth_headers(),
        )
        response = await client.get(
            "/api/persons?limit=50&offset=0", headers=_auth_headers_role("manager")
        )
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert body["total"] >= 2
    names = [p["name"] for p in body["items"]]
    assert names == sorted(names)


async def test_list_persons_respects_limit(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for i in range(3):
            await client.post(
                "/api/persons",
                json={"name": f"LimitTest {i:02d}", "employee_id": f"E_LT_{i:02d}"},
                headers=_auth_headers(),
            )
        response = await client.get("/api/persons?limit=1&offset=0", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["total"] >= 3


@pytest.mark.asyncio
async def test_purge_calls_storage_delete_for_clip_snapshots(db_session: Session) -> None:
    from unittest.mock import MagicMock, patch

    mock_storage = MagicMock()
    gid = uuid.uuid4()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    snap_key = "snapshots/2026/05/28/clip.jpg"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/persons",
            json={"name": "StorageClipTest", "employee_id": "E_SC_01"},
            headers=_auth_headers(role="admin"),
        )
        assert create_resp.status_code == 201
        person_id = create_resp.json()["person_id"]

    from vms.db.session import SessionLocal

    with SessionLocal() as sess:
        cam = Camera(name="sc-cam", rtsp_url="rtsp://localhost/sc", capability_tier="FULL")
        sess.add(cam)
        sess.flush()
        te = TrackingEvent(
            camera_id=cam.camera_id,
            local_track_id="lt-sc-01",
            global_track_id=gid,
            person_id=person_id,
            event_ts=now,
            ingest_ts=now,
            bbox_x1=0,
            bbox_y1=0,
            bbox_x2=10,
            bbox_y2=10,
            seq_id=1,
        )
        sess.add(te)
        clip = PersonClipEmbedding(
            global_track_id=gid,
            camera_id=cam.camera_id,
            event_ts=now,
            embedding=[0.0] * 512,
            snapshot_path=snap_key,
        )
        sess.add(clip)
        sess.commit()

    with patch("vms.api.routes.persons.get_storage", return_value=mock_storage):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.request(
                "DELETE",
                f"/api/persons/{person_id}",
                json={"confirmation_name": "StorageClipTest", "reason": "storage test"},
                headers=_auth_headers(role="admin"),
            )
    assert resp.status_code == 204
    mock_storage.delete.assert_called_with(snap_key)


@pytest.mark.asyncio
async def test_purge_with_no_thumbnail_does_not_call_storage_delete(
    db_session: Session,
) -> None:
    from unittest.mock import MagicMock, patch

    mock_storage = MagicMock()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/persons",
            json={"name": "NoThumbTest", "employee_id": "E_NT_01"},
            headers=_auth_headers(role="admin"),
        )
        assert create_resp.status_code == 201
        person_id = create_resp.json()["person_id"]

    with patch("vms.api.routes.persons.get_storage", return_value=mock_storage):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.request(
                "DELETE",
                f"/api/persons/{person_id}",
                json={"confirmation_name": "NoThumbTest", "reason": "no thumbnail test"},
                headers=_auth_headers(role="admin"),
            )
    assert resp.status_code == 204
    mock_storage.delete.assert_not_called()


@pytest.mark.asyncio
async def test_purge_publishes_faiss_remove() -> None:
    with patch(
        "vms.api.routes.persons.faiss_dirty.publish_remove", new_callable=AsyncMock
    ) as mock_pub:
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
