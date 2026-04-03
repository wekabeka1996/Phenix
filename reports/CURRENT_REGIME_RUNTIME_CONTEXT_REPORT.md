# CURRENT_REGIME_RUNTIME_CONTEXT_REPORT

Date: 2026-03-30

## Scope

This report answers four narrow runtime questions:

1. Where the current regime is actually computed.
2. Whether the active regime truth is symbol-local, global, or mixed.
3. Where regime and regime_confidence materially influence trading behavior.
4. What lifecycle timing metadata exists today, and what is still missing.

Method constraints used for this audit:

- Runtime code and active consumers outweigh documentation comments.
- Config presence was counted only when a live consumer was proven.
- Facts, inferences, assumptions, and unknowns are separated.
- The protocol docs referenced by workspace instructions under docs/ai were not present in the checked repo path, so this audit is anchored to code, config, and tests that were actually available.

## Executive Verdict

- The live structural regime truth is produced by apps/reference/domains/regime_detector/regime_detector.py from EVT:FEATURES_CALCULATED basis-bar events.
- The live structural regime currently emitted by in-repo code is per_symbol, structural, and bar-clocked. The contract supports broader layer/scope combinations, but no in-repo producer of a global structural regime was proven.
- Regime materially affects trading through warmup gating, directional sanity min_regime_confidence gating, Aurora regime gating and threshold scaling, Aurora liveness checks, MR flat-regime gating and parameterization, MD-AMR regime allowlists, execution pending-entry cancellation, and objective score inputs.
- Current lifecycle timing is partial only. The repo has changed, ts_ms, last_update_ts_ms, structural_regime_ref, and hysteresis counters, but no durable stable_since timestamp or true time_in_regime clock. Downstream regime_age_sec is currently freshness since last heartbeat, not dwell time in the current stable regime.

## Evidence Base

Primary runtime files inspected:

- apps/reference/domains/regime_detector/regime_detector.py
- apps/reference/domains/regime_detector/schemas/regime_detected_v1.json
- apps/reference/contracts/runtime_regime_layers.py
- apps/reference/domains/feature_engineering/feature_engineering.py
- apps/reference/domains/feature_engineering/calculation_engine.py
- apps/reference/domains/decision_making/event_handlers.py
- apps/reference/domains/decision_making/readiness_gates.py
- apps/reference/domains/decision_making/safety_gates.py
- apps/reference/domains/decision_making/aurora_handler.py
- apps/reference/domains/decision_making/aurora_decision.py
- apps/reference/domains/decision_making/aurora_config_loader.py
- apps/reference/domains/decision_making/aurora_scoring_helpers.py
- apps/reference/domains/decision_making/mean_reversion_handler.py
- apps/reference/domains/feature_engineering/mean_reversion_strategy.py
- apps/reference/domains/feature_engineering/regime_mapping.py
- apps/reference/domains/decision_making/md_amr_handler.py
- apps/reference/domains/execution_position/event_handlers.py
- apps/reference/domains/objective_engine/runtime.py
- apps/reference/domains/objective_engine/components/information.py

Primary config surfaces inspected:

- config/aurora/regime.yaml
- config/aurora/domains.yaml
- config/aurora/trading.yaml
- config/aurora/strategies/aurora.yaml
- config/aurora/strategies/mean_reversion.yaml
- config/aurora/strategies/md_amr.yaml
- apps/reference/config_models.py

## FACTS

### 1. Actual producer and event cadence

- RegimeDetector subscribes to EVT:FEATURES_CALCULATED and ignores other verbs.
- It only processes feature events whose tf_sec equals basis_tf_sec. Tick-level events with tf_sec=0 are explicitly ignored, and other timeframes are ignored too.
- The emitted contract is EVT:REGIME_DETECTED.
- EVT:REGIME_DETECTED is emitted on every basis-bar close as a heartbeat, not only on transitions. The payload field changed indicates whether the stable regime label changed on that heartbeat.

Implication of the fact above:

- The current regime clock is basis-bar driven, not tick driven.
- Current downstream caches receive repeated same-regime heartbeats.

### 2. What the producer computes

The current producer computes and emits all of the following:

- stable regime label
- confidence
- raw_regime and raw_confidence
- warmup block with ticks_seen, ready map, reasons, and full_ready
- changed
- last_update_ts_ms heartbeat timestamp
- calc_lag_ms
- structural_regime_ref
- hysteresis_confirm_count
- volatility telemetry such as vol_ratio and vol_ratio_slope

Classification details proven in code:

