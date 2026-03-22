# V2_EVALUATOR_REPLAY_FIDELITY_AUDIT

## Verdict

`HARNESS_PARTIAL_NOT_EQUIVALENT`

## Scope

Question audited:

> Is the current canonical V2 replay harness a faithful replay of live Aurora decision logic up to the signal-emission contract?

Boundaries enforced:

- No tuning
- No code fixes
- No path substitution
- No speculation from docs alone
- Runtime/code truth takes precedence over passport claims

## Evidence Status

### Proven

1. The current canonical "V2" harness used in prior ETH/SOL work is `tools/calibration/calibrate_aurora_thresholds.py --input-source recorder-features-v2`.
2. That harness reuses live `RegimeDetector`, `QuadraticScoringKernel`, shield cascade construction, and replayed side-bias history.
3. That harness does **not** instantiate or traverse the live Aurora signal-emission path implemented in Aurora decision logic.
4. That harness does **not** emit `EVT:STRATEGY_SIGNAL_PRODUCED`.
5. That harness does **not** traverse `StrategyGateway.process_signal()` and therefore does not exercise the live post-signal contract.
6. BTCUSDT can reach the live Aurora signal path in current runtime logs.
7. BTCUSDT cannot enter the canonical V2 harness under the same current runtime config because the harness fail-closes at threshold-surface extraction.

### Inferred

1. The harness is suitable for partial geometry/scoring replay analysis.
2. The harness is not suitable as a full-fidelity proxy for live Aurora behavioral conclusions about signal-emission reachability or downstream gating.

### Unproven

1. Same-bar numerical parity between harness score output and live Aurora score output for a matched symbol/bar pair was not established in this audit.
2. Full symbol-by-symbol replay equivalence across all Aurora assets was not established.

## Missing Requested Inputs

The following user-requested evidence files were searched and not found in workspace:

- `Вставленная ​​уценка.md`
- `Копіпаст і технічні блокери.txt`

This report therefore relies on code, SSOT config, existing reports, and live runtime logs only.

## Canonical Current V2 Harness Path

Canonical harness owner chain:

1. `tools/calibration/calibrate_aurora_thresholds.py:main()`
2. `_extract_live_threshold_surface()` for each requested symbol
3. `_run_v2()`
4. `_load_recorder_bars()` from `data/recorder/.../<SYMBOL>_<tf>.csv`
5. `_collect_feature_log_audit()` for feature-log presence/sampling only
6. `_fit_v2_symbol_calibration()`
7. `_replay_symbol()`
8. `RegimeDetector.handle_event(...)`
9. `QuadraticScoringKernel.compute(...)`
10. `ReplayObservation(...)`
11. calibration metrics / overlay / markdown report rendering

Hard facts from code:

- `_extract_live_threshold_surface()` requires `assets.<SYMBOL>.signal_threshold.enabled=true` and `assets.<SYMBOL>.regime_thresholds.DEFAULT` before replay starts.
- `_run_v2()` aborts if recorder bars are absent.
- `_replay_symbol()` builds scoring inputs from recorder bars plus detector regime payload.
- `_replay_symbol()` calls `QuadraticScoringKernel.compute(...)` directly.
- `_replay_symbol()` uses `warmup_readiness={}`.
- `_replay_symbol()` uses `signal_weights={}`, `feature_neutrals={}`, `essential_features=[]`.
- `_replay_symbol()` records score/side/deferred/threshold outputs into `ReplayObservation` objects.
- No call to Aurora live signal emitters exists in this path.

## Canonical Live Aurora Path

Canonical live owner chain proven from code/logs:

1. `DecisionMaking` listens to upstream events:
   - `EVT:FEATURES_CALCULATED`
   - `EVT:RISK_ASSESSMENT_COMPLETED`
   - `EVT:REGIME_DETECTED`
   - `EVT:STRATEGY_SIGNAL_PRODUCED`
2. `event_handlers.py` caches and logs upstream `FEATURES_RX`, `RISK_RX`, regime updates, warmup state, and config-blocked failures.
3. Aurora live decision logic performs pre-score gating, kernel evaluation, blocked/deferred branches, and signal emission.
4. `_emit_signal()` constructs the live `EVT:STRATEGY_SIGNAL_PRODUCED` payload.
5. `DecisionMaking._on_strategy_signal_gateway` hands the signal into `StrategyGateway.process_signal()`.
6. `StrategyGateway.process_signal()` validates timestamps/payloads/contracts and emits or rejects/defer-blocks `EVT:TRADE_INTENT_PROPOSED`.
7. Order-level safety gates can still reject the trade intent downstream, which is visible in `order_log_v1.jsonl`.

Hard live-path facts from code:

- Live path has explicit pre-kernel fail-closed branches for regime liveness, cold-start `BARS_REQUIRED`, readiness-contract failure, liquidity gate, and config contract issues.
- Live path emits `EVT:QUADRATIC_DECISION_TRACE` and multiple `EVT:STRATEGY_DECISION_BLOCKED` outcomes.
- Live path has neutral early return after score/side determination.
- Live path applies holding-period, reentry cooldown, vol-adjusted gates, objective-engine gate, execution gate, entry-plan and quantizer logic before final signal emission.
- `_emit_signal()` populates a rich payload including strategy id, rid, timestamps, scoring fields, readiness/runtime context, bar identity, replay identity, sizing, regime context, and optional TP/SL and quantization fields.
- `StrategyGateway` is a separate live contract layer after `EVT:STRATEGY_SIGNAL_PRODUCED`.

