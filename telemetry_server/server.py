"""The MCP server itself -- a thin wrapper exposing the pure functions in
telemetry_sim.py / anomaly.py / health.py as MCP tools. Run with:

    python -m telemetry_server.server

and point an MCP client (Claude Desktop, Claude Code, etc) at it over stdio.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import METRICS
from .anomaly import detect_anomalies as _detect_anomalies
from .health import CORRELATED_FAULT_THRESHOLD, HEALTH_WINDOW, HEALTH_Z_THRESH, MIN_PERSISTENT_POINTS
from .health import explain_module_health as _explain_module_health
from .health import summarize_module_health
from .telemetry_sim import generate_telemetry, list_module_ids

app = MCPServer(
    name="optical-telemetry",
    title="Optical Module Telemetry",
    instructions=(
        "Tools for querying and analyzing synthetic optical-module telemetry "
        "(temperature, bias current, optical power, wavelength). All data is "
        "synthetically generated for demonstration -- no real hardware is connected."
    ),
)


@app.tool()
def list_modules() -> list[str]:
    """List available (synthetic) optical module IDs."""
    return list_module_ids()


@app.tool()
def get_telemetry(module_id: str, metric: str, hours: int = 24) -> list[dict]:
    """Get recent telemetry for one metric on one module.

    metric must be one of: temperature_c, bias_current_ma, optical_power_dbm, wavelength_nm.
    Returns a list of {"hours_ago": float, "value": float}, oldest first.
    """
    return generate_telemetry(module_id, metric, hours=hours)


@app.tool()
def detect_anomalies(
    module_id: str, metric: str, hours: int = 24, window: int = 8, z_thresh: float = 3.0
) -> list[dict]:
    """Run rolling z-score anomaly detection on one metric's recent telemetry.

    window: trailing-window size in points, must be >= 2 (default 8).
    z_thresh: flag threshold in standard deviations from the window mean, must be > 0
    (default 3.0). Lower it to catch subtler drift at the cost of more false positives.
    Returns flagged points with their z-score and the window stats they were compared to.
    """
    series = generate_telemetry(module_id, metric, hours=hours)
    values = [p["value"] for p in series]
    return _detect_anomalies(values, window=window, z_thresh=z_thresh)


@app.tool()
def get_module_health_summary(
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

    window/z_thresh/min_persistent_points default to the values validated in the README's
    "Honest results" section; override them to trade sensitivity for false-alarm rate
    without editing code. Status severity is the max of point-anomaly counting and a
    correlation-aware signal: any fault hypothesis (see `explain_module_health`) scoring at
    or above `correlated_fault_threshold` counts as one additional correlated fault, so a
    module whose real fault is split across several metrics at once isn't under-reported
    just because no single metric individually clears `min_persistent_points`.
    """
    return summarize_module_health(
        module_id,
        hours=hours,
        recent_hours=recent_hours,
        window=window,
        z_thresh=z_thresh,
        min_persistent_points=min_persistent_points,
        slope_thresholds=slope_thresholds,
        correlated_fault_threshold=correlated_fault_threshold,
    )


@app.tool()
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
    """Return health status, recent metric trends, ranked hypotheses, and next check.

    slope_thresholds optionally overrides per-metric rising/falling sensitivity used by the
    correlation layer, e.g. {"temperature_c": 0.5} to require a steeper rise before flagging
    thermal drift. Unlisted metrics keep their validated default. correlated_fault_threshold
    overrides the correlation-aware severity signal in the nested "summary" (see
    get_module_health_summary).
    """
    return _explain_module_health(
        module_id,
        hours=hours,
        recent_hours=recent_hours,
        window=window,
        z_thresh=z_thresh,
        min_persistent_points=min_persistent_points,
        slope_thresholds=slope_thresholds,
        correlated_fault_threshold=correlated_fault_threshold,
    )


@app.tool()
def list_metrics() -> list[str]:
    """List the telemetry metrics available for any module."""
    return METRICS


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
