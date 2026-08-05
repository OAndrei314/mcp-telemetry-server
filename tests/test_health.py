"""These assertions are pinned to the actual measured behavior at the module's default
seeded data (see README "Honest results" for the full false-positive/recall discussion) --
not to an idealized "healthy module always shows zero anomalies" assumption, which turned
out to be false: independent per-metric z-score flagging has a real false-alarm rate."""
from telemetry_server.health import summarize_module_health


def test_modules_without_injected_faults_never_reach_critical():
    for module_id in ("mod-A1", "mod-B2"):
        summary = summarize_module_health(module_id)
        assert summary["status"] in ("healthy", "degraded")


def test_modules_with_injected_faults_reach_critical():
    for module_id in ("mod-C3", "mod-D4"):
        summary = summarize_module_health(module_id)
        assert summary["status"] == "critical"
        assert summary["health_score"] < summarize_module_health("mod-A1")["health_score"]


def test_health_score_decreases_with_more_flagged_metrics():
    healthy = summarize_module_health("mod-A1")
    critical = summarize_module_health("mod-C3")
    assert critical["health_score"] < healthy["health_score"]
