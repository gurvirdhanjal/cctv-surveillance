"""Tests for AuditLog ORM model."""

from __future__ import annotations

from sqlalchemy.orm import Session

from vms.db.models import AuditLog

_ZERO_HASH = "0" * 64
_FAKE_HASH = "a" * 64


def test_audit_log_insert_system_event(db_session: Session) -> None:
    row = AuditLog(
        event_type="SCHEMA_MIGRATION",
        prev_hash=_ZERO_HASH,
        row_hash=_FAKE_HASH,
    )
    db_session.add(row)
    db_session.commit()
    assert row.audit_id is not None
    assert row.actor_user_id is None
    assert row.event_ts is not None


def test_audit_log_hash_fields_stored(db_session: Session) -> None:
    row = AuditLog(
        event_type="ALERT_FIRED",
        target_type="Alert",
        target_id="42",
        payload='{"alert_type": "INTRUSION"}',
        prev_hash=_FAKE_HASH,
        row_hash="b" * 64,
    )
    db_session.add(row)
    db_session.commit()
    fetched = db_session.get(AuditLog, row.audit_id)
    assert fetched is not None
    assert fetched.prev_hash == _FAKE_HASH
    assert fetched.row_hash == "b" * 64
    assert fetched.target_type == "Alert"


def test_audit_log_chain_sequence(db_session: Session) -> None:
    row1 = AuditLog(event_type="E1", prev_hash=_ZERO_HASH, row_hash="1" * 64)
    db_session.add(row1)
    db_session.commit()
    row2 = AuditLog(event_type="E2", prev_hash=row1.row_hash, row_hash="2" * 64)
    db_session.add(row2)
    db_session.commit()
    assert row2.prev_hash == row1.row_hash
    assert row1.audit_id < row2.audit_id
