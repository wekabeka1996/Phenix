# CURRENT WARMUP / QUADRATIC / DECISION LIFECYCLE AUDIT

Date: 2026-03-10
Scope: current active Aurora runtime under `config/aurora`, code-first only
Method: config + runtime code + selected tests; no trust in stale docs unless confirmed by code

## 1. Executive Summary

This branch contains working infrastructure for:

- multi-timeframe bar aggregation (3m, 5m, 15m, 4h, 1d)
- feature-engineering warmup gating
- rule-based regime detection on 5m
- Phase 9 pillar computation hooks
- Quadratic scoring kernel
- full decision-to-order execution chain

However, the currently active live runtime is not a fully wired Quadratic runtime.

Confirmed current-state facts:

1. Aurora is currently running with `scoring_version: "v2"`, not `quadratic`.
2. Regime detection currently depends only on 5m bars and internal SMA/ATR buffers.
3. Phase 9 pillars require M15/H4/D1 bars, and FE can ingest them.
4. A dedicated pillar backfill service exists for Binance klines.
5. No confirmed startup path was found that actually runs pillar backfill and emits `EVT:HTF_BARS_IMPORTED` before live trading starts.
6. `warmup.full_ready` in FE does not include pillar readiness, so FE readiness and Quadratic readiness are currently different contracts.
7. If Quadratic is enabled today without HTF hydration, FE can still emit `CMD:PROCESS_STRATEGY`, but `QuadraticScoringKernel` will defer on `PILLAR_WARMUP` until `pillar_sum` appears.
8. Market-data startup is live WebSocket driven; no confirmed historical seed or delta-sync bootstrap was found for bars or HTF state.
9. Disaster recovery restores position-related state from snapshots/WAL, but no equivalent FE/regime/pillar warm-state restore was found.

Bottom line:

- Current live path is bar-driven and operational for legacy Aurora v2.
- Current repo contains Phase 9 pieces, but not a fully bootstrapped Quadratic live startup.
- The most dangerous contradiction is not "missing code", but mismatched readiness contracts: FE may report ready while Quadratic remains not ready.

## 2. Evidence Model

Status definitions used in this audit:

- CONFIRMED: directly verified in active code/config/tests
- LIKELY: strongly implied by code shape, but not executed end-to-end in this audit
- NOT VERIFIED: plausible, but not established from inspected evidence

Primary evidence anchors used:

- `apps/reference/main.py`
- `apps/reference/bootstrap/domain_builder.py`
- `config/aurora/trading.yaml`
- `config/aurora/regime.yaml`
- `config/aurora/domains.yaml`
- `config/aurora/strategies/aurora.yaml`
- `apps/reference/domains/feature_engineering/feature_engineering.py`
- `apps/reference/domains/feature_engineering/pillar_backfill.py`
- `apps/reference/domains/feature_engineering/types.py`
- `apps/reference/domains/regime_detector/regime_detector.py`
- `apps/reference/domains/decision_making/aurora_handler.py`
- `apps/reference/domains/decision_making/aurora_config_loader.py`
- `apps/reference/domains/decision_making/aurora_decision.py`
- `apps/reference/domains/decision_making/quadratic_scoring_kernel.py`
- `apps/reference/domains/decision_making/decision_making.py`
- `apps/reference/domains/decision_making/strategy_gateway.py`
- `apps/reference/domains/execution_position/fsm.py`
- `apps/reference/domains/execution_position/intent_router.py`
- `apps/reference/domains/execution_position/event_handlers.py`
- `apps/reference/domains/execution_position/open_executor.py`
- `apps/reference/domains/market_data/market_data_connector.py`
- `apps/reference/domains/market_data/proxy.py`
- `apps/reference/domains/market_data/worker.py`
- selected tests under `tests/integration`, `tests/e2e`, `tests/unit`, `tests/apps/reference/tests`

## 3. Current Active Runtime Topology

