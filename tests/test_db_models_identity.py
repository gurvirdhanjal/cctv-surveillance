"""Tests for identity ORM models: User, UserCameraPermission, Person, PersonEmbedding."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vms.db.models import Camera, Person, PersonEmbedding, User, UserCameraPermission

_DUMMY_EMBEDDING = [0.0] * 512


def test_user_insert_and_defaults(db_session: Session) -> None:
    user = User(username="guard1", password_hash="$2b$12$hash")
    db_session.add(user)
    db_session.commit()
    assert user.user_id is not None
    assert user.role == "guard"
    assert user.is_active is True


def test_user_role_check_constraint(db_session: Session) -> None:
    user = User(username="bad_role", password_hash="hash", role="superuser")
    db_session.add(user)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_user_username_unique(db_session: Session) -> None:
    db_session.add(User(username="alice", password_hash="h1"))
    db_session.commit()
    db_session.add(User(username="alice", password_hash="h2"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_user_camera_permission(db_session: Session) -> None:
    user = User(username="guard2", password_hash="h")
    cam = Camera(name="Cam-A", rtsp_url="rtsp://a/s")
    db_session.add_all([user, cam])
    db_session.commit()
    perm = UserCameraPermission(user_id=user.user_id, camera_id=cam.camera_id)
    db_session.add(perm)
    db_session.commit()
    assert perm.perm_id is not None


def test_user_camera_permission_unique(db_session: Session) -> None:
    user = User(username="guard3", password_hash="h")
    cam = Camera(name="Cam-B", rtsp_url="rtsp://b/s")
    db_session.add_all([user, cam])
    db_session.commit()
    db_session.add(UserCameraPermission(user_id=user.user_id, camera_id=cam.camera_id))
    db_session.commit()
    db_session.add(UserCameraPermission(user_id=user.user_id, camera_id=cam.camera_id))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_person_insert_and_defaults(db_session: Session) -> None:
    person = Person(employee_id="EMP001", name="Alice Singh")
    db_session.add(person)
    db_session.commit()
    assert person.person_id is not None
    assert person.is_active is True
    assert person.purged_at is None
    assert person.created_at is not None


def test_person_employee_id_unique(db_session: Session) -> None:
    db_session.add(Person(employee_id="EMP002", name="Bob"))
    db_session.commit()
    db_session.add(Person(employee_id="EMP002", name="Bob2"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_person_embedding_insert(db_session: Session) -> None:
    person = Person(employee_id="EMP003", name="Carol")
    db_session.add(person)
    db_session.commit()
    emb = PersonEmbedding(
        person_id=person.person_id,
        embedding=_DUMMY_EMBEDDING,
        quality_score=0.85,
    )
    db_session.add(emb)
    db_session.commit()
    assert emb.embedding_id is not None
    assert emb.quality_score == 0.85


def test_person_embedding_quality_bounds(db_session: Session) -> None:
    person = Person(employee_id="EMP004", name="Dave")
    db_session.add(person)
    db_session.commit()
    emb = PersonEmbedding(person_id=person.person_id, embedding=_DUMMY_EMBEDDING, quality_score=1.5)
    db_session.add(emb)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_person_cascade_delete_embeddings(db_session: Session) -> None:
    person = Person(employee_id="EMP005", name="Eve")
    db_session.add(person)
    db_session.commit()
    emb = PersonEmbedding(person_id=person.person_id, embedding=_DUMMY_EMBEDDING, quality_score=0.9)
    db_session.add(emb)
    db_session.commit()
    emb_id = emb.embedding_id
    db_session.delete(person)
    db_session.commit()
    assert db_session.get(PersonEmbedding, emb_id) is None
