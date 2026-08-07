from telemetry_server.anomaly import detect_anomalies


def test_flat_series_has_no_anomalies():
    values = [10.0] * 30
    assert detect_anomalies(values) == []


def test_stable_series_with_one_spike_flags_the_spike():
    values = [10.0 + (0.01 * (i % 3)) for i in range(30)]
    values[25] = 50.0  # obvious spike well past the window
    anomalies = detect_anomalies(values, window=8, z_thresh=3.0)
    flagged_indices = {a["index"] for a in anomalies}
    assert 25 in flagged_indices


def test_no_anomalies_flagged_before_window_fills():
    values = [1.0, 100.0, 1.0, 100.0]  # wild swings, but shorter than default window
    assert detect_anomalies(values, window=8) == []