| Layer | Active component | Current role | Current status |
| --- | --- | --- | --- |
| Entry | `apps/reference/main.py` | loads `config/aurora`, builds domains, starts runtime | CONFIRMED |
| Composition root | `bootstrap/domain_builder.py` | constructs live domains | CONFIRMED |
| Market data | `MarketDataProxy` or `MarketDataConnector` | live WS tick ingestion | CONFIRMED |
| Bar layer | `BarAggregator` | emits 180/300/900/14400/86400 bar closes | CONFIRMED |
| Feature engineering | `FeatureEngineering` | computes features, warmup, pillars, emits `CMD:PROCESS_STRATEGY` | CONFIRMED |
| Regime | `RegimeDetector` | 5m-only rule-based regime model | CONFIRMED |
| Strategy | `AuroraHandler` | active Aurora signal logic | CONFIRMED |
| Signal gate | `StrategyGateway` | turns strategy signal into intent | CONFIRMED |
| Execution | `ExecPosFSM` + helpers | routes intents into open/close/order lifecycle | CONFIRMED |
| DR | snapshot + WAL replay for positions | partial warm restart | CONFIRMED |
| HTF startup hydration | pillar backfill bootstrap | no startup call path found | CONFIRMED ABSENCE |

## 4. Startup / Bootstrap Trace

Observed startup flow:

1. `main.py` loads `config/aurora` through `ConfigLoader(config_dir=project_root / "config" / "aurora")`.
2. `build_live_domains()` instantiates account, market data, FE, risk, position tracking, execution, decision, regime, recorder, optional bar aggregator.
3. `main.py` performs exchange filter validation.
4. `main.py` restores DR snapshot/WAL for position-related state.
5. `main.py` starts account connector, market data, FE, risk, position tracking, decision making, regime detector, recorder.

What startup does not visibly do:

| Startup concern | Observed path | Result |
| --- | --- | --- |
| Historical kline seed for 5m regime | no explicit startup loader found | CONFIRMED ABSENCE |
| HTF pillar backfill | no confirmed call to `pillar_backfill.warmup_pillars()` | CONFIRMED ABSENCE |
| `EVT:HTF_BARS_IMPORTED` bootstrap emit | FE listens for it, but no startup producer found | CONFIRMED ABSENCE |
| FE warm-state restore | no restore path found | CONFIRMED ABSENCE |
| Regime warm-state restore | no restore path found | CONFIRMED ABSENCE |
| Pillar state restore | no restore path found | CONFIRMED ABSENCE |

Implication:

- startup is live-stream-first, not history-seeded
- DR is strong for execution state, but weak for analytics state

## 5. Warmup Inventory

### 5.1 Deterministic bar-time warmups from active config

Computed from current active config:

| Subsystem | Driver | Requirement | Approx wall time |
| --- | --- | --- | --- |
| Regime detector | SMA short | 48 x 5m | 4h |
| Regime detector | SMA long | 192 x 5m | 16h |
| Regime detector | ATR baseline | 14 ATR + 288 ATR SMA baseline, effectively 301 x 5m | 25.08h |
| Regime detector | ATR baseline + hysteresis | 301 x 5m + 3 bars | 25.33h |
| Pillar tactician | M15 min bars | 20 x 15m | 5h |
| Pillar operator | H4 min bars | 50 x 4h | 8.33d |
| Pillar strategist | D1 SMA/min bars | 200 x 1d | 200d |

Configured startup HTF backfill targets:

| HTF | Backfill candles | Natural warmup if no backfill | Startup target |
| --- | --- | --- | --- |
| M15 | 50 | 12.5h for 50 bars, 5h minimum for readiness | 50 candles |
| H4 | 100 | 16.67d for 100 bars, 8.33d minimum for readiness | 100 candles |
| D1 | 200 | 200d | 200 candles |

Operational conclusion:

- For the current regime detector, the hard bar-only warmup is about 25.33 hours.
- For a true Quadratic runtime without startup HTF hydration, the real wall-clock warmup becomes dominated by D1 and stretches to about 200 days.
- The pillar backfill config exists precisely because natural Quadratic warmup is otherwise operationally unacceptable.

### 5.2 FE microstructure warmup

