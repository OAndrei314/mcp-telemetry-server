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
    assert all(not m["flagged"] for m in loose["metrics"].values())
    # Point-anomaly counting alone is silenced, but the correlation layer is a genuinely
    # independent signal and still sees the real thermal/bias co-drift -- loosening this one
    # knob correctly can't fully silence a fault the other signal still detects.
    assert loose["status"] == "degraded"
    assert loose["correlated_faults"] == ["thermal_bias_coupling"]

    # Silencing both independent signals together does reach "healthy", proving
    # min_persistent_points is still load-bearing rather than a no-op.
    both_loose = summarize_module_health(
        "mod-C3", min_persistent_points=100, correlated_fault_threshold=2.0
    )
    assert both_loose["status"] == "healthy"


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


def test_dual_fault_module_health_status_reflects_correlated_severity():
    """mod-E5 has two real, independently-injected faults (see test_correlation.py's
    test_dual_fault_module_produces_two_genuinely_high_scoring_hypotheses, which confirms
    the correlation layer correctly scores both at >0.5 confidence), but point-anomaly
    counting alone only flags 1 of its 3 affected metrics -- splitting the same total
    anomaly budget across temperature_c/bias_current_ma/optical_power_dbm instead of
    concentrating it in one or two makes each individual metric less likely to clear the
    persistence bar. `summarize_module_health` now also counts fault hypotheses (other than
    "ordinary_measurement_noise") scoring >= `correlated_fault_threshold` as a second,
    independent severity signal and takes the max of the two -- so this module is correctly
    reported as "critical", matching what a human reading both signals would conclude,
    instead of "degraded" (the same status as a fault-free module)."""
    summary = summarize_module_health("mod-E5")
    assert summary["status"] == "critical"
    flagged = [metric for metric, m in summary["metrics"].items() if m["flagged"]]
    assert len(flagged) == 1
    assert set(summary["correlated_faults"]) == {"thermal_bias_coupling", "optical_power_degradation"}


def test_correlated_fault_threshold_override_actually_changes_the_verdict():
    """Raising the threshold above every hypothesis's achievable confidence should disable
    the correlated-fault signal entirely, falling back to point-anomaly counting alone --
    proving this is a real, load-bearing parameter, not just accepted and ignored."""
    default = summarize_module_health("mod-E5")
    assert default["status"] == "critical"

    desensitized = summarize_module_health("mod-E5", correlated_fault_threshold=2.0)
    assert desensitized["status"] == "degraded"
    assert desensitized["correlated_faults"] == []


def test_correlated_fault_threshold_must_be_positive():
    with pytest.raises(ValueError):
        summarize_module_health("mod-A1", correlated_fault_threshold=0.0)


def test_fault_free_modules_have_no_correlated_faults():
    """The correlation-aware severity signal must not itself become a new source of false
    positives on modules with no injected fault."""
    for module_id in ("mod-A1", "mod-B2"):
        summary = summarize_module_health(module_id)
        assert summary["correlated_faults"] == []
