"""Tests for the detector registry."""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from vms.anomaly.base import AnomalyDetector, DetectorContext, FSMConfig, Severity
from vms.anomaly.registry import RegistryLoadResult, load_enabled_detectors


class _StubOK(AnomalyDetector):
    alert_type = "UNKNOWN_PERSON"
    severity = Severity.HIGH
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL",)

    def should_run(self, ctx: DetectorContext) -> bool:
        return True

    def evaluate(self, ctx: DetectorContext) -> None:
        return None

    def fsm_config(self) -> FSMConfig:
        return FSMConfig()


def test_load_skips_disabled_rows(db_session: Session) -> None:
    db_session.execute(
        text("UPDATE anomaly_detectors SET is_enabled = false WHERE alert_type = 'VIOLENCE'")
    )
    db_session.execute(
        text("UPDATE anomaly_detectors SET class_path = :cp WHERE alert_type = 'UNKNOWN_PERSON'"),
        {"cp": "tests.test_anomaly_registry._StubOK"},
    )
    db_session.flush()

    result = load_enabled_detectors(db_session)
    assert "VIOLENCE" not in result.detectors
    assert "UNKNOWN_PERSON" in result.detectors
    assert isinstance(result.detectors["UNKNOWN_PERSON"], _StubOK)


def test_load_records_errors_per_row(db_session: Session) -> None:
    db_session.execute(
        text(
            "UPDATE anomaly_detectors SET class_path = 'nonexistent.module.Bogus' "
            "WHERE alert_type = 'INTRUSION'"
        )
    )
    db_session.flush()
    result = load_enabled_detectors(db_session)
    assert "INTRUSION" not in result.detectors
    assert any(e.alert_type == "INTRUSION" for e in result.errors)


def test_load_parses_config_json(db_session: Session) -> None:
    db_session.execute(
        text(
            "UPDATE anomaly_detectors SET class_path = :cp, config_json = :cfg "
            "WHERE alert_type = 'UNKNOWN_PERSON'"
        ),
        {
            "cp": "tests.test_anomaly_registry._StubOK",
            "cfg": json.dumps({"foo": "bar"}),
        },
    )
    db_session.flush()
    result = load_enabled_detectors(db_session)
    assert result.detectors["UNKNOWN_PERSON"].config == {"foo": "bar"}


def test_load_malformed_config_json_records_error(db_session: Session) -> None:
    db_session.execute(
        text(
            "UPDATE anomaly_detectors SET class_path = :cp, config_json = '{ not json' "
            "WHERE alert_type = 'CROWD_DENSITY'"
        ),
        {"cp": "tests.test_anomaly_registry._StubOK"},
    )
    db_session.flush()
    result = load_enabled_detectors(db_session)
    assert "CROWD_DENSITY" not in result.detectors
    assert any("config_json" in e.reason for e in result.errors)


def test_load_returns_result_summary(db_session: Session) -> None:
    result = load_enabled_detectors(db_session)
    assert isinstance(result, RegistryLoadResult)
    assert isinstance(result.detectors, dict)
    assert isinstance(result.errors, list)
