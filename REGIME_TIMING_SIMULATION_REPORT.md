# Regime Timing Simulation Report

## Scope

Goal: build deterministic simulations for suspected regime-pipeline edge cases and prove which ones can reproduce the observed "half of bars without regime" symptom.

This report is grounded in the current code reality, not in hypothetical architecture:

- Regime detector: `apps/reference/domains/regime_detector/regime_detector.py`
- FeatureEngineering regime injection seam: `apps/reference/domains/feature_engineering/feature_engineering.py`
- Aurora cached fallback path: `apps/reference/domains/decision_making/aurora_decision.py`
- MR cached regime path: `apps/reference/domains/decision_making/mean_reversion_handler.py`
- TTL gate: `apps/reference/domains/decision_making/readiness_gates.py`

## Execution

Simulation pack added:

- `tests/sim/test_regime_timing_edge_cases.py`

Validation batch:

`c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/sim/test_regime_timing_edge_cases.py tests/runtime/test_task24_regime_detector_correctness.py tests/bootstrap/test_warmup_ssot_alignment.py tests/domains/regime_detector/test_regime_warmup_backfill.py tests/domains/test_dm_bar_ttl_preemit.py -q`

Observed result:

- 55 passed
- 0 failed

Interpretation rule used in this report:

- "Reproduced" means a deterministic passing test proves the current behavior exists.
- "Disproven" means a deterministic passing test ruled out that explanation for the tested seam.

## Main Findings

### 1. The strongest reproducible timing seam is delayed regime-event delivery, not dropped hysteresis emission.

Reproduced on MR:

- `test_mr_one_bar_delayed_regime_event_uses_previous_cached_cmd_regime`
- `test_mr_duplicate_and_skipped_regime_events_replay_deterministically`

Trigger:

- Bar N produces CMD processing before EVT:REGIME_DETECTED(N) updates the cache.

Mechanism:

- FeatureEngineering emits CMD with `regime=self.last_regime.get(symbol)`.
- MR prefers `cmd.regime`, then falls back to its handler-local per-symbol cache.
- If EVT(N) is delayed or skipped, the previous cached regime is reused for the current bar.

Observed effect:

- The current bar is processed with a structurally valid but stale regime.
- This does not look like "missing regime" in raw payload shape; it looks like a present regime with previous-bar truth.

Impacted strategies:

- Confirmed: Mean Reversion handler.
- Plausible by design: any consumer that trusts cached regime injection more than same-bar detector truth.

Verdict:

- This is the closest deterministic reproduction of a real regime-timing defect risk in the current flow.

### 2. Aurora does not silently trade when regime is truly absent, but it can reuse cached previous-bar regime when payload fields are missing.

Reproduced on Aurora:

- `test_aurora_missing_regime_without_cache_blocks_with_canonical_reason`
- `test_aurora_missing_regime_payload_uses_cached_previous_regime_with_traceable_ts`

Trigger A:

- CMD arrives with no regime payload and no prior detector heartbeat/state.

Mechanism A:

- Aurora liveness guard blocks before the kernel because no detector heartbeat has populated state.

Observed effect A:

- Canonical fail-closed blocked outcome with reason code `NRR-REGIME-NO-HEARTBEAT`.

Verdict A:

- Contract-valid fail-closed behavior.

Trigger B:

- CMD arrives with missing regime payload, but the handler already has a previous regime cached from an older EVT:REGIME_DETECTED.

Mechanism B:

- Aurora fills missing `features.regime` and `features.regime_ts_ms` from handler state before the kernel call.

Observed effect B:

- Kernel input carries a real regime value for the current bar, but the attached `regime_ts_ms` remains from the previous bar.
- The fallback is traceable because `regime_ts_ms < bar_close_ts`, but there is no explicit flag saying "previous-bar cache reused".

Impacted strategies:

- Confirmed: Aurora.

Verdict B:

- Not silent corruption, but still a defect-risk and an observability gap.

### 3. Several naive explanations for "half the bars without regime" were disproven.

Disproven explanation: hysteresis is dropping every other regime event.

- Test: `test_hysteresis_raw_regime_churn_can_look_missing_without_dropped_emission`
- Result: hysteresis carry can keep the stable state unchanged while raw regime churns, but the detector still emits a regime event each basis bar.

Disproven explanation: startup warmup buffer creates a permanent every-other-bar no-regime cadence.

