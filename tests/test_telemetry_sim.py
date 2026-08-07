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
