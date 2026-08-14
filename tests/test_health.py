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


def test_dual_fault_module_health_status_undercounts_severity():
    """Genuine, measured limitation, not a design goal: mod-E5 has two real,
    independently-injected faults (see test_correlation.py's
    test_dual_fault_module_produces_two_genuinely_high_scoring_hypotheses, which confirms
    the correlation layer correctly scores both at >0.5 confidence). But
    summarize_module_health only counts a metric as "flagged" once >=2 of its own points
    cross z_thresh -- splitting the same total anomaly budget across three metrics
    (temperature_c, bias_current_ma, optical_power_dbm) instead of concentrating it in one
    or two makes each individual metric less likely to clear that persistence bar. Measured
    result: mod-E5 lands on "degraded" with only 1 flagged metric, the same status as the
    two fault-free modules -- point-anomaly-based severity scoring doesn't yet account for
    "several distinct metrics show real correlated drift", the way rank_fault_hypotheses
    does. This test pins the current (surprising) behavior so a future fix is a deliberate
    change, not a silent regression."""
    summary = summarize_module_health("mod-E5")
    assert summary["status"] == "degraded"
    flagged = [metric for metric, m in summary["metrics"].items() if m["flagged"]]
    assert len(flagged) == 1
