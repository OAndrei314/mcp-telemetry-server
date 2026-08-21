import pytest

from telemetry_server.telemetry_sim import generate_telemetry, list_module_ids


def test_list_module_ids_is_stable_and_nonempty():
    ids = list_module_ids()
    assert ids == sorted(ids)
    assert len(ids) >= 2


def test_generate_telemetry_is_deterministic():
    a = generate_telemetry("mod-A1", "temperature_c", hours=12)
    b = generate_telemetry("mod-A1", "temperature_c", hours=12)
    assert a == b


def test_generate_telemetry_point_count():
    series = generate_telemetry("mod-A1", "temperature_c", hours=10, points_per_hour=4)
    assert len(series) == 40
    assert series[0]["hours_ago"] > series[-1]["hours_ago"]
    assert series[-1]["hours_ago"] == 0.0


def test_unknown_module_raises():
    with pytest.raises(ValueError):
        generate_telemetry("not-a-real-module", "temperature_c")


def test_unknown_metric_raises():
    with pytest.raises(ValueError):
        generate_telemetry("mod-A1", "not_a_real_metric")


def test_thermal_drift_module_ends_hotter_than_it_started():
    series = generate_telemetry("mod-C3", "temperature_c", hours=24)
    early_avg = sum(p["value"] for p in series[:20]) / 20
    late_avg = sum(p["value"] for p in series[-4:]) / 4
    assert late_avg > early_avg + 2.0  # injected drift should be clearly visible


def test_isolated_bias_drift_module_leaves_temperature_flat():
    """mod-F6 injects bias_current_ma drift alone -- unlike mod-C3, temperature_c must stay
    untouched so the correlation layer's thermal_bias_coupling hypothesis (which scores on
    temperature_c + bias_current_ma together) has a genuine single-metric case to arbitrate,
    not a second copy of mod-C3's already-coupled fault."""
    bias_series = generate_telemetry("mod-F6", "bias_current_ma", hours=24)
    temp_series = generate_telemetry("mod-F6", "temperature_c", hours=24)

    bias_early = sum(p["value"] for p in bias_series[:20]) / 20
    bias_late = sum(p["value"] for p in bias_series[-4:]) / 4
    assert bias_late > bias_early + 2.0  # injected drift should be clearly visible

    temp_early = sum(p["value"] for p in temp_series[:20]) / 20
    temp_late = sum(p["value"] for p in temp_series[-4:]) / 4
    assert abs(temp_late - temp_early) < 2.0  # no injected drift here


def test_dual_fault_module_shows_both_independently_injected_drifts():
    """mod-E5 injects thermal drift and power degradation independently of each other
    (unlike mod-C3/mod-D4, which each have exactly one active fault) -- both should be
    clearly visible in their respective metrics at the same time."""
    temp_series = generate_telemetry("mod-E5", "temperature_c", hours=24)
    power_series = generate_telemetry("mod-E5", "optical_power_dbm", hours=24)

    temp_early = sum(p["value"] for p in temp_series[:20]) / 20
    temp_late = sum(p["value"] for p in temp_series[-4:]) / 4
    assert temp_late > temp_early + 2.0

    power_early = sum(p["value"] for p in power_series[:20]) / 20
    power_late = sum(p["value"] for p in power_series[-4:]) / 4
    assert power_late < power_early - 1.0
