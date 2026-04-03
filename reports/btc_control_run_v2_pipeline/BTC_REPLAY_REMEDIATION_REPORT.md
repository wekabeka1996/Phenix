# BTC Replay Remediation Report

## Hard Verdict

NO_GO_REPLAY_FOUNDATION_STILL_NOT_TRUSTWORTHY

## Canonical Rerun

- Command: python tools/calibration/calibrate_aurora_thresholds.py --input-source recorder-features-v2 --threshold-source-mode live-effective --symbols BTCUSDT --from-date 2026-03-01 --to-date 2026-03-31 --recorder-dir data/recorder --feature-log-dir logs/features --tf-sec 300 --out-dir reports/btc_control_run_v2_repaired
- Result: the production-class entrypoint now executes successfully and writes artifacts under reports/btc_control_run_v2_repaired.
- Baseline source resolved for BTCUSDT: decision.signal_threshold.
- Candidate result: fail-closed no candidate, empty overlay, run verdict NO_GO.

## What Changed In Code

- tools/calibration/calibrate_aurora_thresholds.py now exposes explicit threshold-source-mode choices.
- tools/calibration/calibrate_aurora_thresholds.py now records source/path metadata for the active baseline surface and blocks candidate emission when the live source is global.
- tools/calibration/calibrate_aurora_thresholds.py now enforces active Aurora basis_required_bars before replay scoring.
- tools/calibration/README.md now documents live-effective control replay semantics.
- tests/tools/test_aurora_threshold_calibrator.py locks the new threshold-source contract with unit tests.

## Conclusion 1: Threshold Entry Contract

### FACTS

- Live Aurora resolves per-symbol signal_threshold only when the asset override is enabled; otherwise it falls back to decision.signal_threshold.
- The previous canonical BTC run failed before replay because the calibrator hard-required assets.BTCUSDT.signal_threshold.enabled=true.
- The repaired calibrator now exposes two explicit modes:
  - asset-override-only
  - live-effective
- The repaired canonical BTC rerun succeeds when called with threshold-source-mode=live-effective.
- The repaired run manifest records:
  - threshold_source_mode=live-effective
  - BTC signal_threshold_source=global_decision
  - BTC signal_threshold_path=decision.signal_threshold

### INFERENCES

- The correct repair strategy is option C: two explicit modes.
- The old calibrator was not merely missing a fallback; it was conflating the live-effective baseline contract with the per-asset calibration target contract.

### ASSUMPTIONS

- None.

### UNKNOWNS

- Whether future governance will promote decision.signal_threshold itself into an approved stage-1 calibration surface.

### Diagnostic Split

- symptom: canonical BTC control run aborted before replay.
- root cause: calibrator encoded only the per-asset override contract.
- contributing factor: CALIBRATION_STANDARD_V1 still freezes candidate outputs to per-asset threshold surfaces.
- masking layer: earlier manual-surface replay bypassed the contract failure and therefore could not count as canonical proof.

### Cause / Mechanism / Effect / Operational Risk

- cause: contract conflation.
- mechanism: _extract_live_threshold_surface hard-required assets.<SYMBOL>.signal_threshold.enabled=true.
- effect: BTC control replay could not execute through the intended production-class entrypoint.
- operational risk: any stage-1 decision based on the old bypass path would overstate replay validity.

## Conclusion 2: Readiness and Cold-Start Semantics

### FACTS

- Active Aurora compatibility profile currently resolves basis_required_bars=301.
- Live Aurora checks basis_required_bars before it allows the scoring path to produce actionable output.
- The repaired replay now resolves and enforces basis_required_bars before scoring.
- The repaired replay still does not reproduce full CMD envelope validation, reject WAL emission, or the entire warmup.readiness payload contract.

### INFERENCES

- Cold-start fidelity is narrower than before and no longer ignores a proven live contract.
- This is still only a partial repair because replay remains below the live handler boundary.

### ASSUMPTIONS

- Recorder rows are a valid proxy for accepted bar cadence after basic loader validation.

### UNKNOWNS

- Whether there are live BTC bars that would be rejected by the real CMD envelope but still scored by recorder replay.

### Diagnostic Split

