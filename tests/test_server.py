"""Verifies the MCP server wiring itself -- that all tools are registered under the
expected names and are actually callable through the MCP tool-call path, not just as
plain Python functions.

Note: `result.structured_content["result"]` (not `result.content[0].text`) is the right
way to read a tool's return value -- `content` is a human-readable rendering that, for
list-typed returns, the SDK splits into one TextContent block per element rather than
one JSON blob. Found by actually running this, not by guessing at the API."""
import asyncio

from telemetry_server.server import app


def test_all_tools_are_registered():
    tools = asyncio.run(app.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "list_modules",
        "get_telemetry",
        "detect_anomalies",
        "get_module_health_summary",
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
