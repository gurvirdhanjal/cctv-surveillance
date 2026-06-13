"""Tests for GET /api/audit/verify and GET /api/audit/export."""

from __future__ import annotations

from datetime import datetime, timezone

from vms.api.schemas import AuditVerifyResponse, ForensicClipItem, ForensicClipsResponse


def test_schemas_importable() -> None:
    resp = AuditVerifyResponse(rows_checked=0, broken_chain_at=None)
    assert resp.rows_checked == 0
    assert resp.broken_chain_at is None

    clip = ForensicClipItem(
        clip_emb_id=1,
        global_track_id="track-123",
        camera_id=1,
        event_ts=datetime.utcnow(),
        snapshot_url="http://example.com/snap.jpg",
    )
    assert clip.clip_emb_id == 1

    clips_resp = ForensicClipsResponse(clips=[clip], total=1)
    assert clips_resp.total == 1
    assert len(clips_resp.clips) == 1
