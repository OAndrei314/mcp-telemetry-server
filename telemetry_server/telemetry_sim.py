"""Synthetic optical-module telemetry generator.

No real hardware or proprietary data involved -- this generates plausible-shaped time
series (temperature, bias current, optical power, wavelength) for a small fixed set of
fictional modules, two of which have a deliberately injected drift/degradation in their
most recent readings so the anomaly detector in `anomaly.py` has something real to find.
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
        if profile["anomaly"] == "thermal_drift":
            values[in_window] += ramp_progress * (6.0 * std)  # drifting up
        elif profile["anomaly"] == "power_degradation":
            values[in_window] -= ramp_progress * (8.0 * std)  # dropping

    return [
        {"hours_ago": round(float(h), 3), "value": round(float(v), 4)}
        for h, v in zip(hours_ago, values)
    ]