FE `warmup.full_ready` is not purely bar-time based. It depends on tick/order-book/trade activity and on configured readiness keys.

Current declared FE readiness keys include:

- `obi`
- `tfi`
- `delta_price`
- `depth_imbalance`
- `liquidity_kappa`
- `absorption`
- `ema_bias`
- `volume_spike`
- `volatility_state`
- `macro_sync`
- `macro_resid`
- `spread_bps`
- `large_trade_imbalance`
- `volume_zscore`

Important current fact:

- HTF pillar readiness is not part of this registry.

Therefore:

- FE `full_ready=true` does not mean Quadratic-ready.
- FE `full_ready` mainly certifies microstructure/tick-derived readiness plus local sanity gates.

### 5.3 Warmup gate semantics

`FeatureEngineering` emits `CMD:PROCESS_STRATEGY` only if:

1. bar exists
2. `tf_sec >= 60`
3. `warmup` exists
4. `warmup.full_ready == true`, unless enforcement mode allows bypass
5. bar close timestamp exists
6. OHLCV fields exist

Current config:

- `domains.feature_engineering.warmup.enforcement_mode = fail_fast`

Result:

- FE is a fail-closed bar trigger for strategy processing.
- But the fail-closed contract currently protects microstructure readiness, not pillar readiness.

## 6. Bar-Only vs Microstructure Dependency Matrix

| Consumer | Depends on bars only | Depends on microstructure/tick stream | Notes |
| --- | --- | --- | --- |
| BarAggregator | no | yes | builds bars from incoming ticks |
| RegimeDetector | yes, 5m only | no direct tick dependency | processes only `basis_tf_sec=300` |
| FE base microstructure features | no | yes | OBI, TFI, spread, trade flow, macro sync |
| FE bar-volatility block | yes | indirectly via bars | ATR on per-timeframe bar close |
| FE pillars | yes | no direct tick dependency once bars exist | needs M15/H4/D1 bar histories |
| Aurora v2 scoring | mostly FE features + regime | yes via FE | active runtime path |
| Aurora Quadratic scoring | FE + pillar_sum + regime | yes via FE plus HTF bars | available but not active |
| StrategyGateway | no | no | uses emitted strategy signal + caches |
| ExecPos advanced stale cancel | yes, uses cached features at regime change | yes because features contain ATR/price context | mixed path |

Key architectural fact:

- Current system is not purely bar-driven even after T2B orchestration.
- It is hybrid: the trigger is bar-driven, but some decision safety context remains tick-side.

## 7. Quadratic Runtime State

### 7.1 What exists

Confirmed present in code:

- `QuadraticScoringKernel`
- pillar computation/hydration hooks in FE
- active config schema for pillars and backfill
- Aurora config loader routing to Quadratic when `decision.scoring_version == "quadratic"`
- tests that force Quadratic path and verify `pillar_sum` wiring

### 7.2 What is active now

Current active config in `config/aurora/strategies/aurora.yaml`:

- `decision.scoring_version: "v2"`

So current runtime status is:

- Quadratic code path available: YES
- Quadratic code path active by config: NO

### 7.3 What happens if Quadratic is enabled today

Observed code behavior:

1. FE will emit `CMD:PROCESS_STRATEGY` when FE `warmup.full_ready=true`.
2. FE adds pillar payload only if `pillar_sum` is available.
3. If `pillar_sum` is missing, FE still emits CMD if microstructure warmup passes.
4. `QuadraticScoringKernel.compute()` then defers with `defer_reason = "PILLAR_WARMUP"`.

Therefore the likely live behavior after simply flipping `scoring_version` to `quadratic` is:

- signals remain deferred until pillars are hydrated naturally or via missing startup backfill path

This is not a crash, but it is a readiness-contract mismatch.

### 7.4 Quadratic readiness gap

| Contract | Current source | Includes pillars? | Result |
| --- | --- | --- | --- |
| FE `warmup.full_ready` | `compute_warmup_full_ready_for_symbol()` | no | may be true too early for Quadratic |
| Quadratic runtime readiness | presence of valid `pillar_sum` | yes | enforced later inside scoring kernel |

