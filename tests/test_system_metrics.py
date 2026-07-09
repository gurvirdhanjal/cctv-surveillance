"""Tests for the system-metrics sampler + GET /api/system/metrics (Phase 4P Task 5)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import redis as sync_redis
from httpx import ASGITransport, AsyncClient

from vms.api.deps import create_access_token
from vms.api.main import app
from vms.api.realtime.bridge import _emit_system_metrics
from vms.api.realtime.server import sio
from vms.scheduler.jobs import JOBS
from vms.scheduler.system_metrics import (
    METRICS_KEY,
    METRICS_STREAM,
    sample_system_metrics,
    system_metrics_sample_job,
)

_REDIS_URL = "redis://localhost:6379/0"


def _auth(role: str = "guard") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# -- sampler ------------------------------------------------------------------


def test_sample_returns_spec_schema() -> None:
    sample = sample_system_metrics()

    assert set(sample) == {"gpu", "cpu_pct", "disk", "inference_fps", "ingest_lag_ms", "ts"}
    assert sample["gpu"] is None or set(sample["gpu"]) == {
        "util_pct",
        "mem_used_mb",
        "mem_total_mb",
    }
    assert isinstance(sample["cpu_pct"], float)
    assert set(sample["disk"]) == {"used_gb", "total_gb"}
    assert sample["disk"]["total_gb"] > 0
    # v1: pipeline counters not exposed cross-process — honest nulls, never fake 0
    assert sample["inference_fps"] is None
    assert sample["ingest_lag_ms"] is None
    datetime.fromisoformat(sample["ts"])


def test_sample_gpu_none_when_nvml_unavailable(monkeypatch: Any) -> None:
    import pynvml

    def _boom() -> None:
        raise RuntimeError("no NVML on this host")

    monkeypatch.setattr(pynvml, "nvmlInit", _boom)

    sample = sample_system_metrics()

    assert sample["gpu"] is None


def test_sample_job_writes_redis_key_and_stream() -> None:
    r = sync_redis.from_url(_REDIS_URL)  # type: ignore[no-untyped-call]
    try:
        r.delete(METRICS_KEY)
        before = int(r.xlen(METRICS_STREAM))

        system_metrics_sample_job()

        raw = r.get(METRICS_KEY)
        assert raw is not None
        payload = json.loads(raw)
        assert "cpu_pct" in payload
        assert int(r.ttl(METRICS_KEY)) > 0
        assert int(r.xlen(METRICS_STREAM)) == before + 1
    finally:
        r.delete(METRICS_KEY)
        r.close()


def test_system_metrics_job_registered() -> None:
    assert any(j.name == "system_metrics_sample" for j in JOBS)


# -- endpoint -----------------------------------------------------------------


async def _get_metrics(headers: dict[str, str] | None = None) -> tuple[int, Any]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/system/metrics", headers=headers or {})
    return resp.status_code, (resp.json() if resp.content else {})


async def test_endpoint_returns_fresh_payload_for_any_role() -> None:
    r = sync_redis.from_url(_REDIS_URL)  # type: ignore[no-untyped-call]
    payload = {
        "gpu": None,
        "cpu_pct": 12.5,
        "disk": {"used_gb": 1.0, "total_gb": 2.0},
        "inference_fps": None,
        "ingest_lag_ms": None,
        "ts": _utcnow().isoformat(),
    }
    try:
        r.set(METRICS_KEY, json.dumps(payload))

        status, body = await _get_metrics(_auth(role="guard"))

        assert status == 200
        assert body["cpu_pct"] == 12.5
        assert body["gpu"] is None
    finally:
        r.delete(METRICS_KEY)
        r.close()


async def test_endpoint_503_when_key_absent() -> None:
    r = sync_redis.from_url(_REDIS_URL)  # type: ignore[no-untyped-call]
    try:
        r.delete(METRICS_KEY)
        status, body = await _get_metrics(_auth())
        assert status == 503
        assert body["detail"] == "metrics unavailable"
    finally:
        r.close()


async def test_endpoint_503_when_stale() -> None:
    r = sync_redis.from_url(_REDIS_URL)  # type: ignore[no-untyped-call]
    stale_ts = (_utcnow() - timedelta(minutes=5)).isoformat()
    payload = {
        "gpu": None,
        "cpu_pct": 1.0,
        "disk": {"used_gb": 1.0, "total_gb": 2.0},
        "inference_fps": None,
        "ingest_lag_ms": None,
        "ts": stale_ts,
    }
    try:
        r.set(METRICS_KEY, json.dumps(payload))
        status, _ = await _get_metrics(_auth())
        assert status == 503
    finally:
        r.delete(METRICS_KEY)
        r.close()


async def test_endpoint_unauthenticated_returns_401() -> None:
    status, _ = await _get_metrics(None)
    assert status == 401


# -- websocket relay ----------------------------------------------------------


async def test_bridge_emits_system_metrics_event() -> None:
    inner = {"cpu_pct": 3.0, "gpu": None, "ts": "2026-07-09T10:00:00"}
    entry = {"payload": json.dumps(inner)}

    with patch.object(sio, "emit", new_callable=AsyncMock) as mock_emit:
        await _emit_system_metrics(entry)

    event_name, payload = mock_emit.call_args[0]
    assert event_name == "system_metrics"
    assert payload == inner
