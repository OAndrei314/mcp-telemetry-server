"""These assertions are pinned to the actual measured behavior at the module's default
seeded data (see README "Honest results" for the full false-positive/recall discussion) --
not to an idealized "healthy module always shows zero anomalies" assumption, which turned
out to be false: independent per-metric z-score flagging has a real false-alarm rate."""
import pytest

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


def test_min_persistent_points_override_actually_changes_the_verdict():
    """The formerly-hardcoded thresholds are now real parameters, not just accepted and
    ignored -- prove it by picking an override that flips the outcome versus the default."""
    default = summarize_module_health("mod-C3")
    assert default["status"] == "critical"

    loose = summarize_module_health("mod-C3", min_persistent_points=100)
    assert loose["status"] == "healthy"
    assert all(not m["flagged"] for m in loose["metrics"].values())


def test_z_thresh_override_actually_changes_the_verdict():
    default = summarize_module_health("mod-A1")

    sensitive = summarize_module_health("mod-A1", z_thresh=0.5)
    assert sensitive["status"] != default["status"] or sensitive["health_score"] < default["health_score"]


def test_min_persistent_points_below_one_rejected():
    with pytest.raises(ValueError):
        summarize_module_health("mod-A1", min_persistent_points=0)


def test_unknown_module_still_rejected_with_overrides_supplied():
    with pytest.raises(ValueError):
        summarize_module_health("not-a-real-module", window=5, z_thresh=2.0)
