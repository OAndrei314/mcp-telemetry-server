"""Multi-metric drift explanations for synthetic optical-module telemetry.

The z-score detector is intentionally local to one metric. This module adds a second,
still-transparent layer: recent trend direction across metrics. Correlated drift is a
stronger operational signal than one noisy point crossing a threshold.
"""
from __future__ import annotations

from . import METRICS
from .telemetry_sim import generate_telemetry

SLOPE_THRESHOLDS = {
    "temperature_c": 0.35,
    "bias_current_ma": 0.45,
    "optical_power_dbm": 0.04,
    # Recalibrated from 0.003 (see README "Honest results"): measured noise-only slope
    # across all 6 fault-free-for-this-metric modules tops out at 0.00587 (mod-F6) --
    # 0.003 was below that observed max and produced a real spurious
    # "wavelength_control_drift" hypothesis. 0.008 sits above the measured noise ceiling
    # with margin. No module currently injects a genuine wavelength_nm fault, so this is
    # validated against known-good (noise) data only, not a known-bad case -- see
    # "Status / next steps".
    "wavelength_nm": 0.008,
}


def _resolve_slope_thresholds(overrides: dict[str, float] | None) -> dict[str, float]:
    """Merge caller-supplied per-metric overrides onto the validated defaults.

    Partial overrides are allowed (e.g. only `{"temperature_c": 0.5}`) -- every metric
    not mentioned keeps its default threshold.
    """
    if not overrides:
        return SLOPE_THRESHOLDS
    unknown = set(overrides) - set(SLOPE_THRESHOLDS)
    if unknown:
        raise ValueError(f"unknown metric(s) in slope_thresholds: {sorted(unknown)}")
    return {**SLOPE_THRESHOLDS, **overrides}


def _linear_slope(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator = sum((x - mean_x) ** 2 for x in xs)
    return numerator / denominator if denominator else 0.0


def metric_trends(
    module_id: str,
    hours: int = 24,
    recent_hours: float = 6.0,
    slope_thresholds: dict[str, float] | None = None,
) -> dict[str, dict]:
    """Return recent per-metric slopes.

    `generate_telemetry` returns `hours_ago` from old to new. We convert that into an
    elapsed-time axis so positive slope always means "increasing toward now".

    `slope_thresholds` optionally overrides the rising/falling sensitivity for one or
    more metrics; unlisted metrics keep their validated default (see module docstring).
    """
    thresholds = _resolve_slope_thresholds(slope_thresholds)
    trends = {}
    for metric in METRICS:
        series = generate_telemetry(module_id, metric, hours=hours)
        recent = [point for point in series if point["hours_ago"] <= recent_hours]
        if len(recent) < 2:
            trends[metric] = {
                "slope_per_hour": 0.0,
                "recent_delta": 0.0,
                "direction": "flat",
            }
            continue

        xs = [recent_hours - point["hours_ago"] for point in recent]
        ys = [point["value"] for point in recent]
        slope = _linear_slope(xs, ys)
        threshold = thresholds[metric]
        if slope >= threshold:
            direction = "rising"
        elif slope <= -threshold:
            direction = "falling"
        else:
            direction = "flat"

        trends[metric] = {
            "slope_per_hour": round(slope, 5),
            "recent_delta": round(ys[-1] - ys[0], 5),
            "direction": direction,
        }
    return trends


def rank_fault_hypotheses(
    module_id: str,
    hours: int = 24,
    recent_hours: float = 6.0,
    slope_thresholds: dict[str, float] | None = None,
) -> list[dict]:
    """Rank transparent root-cause hypotheses from correlated trend directions."""
    trends = metric_trends(
        module_id, hours=hours, recent_hours=recent_hours, slope_thresholds=slope_thresholds
    )

    temp_rising = trends["temperature_c"]["direction"] == "rising"
    bias_rising = trends["bias_current_ma"]["direction"] == "rising"
    power_falling = trends["optical_power_dbm"]["direction"] == "falling"
    wavelength_moving = trends["wavelength_nm"]["direction"] != "flat"

    hypotheses = []

    thermal_score = 0.1
    thermal_reasons = []
    if temp_rising:
        thermal_score += 0.35
        thermal_reasons.append("temperature trend is rising")
    if bias_rising:
        thermal_score += 0.3
        thermal_reasons.append("bias-current trend is rising")
    if temp_rising and bias_rising:
        thermal_score += 0.2
        thermal_reasons.append("temperature and bias current drift together")
    hypotheses.append(
        {
            "label": "thermal_bias_coupling",
            "confidence": round(min(thermal_score, 0.95), 3),
            "evidence": thermal_reasons or ["no strong thermal/bias co-drift"],
            "next_check": "Run a controlled temperature sweep and inspect bias-compensation loop margins.",
        }
    )

    # Distinct from thermal_bias_coupling above: that hypothesis structurally caps at 0.4
    # when bias current rises without a temperature co-drift (see README "Status / next
    # steps" and mod-F6 in telemetry_sim.py), so an isolated bias-only fault was previously
    # invisible to correlated-fault scoring -- it could only reach "degraded" by chance, via
    # an unrelated metric's point-anomaly false alarm. This hypothesis fires only when bias
    # is rising *and* temperature is not, so it never competes with thermal_bias_coupling for
    # the same evidence -- a module can score high on at most one of the two.
    bias_isolated_score = 0.1
    bias_isolated_reasons = []
    if bias_rising and not temp_rising:
        bias_isolated_score += 0.55
        bias_isolated_reasons.append(
            "bias-current trend is rising without a temperature co-drift"
        )
    hypotheses.append(
        {
            "label": "bias_current_isolated_drift",
            "confidence": round(min(bias_isolated_score, 0.9), 3),
            "evidence": bias_isolated_reasons or ["no isolated bias-current drift"],
            "next_check": "Inspect the bias-compensation loop and laser driver for drift independent of thermal effects.",
        }
    )

    power_score = 0.1
    power_reasons = []
    if power_falling:
        power_score += 0.6
        power_reasons.append("optical power trend is falling")
    if not temp_rising:
        power_score += 0.1
        power_reasons.append("power loss is not primarily explained by module heating")
    hypotheses.append(
        {
            "label": "optical_power_degradation",
            "confidence": round(min(power_score, 0.9), 3),
            "evidence": power_reasons or ["no sustained optical-power drop"],
            "next_check": "Inspect connector cleanliness, receiver margin, and laser aging telemetry.",
        }
    )

    wavelength_score = 0.1
    wavelength_reasons = []
    if wavelength_moving:
        wavelength_score += 0.45
        wavelength_reasons.append("wavelength trend is moving over the recent window")
    if temp_rising and wavelength_moving:
        wavelength_score += 0.2
        wavelength_reasons.append("wavelength movement coincides with temperature rise")
    hypotheses.append(
        {
            "label": "wavelength_control_drift",
            "confidence": round(min(wavelength_score, 0.85), 3),
            "evidence": wavelength_reasons or ["wavelength trend is stable"],
            "next_check": "Check wavelength locker state and thermal-control loop stability.",
        }
    )

    quiet_score = 0.75 if not any((temp_rising, bias_rising, power_falling, wavelength_moving)) else 0.05
    hypotheses.append(
        {
            "label": "ordinary_measurement_noise",
            "confidence": round(quiet_score, 3),
            "evidence": ["no correlated sustained drift"] if quiet_score > 0.5 else ["correlated drift exists"],
            "next_check": "Keep monitoring or increase the persistence threshold before paging an operator.",
        }
    )

    return sorted(hypotheses, key=lambda item: item["confidence"], reverse=True)
