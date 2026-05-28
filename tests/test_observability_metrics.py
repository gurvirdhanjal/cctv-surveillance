"""Smoke-test that metrics objects exist and are incrementable."""

from __future__ import annotations


def test_alerts_fired_counter_exists_and_increments() -> None:
    from vms.observability.metrics import alerts_fired_total

    before = alerts_fired_total.labels(alert_type="INTRUSION", camera_id="1")._value.get()
    alerts_fired_total.labels(alert_type="INTRUSION", camera_id="1").inc()
    after = alerts_fired_total.labels(alert_type="INTRUSION", camera_id="1")._value.get()
    assert after == before + 1.0


def test_zone_head_count_gauge_exists() -> None:
    from vms.observability.metrics import zone_head_count

    zone_head_count.labels(zone_id="42").set(7)
    assert zone_head_count.labels(zone_id="42")._value.get() == 7.0
