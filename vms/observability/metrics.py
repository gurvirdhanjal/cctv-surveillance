"""Prometheus metrics registry for VMS.

Counters and gauges are registered once at import time (process-singleton).
Import this module early (before workers start) so metrics are consistent.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Anomaly / alert metrics
# ---------------------------------------------------------------------------

alerts_fired_total = Counter(
    "vms_alerts_fired_total",
    "Total number of alert events that transitioned to FIRED state.",
    ["alert_type", "camera_id"],
)

alerts_suppressed_total = Counter(
    "vms_alerts_suppressed_total",
    "Alerts suppressed by maintenance windows.",
    ["alert_type"],
)

alerts_deduped_total = Counter(
    "vms_alerts_deduped_total",
    "Alerts skipped inside a dedup window.",
    ["alert_type"],
)

detector_errors_total = Counter(
    "vms_detector_errors_total",
    "Total detector exceptions (each increments the consecutive-error counter).",
    ["detector_name"],
)

detector_disabled_total = Counter(
    "vms_detector_disabled_total",
    "Number of times a detector was auto-disabled after consecutive errors.",
    ["detector_name"],
)

frames_processed_total = Counter(
    "vms_frames_processed_total",
    "Frames consumed by AnomalyOrchestrator.",
    ["camera_id"],
)

# ---------------------------------------------------------------------------
# Head count / zone metrics
# ---------------------------------------------------------------------------

zone_head_count = Gauge(
    "vms_zone_head_count",
    "Current number of unique tracked persons in a zone.",
    ["zone_id"],
)

# ---------------------------------------------------------------------------
# Inference metrics
# ---------------------------------------------------------------------------

inference_latency_seconds = Histogram(
    "vms_inference_latency_seconds",
    "Time from frame capture to DetectionFrame publish (seconds).",
    buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0),
)