- Confidence is derived from SMA divergence.
- A confidence cutoff can demote the regime to UNCERTAIN.
- Volatility classification can produce HIGH_VOLATILITY or LOW_VOLATILITY and includes a slope gate that can reject a fading storm classification.
- Mean-reversion classification exists as a separate model path.
- Trend classification is a fallback path.
- Hysteresis stabilizes the output before it is emitted as the live regime label.

### 3. What the current emitted regime means

The current RegimeDetector payload is emitted with:

- regime_layer=structural
- regime_scope=per_symbol
- regime_clock=bar
- regime_owner=regime_detector

The runtime contract in apps/reference/contracts/runtime_regime_layers.py supports more possibilities:

- structural
- execution_micro
- global_backdrop
- per_symbol
- global

But the active in-repo producer inspected for this audit emits only structural plus per_symbol plus bar.

### 4. Current consumer semantics by layer

#### FeatureEngineering

- FeatureEngineering caches structural regime payloads in last_regime[symbol].
- It injects that cached regime snapshot into CMD:PROCESS_STRATEGY.

This proves regime is part of the strategy command context, not only a side cache.

#### DecisionMaking central cache

- DecisionMaking event_handlers.on_regime ignores non-structural regime payloads.
- Structural payloads are copied into latest_regime, latest_warmup, latest_structural_regime_by_symbol, latest_structural_warmup_by_symbol, and _per_symbol_regimes[symbol].
- _per_symbol_regimes[symbol] stores regime, confidence, warmup, ts_ms, layer, scope, clock, and structural_regime_ref.

This proves the current central trade-decision cache treats live structural regime as per-symbol state.

#### ExecutionPosition

- execution_position.event_handlers.on_regime_detected always caches the latest structural label by symbol when symbol is present.
- Global exposure adaptation only runs when should_apply_global_execution_regime(payload) is true.
- should_apply_global_execution_regime requires regime_scope=global and regime_layer in execution_micro or global_backdrop.

This proves that current per-symbol structural regime does not directly drive global exposure adaptation.

### 5. Where regime materially affects trading decisions

The following effects are proven live in the inspected runtime paths.

| Consumer | Inputs read | Proven material effect |
| --- | --- | --- |
| DecisionMaking ReadinessGates | regime warmup.full_ready and features warmup.full_ready | Blocks trade-intent progression when regime warmup or feature warmup is not full_ready |
| DecisionMaking SafetyGates | regime_confidence and directional_sanity.min_regime_confidence | Denies non-reduce-only opens when effective confidence is below the configured threshold |
| AuroraHandler and Aurora decision flow | regime, regime_confidence, last_update_ts_ms | Applies regime liveness checks, regime allowlist logic, regime threshold selection, and objective inputs |
| Aurora anchor shock logic | macro_resid with anchor_shock_veto config | Blocks non-anchor BUYs when macro_resid is below the adverse BTC-anchor threshold |
| MeanReversion | structural regime mapped through map_to_flat_regime | Rejects non-flat regimes and applies flat-regime-specific size, stop, and target parameters |
| MD-AMR | cached regime plus compatibility-expanded allowlist | Blocks entry when current regime is outside the effective allowlist |
| ExecutionPosition | regime event and pending_entry_ttl config | Cancels pending entries on regime events when cancel_on_regime_change is enabled |
| Objective engine | regime_age_sec, regime_confidence, readiness_completeness | Adds staleness penalty and regime_confidence reward to objective score |

Additional proven config facts that make the objective path material in current repo state:

- config/aurora/domains.yaml has objective_engine.enabled: true.
- config/aurora/strategies/aurora.yaml has objective.enabled: true and multiple regime entries in GATE mode.
- config/aurora/strategies/md_amr.yaml has objective.enabled: true and multiple regime entries in GATE mode.
- config/aurora/strategies/mean_reversion.yaml has objective.enabled: true, but its inspected regime entries are OBSERVE mode rather than GATE mode.

Therefore:

- Hard open-blocking from regime_confidence is directly proven in SafetyGates.
- Objective modulation from regime_confidence is directly proven in objective scoring.
- Objective hard-gating is currently proven for Aurora and MD-AMR config paths, and only observe-mode is proven in the inspected MR config path.

### 6. Symbol-local versus global versus mixed

Current active runtime truth can be stated precisely as follows:

- Current structural regime truth is symbol-local.
- The overall contract system is mixed-capable because it supports global_backdrop and execution_micro layers with global scope.
- The current active producer proven in this audit does not emit a global structural regime.
- ExecutionPosition is already coded to treat global execution regimes differently from structural per-symbol regimes.

So the correct present-tense statement is:

- The live structural regime currently used by strategy logic is per-symbol.
- The runtime regime framework is mixed-capable, but that broader capability should not be mistaken for current live structural behavior.

### 7. Lifecycle metadata that exists today

