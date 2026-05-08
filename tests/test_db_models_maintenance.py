"""Tests for MaintenanceWindow ORM model and its CHECK constraints."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vms.db.models import MaintenanceWindow, User

_T1 = datetime(2026, 5, 10, 2, 0, 0)
_T2 = datetime(2026, 5, 10, 4, 0, 0)


def _user(db_session: Session) -> User:
    user = User(username="maint_user", password_hash="h", role="admin")
    db_session.add(user)
    db_session.commit()
    return user


def test_one_time_window_insert(db_session: Session) -> None:
    user = _user(db_session)
    mw = MaintenanceWindow(
        name="Saturday Maintenance",
        scope_type="CAMERA",
        scope_id=1,
        schedule_type="ONE_TIME",
        starts_at=_T1,
        ends_at=_T2,
        created_by=user.user_id,
    )
    db_session.add(mw)
    db_session.commit()
    assert mw.window_id is not None


def test_recurring_window_insert(db_session: Session) -> None:
    user = _user(db_session)
    mw = MaintenanceWindow(
        name="Weekly Shift Handover",
        scope_type="ZONE",
        scope_id=2,
        schedule_type="RECURRING",
        cron_expr="0 6 * * 1",
        duration_minutes=30,
        created_by=user.user_id,
    )
    db_session.add(mw)
    db_session.commit()
    assert mw.window_id is not None


def test_invalid_scope_type_rejected(db_session: Session) -> None:
    user = _user(db_session)
    mw = MaintenanceWindow(
        name="Bad",
        scope_type="BUILDING",  # invalid
        scope_id=1,
        schedule_type="ONE_TIME",
        starts_at=_T1,
        ends_at=_T2,
        created_by=user.user_id,
    )
    db_session.add(mw)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_one_time_missing_ends_at_rejected(db_session: Session) -> None:
    user = _user(db_session)
    mw = MaintenanceWindow(
        name="Bad2",
        scope_type="CAMERA",
        scope_id=1,
        schedule_type="ONE_TIME",
        starts_at=_T1,
        ends_at=None,  # required for ONE_TIME
        created_by=user.user_id,
    )
    db_session.add(mw)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_recurring_missing_cron_rejected(db_session: Session) -> None:
    user = _user(db_session)
    mw = MaintenanceWindow(
        name="Bad3",
        scope_type="CAMERA",
        scope_id=1,
        schedule_type="RECURRING",
        cron_expr=None,  # required for RECURRING
        duration_minutes=30,
        created_by=user.user_id,
    )
    db_session.add(mw)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_one_time_inverted_window_rejected(db_session: Session) -> None:
    user = _user(db_session)
    mw = MaintenanceWindow(
        name="Bad4",
        scope_type="CAMERA",
        scope_id=1,
        schedule_type="ONE_TIME",
        starts_at=_T2,
        ends_at=_T1,  # ends before starts
        created_by=user.user_id,
    )
    db_session.add(mw)
    with pytest.raises(IntegrityError):
        db_session.commit()