## Shared Subset vs Missing Live Semantics

### Shared with live path

- Regime detection class reuse
- Quadratic kernel reuse
- Shield cascade reuse
- Side-bias / current-side replay
- Live config-derived threshold surface when allowed by config

### Not replayed by harness

- Live upstream event ingestion contract
- Live warmup/readiness contract
- Live `BARS_REQUIRED` cold-start gate
- Live liquidity gate orchestration context
- Live blocked-event emission semantics
- Live neutral/blocked/deferred observable event contract
- Live `_emit_signal()` payload construction
- `EVT:STRATEGY_SIGNAL_PRODUCED`
- `StrategyGateway.process_signal()`
- `EVT:TRADE_INTENT_PROPOSED`
- Downstream payload-schema validation
- DecisionMaking safety-gate rejects recorded in order log
- Entry plan / objective engine / quantizer / runtime-readiness payload semantics

## Component Reachability Matrix

| Component / Contract Stage | Current V2 Harness | Live Aurora Path | Evidence | Fidelity Result |
| --- | --- | --- | --- | --- |
| Symbol allowlist / runtime asset presence | Yes | Yes | harness `_extract_live_threshold_surface()`; live Aurora symbol config resolution | Partial |
| Per-symbol threshold enabled contract | Yes, hard pre-entry gate | Yes, but inside live handler config semantics | harness fail-close before replay; live path can still run BTC now | Divergent |
| Recorder bar loading | Yes | No | harness `_load_recorder_bars()` only | Divergent |
| Upstream event ingress (`FEATURES_RX`, `RISK_RX`, `REGIME`) | No | Yes | `event_handlers.py`, live logs | Divergent |
| RegimeDetector | Yes | Yes | harness `_replay_symbol()`; live Aurora uses structural regime state | Partial |
| QuadraticScoringKernel | Yes | Yes | direct compute reuse | Shared core |
| Warmup readiness semantics | Stubbed as empty dict | Yes | harness `warmup_readiness={}` vs live warmup/readiness handling | Divergent |
| Signal weights / neutrals / essential feature contract | Stubbed empty | Yes | harness passes empty surfaces | Divergent |
| Liquidity gate | Not orchestrated as live handler branch | Yes | live `aurora_decision.py` | Divergent |
| Deferred/blocked event emission | No emitted live events | Yes | live `_emit_strategy_blocked(...)` branches | Divergent |
| Neutral return semantics | Internal side output only | Yes with live state updates | harness stores side/score only | Partial |
| Objective engine gate | No | Conditional live | live `aurora_decision.py` | Divergent |
| Entry plan | No | Conditional live | live `aurora_decision.py` | Divergent |
| Quantizer | No | Conditional live | live `_emit_signal()` path | Divergent |
| Signal emission payload build | No | Yes | live `_emit_signal()` | Divergent |
| `EVT:STRATEGY_SIGNAL_PRODUCED` | No | Yes | live emit call | Divergent |
| StrategyGateway | No | Yes | `strategy_gateway.py` | Divergent |
| `EVT:TRADE_INTENT_PROPOSED` | No | Yes | live gateway logs | Divergent |
| Order-log safety rejects | No | Yes | `order_log_v1.jsonl` | Divergent |

## Event / Contract Fidelity Matrix

| Event / Contract | Harness | Live | Evidence | Fidelity Result |
| --- | --- | --- | --- | --- |
| `EVT:FEATURES_CALCULATED` upstream contract | Not replayed as event | Yes | `DecisionMaking` listeners, `event_handlers.py` | Not equivalent |
| `RISK_RX` / risk state contract | Not replayed as event | Yes | `event_handlers.py`, live log | Not equivalent |
| `EVT:REGIME_DETECTED` / structural regime contract | Detector used internally only | Yes | live listeners and regime state cache | Partial only |
| `EVT:QUADRATIC_DECISION_TRACE` | No live event emission in harness | Yes | live code/logs | Not equivalent |
| `EVT:DECISION_BLOCKED` | No | Yes | `event_handlers.py` | Not equivalent |
| `EVT:STRATEGY_DECISION_BLOCKED` | No | Yes | repeated `_emit_strategy_blocked(...)` branches | Not equivalent |
| `EVT:HANDLER_READINESS_DIAGNOSTICS` | No evidence of harness emission | Registered in live domain contract | domain dict / live handler diagnostics | Not equivalent |
| `EVT:STRATEGY_SIGNAL_PRODUCED` | No | Yes | live `_emit_signal()` | Not equivalent |
| `EVT:TRADE_INTENT_PROPOSED` | No | Yes | `StrategyGateway.process_signal()` and live logs | Not equivalent |

## Comparative Trace

### Trace A: BTCUSDT on canonical V2 harness

