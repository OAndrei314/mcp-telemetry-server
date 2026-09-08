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


def test_isolated_bias_drift_scores_thermal_bias_coupling_below_half():
    """mod-F6 stress-tests the exact gap the README flagged as untested: a fault that
    engages only *one* of the two metrics thermal_bias_coupling scores together (bias
    current alone, no temperature rise). thermal_score's own formula (0.1 base + 0.3 for
    bias_rising, no +0.2 co-drift bonus since temp never rises) caps at exactly 0.4 for
    this case -- below CORRELATED_FAULT_THRESHOLD (0.5), so an isolated single-metric fault
    is correctly NOT misattributed to the coupled thermal/bias hypothesis."""
    trends = metric_trends("mod-F6")
    hypotheses = rank_fault_hypotheses("mod-F6")
    by_label = {h["label"]: h["confidence"] for h in hypotheses}

    assert trends["bias_current_ma"]["direction"] == "rising"
    assert trends["temperature_c"]["direction"] == "flat"
    assert by_label["thermal_bias_coupling"] == 0.4


def test_isolated_bias_drift_ranks_bias_current_isolated_drift_first():
    """The gap the previous test's docstring used to flag as unresolved: mod-F6's real
    fault now has a dedicated hypothesis that specifically requires bias rising *without*
    a temperature co-drift, so it outranks thermal_bias_coupling's structurally-capped 0.4
    instead of leaving the module's real fault with no hypothesis above the persistence/
    correlation bar at all."""
    hypotheses = rank_fault_hypotheses("mod-F6")
    by_label = {h["label"]: h["confidence"] for h in hypotheses}

    assert by_label["bias_current_isolated_drift"] == 0.65
    assert hypotheses[0]["label"] == "bias_current_isolated_drift"
    assert "without a temperature co-drift" in hypotheses[0]["evidence"][0]


def test_bias_current_isolated_drift_stays_at_baseline_when_temperature_also_rises():
    """mod-C3 has a genuine *coupled* thermal/bias fault (both metrics rising together) --
    bias_current_isolated_drift must not also fire here, or the two hypotheses would
    double-count the same evidence instead of cleanly partitioning coupled vs. isolated
    bias drift."""
    hypotheses = rank_fault_hypotheses("mod-C3")
    by_label = {h["label"]: h["confidence"] for h in hypotheses}

    assert by_label["bias_current_isolated_drift"] == 0.1
    assert by_label["bias_current_isolated_drift"] < by_label["thermal_bias_coupling"]


def test_bias_current_isolated_drift_stays_at_baseline_on_fault_free_modules():
    for module_id in ("mod-A1", "mod-B2"):
        by_label = {h["label"]: h["confidence"] for h in rank_fault_hypotheses(module_id)}
        assert by_label["bias_current_isolated_drift"] == 0.1


def test_isolated_wavelength_drift_ranks_wavelength_control_drift_first():
    """mod-G7 gives wavelength_control_drift its first known-bad case (see README
    "Status / next steps" -- it had only ever been checked against noise-only known-good
    data before). Measured, not assumed: wavelength_score's own formula (0.1 base + 0.45 for
    wavelength moving, no +0.2 co-drift bonus since temperature never rises) lands at exactly
    0.55 -- above CORRELATED_FAULT_THRESHOLD (0.5) with margin, and clearly ahead of every
    other hypothesis, which stay near their inactive baseline."""
    trends = metric_trends("mod-G7")
    hypotheses = rank_fault_hypotheses("mod-G7")
    by_label = {h["label"]: h["confidence"] for h in hypotheses}

    assert trends["wavelength_nm"]["direction"] == "rising"
    assert trends["temperature_c"]["direction"] == "flat"
    assert by_label["wavelength_control_drift"] == 0.55
    assert hypotheses[0]["label"] == "wavelength_control_drift"
    assert "wavelength trend is moving" in hypotheses[0]["evidence"][0]


def test_coupled_temperature_wavelength_drift_scores_above_the_isolated_case():
    """mod-H8 closes the last gap the README flagged: wavelength_score's "+0.2 if wavelength
    movement coincides with a temperature rise" bonus had never fired on real fault data
    before (mod-G7's isolated wavelength drift deliberately holds temperature flat). Measured,
    not assumed: with the bonus applied (0.1 base + 0.45 wavelength moving + 0.2 co-drift),
    wavelength_control_drift lands at exactly 0.75 -- clearly above mod-G7's isolated-case
    0.55, i.e. the bonus term is well-separated from the single-fault case, not a rounding
    artifact."""
    trends = metric_trends("mod-H8")
    hypotheses = rank_fault_hypotheses("mod-H8")
    by_label = {h["label"]: h["confidence"] for h in hypotheses}

    assert trends["temperature_c"]["direction"] == "rising"
    assert trends["wavelength_nm"]["direction"] == "rising"
    assert trends["bias_current_ma"]["direction"] == "flat"
    assert by_label["wavelength_control_drift"] == 0.75
    assert hypotheses[0]["label"] == "wavelength_control_drift"
    assert "coincides with temperature rise" in hypotheses[0]["evidence"][1]


def test_coupled_temperature_wavelength_drift_does_not_also_trip_thermal_bias_coupling():
    """The other half of the question the README posed: does the co-drift bonus
    double-count evidence the two hypotheses already partly share? thermal_bias_coupling
    only requires temp_rising (+0.35) here, since bias_current_ma never moves on mod-H8 --
    it lands at exactly 0.45, a genuine near-miss just under CORRELATED_FAULT_THRESHOLD
    (0.5), driven entirely by temperature evidence that wavelength_control_drift's bonus
    also consumes. It stays below the threshold on this data, so mod-H8 correctly produces
    one correlated fault, not two -- but the margin is thin (0.05), not comfortably clear,
    worth flagging honestly rather than treating the threshold as bulletproof."""
    hypotheses = rank_fault_hypotheses("mod-H8")
    by_label = {h["label"]: h["confidence"] for h in hypotheses}

    assert by_label["thermal_bias_coupling"] == 0.45
    assert by_label["thermal_bias_coupling"] < 0.5
    assert by_label["wavelength_control_drift"] > by_label["thermal_bias_coupling"]


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
