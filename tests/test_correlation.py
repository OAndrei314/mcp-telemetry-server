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
