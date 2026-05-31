from __future__ import annotations

import json
from unittest.mock import MagicMock

from vms.ble.messages import BleEvent
from vms.ble.resolver import ZoneResolver, lookup_person_by_badge


def test_zone_resolver_known_reader() -> None:
    r = ZoneResolver('{"AA:BB": 3, "CC:DD": 7}')
    assert r.zone_for_reader("AA:BB") == 3
    assert r.zone_for_reader("CC:DD") == 7


def test_zone_resolver_unknown_reader_returns_none() -> None:
    r = ZoneResolver('{"AA:BB": 3}')
    assert r.zone_for_reader("FF:FF") is None


def test_zone_resolver_invalid_json_returns_none() -> None:
    r = ZoneResolver("{bad")
    assert r.zone_for_reader("any") is None


def test_ble_event_mqtt_parse() -> None:
    payload = json.dumps({"badge_id": "AA:BB:CC:DD:EE:FF", "reader_id": "R1", "rssi": -65})
    event = BleEvent.from_mqtt_payload(payload, timestamp_ms=1000)
    assert event.badge_id == "AA:BB:CC:DD:EE:FF"
    assert event.rssi == -65
    assert event.timestamp_ms == 1000


def test_ble_event_redis_roundtrip() -> None:
    event = BleEvent(badge_id="AB:CD", reader_id="R2", rssi=-72, timestamp_ms=5000)
    restored = BleEvent.from_redis_fields(event.to_redis_fields())
    assert restored == event


def test_lookup_person_by_badge_found() -> None:
    db = MagicMock()
    mock_person = MagicMock()
    mock_person.person_id = 42
    db.query.return_value.filter.return_value.first.return_value = mock_person
    assert lookup_person_by_badge(db, "AA:BB") == 42


def test_lookup_person_by_badge_not_found() -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    assert lookup_person_by_badge(db, "XX:YY") is None


def test_anchor_person_by_badge_fills_unidentified_entries() -> None:
    from unittest.mock import MagicMock
    from vms.identity.engine import IdentityEngine
    from vms.identity.reid import ReIdService

    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = None
    engine = IdentityEngine(reid_service=reid)

    # Create a tracklet with no person_id
    engine.assign_global_track_id(camera_id=1, local_track_id=1, embedding=None)
    assert engine._registry[(1, 1)].person_id is None

    # BLE badge says it's person 99
    engine.anchor_person_by_badge(person_id=99, badge_id="AA:BB")
    assert engine._registry[(1, 1)].person_id == 99


def test_anchor_person_by_badge_does_not_overwrite_face_id() -> None:
    from unittest.mock import MagicMock
    from vms.identity.engine import IdentityEngine
    from vms.identity.reid import ReIdService
    import numpy as np

    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = 5  # face says person 5
    engine = IdentityEngine(reid_service=reid)

    emb = tuple(float(x) for x in np.random.default_rng(0).standard_normal(512))
    engine.assign_and_identify(camera_id=1, local_track_id=1, embedding=emb)
    assert engine._registry[(1, 1)].person_id == 5

    # BLE says person 99 — should NOT overwrite the face identification
    engine.anchor_person_by_badge(person_id=99, badge_id="AA:BB")
    assert engine._registry[(1, 1)].person_id == 5  # face wins
