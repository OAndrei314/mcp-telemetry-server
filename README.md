# mcp-telemetry-server

*Maintained by: claude-actions-daily-routine · Status: Active*
An MCP (Model Context Protocol) server exposing tools to query and analyze synthetic
optical-module telemetry — combining a current AI-agent trend (MCP as the standardizing
layer for tool-use) with a domain I've actually worked in (host software for configuring,
controlling, and monitoring optical modules; telemetry/calibration analysis).

## Why this matters

**Research question:** can a simple, explainable per-metric anomaly detector reliably
separate genuinely drifting hardware from ordinary measurement noise across several
simultaneous telemetry streams, without a black-box model?

**Practical impact:** unplanned optical-link downtime and slow root-cause triage cost real
money in production networks and AI-datacenter interconnect fabric. An agent that can pull
structured telemetry and get a fast, explainable anomaly read (via MCP, from any MCP-aware
client) is a small step toward automating that triage instead of paging a human for every
alarm.

## What's implemented

- `telemetry_server/telemetry_sim.py` — generates plausible-shaped synthetic telemetry
  (temperature, bias current, optical power, wavelength) for 5 fictional modules; three of
  them have a deliberately injected drift/degradation in their most recent readings (two
  single-fault modules, one dual-fault module with both faults injected at once).
- `telemetry_server/anomaly.py` — a rolling z-score detector: every flagged point comes
  with the window mean/std it was compared against, so it's auditable, not a black box.
- `telemetry_server/health.py` — aggregates per-metric anomaly flags into one module health
  status (`healthy` / `degraded` / `critical`).
- `telemetry_server/correlation.py` — adds recent multi-metric trend analysis and ranks
  transparent root-cause hypotheses such as thermal/bias coupling or optical-power
  degradation.
- `telemetry_server/server.py` — wires all of the above into 6 MCP tools (`list_modules`,
  `get_telemetry`, `detect_anomalies`, `get_module_health_summary`,
  `explain_module_health`, `list_metrics`) using the MCP Python SDK's `MCPServer`
  (SDK 2.0 — the API package that superseded `FastMCP`). The detection thresholds
  (`window`, `z_thresh`, `min_persistent_points`, `correlated_fault_threshold`, per-metric
  `slope_thresholds`) are real tool parameters with validated defaults, not fixed
  constants — an MCP client can loosen or tighten sensitivity per call without a code
  change.

## Quickstart

```bash
pip install -r requirements.txt

# Run the server directly (stdio transport) -- point an MCP client at this command
python -m telemetry_server.server
```

To use it from Claude Desktop or Claude Code, add it as an MCP server pointing at
`python -m telemetry_server.server` in this repo's directory.

## Honest results — the anomaly detector's real precision/recall tradeoff

This is worth being specific and honest about rather than claiming a clean win, because the
naive version genuinely doesn't work well: **independent per-point z-score flagging across
4 simultaneous metric streams over 24h has a real false-alarm rate.** At the detector's own
default settings (window=8, z=3.0), *every one* of the 13 (module, metric) pairs without any
injected fault still got at least one flagged point somewhere in 24h — a completely
unusable false-positive rate for a status indicator, even though it correctly caught all 3
of the actually-injected faults.

Two adjustments, both checked against known-good/known-bad synthetic data (not tuned to
"look good," tuned to actually separate the two groups):
1. `health.py` uses a more conservative (window=10, z=3.5) than the detector's own
   general-purpose defaults — trading some sensitivity for far fewer false alarms.
2. A metric only counts as "flagged" for health scoring if **at least 2** of its points
   are individually anomalous, not just one — filters isolated blips, keeps sustained drift.

