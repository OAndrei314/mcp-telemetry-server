"""Verifies the MCP server wiring itself -- that all tools are registered under the
expected names and are actually callable through the MCP tool-call path, not just as
plain Python functions.

Note: `result.structured_content["result"]` (not `result.content[0].text`) is the right
way to read a tool's return value -- `content` is a human-readable rendering that, for
list-typed returns, the SDK splits into one TextContent block per element rather than
one JSON blob. Found by actually running this, not by guessing at the API."""
import asyncio
import json

from telemetry_server.server import app


def _tool_result_payload(result):
    if result.structured_content is not None:
        return result.structured_content["result"]
    return json.loads(result.content[0].text)


def test_all_tools_are_registered():
    tools = asyncio.run(app.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "list_modules",
        "get_telemetry",
        "detect_anomalies",
        "get_module_health_summary",
        "explain_module_health",
        "list_metrics",
    }


def test_list_modules_tool_call_round_trip():
    result = asyncio.run(app.call_tool("list_modules", {}))
    modules = result.structured_content["result"]
    assert "mod-A1" in modules


def test_get_telemetry_tool_call_round_trip():
    result = asyncio.run(
        app.call_tool("get_telemetry", {"module_id": "mod-A1", "metric": "temperature_c", "hours": 6})
    )
    series = result.structured_content["result"]
    assert isinstance(series, list)
    assert len(series) > 0
    assert "value" in series[0]


def test_explain_module_health_tool_call_round_trip():
    result = asyncio.run(app.call_tool("explain_module_health", {"module_id": "mod-D4"}))
    explanation = _tool_result_payload(result)

    assert explanation["fault_hypotheses"][0]["label"] == "optical_power_degradation"
    assert explanation["recommended_next_check"]


def test_explain_module_health_tool_call_surfaces_both_dual_fault_hypotheses():
    """mod-E5 has two independently-injected faults (see test_health.py and
    test_correlation.py for the underlying measurements) -- confirm both survive the full
    MCP tool-call path, not just the plain-Python correlation.rank_fault_hypotheses call."""
    result = asyncio.run(app.call_tool("explain_module_health", {"module_id": "mod-E5"}))
    explanation = _tool_result_payload(result)
    top_two = {h["label"] for h in explanation["fault_hypotheses"][:2]}

    assert top_two == {"thermal_bias_coupling", "optical_power_degradation"}
    assert explanation["summary"]["status"] == "critical"
    assert set(explanation["summary"]["correlated_faults"]) == {
        "thermal_bias_coupling",
        "optical_power_degradation",
    }


def test_detect_anomalies_tool_call_accepts_window_and_z_thresh_overrides():
    """These were previously fixed inside the tool wrapper -- confirm they're now real,
    caller-facing MCP tool parameters that actually change the result, through the
    call_tool path an MCP client actually uses (not just the plain Python function)."""
    strict = asyncio.run(
        app.call_tool(
            "detect_anomalies",
            {"module_id": "mod-A1", "metric": "temperature_c", "hours": 24, "z_thresh": 10.0},
        )
    )
    lenient = asyncio.run(
        app.call_tool(
            "detect_anomalies",
            {"module_id": "mod-A1", "metric": "temperature_c", "hours": 24, "z_thresh": 0.1},
        )
    )
    assert len(_tool_result_payload(strict)) == 0
    assert len(_tool_result_payload(lenient)) > 0


def test_get_module_health_summary_tool_call_accepts_min_persistent_points_override():
    default = _tool_result_payload(
        asyncio.run(app.call_tool("get_module_health_summary", {"module_id": "mod-C3"}))
    )
    assert default["status"] == "critical"

    # Loosening min_persistent_points alone can't fully silence mod-C3: the correlation
    # layer is a genuinely independent signal and still sees the real thermal/bias co-drift
    # (see test_health.py's test_min_persistent_points_override_actually_changes_the_verdict
    # for the full two-signal breakdown).
    loosened = _tool_result_payload(
        asyncio.run(
            app.call_tool(
                "get_module_health_summary",
                {"module_id": "mod-C3", "min_persistent_points": 100},
            )
        )
    )
    assert loosened["status"] == "degraded"
    assert all(not m["flagged"] for m in loosened["metrics"].values())


def test_get_module_health_summary_tool_call_accepts_correlated_fault_threshold_override():
    """correlated_fault_threshold is the new correlation-aware severity knob (see
    test_health.py) -- confirm it's wired through the actual MCP call_tool path, not just
    the plain Python function."""
    default = _tool_result_payload(
        asyncio.run(app.call_tool("get_module_health_summary", {"module_id": "mod-E5"}))
    )
    assert default["status"] == "critical"

    desensitized = _tool_result_payload(
        asyncio.run(
            app.call_tool(
                "get_module_health_summary",
                {"module_id": "mod-E5", "correlated_fault_threshold": 2.0},
            )
        )
    )
    assert desensitized["status"] == "degraded"
    assert desensitized["correlated_faults"] == []


def test_explain_module_health_tool_call_accepts_slope_thresholds_override():
    default = _tool_result_payload(
        asyncio.run(app.call_tool("explain_module_health", {"module_id": "mod-C3"}))
    )
    assert default["fault_hypotheses"][0]["label"] == "thermal_bias_coupling"

    desensitized = _tool_result_payload(
        asyncio.run(
            app.call_tool(
                "explain_module_health",
                {
                    "module_id": "mod-C3",
                    "slope_thresholds": {"temperature_c": 100.0, "bias_current_ma": 100.0},
                },
            )
        )
    )
    assert desensitized["fault_hypotheses"][0]["label"] != "thermal_bias_coupling"
