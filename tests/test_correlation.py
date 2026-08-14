import pytest

from telemetry_server.correlation import metric_trends, rank_fault_hypotheses


def test_healthy_module_ranks_noise_above_fault_hypotheses():
    hypotheses = rank_fault_hypotheses("mod-A1")

    assert hypotheses[0]["label"] == "ordinary_measurement_noise"
    assert hypotheses[0]["confidence"] > hypotheses[1]["confidence"]


def test_thermal_drift_module_ranks_thermal_bias_coupling():
    trends = metric_trends("mod-C3")
    hypotheses = rank_fault_hypotheses("mod-C3")

    assert trends["temperature_c"]["direction"] == "rising"
    assert trends["bias_current_ma"]["direction"] == "rising"
    assert hypotheses[0]["label"] == "thermal_bias_coupling"
    assert "temperature and bias current drift together" in hypotheses[0]["evidence"]


def test_power_degradation_module_ranks_optical_power_drop():
    trends = metric_trends("mod-D4")
    hypotheses = rank_fault_hypotheses("mod-D4")

    assert trends["optical_power_dbm"]["direction"] == "falling"
    assert hypotheses[0]["label"] == "optical_power_degradation"


def test_slope_thresholds_override_actually_changes_the_verdict():
    """The formerly-hardcoded SLOPE_THRESHOLDS are now a real, overridable parameter --
    prove a high-enough override desensitizes thermal_bias_coupling on a module that
    otherwise clearly ranks it first."""
    default = rank_fault_hypotheses("mod-C3")
    assert default[0]["label"] == "thermal_bias_coupling"

    desensitized = rank_fault_hypotheses(
        "mod-C3", slope_thresholds={"temperature_c": 100.0, "bias_current_ma": 100.0}
    )
    assert desensitized[0]["label"] != "thermal_bias_coupling"


def test_slope_thresholds_override_is_partial_not_replace():
    """Overriding one metric's threshold must not silently reset the others to some
    implicit default -- unlisted metrics keep SLOPE_THRESHOLDS' own default."""
    baseline = metric_trends("mod-D4")
    overridden = metric_trends("mod-D4", slope_thresholds={"temperature_c": 100.0})

    assert overridden["optical_power_dbm"]["direction"] == baseline["optical_power_dbm"]["direction"]
    assert overridden["temperature_c"]["direction"] == "flat"


def test_unknown_metric_in_slope_thresholds_rejected():
    with pytest.raises(ValueError):
        rank_fault_hypotheses("mod-A1", slope_thresholds={"not_a_real_metric": 1.0})


def test_dual_fault_module_produces_two_genuinely_high_scoring_hypotheses():
    """mod-C3 and mod-D4 each have exactly one active fault, so the *other* hypothesis
    never rises much above its 0.1 baseline in the other tests above -- the ranking has
    never actually had to arbitrate between two real, simultaneously-elevated hypotheses.
    mod-E5 has both faults at once, independently injected. Measured (not assumed):
    thermal_bias_coupling lands at 0.95 and optical_power_degradation at 0.7 -- both well
    above the ~0.1 baseline a genuinely inactive hypothesis sits at elsewhere in this
    file, and correctly ordered by which fault's evidence is stronger."""
    hypotheses = rank_fault_hypotheses("mod-E5")
    by_label = {h["label"]: h["confidence"] for h in hypotheses}

    assert by_label["thermal_bias_coupling"] > 0.5
    assert by_label["optical_power_degradation"] > 0.5
    assert hypotheses[0]["label"] == "thermal_bias_coupling"
    assert hypotheses[1]["label"] == "optical_power_degradation"