- symptom: replay previously lacked an explicit live basis-required gate.
- root cause: replay loop was built around scoreable recorder rows, not around the live handler contract.
- contributing factor: replay stops below CMD:PROCESS_STRATEGY and below blocked/deferred truth emission.
- masking layer: on a full-month March window, late-bar slices are unaffected by start-of-run basis gating, so the defect is easy to miss in micro-slice-only analysis.

### Cause / Mechanism / Effect / Operational Risk

- cause: architectural shortcut in replay.
- mechanism: direct recorder loop into QuadraticScoringKernel without the live compatibility profile gate.
- effect: start-of-run readiness drift was previously understated.
- operational risk: short-window or restart-window replays can misstate actionable eligibility.

## Conclusion 3: Remaining Fidelity Blockers

### FACTS

- The repaired feature-log audit still reports has_timestamp_fields=false for BTCUSDT.
- The repaired replay still shows these slices:
  - 2026-03-31 07:29:59.999 replay: regime TREND_UP, score -0.0259507, side sell, shield 0.8.
  - 2026-03-31 07:34:59.999 replay: regime TREND_UP, score -0.03472356, side neutral.
  - 2026-03-31 19:04:59.999 replay: regime MEAN_REVERSION, score -0.02899209, side sell, shield 0.75.
- Live BTC still shows:
  - 07:30 score -0.135080, side sell, shield_mult 0.600, TRADE_INTENT_PROPOSED.
  - 07:35 score -0.139757, side sell, shadow why hold:sell:score=-0.1398<=-thr_neutral=-0.0500.
  - 19:05 and 19:15 score -0.147459, side sell, shield_mult 0.450, TRADE_INTENT_PROPOSED.
- Replay still stops at ReplayObservation; it does not replay EVT:STRATEGY_SIGNAL_PRODUCED into StrategyGateway and EVT:TRADE_INTENT_PROPOSED.

### INFERENCES

- Entry-contract validity is repaired, but behavioral fidelity remains unproven.
- The unchanged score, shield, and hold-state drift strongly suggests that the remaining blocker set is dominated by missing feature provenance and below-live replay boundaries rather than by threshold-surface extraction alone.

### ASSUMPTIONS

- None beyond the observed logs and repaired replay artifacts.

### UNKNOWNS

- Exact bar-by-bar source of the replay/live score-scale drift.
- Whether a higher-fidelity feature join would collapse the hold-state and shield drift.
- Whether downstream gateway parity would still diverge even if signal-layer parity improved.

### Diagnostic Split

- symptom: live and replay still disagree on score magnitude, shield attenuation, and hold-state continuity after the repair.
- root cause: unresolved feature provenance and replay boundary mismatch.
- contributing factor: replay does not reproduce the live command envelope, full readiness payload, or signal-to-gateway path.
- masking layer: regime labels can still align on warmed windows, which can falsely suggest stronger fidelity than the actionable outputs support.

### Cause / Mechanism / Effect / Operational Risk

- cause: incomplete live-state reconstruction.
- mechanism: recorder-driven replay lacks timestamped feature provenance and downstream signal/gateway truth.
- effect: threshold-surface trust remains below the bar required for stage-1 BTC calibration foundation use.
- operational risk: threshold calibration performed on this replay could optimize against a materially wrong activation and continuation surface.

## Direct Answers

1. Is BTC replay now contract-valid for the current live config?
   - FACT: Yes for control-baseline execution when threshold-source-mode=live-effective is made explicit.
   - FACT: No as a promotable per-asset calibration target, because current BTC live threshold source is global decision.signal_threshold.

2. Has the critical mismatch set materially shrunk?
   - FACT: The pre-replay entry blocker is repaired.
   - INFERENCE: That shrink is not material enough for stage-1 trust because the remaining high-severity behavior mismatches are still active.

3. Are remaining mismatches bounded enough for stage-1 threshold-surface calibration?
   - FACT: No. Feature provenance, hold-state continuity, score-scale drift, shield drift, and signal/gateway semantics remain unproven or still divergent.

4. What exactly remains unproven?
   - Exact bar-aligned live feature equivalence for BTC.
   - Replay reproduction of live hold-state continuity.
   - Replay reproduction of live score and shield magnitude.
   - Replay reproduction of live EVT:STRATEGY_SIGNAL_PRODUCED -> StrategyGateway -> EVT:TRADE_INTENT_PROPOSED semantics.

## Final Verdict

NO_GO_REPLAY_FOUNDATION_STILL_NOT_TRUSTWORTHY
