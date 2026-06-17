"""Tests for temporal quality-windowed gallery sub-sampling."""

from __future__ import annotations

import uuid

import pytest


def _make_engine() -> object:
    """Return a minimal IdentityEngine with no FAISS/DB deps."""
    from vms.identity.engine import IdentityEngine

    engine = IdentityEngine.__new__(IdentityEngine)
    engine._registry = {}
    engine._topology = None
    engine._settings = None
    return engine


def _make_entry() -> object:
    from vms.identity.engine import _TrackletEntry

    return _TrackletEntry(
        global_track_id=uuid.uuid4(),
        camera_id=1,
        local_track_id=42,
        first_seen_ms=0,
        last_seen_ms=0,
    )


class _FakeSettings:
    reid_gallery_size = 8
    reid_confirm_after_sightings = 3
    reid_quality_window_s = 2.0
    reid_face_quality_floor = 0.0
    reid_body_quality_floor = 0.0


def test_within_window_lower_quality_rejected() -> None:
    """Second embedding in same window with lower quality must not replace first."""
    engine = _make_engine()
    entry = _make_entry()
    s = _FakeSettings()

    high_q = (0.5,) * 512
    low_q = (0.1,) * 512

    engine._update_galleries(
        entry, high_q, None, s, timestamp_ms=1000, face_quality=10.0, body_quality=0.0
    )
    engine._update_galleries(
        entry, low_q, None, s, timestamp_ms=1500, face_quality=5.0, body_quality=0.0
    )

    assert len(entry.gallery) == 1
    assert entry.gallery[0][0] == pytest.approx(0.5, abs=1e-4)


def test_within_window_higher_quality_replaces() -> None:
    """Second embedding in same window with higher quality replaces first."""
    engine = _make_engine()
    entry = _make_entry()
    s = _FakeSettings()

    low_q = (0.1,) * 512
    high_q = (0.5,) * 512

    engine._update_galleries(
        entry, low_q, None, s, timestamp_ms=1000, face_quality=3.0, body_quality=0.0
    )
    engine._update_galleries(
        entry, high_q, None, s, timestamp_ms=1500, face_quality=9.0, body_quality=0.0
    )

    assert len(entry.gallery) == 1
    assert entry.gallery[0][0] == pytest.approx(0.5, abs=1e-4)


def test_new_window_always_appends() -> None:
    """Embedding in a new window always appends regardless of quality."""
    engine = _make_engine()
    entry = _make_entry()
    s = _FakeSettings()

    emb1 = (0.5,) * 512
    emb2 = (0.2,) * 512

    engine._update_galleries(
        entry, emb1, None, s, timestamp_ms=0, face_quality=9.0, body_quality=0.0
    )
    engine._update_galleries(
        entry, emb2, None, s, timestamp_ms=3000, face_quality=1.0, body_quality=0.0
    )

    assert len(entry.gallery) == 2


def test_gallery_respects_max_size() -> None:
    """Gallery never exceeds reid_gallery_size slots."""
    engine = _make_engine()
    entry = _make_entry()
    s = _FakeSettings()

    for i in range(20):
        emb = (float(i),) + (0.0,) * 511
        engine._update_galleries(
            entry,
            emb,
            None,
            s,
            timestamp_ms=i * 3000,
            face_quality=float(i),
            body_quality=0.0,
        )

    assert len(entry.gallery) <= s.reid_gallery_size


def test_face_quality_floor_rejects_low_norm() -> None:
    """Face embeddings with quality below reid_face_quality_floor are discarded."""
    engine = _make_engine()
    entry = _make_entry()

    class _StrictFaceSettings(_FakeSettings):
        reid_face_quality_floor = 5.0

    emb = (0.3,) * 512
    engine._update_galleries(
        entry, emb, None, _StrictFaceSettings(), timestamp_ms=0, face_quality=2.0, body_quality=0.0
    )

    assert len(entry.gallery) == 0


def test_body_quality_floor_rejects_low_blur() -> None:
    """Body embeddings with Laplacian quality below reid_body_quality_floor are discarded."""
    engine = _make_engine()
    entry = _make_entry()

    class _StrictBodySettings(_FakeSettings):
        reid_body_quality_floor = 30.0

    body_emb = (0.3,) * 768
    engine._update_galleries(
        entry, None, body_emb, _StrictBodySettings(), timestamp_ms=0, face_quality=0.0, body_quality=10.0
    )

    assert len(entry.body_gallery) == 0


def test_body_quality_floor_accepts_sharp_crop() -> None:
    """Body embeddings with Laplacian quality above reid_body_quality_floor are accepted."""
    engine = _make_engine()
    entry = _make_entry()

    class _StrictBodySettings(_FakeSettings):
        reid_body_quality_floor = 30.0

    body_emb = (0.3,) * 768
    engine._update_galleries(
        entry, None, body_emb, _StrictBodySettings(), timestamp_ms=0, face_quality=0.0, body_quality=100.0
    )

    assert len(entry.body_gallery) == 1
