"""A simple, explainable rolling z-score anomaly detector -- deliberately not a black box:
every flagged point comes with the window mean/std it was compared against."""
from __future__ import annotations


def detect_anomalies(
    values: list[float], window: int = 8, z_thresh: float = 3.0
) -> list[dict]:
    """Flags points whose deviation from the trailing window mean exceeds z_thresh * std.

    Returns a list of {"index", "value", "z_score", "window_mean", "window_std"} for
    each flagged point. The first `window` points are never flagged (no history yet).
    """
    if window < 2:
        raise ValueError(f"window must be >= 2, got {window}")
    if z_thresh <= 0:
        raise ValueError(f"z_thresh must be > 0, got {z_thresh}")

    anomalies = []
    for i in range(window, len(values)):
        window_vals = values[i - window : i]
        mean = sum(window_vals) / window
        variance = sum((v - mean) ** 2 for v in window_vals) / window
        std = variance**0.5
        if std < 1e-9:
            continue  # flat window, nothing to compare against
        z = (values[i] - mean) / std
        if abs(z) >= z_thresh:
            anomalies.append(
                {
                    "index": i,
                    "value": values[i],
                    "z_score": round(z, 3),
                    "window_mean": round(mean, 4),
                    "window_std": round(std, 4),
                }
            )
    return anomalies
