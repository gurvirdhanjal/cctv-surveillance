"""Tests for vms-cli."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from vms.cli.main import cli


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "alerts" in result.output
    assert "detectors" in result.output
    assert "head-count" in result.output


def test_cli_alerts_list_invokes_api(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = [
        {
            "alert_id": 1,
            "alert_type": "VIOLENCE",
            "severity": "CRITICAL",
            "state": "active",
            "camera_id": 5,
            "zone_id": None,
            "triggered_at": "2026-05-15T10:00:00Z",
        },
    ]

    def fake_get(url: str, headers: dict[str, str], params: dict[str, object]) -> object:
        class R:
            status_code = 200

            def json(self) -> list[object]:
                return sample

        return R()

    import vms.cli.main as mod

    monkeypatch.setattr(mod.httpx, "get", fake_get, raising=True)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["alerts", "list", "--api", "http://x", "--token", "t"],
    )
    assert result.exit_code == 0
    assert "VIOLENCE" in result.output