Severity: HIGH

Reason:

- system can appear warmed and still not be strategy-ready under Quadratic

## 8. Scoring -> Decision -> Order Lifecycle Trace

### 8.1 Current happy-path chain

1. Market data emits `EVT:MARKET_TICK_RECEIVED`.
2. `BarAggregator` emits `EVT:BAR_CLOSED` for configured timeframes.
3. FE ingests bar close, calculates features, emits `EVT:FEATURES_CALCULATED`.
4. FE emits `CMD:PROCESS_STRATEGY` when bar and warmup gates pass.
5. `AuroraHandler.on_process_strategy()` validates TF and bar identity.
6. Aurora scoring runs through v2 or Quadratic kernel depending on config.
7. Strategy emits `EVT:STRATEGY_SIGNAL_PRODUCED`.
8. `StrategyGateway.process_signal()` applies gate chain and emits `EVT:TRADE_INTENT_PROPOSED`.
9. `execution_position.intent_router` routes intent to `CMD:OPEN` or `CMD:CLOSE`.
10. `open_executor` or close flow validates order policy and places orders.
11. `EVT:ORDER_ACK` and `EVT:ORDER_FILL` update watchdog, state caches, portfolio/exposure flows.

### 8.2 Important side-channel dependency

Aurora decision trigger is `CMD:PROCESS_STRATEGY`, but Aurora still caches `price_motion` from `EVT:FEATURES_CALCULATED` because `CMD:PROCESS_STRATEGY` does not carry it.

That means decisioning is not purely single-message deterministic today.

It depends on:

- trigger channel: `CMD:PROCESS_STRATEGY`
- supplemental cached context: `EVT:FEATURES_CALCULATED`

Severity: MEDIUM

Reason:

- creates an ordering dependency between two upstream events for one logical decision cycle

### 8.3 Execution-layer warmup sensitivity

Execution layer is not passive after intent creation.

Observed execution consumers:

- `EVT:FEATURES_CALCULATED` updates latest feature snapshots
- `EVT:REGIME_DETECTED` can trigger stale pending-entry cancellation logic
- advanced stale cancel uses current feature context such as price and ATR

This means incomplete or delayed analytics state can affect not only entry creation, but also post-intent order survivability.

## 9. Backfill / Replay / Delta-Sync Audit

### 9.1 HTF pillar backfill

What exists:

- `feature_engineering/pillar_backfill.py`
- async Binance kline fetch via exchange adapter
- FE listener for `EVT:HTF_BARS_IMPORTED`

What was not found:

- startup caller that runs backfill service
- startup emitter of `EVT:HTF_BARS_IMPORTED`
- DR restore path for pillar state

Assessment: CONFIRMED wiring gap

### 9.2 Market data historical bootstrap

`MarketDataConnector` docstring promises a hybrid path involving REST and klines, but inspected runtime code starts:

- WebSocket subscription
- periodic aggregation emitter

No active historical bootstrap or kline-seed path was confirmed in the startup path.

Assessment: CONFIRMED code/doc drift, LIKELY cold-start history gap

### 9.3 Gap handling

`BarAggregator` detects temporal gaps and annotates bars with:

- `gap_bars_skipped`
- `is_gap_bar`

But no filler-bar reconstruction path was found in the active startup/runtime path.

Meaning:

- gaps are observed, not repaired

Assessment: CONFIRMED

### 9.4 Replay / recovery

Current DR strength:

- snapshots + WAL replay for position/execution state

Current DR weakness:

- no equivalent replay/hydration path found for regime buffers, FE warmup buffers, HTF pillars, or market-data historical state

Assessment: CONFIRMED partial recovery only

## 10. Confirmed Bugs / Dangerous Contradictions