- Test: `test_startup_required_bars_boundary_becomes_ready_at_threshold_and_buffer_only_expands_plan`
- Supporting tests: warmup SSOT alignment and warmup backfill suite.
- Result: `basis_import_buffer` expands the startup import plan only. Once readiness is reached, it does not create an alternating missing-regime cadence.

Disproven explanation: cross-symbol queue lag contaminates regime cache across symbols.

- Test: `test_mr_cross_symbol_delays_are_isolated_per_symbol`
- Result: the tested caches remain symbol-isolated.

Disproven explanation: late FEATURES_CALCULATED replays the same MR bar.

- Test: `test_mr_cmd_before_features_event_does_not_reprocess_same_bar`
- Result: FEATURES is a data cache update path, not a second decision trigger for the same bar.

### 4. Explicit fail-closed paths are working and can look like "missing regime" if logs are read loosely.

Reproduced:

- `test_detector_alternating_stale_ready_cadence_is_explicit`
- `test_stale_data_sets_regime_uncertain`
- `test_stale_features_do_not_update_buffers`
- `test_bar_ttl_edge_is_inclusive_and_one_ms_over_fails_in_close_ts_mode`

Trigger:

- Stale bars, old feature timestamps, or TTL overrun by even 1 ms in close-ts mode.

Mechanism:

- Detector emits `UNCERTAIN` or refuses to advance buffers.
- Readiness gates reject stale decision inputs.

Observed effect:

- Downstream may observe many bars that are non-tradable or marked uncertain, but this is explicit fail-closed behavior rather than silent regime loss.

Verdict:

- Contract-valid.

## Trace Excerpts That Matter

Detector hysteresis/log evidence already present in repo logs is consistent with the simulations:

```text
[SOLUSDT] REGIME_AUDIT source=detector regime=UNCERTAIN changed=no carried=yes kind=hysteresis_carried ...
[SOLUSDT] Hysteresis: stable regime transition UNCERTAIN -> LOW_VOLATILITY (confirmed 2 bars)
```

These lines support the deterministic test conclusion that hysteresis can look visually sparse without actually dropping regime emission.

Aurora cached fallback trace, as proven by simulation assertions:

```text
bar_close_ts = current bar
features.regime = LOW_VOLATILITY
features.regime_ts_ms = previous bar ts
```

This is the exact signature of previous-cache reuse rather than same-bar regime truth.

## Root Cause Ranking

### Most likely causes of a real operator-visible "half bars without regime" impression

1. Delayed or skipped regime EVT causes current bars to reuse previous cached regime.
2. Explicit `UNCERTAIN` fail-closed bars are interpreted as missing regime instead of present-but-uncertain regime.
3. Aurora fallback from cached state obscures same-bar freshness because provenance is only implicit in timestamps.

### Causes tested and not supported by evidence

1. Hysteresis dropping every other detector event.
2. Cross-symbol backlog mixing regimes between symbols.
3. Startup `basis_import_buffer` creating a persistent runtime cadence bug.
4. Late FEATURES event causing a second MR decision for the same bar.

## Smallest Safe Hardening Changes

1. Add explicit provenance fields whenever CMD uses cached regime rather than same-bar detector output.

Suggested fields:

- `regime_source`
- `regime_event_ts_ms`
- `regime_same_bar`

Why first:

- This is the smallest change that turns the main timing seam from forensic inference into an explicit contract.

2. Emit a dedicated observability reason when Aurora or MR consumes previous-bar cached regime for the current bar.

Why second:

- Current behavior is traceable only if an operator compares `regime_ts_ms` and `bar_close_ts`. That is too implicit for production diagnosis.

3. Add a narrow integration contract test that wires real detector -> FE -> MR/Aurora across delayed EVT ordering.

Why third:

- The new simulation pack proves the seams, but an end-to-end test would protect the real event choreography from future drift.

4. Consider a strict same-bar freshness guard for entry decisions only.

Why last:

- This changes runtime semantics, so it should follow only after the provenance and observability contract is explicit.

## Bottom Line

The simulations do not support the theory that hysteresis or startup warmup is dropping regime on every other bar. The strongest reproducible seam is ordering: when the current bar is processed before the current regime EVT lands, both MR and Aurora can deterministically consume previous cached regime state. Separately, explicit fail-closed `UNCERTAIN` and TTL behavior can look like missing regime if logs are interpreted loosely, but those paths are contract-valid and are already working as designed.
