"""Combines telemetry + anomaly detection across all metrics into one health summary.

Calibration note (measured, not assumed -- see README "Honest results"): a per-point
z-score flag is noisy enough, run independently across 4 simultaneous metric streams
over a 24h window, that raw point counts are a bad status signal -- a purely healthy
module regularly racks up several spurious single-point flags. Two adjustments, both
empirically checked against a known-good/known-bad set of synthetic modules:

1. Health scoring uses a more conservative (window, z_thresh) than `detect_anomalies`'s
   own defaults -- lower false-alarm rate at some cost to sensitivity.
2. A metric only counts as "flagged" if at least `MIN_PERSISTENT_POINTS` points in it
   were flagged, not just one -- filters out isolated noise blips while still catching
   sustained drift (which by construction produces several consecutive flagged points).
"""
from __future__ import annotations

from . import METRICS
from .anomaly import detect_anomalies
from .telemetry_sim import MODULE_PROFILES, generate_telemetry

HEALTH_WINDOW = 10
HEALTH_Z_THRESH = 3.5
MIN_PERSISTENT_POINTS = 2


def summarize_module_health(module_id: str, hours: int = 24) -> dict:
    if module_id not in MODULE_PROFILES:
        raise ValueError(f"unknown module_id {module_id!r}; known: {sorted(MODULE_PROFILES)}")

    per_metric = {}
    flagged_metric_count = 0
    for metric in METRICS:
        series = generate_telemetry(module_id, metric, hours=hours)
        values = [p["value"] for p in series]
        anomalies = detect_anomalies(values, window=HEALTH_WINDOW, z_thresh=HEALTH_Z_THRESH)
        is_flagged = len(anomalies) >= MIN_PERSISTENT_POINTS
        per_metric[metric] = {
            "latest_value": values[-1],
            "num_anomalies": len(anomalies),
            "flagged": is_flagged,
        }
        flagged_metric_count += is_flagged

    if flagged_metric_count == 0:
        status = "healthy"
    elif flagged_metric_count == 1:
        status = "degraded"
    else:
        status = "critical"
    health_score = max(0.0, 1.0 - 0.35 * flagged_metric_count)

    return {
        "module_id": module_id,
        "status": status,
        "health_score": round(health_score, 3),
        "metrics": per_metric,
    }
