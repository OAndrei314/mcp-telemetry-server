"""The MCP server itself -- a thin wrapper exposing the pure functions in
telemetry_sim.py / anomaly.py / health.py as MCP tools. Run with:

    python -m telemetry_server.server

and point an MCP client (Claude Desktop, Claude Code, etc) at it over stdio.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import METRICS
from .anomaly import detect_anomalies as _detect_anomalies
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
def detect_anomalies(module_id: str, metric: str, hours: int = 24) -> list[dict]:
    """Run rolling z-score anomaly detection on one metric's recent telemetry.

    Returns flagged points with their z-score and the window stats they were compared to.
    """
    series = generate_telemetry(module_id, metric, hours=hours)
    values = [p["value"] for p in series]
    return _detect_anomalies(values)


@app.tool()
def get_module_health_summary(module_id: str, hours: int = 24) -> dict:
    """Aggregate anomaly counts across all metrics into one health status + score."""
    return summarize_module_health(module_id, hours=hours)


@app.tool()
def explain_module_health(module_id: str, hours: int = 24, recent_hours: float = 6.0) -> dict:
    """Return health status, recent metric trends, ranked hypotheses, and next check."""
    return _explain_module_health(module_id, hours=hours, recent_hours=recent_hours)


@app.tool()
def list_metrics() -> list[str]:
    """List the telemetry metrics available for any module."""
    return METRICS


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
