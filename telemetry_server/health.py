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
from .correlation import metric_trends, rank_fault_hypotheses
from .telemetry_sim import MODULE_PROFILES, generate_telemetry

HEALTH_WINDOW = 10
HEALTH_Z_THRESH = 3.5
MIN_PERSISTENT_POINTS = 2

# See README "Status / next steps": a module whose real fault is split across several
# metrics at once (mod-E5) under-reports on point-anomaly counting alone, because splitting
# the same total anomaly magnitude across three metrics makes each one individually less
# likely to clear MIN_PERSISTENT_POINTS. Measured (see tests/test_health.py): for the
# fault-free modules, every hypothesis other than "ordinary_measurement_noise" tops out at
# 0.2 (no real correlated evidence, just a passive scoring bonus); for modules with a real,
# engaged fault, the same hypotheses land at 0.7+. 0.5 sits cleanly between those two
# measured clusters.
CORRELATED_FAULT_THRESHOLD = 0.5


def summarize_module_health(
    module_id: str,
    hours: int = 24,
    recent_hours: float = 6.0,
    window: int = HEALTH_WINDOW,
    z_thresh: float = HEALTH_Z_THRESH,
    min_persistent_points: int = MIN_PERSISTENT_POINTS,
    slope_thresholds: dict[str, float] | None = None,
    correlated_fault_threshold: float = CORRELATED_FAULT_THRESHOLD,
) -> dict:
    """Aggregate anomaly counts across all metrics into one health status + score.

    `window`, `z_thresh`, and `min_persistent_points` default to the values validated in
    the README's "Honest results" section (empirically checked against known-good/known-bad
    synthetic data). Override them to trade sensitivity for fewer false alarms, or vice
    versa, without editing code -- e.g. a noisier module class might need a larger window.

    Severity is now the max of two independent signals, not point-anomaly counts alone:
    `flagged_metric_count` (metrics individually clearing the persistence bar) and
    `correlated_fault_count` (fault hypotheses from the correlation layer -- see
    `correlation.rank_fault_hypotheses` -- scoring at or above `correlated_fault_threshold`,
    excluding "ordinary_measurement_noise"). Taking the max means this can only raise
    severity relative to point-counting alone, never lower it: a module a human would call
    "two real, correlated faults" no longer gets scored the same as a fault-free module just
    because the anomaly magnitude was spread across more metrics. `recent_hours` and
    `slope_thresholds` are forwarded to the correlation layer unchanged (see
    `correlation.metric_trends`).
    """
    if module_id not in MODULE_PROFILES:
        raise ValueError(f"unknown module_id {module_id!r}; known: {sorted(MODULE_PROFILES)}")
    if min_persistent_points < 1:
        raise ValueError(f"min_persistent_points must be >= 1, got {min_persistent_points}")
    if correlated_fault_threshold <= 0:
        raise ValueError(
            f"correlated_fault_threshold must be > 0, got {correlated_fault_threshold}"
        )

    per_metric = {}
    flagged_metric_count = 0
    for metric in METRICS:
        series = generate_telemetry(module_id, metric, hours=hours)
        values = [p["value"] for p in series]
        anomalies = detect_anomalies(values, window=window, z_thresh=z_thresh)
        is_flagged = len(anomalies) >= min_persistent_points
        per_metric[metric] = {
            "latest_value": values[-1],
            "num_anomalies": len(anomalies),
            "flagged": is_flagged,
        }
        flagged_metric_count += is_flagged

    hypotheses = rank_fault_hypotheses(
        module_id, hours=hours, recent_hours=recent_hours, slope_thresholds=slope_thresholds
    )
    correlated_faults = [
        h["label"]
        for h in hypotheses
        if h["label"] != "ordinary_measurement_noise" and h["confidence"] >= correlated_fault_threshold
    ]
    severity_count = max(flagged_metric_count, len(correlated_faults))

    if severity_count == 0:
        status = "healthy"
    elif severity_count == 1:
        status = "degraded"
    else:
        status = "critical"
    health_score = max(0.0, 1.0 - 0.35 * severity_count)

    return {
        "module_id": module_id,
        "status": status,
        "health_score": round(health_score, 3),
        "metrics": per_metric,
        "correlated_faults": correlated_faults,
    }


def explain_module_health(
    module_id: str,
    hours: int = 24,
    recent_hours: float = 6.0,
    window: int = HEALTH_WINDOW,
    z_thresh: float = HEALTH_Z_THRESH,
    min_persistent_points: int = MIN_PERSISTENT_POINTS,
    slope_thresholds: dict[str, float] | None = None,
    correlated_fault_threshold: float = CORRELATED_FAULT_THRESHOLD,
) -> dict:
    """Return health status plus ranked, transparent next-check hypotheses.

    `slope_thresholds` optionally overrides per-metric rising/falling sensitivity in the
    correlation layer (see `correlation.SLOPE_THRESHOLDS` for defaults and valid keys).
    `correlated_fault_threshold` overrides the correlation-aware severity signal in
    `summarize_module_health` (see its docstring).
    """
    summary = summarize_module_health(
        module_id,
        hours=hours,
        recent_hours=recent_hours,
        window=window,
        z_thresh=z_thresh,
        min_persistent_points=min_persistent_points,
        slope_thresholds=slope_thresholds,
        correlated_fault_threshold=correlated_fault_threshold,
    )
    hypotheses = rank_fault_hypotheses(
        module_id, hours=hours, recent_hours=recent_hours, slope_thresholds=slope_thresholds
    )
    return {
        "summary": summary,
        "recent_trends": metric_trends(
            module_id, hours=hours, recent_hours=recent_hours, slope_thresholds=slope_thresholds
        ),
        "fault_hypotheses": hypotheses,
        "recommended_next_check": hypotheses[0]["next_check"] if hypotheses else None,
    }
