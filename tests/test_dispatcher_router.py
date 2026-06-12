"""Tests for the alert routing matcher."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from vms.db.models import AlertRouting


def _rule(
    db: Session,
    *,
    channel: str,
    target: str,
    alert_type: str | None = None,
    severity: str | None = None,
    zone_id: int | None = None,
    is_active: bool = True,
) -> AlertRouting:
    r = AlertRouting(
        channel=channel,
        target=target,
        alert_type=alert_type,
        severity=severity,
        zone_id=zone_id,
        is_active=is_active,
    )
    db.add(r)
    db.flush()
    return r


@pytest.mark.integration
def test_match_routing_rules_returns_matching_rule(db_session: Session) -> None:
    """A rule with matching alert_type and no zone filter matches."""
    from vms.dispatcher.router import match_routing_rules

    _rule(db_session, channel="WEBHOOK", target="https://hook.example.com", alert_type="VIOLENCE")
    db_session.commit()

    results = match_routing_rules(
        db_session, alert_type="VIOLENCE", severity="CRITICAL", zone_id=None
    )
    assert len(results) == 1
    assert results[0].channel == "WEBHOOK"


@pytest.mark.integration
def test_match_routing_rules_null_type_matches_any_alert_type(db_session: Session) -> None:
    """A rule with alert_type=NULL matches any alert type."""
    from vms.dispatcher.router import match_routing_rules

    _rule(db_session, channel="EMAIL", target="guard@example.com", alert_type=None)
    db_session.commit()

    r1 = match_routing_rules(db_session, alert_type="INTRUSION", severity="HIGH", zone_id=None)
    r2 = match_routing_rules(db_session, alert_type="VIOLENCE", severity="CRITICAL", zone_id=None)
    assert len(r1) == 1
    assert len(r2) == 1


@pytest.mark.integration
def test_match_routing_rules_inactive_rules_excluded(db_session: Session) -> None:
    """is_active=False rules are never returned."""
    from vms.dispatcher.router import match_routing_rules

    _rule(db_session, channel="SLACK", target="#ch", is_active=False)
    db_session.commit()

    results = match_routing_rules(
        db_session, alert_type="VIOLENCE", severity="CRITICAL", zone_id=None
    )
    assert results == []


@pytest.mark.integration
def test_match_routing_rules_websocket_channel_excluded(db_session: Session) -> None:
    """WEBSOCKET rules are never returned (already handled by anomaly orchestrator)."""
    from vms.dispatcher.router import match_routing_rules

    _rule(db_session, channel="WEBSOCKET", target="frontend")
    db_session.commit()

    results = match_routing_rules(
        db_session, alert_type="VIOLENCE", severity="CRITICAL", zone_id=None
    )
    assert results == []


@pytest.mark.integration
def test_match_routing_rules_zone_filter_respected(db_session: Session) -> None:
    """A rule with zone_id only matches alerts from that zone."""
    from vms.dispatcher.router import match_routing_rules

    _rule(db_session, channel="WEBHOOK", target="https://h.io", zone_id=5)
    db_session.commit()

    matched = match_routing_rules(db_session, alert_type="INTRUSION", severity="HIGH", zone_id=5)
    missed = match_routing_rules(db_session, alert_type="INTRUSION", severity="HIGH", zone_id=6)
    assert len(matched) == 1
    assert missed == []