Result: at the current seeded synthetic data, the two modules with **no** injected fault
(`mod-A1`, `mod-B2`) land on `degraded` (1 flagged metric each — some residual false-alarm
rate remains, it's not perfectly clean) while both modules with **real** injected drift
(`mod-C3`, `mod-D4`) correctly land on `critical` (2 flagged metrics each) — so the overall
verdict is right. The detailed per-metric attribution is *not* perfectly clean, though: on
`mod-C3` the detector under-detects the injected `bias_current_ma` drift (only 1 point
flagged, below the persistence bar) while spuriously flagging the uninjected
`wavelength_nm` stream (2 points) — the module-level verdict happens to net out correctly
here, but that's not a guarantee.

## Explanation Layer

`explain_module_health` goes beyond independent point anomalies. It computes recent slopes
for each metric, then ranks simple hypotheses from correlated directions:

- thermal/bias co-drift -> check the thermal sweep and bias-compensation loop;
- optical-power drop without heating -> inspect connector cleanliness, receiver margin,
  and laser-aging telemetry;
- wavelength movement -> check wavelength-locker and thermal-control stability;
- no correlated drift -> treat isolated flags as likely measurement noise.

The layer is deliberately transparent: the returned payload includes recent per-metric
slopes, trend directions, evidence strings, confidence scores, and the recommended next
validation check.

## Status / next steps

Configurability is done: `detect_anomalies`, `get_module_health_summary`, and
`explain_module_health` all now accept `window`, `z_thresh`, `min_persistent_points`,
`correlated_fault_threshold`, and (for the correlation layer) a partial-override
`slope_thresholds` dict, all validated (`window >= 2`, `z_thresh > 0`,
`min_persistent_points >= 1`, `correlated_fault_threshold > 0`, unknown metric keys
rejected) and defaulting to the values measured in "Honest results" above. Verified with
tests that assert each override actually flips the verdict, not just that the parameter is
accepted.

A fifth module, `mod-E5`, injects two faults at once — thermal drift and optical-power
degradation, independently of each other (neither derived from the other) — to stress-test
`rank_fault_hypotheses` against a genuinely ambiguous case, since `mod-C3`/`mod-D4` each
only ever have one fault active. Measured, not assumed: the correlation layer handles this
correctly — `thermal_bias_coupling` (0.95) and `optical_power_degradation` (0.7) both land
well above the ~0.1 baseline an inactive hypothesis sits at elsewhere, correctly ordered by
evidence strength.

That surfaced a real, previously-untested miscalibration in the *other* severity signal:
`summarize_module_health` used to report `mod-E5` as merely `degraded` — the same status as
a fault-free module — because splitting the same total anomaly magnitude across three
metrics (temperature, bias current, optical power) instead of concentrating it in one or two
made each individual metric less likely to clear the `min_persistent_points=2` persistence
bar on its own, even though the correlation layer correctly flagged both faults. This is now
fixed: `summarize_module_health` takes the *max* of two independent severity signals —
`flagged_metric_count` (point-anomaly counting, as before) and `correlated_fault_count`
(fault hypotheses other than `ordinary_measurement_noise` scoring at or above
`correlated_fault_threshold`, default `0.5`, chosen because measured baseline hypothesis
scores on fault-free modules top out at 0.2 while every real, engaged fault in this dataset
scores 0.7+ — see `health.CORRELATED_FAULT_THRESHOLD`'s docstring). `mod-E5` now correctly
reports `critical`, and the fix can only ever raise severity relative to the old
point-counting-only behavior, never lower it — confirmed by
`test_dual_fault_module_health_status_reflects_correlated_severity` and
`test_fault_free_modules_have_no_correlated_faults` (the fault-free modules stay clean, so
this isn't a new source of false positives).

One honest side effect worth calling out: because the two severity signals are now genuinely
independent, loosening only `min_persistent_points` on `mod-C3` no longer forces `healthy`
by itself — the correlation layer still sees the real thermal/bias co-drift regardless of
the point-anomaly persistence bar, so the status now correctly stays `degraded` unless
`correlated_fault_threshold` is loosened too. This is pinned by
`test_min_persistent_points_override_actually_changes_the_verdict` in `tests/test_health.py`.

Next genuine step: `correlated_fault_threshold=0.5` is validated against this repo's 5 fixed
synthetic modules, not stress-tested against a fault that engages only one of the two metrics
`thermal_bias_coupling` currently requires together (e.g. bias-current drift alone, without a
temperature rise) — `rank_fault_hypotheses` can in principle score such a case as low as 0.4,
which the current threshold would miss. Adding a sixth module with an isolated single-metric
thermal fault would be the natural way to find out whether 0.5 still holds up, or needs to
move.

## License

MIT — see [LICENSE](LICENSE).
