"""Synthetic optical-module telemetry generator.

No real hardware or proprietary data involved -- this generates plausible-shaped time
series (temperature, bias current, optical power, wavelength) for a small fixed set of
fictional modules. Three of them have a deliberately injected drift/degradation in their
most recent readings so the anomaly detector in `anomaly.py` and the correlation layer in
`correlation.py` have something real to find:

- mod-C3: isolated thermal drift (temperature_c + bias_current_ma rising together).
- mod-D4: isolated optical power degradation (optical_power_dbm falling).
- mod-E5: both of the above *at once*, injected independently of each other (not one
  derived from the other) -- a genuinely ambiguous case where two distinct root-cause
  hypotheses should both score high, unlike mod-C3/mod-D4 where exactly one fault is
  ever active.
- mod-F6: bias_current_ma drift *alone*, with temperature_c held flat -- unlike mod-C3,
  only one of the two metrics `thermal_bias_coupling` scores together actually moves.
  Added to stress-test whether `CORRELATED_FAULT_THRESHOLD` (see health.py) can tell a
  real, isolated single-metric fault apart from an actual coupled thermal/bias fault.
- mod-G7: wavelength_nm drift *alone*, with temperature_c held flat -- the first module
  with a genuine injected wavelength fault (see README "Status / next steps"). Every other
  module leaves wavelength_nm as pure noise, so `wavelength_control_drift` (correlation.py)
  had only ever been checked against known-good data. This gives it a known-bad case too.
"""
from __future__ import annotations

import hashlib

from . import METRICS

# module_id -> (has_anomaly, anomalous_metrics)
MODULE_PROFILES = {
    "mod-A1": {"anomaly": None},
    "mod-B2": {"anomaly": None},
    "mod-C3": {"anomaly": "thermal_drift", "metrics": ["temperature_c", "bias_current_ma"]},
    "mod-D4": {"anomaly": "power_degradation", "metrics": ["optical_power_dbm"]},
    "mod-E5": {
        "anomaly": "dual_fault",
        "metrics": ["temperature_c", "bias_current_ma", "optical_power_dbm"],
    },
    "mod-F6": {"anomaly": "bias_only_drift", "metrics": ["bias_current_ma"]},
    "mod-G7": {"anomaly": "wavelength_only_drift", "metrics": ["wavelength_nm"]},
}

_BASELINE = {
    "temperature_c": (45.0, 1.5),
    "bias_current_ma": (60.0, 2.0),
    "optical_power_dbm": (0.0, 0.3),
    "wavelength_nm": (1550.12, 0.02),
}


def list_module_ids() -> list[str]:
    return sorted(MODULE_PROFILES.keys())


def _seed_for(module_id: str, metric: str) -> int:
    digest = hashlib.sha256(f"{module_id}:{metric}".encode()).hexdigest()
    return int(digest[:8], 16)


def generate_telemetry(
    module_id: str, metric: str, hours: int = 24, points_per_hour: int = 4
) -> list[dict]:
    if module_id not in MODULE_PROFILES:
        raise ValueError(f"unknown module_id {module_id!r}; known: {list_module_ids()}")
    if metric not in METRICS:
        raise ValueError(f"unknown metric {metric!r}; known: {METRICS}")

    import numpy as np

    rng = np.random.default_rng(_seed_for(module_id, metric))
    mean, std = _BASELINE[metric]
    n = hours * points_per_hour
    hours_ago = np.linspace(hours, 0, n)
    values = rng.normal(mean, std, size=n)

    profile = MODULE_PROFILES[module_id]
    if profile["anomaly"] and metric in profile.get("metrics", []):
        anomaly_window_hours = min(4.0, hours)
        in_window = hours_ago <= anomaly_window_hours
        ramp_progress = (anomaly_window_hours - hours_ago[in_window]) / anomaly_window_hours
        # dual_fault applies both ramps below, each to its own metric family, independently
        # of each other -- two co-occurring faults, not one causing the other.
        if profile["anomaly"] in ("thermal_drift", "dual_fault") and metric in (
            "temperature_c",
            "bias_current_ma",
        ):
            values[in_window] += ramp_progress * (6.0 * std)  # drifting up
        elif profile["anomaly"] in ("power_degradation", "dual_fault") and metric == "optical_power_dbm":
            values[in_window] -= ramp_progress * (8.0 * std)
        elif profile["anomaly"] == "bias_only_drift" and metric == "bias_current_ma":
            values[in_window] += ramp_progress * (6.0 * std)  # dropping
        elif profile["anomaly"] == "wavelength_only_drift" and metric == "wavelength_nm":
            values[in_window] += ramp_progress * (6.0 * std)  # locker drifting off-channel

    return [
        {"hours_ago": round(float(h), 3), "value": round(float(v), 4)}
        for h, v in zip(hours_ago, values)
    ]
