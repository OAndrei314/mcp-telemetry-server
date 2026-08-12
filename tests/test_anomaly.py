import pytest

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


def test_smaller_window_catches_a_spike_a_larger_window_absorbs():
    """window is now a caller-facing parameter (via the MCP tools) rather than an internal
    constant -- prove it actually changes what gets flagged, not just that it's accepted.

    Series: 20 wildly oscillating points, then a flat run, then a moderate spike. A narrow
    window (baseline drawn only from the flat run) flags the spike; a wide window (baseline
    drawn mostly from the earlier oscillation, so std is already large) does not."""
    values = [10.0 + 8.0 * (1 if i % 2 == 0 else -1) for i in range(20)]
    values += [10.0 + 0.01 * (i % 3) for i in range(20, 35)]
    values.append(10.5)  # index 35, moderate spike
    values += [10.0 + 0.01 * (i % 3) for i in range(36, 40)]

    narrow = detect_anomalies(values, window=4, z_thresh=3.0)
    wide = detect_anomalies(values, window=30, z_thresh=3.0)
    assert 35 in {a["index"] for a in narrow}
    assert 35 not in {a["index"] for a in wide}


@pytest.mark.parametrize("window", [0, 1, -3])
def test_window_below_two_rejected(window):
    with pytest.raises(ValueError):
        detect_anomalies([1.0] * 10, window=window)


@pytest.mark.parametrize("z_thresh", [0, -1.0])
def test_non_positive_z_thresh_rejected(z_thresh):
    with pytest.raises(ValueError):
        detect_anomalies([1.0] * 10, z_thresh=z_thresh)
