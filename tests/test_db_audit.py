"""Tests for vms.db.audit.write_audit_event — hash-chain integrity."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from vms.db.audit import compute_row_hash, write_audit_event
from vms.db.models import AuditLog

_ZERO_HASH = "0" * 64


def _last_hash(session: Session) -> str:
    last = session.execute(
        select(AuditLog).order_by(AuditLog.audit_id.desc()).limit(1)
    ).scalar_one_or_none()
    return last.row_hash if last is not None else _ZERO_HASH


def test_first_row_uses_zero_prev_hash(db_session: Session) -> None:
    expected_prev = _last_hash(db_session)
    row = write_audit_event(db_session, event_type="SCHEMA_MIGRATION")
    assert row.prev_hash == expected_prev
    assert len(row.row_hash) == 64


def test_second_row_chains_from_first(db_session: Session) -> None:
    row1 = write_audit_event(db_session, event_type="E1")
    row2 = write_audit_event(db_session, event_type="E2")
    assert row2.prev_hash == row1.row_hash


def test_row_hash_is_deterministic(db_session: Session) -> None:
    row = write_audit_event(
        db_session,
        event_type="ALERT_FIRED",
        target_type="Alert",
        target_id="7",
        payload='{"x": 1}',
    )
    recomputed = compute_row_hash(
        audit_id=row.audit_id,
        event_type=row.event_type,
        actor_user_id=row.actor_user_id,
        target_type=row.target_type,
        target_id=row.target_id,
        payload=row.payload,
        prev_hash=row.prev_hash,
        event_ts=row.event_ts,
    )
    assert recomputed == row.row_hash


def test_write_audit_event_persists(db_session: Session) -> None:
    row = write_audit_event(db_session, event_type="PERSON_ENROLLED", target_id="42")
    fetched = db_session.get(AuditLog, row.audit_id)
    assert fetched is not None
    assert fetched.event_type == "PERSON_ENROLLED"


def test_chain_integrity_across_three_rows(db_session: Session) -> None:
    expected_first_prev = _last_hash(db_session)
    rows = [write_audit_event(db_session, event_type=f"E{i}") for i in range(3)]
    assert rows[0].prev_hash == expected_first_prev
    assert rows[1].prev_hash == rows[0].row_hash
    assert rows[2].prev_hash == rows[1].row_hash