| Severity | Finding | Status | Why it matters |
| --- | --- | --- | --- |
| HIGH | Active Aurora config is still `v2`, not `quadratic` | CONFIRMED | repo can look Phase-9-ready while live runtime is not actually using Quadratic |
| HIGH | Startup pillar backfill service exists but no startup caller was found | CONFIRMED | true Quadratic live startup is not bootstrapped |
| HIGH | FE `full_ready` excludes pillar readiness | CONFIRMED | FE can declare ready before Quadratic is ready |
| HIGH | Quadratic enabled without HTF hydration will defer on `PILLAR_WARMUP` | CONFIRMED from code, LIKELY in live | switching config alone can silently suppress signals |
| HIGH | Market-data startup shows no confirmed historical seed/delta-sync path | CONFIRMED ABSENCE | cold restart begins from live stream only |
| MEDIUM | `MarketDataConnector` docstring promises REST/klines path not seen in active startup code | CONFIRMED | operator expectations can be wrong |
| MEDIUM | Aurora decision path still depends on `EVT:FEATURES_CALCULATED` side cache for `price_motion` | CONFIRMED | two-channel ordering dependency inside one decision cycle |
| MEDIUM | DR restores execution state but not analytics warm state | CONFIRMED | restart consistency is asymmetric |
| MEDIUM | Gap detection exists without gap repair/filler bars | CONFIRMED | indicator continuity after outages is weaker than a seeded/repaired design |

## 11. Likely Failure Modes Before Next Live/Testnet Run

| Scenario | Expected behavior | Status |
| --- | --- | --- |
| Current Aurora v2 cold start | FE can become ready quickly; regime still needs about 25.33h natural 5m accumulation unless pre-seeded elsewhere | LIKELY |
| Flip to Quadratic without new wiring | FE starts processing, kernel keeps deferring on `PILLAR_WARMUP` until HTF bars accumulate or are hydrated | LIKELY |
| Restart after downtime | execution state restored better than analytics state; regime/pillars re-warm from live flow | LIKELY |
| Market interruption with bar gaps | gap metadata appears, but no auto-history repair found | LIKELY |

## 12. Tests: What They Prove and What They Do Not

Confirmed by tests:

- FE emits `CMD:PROCESS_STRATEGY` and blocks it on `full_ready=false`
- handlers subscribe to `CMD:PROCESS_STRATEGY`
- internal H4/D1 pillar timeframes can update state without emitting decision events
- forced Quadratic path can consume `pillar_sum` and produce a signal path in tests

Not confirmed by tests inspected here:

- full startup path from `main.py` that hydrates HTF pillars before first live decision
- real end-to-end startup backfill from Binance into `EVT:HTF_BARS_IMPORTED`
- restart restoration of FE/regime/pillar state
- real live/testnet run where current startup reaches true Quadratic-ready state immediately

## 13. Final Assessment

Current runtime maturity by area:

| Area | Assessment |
| --- | --- |
| Legacy Aurora v2 bar-driven runtime | operationally wired |
| 5m regime runtime | wired but naturally cold on fresh start unless externally seeded |
| FE microstructure warmup contract | wired and fail-closed |
| Quadratic kernel availability | implemented |
| Quadratic live activation | not active by config |
| Quadratic startup hydration | not fully wired |
| Execution lifecycle | strongly wired |
| Restart analytics continuity | incomplete |

Principal conclusion:

The system is not missing a Quadratic idea. It is missing a clean runtime contract that aligns:

1. startup hydration
2. readiness semantics
3. live activation config
4. recovery semantics

Until those four are aligned, the safe statement is:

- Phase 9 exists in code
- Phase 9 is not yet a fully bootstrapped active live runtime

## 14. Must-Fix Before Enabling Quadratic in Live/Testnet

1. Wire startup HTF backfill from runtime bootstrap and emit `EVT:HTF_BARS_IMPORTED` before Aurora signal generation.
2. Add explicit Quadratic readiness gate so FE/DM/operator telemetry cannot report ready while `pillar_sum` is absent.
3. Decide explicitly whether current target runtime is Aurora `v2` or Quadratic; do not leave both as implicit possibilities.
4. Add startup/restart strategy for regime and pillar state: history seed, snapshot restore, or explicit cold-start deny window.
5. Add one end-to-end integration test from startup bootstrap to first Quadratic-ready `CMD:PROCESS_STRATEGY` cycle.
