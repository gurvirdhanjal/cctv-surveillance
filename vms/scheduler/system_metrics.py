"""System metrics sampler (Phase 4P Task 5, spec §8.4).

Runs in the scheduler process (invariant: scheduler owns recurring work).
Each sample lands in two places: the METRICS_KEY Redis string consumed by
GET /api/system/metrics, and the METRICS_STREAM stream relayed to the
websocket as the `system_metrics` event by the realtime bridge.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

METRICS_KEY = "system:metrics"
METRICS_STREAM = "vms:system_metrics"


def _gpu_metrics() -> dict[str, float] | None:
    """NVML GPU stats, or None when no GPU/NVML — the UI hides the gauge, never fakes 0."""
    try:
        import pynvml  # type: ignore[import-untyped]

        pynvml.nvmlInit()
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return {
                "util_pct": float(util.gpu),
                "mem_used_mb": round(mem.used / 2**20, 1),
                "mem_total_mb": round(mem.total / 2**20, 1),
            }
        finally:
            pynvml.nvmlShutdown()
    except Exception:
        return None


def sample_system_metrics() -> dict[str, Any]:
    import psutil  # type: ignore[import-untyped]

    disk = psutil.disk_usage("/")
    return {
        "gpu": _gpu_metrics(),
        "cpu_pct": float(psutil.cpu_percent(interval=None)),
        "disk": {
            "used_gb": round(disk.used / 2**30, 1),
            "total_gb": round(disk.total / 2**30, 1),
        },
        # v1: inference/ingest counters are not exposed cross-process yet — honest nulls
        "inference_fps": None,
        "ingest_lag_ms": None,
        "ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }


def system_metrics_sample_job() -> None:
    import redis as sync_redis

    from vms.config import get_settings

    settings = get_settings()
    payload = json.dumps(sample_system_metrics())
    r = sync_redis.from_url(settings.redis_url)  # type: ignore[no-untyped-call]
    try:
        r.set(METRICS_KEY, payload, ex=settings.metrics_sample_interval_s * 6)
        r.xadd(METRICS_STREAM, {"payload": payload}, maxlen=100, approximate=True)
    finally:
        r.close()