Current lifecycle-adjacent fields that do exist:

- changed
- ts_ms
- last_update_ts_ms
- structural_regime_ref
- raw_regime
- stable_confidence
- hysteresis_confirm_count

Current lifecycle-adjacent behaviors that also exist:

- Consumers keep only the latest regime snapshot per symbol.
- RegimeDetector emits same-regime heartbeats repeatedly.
- DecisionMaking overwrites _per_symbol_regimes[symbol] on each new heartbeat.
- Aurora, MR, and MD-AMR handlers overwrite their cached regime ts on each heartbeat.

### 8. Lifecycle metadata that is missing today

The following were not found as explicit runtime fields in the current live structural regime path:

- stable_since_ts_ms
- previous_regime
- previous_regime_ts_ms
- time_in_regime_sec as durable dwell time
- bars_in_current_regime
- confirmed_at_ts_ms separate from latest heartbeat ts
- regime transition history beyond the last snapshot

Most important missing semantic:

- objective inputs currently compute regime_age_sec from now_ms minus state.regime_ts_ms.
- state.regime_ts_ms is refreshed on each incoming heartbeat.
- Because EVT:REGIME_DETECTED is emitted every basis bar even when the regime has not changed, current regime_age_sec measures heartbeat freshness, not age of the stable regime.

This is the strongest proof that lifecycle timing is only partial today.

### 9. Proven config/runtime mismatches and drift candidates

#### 9.1 Global Aurora threshold surface mismatch

Proven live reads found:

- Global Aurora load path reads decision.regime_threshold_multipliers.
- Symbol-specific override path reads assets.<SYMBOL>.regime_thresholds.

Not proven live in the inspected Aurora path:

- a read of global decision.regime_thresholds.

This means the current audited statement is:

- regime_threshold_multipliers is live as the global Aurora default.
- assets.*.regime_thresholds is live as the per-symbol override.
- global decision.regime_thresholds is declared in YAML but was not proven live in the current Aurora runtime path.

#### 9.2 Pending-entry cancel semantics mismatch

execution_position.event_handlers.on_regime_detected cancels pending entries when:

- pending_entry_ttl.enabled is true
- cancel_on_regime_change is true
- symbol is present

That path does not inspect payload.changed before canceling.

Therefore the strict fact is:

- Current execution-position cancel behavior is keyed on regime event receipt plus config, not on a proven changed=true check.

#### 9.3 MR allowlist token mismatch

The current MR path works as follows:

- mean_reversion_strategy maps structural regimes into FlatRegime via regime_mapping.py.
- The entry gate compares flat_regime.name against allowed_regimes.
- map_to_flat_regime returns FLAT_* values for eligible flat conditions and None for TREND_UP, TREND_DOWN, HIGH_VOLATILITY, and UNCERTAIN.

Therefore:

- The literal config token MEAN_REVERSION in MR allowed_regimes is not the runtime value actually compared by the gate.
- In the current audited runtime, FLAT_LOW, FLAT_NORMAL, and FLAT_HIGH are the live allowlist tokens that matter.

## INFERENCES

- Any future global market-backdrop or BTC-led context should remain additive and separate from the raw structural regime label. The current runtime already distinguishes structural versus global execution-style contexts conceptually, and downstream code depends on that distinction.
- Because true regime dwell time is not stored today, a new lifecycle-aware policy cannot be reconstructed faithfully from existing state caches alone. It needs additive state that preserves first-confirmed timing rather than only last-heartbeat timing.
- The current execution-position config name cancel_on_regime_change is broader in behavior than its name suggests, because cancellation is not gated by a proven changed flag check in the inspected runtime path.
- The unproven global decision.regime_thresholds surface is likely legacy or dead config, but that should remain an inference until either a consumer is found or the field is removed.

## ASSUMPTIONS

- This audit assumes the checked repository contains the active in-repo regime producers and consumers relevant to the requested scope.
- This audit does not assume any hidden external producer of EVT:REGIME_DETECTED beyond what was present in repo code.

## UNKNOWNS

- Whether an external runtime component outside the repo emits global structural or global_backdrop regime events in production.
- Whether any legacy dashboard or tooling path still reads the global decision.regime_thresholds YAML field.
- Whether production deployment uses the repo YAML exactly as checked, especially for objective gate modes.

## Bottom Line

The current live regime system is best described as a per-symbol structural regime producer with bar-clocked heartbeats, downstream warmup and confidence gating, and strategy-specific policy usage. The repo is capable of supporting broader context layers, but those broader layers are not the same thing as the current live structural truth. Any lifecycle-aware or BTC-led enhancement should be built as additive context on top of this structural truth, not as a rewrite of the structural regime itself.