Requested path: same canonical recorder-features-v2 harness class used for ETH/SOL.

Observed path:

1. `main()` begins threshold-surface extraction for BTCUSDT.
2. `_extract_live_threshold_surface()` reads `aurora.assets.BTCUSDT.signal_threshold`.
3. Harness aborts with:

   `CalibrationError: Symbol BTCUSDT requires assets.BTCUSDT.signal_threshold.enabled=true for this calibrator`

Consequence:

- BTC does not reach `_run_v2()`.
- BTC does not reach `_load_recorder_bars()` replay loop.
- BTC does not reach `QuadraticScoringKernel.compute(...)` inside the harness.
- BTC does not reach any signal-emission contract because the harness itself never emits one.

### Trace B: BTCUSDT on canonical live Aurora path

Observed runtime path on 2026-03-21:

1. `RISK_RX` logged for BTCUSDT.
2. `FEATURES_RX` logged for BTCUSDT.
3. Live Aurora logs `QUADRATIC_DECISION_TRACE score=-0.015522 side=sell deferred=False regime=MEAN_REVERSION`.
4. Live Aurora logs `SIGNAL: SELL score=-0.0155 (thr_buy=0.0113, thr_sell=0.0113)`.
5. DecisionMaking logs `STRATEGY_SIGNAL_GATEWAY: Processing SELL signal rid=aurora_BTCUSDT_1774105500290 strategy_id=aurora`.
6. DecisionMaking logs `STRATEGY_SIGNAL_GATEWAY: All gates passed, emitting TRADE_INTENT_PROPOSED`.
7. Order log records `ORDER_REJECTED` for the same RID with `nrr_code=NRR-027` and `why="SAFETY_GATES:uptrend blocks short"`.

Consequence:

- Live BTC reaches the kernel, reaches signal emission, reaches gateway, reaches trade-intent proposal attempt, and only then is rejected by downstream safety gates.
- This runtime path is materially broader than the canonical harness path.

## Divergence Localization

### Divergence 1: Pre-entry contract

The harness has a symbol-level threshold-enabled precondition before replay starts. Live runtime currently shows BTC can traverse live Aurora decision logic. Therefore harness reachability is not equivalent even before scoring begins.

### Divergence 2: Input model

Harness input axis is recorder CSV bars plus sampled feature-log audit. Live path input axis is actual event flow through features/risk/regime handlers with cached state and readiness context.

### Divergence 3: Readiness and warmup contract

Harness hardcodes `warmup_readiness={}`. Live path uses real warmup/readiness state and fail-closed guards, including readiness-contract resolution and `BARS_REQUIRED` gating.

### Divergence 4: Scoring context surface

Harness passes empty `signal_weights`, `feature_neutrals`, and `essential_features`. Live path resolves symbol-aware scoring context from runtime config and handler state.

### Divergence 5: Event semantics

Harness stores `ReplayObservation` objects. Live path emits actual domain events and blocked outcomes. This is a contract difference, not merely an observability difference.

### Divergence 6: Signal-emission boundary

The audit target was fidelity up to signal-emission contract. Harness never reaches `_emit_signal()` and never emits `EVT:STRATEGY_SIGNAL_PRODUCED`. Therefore strict equivalence to that boundary is disproven.

### Divergence 7: Post-signal gateway

Even after signal emission, live path includes `StrategyGateway` and can fail on payload/schema/safety-gate conditions. Harness contains no corresponding layer.

## Why Verdict Is Not `HARNESS_FIDELITY_CONFIRMED`

That verdict would require proof that the canonical harness faithfully replays live Aurora logic up to `EVT:STRATEGY_SIGNAL_PRODUCED`.

Evidence contradicts this:

1. Harness can fail before replay on contracts that do not describe the observed live BTC path.
2. Harness bypasses live readiness, blocked-event, and signal-emission contracts.
3. Harness never emits `EVT:STRATEGY_SIGNAL_PRODUCED`.

Therefore full fidelity up to signal-emission contract is disproven.

## Why Verdict Is Not `HARNESS_FIDELITY_INCONCLUSIVE`

The result is not merely missing evidence. The code directly proves that the harness terminates in `ReplayObservation` production rather than live signal-event emission, and runtime logs directly prove the broader live path exists. That is sufficient to establish partial but non-equivalent fidelity.

## Final Conclusion

The current canonical V2 harness is a **partial replay of the live Aurora scoring core**, not a faithful replay of the live Aurora decision path up to the signal-emission contract.

It is faithful only to a narrowed subset:

- detector-assisted regime context
- quadratic kernel invocation
- threshold/shield/side-bias style replay

It is **not** faithful to the live decision contract boundary because it omits the live ingress state model, fail-closed readiness gates, blocked-event semantics, `_emit_signal()` payload construction, and `StrategyGateway` handoff.

## Recommended Next Package

`REPLAY_EQUIVALENCE_TRACE_PACKAGE`

Reason:

The next highest-value work item is not threshold tuning. It is a purpose-built equivalence harness or observability package that can produce same-bar side-by-side traces for live Aurora vs replay Aurora across the exact signal-emission boundary.
