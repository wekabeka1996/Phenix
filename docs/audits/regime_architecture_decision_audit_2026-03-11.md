# REGIME ARCHITECTURE DECISION AUDIT

Date: 2026-03-11
Repository: Aurora / Phenix, branch Phenix_v2
Method: code-first and architecture-first audit only; no implementation; no claims without runtime evidence

## 1. Direct Answers

### 1. How is regime currently computed in runtime?

Current runtime regime is computed inside `apps/reference/domains/regime_detector/regime_detector.py` from `EVT:FEATURES_CALCULATED` with two hard filters:

1. only `FEATURES_CALCULATED` events are accepted
2. only events with `tf_sec == basis_tf_sec` are processed

Tick-level features (`tf_sec == 0`) are explicitly ignored, and non-basis timeframes are ignored.

The classifier is rule-based and priority ordered:

1. data-quality / staleness fail-closed gates
2. volatility regime from ATR / ATR baseline
3. mean-reversion regime from SMA spread plus price deviation around SMAs
4. trend regime from SMA short vs SMA long plus price position vs SMA short
5. uncertain-cutoff demotion
6. hysteresis smoothing and heartbeat emission

Inputs actually used by the detector are bar-derived or directly bar-carried fields:

- `price`
- `sma_short`
- `sma_long`
- `high`
- `low`
- prior close via internal per-symbol price buffer
- ATR buffers and ATR baseline buffers maintained inside the detector
- `tf_sec`
- event timestamp for freshness

The detector emits `EVT:REGIME_DETECTED` on every basis bar close as a heartbeat, with `changed`, `warmup`, `data_quality`, `raw_regime`, `stable_regime` telemetry.

### 2. Is the current regime global or per-symbol in practice?

The classifier itself is per-symbol in practice.

Evidence:

- the detector stores per-symbol price, ATR, hysteresis and last-emitted state in symbol-indexed dicts
- the emitted event payload contains `symbol`
- FeatureEngineering caches regime by `symbol` and injects that symbol-specific regime into `CMD:PROCESS_STRATEGY`
- AuroraHandler, MeanReversionHandler and MD_AMR all cache regime per symbol

However, one important downstream execution consumer still applies regime globally in effect:

- `execution_position.event_handlers.EPEventHandlers.on_regime_detected()` maps the label to a bucket and calls `exposure_guard.on_regime_changed(bucket)` without symbol scoping
- `ExposureGuard.on_regime_changed()` mutates one shared directional ratio for the whole execution domain

So the correct answer is:

- structural regime computation is per-symbol
- some downstream adaptation still behaves globally

### 3. Which features currently influence regime?

Only these features influence the live regime detector today:

- price
- SMA short
- SMA long
- high
- low
- previous close from detector-maintained buffers
- ATR and ATR baseline derived from bar true range history
- freshness / data-quality fields derived from event timestamp and config TTL

No FE microstructure features influence the current detector.

### 4. Are only bars used, or are any bar-derived / FE-derived / microstructure-derived signals already involved?

For core regime classification, only bars and bar-derived values are used.

More precisely:

- yes: bar-carried price, high, low, bar-close timing
- yes: detector-local bar-derived SMA / ATR / ATR baseline buffers
- no: OBI / TFI / spread / liquidity kappa / depth imbalance / macro_resid / large trade imbalance / funding / OI do not feed the live classifier
- no: tick-level or order-book microstructure does not feed the classifier

But those signals already exist elsewhere in the runtime:

- FeatureEngineering computes microstructure and macro/liquidity features on ticks
- FeatureEngineering snapshots a subset into `CMD:PROCESS_STRATEGY`
- strategies and objective/execution logic consume some of them

So the architecture is already split between:

- structural regime: bar-only
- execution/context features: hybrid and partially microstructure-aware

### 5. Which downstream consumers assume regime is global?

Confirmed global-or-shared semantics today:

1. `DecisionMaking` stores `_shared["latest_regime"]`
   - this is a last-writer-wins shared slot, not symbol-scoped
   - any consumer using `latest_regime` gets the most recently arrived symbol event, not an explicitly requested symbol

2. `DecisionMaking` stores `_shared["latest_warmup"]`
   - same last-writer-wins pattern

3. `ExposureGuard.on_regime_changed(bucket)` is global in effect
   - no symbol parameter
   - one symbol's regime event can change shared directional limits used by execution for all symbols

4. `IntentEmitter.handle_regime_flip()` is portfolio-position oriented rather than strategy-symbol regime-matrix oriented
   - it checks the symbol position, but the closure rules are hard-coded against trend labels and do not use per-strategy allowed-regime contracts

### 6. Which strategies would benefit from per-symbol regime?

Confirmed strong beneficiaries:

1. Aurora
   - uses per-symbol regime cache in handler state
   - feeds regime into scoring thresholds, objective inputs, TP/SL behavior and anti-churn regime inertia
   - instrument-level regime sizing already exists

2. Mean Reversion
   - maps regime per symbol into flat regime eligibility
   - its allowed-regime logic is per asset
   - liquidity gate is also per symbol

3. MD_AMR
   - maintains per-symbol regime, regime confidence and regime timestamp
   - entry allowlist is per asset
   - objective engine inputs include per-symbol regime age and confidence
   - TP/SL can be regime-based per symbol

The biggest marginal benefit is for Mean Reversion and MD_AMR because their entry logic is explicitly asset-scoped and regime-gated. Aurora already behaves per symbol for most strategy logic, so the gain there is more consistency than a category change.

### 7. Which risks appear if microstructure is injected directly into the core regime classifier?

The codebase already shows why this is risky:

1. clock-domain mismatch
   - the detector intentionally ignores `tf_sec == 0` to avoid double-clocking
   - FE microstructure is tick-driven while regime is basis-bar driven
   - merging them into one classifier would reintroduce clock coupling the detector explicitly rejects

2. stale / unhealthy book noise
   - FE has explicit spread health gates, book health checks, missing-bid/ask handling and not-ready reasons
   - that is acceptable for execution gating, but too fragile for a structural classifier that is supposed to be stable

3. warmup explosion and availability coupling
   - FE `full_ready` depends on many microstructure readiness keys
   - coupling structural regime to those keys would make regime availability depend on book/trade readiness, not just bar history

4. regime churn
   - microstructure changes faster than structural market state
   - feeding spread, OBI or trade imbalance into the core classifier would increase label churn and fight detector hysteresis

5. execution feedback contamination
   - several micro features are execution-adjacent or venue-state-adjacent
   - if the same signals define both regime and execution response, regime becomes partially a reflection of order-book mechanics instead of market structure

6. cross-symbol comparability loss
   - structural regime is currently comparable across symbols because it uses simple bar-derived measures
   - microstructure features are venue-, liquidity- and symbol-specific and would distort label comparability

### 8. What architecture is best?

Best target architecture: layered hybrid.

Recommended layers:

1. global backdrop regime
2. per-symbol structural regime
3. execution micro regime

But with one important constraint:

- only the global backdrop and per-symbol structural layers should stay bar-only
- the execution micro regime should not be part of the core structural classifier

This is not a theoretical preference. It matches the codebase split already present in runtime:

- core regime detector is bar-only and stable
- FE already computes fast microstructure context separately
- execution and objective logic already consume fast context separately

## 2. Current Regime Topology

### 2.1 Upstream production

Current topology is:

1. `market_data` produces ticks
2. `feature_engineering` computes tick-time features and bar-close payloads
3. `regime_detector` consumes `EVT:FEATURES_CALCULATED` only for `basis_tf_sec`
4. `regime_detector` emits per-symbol `EVT:REGIME_DETECTED`
5. `feature_engineering` caches the last regime per symbol
6. `feature_engineering` injects that regime snapshot into `CMD:PROCESS_STRATEGY`
7. strategy handlers consume either injected regime, direct regime events, or both

### 2.2 Current structural inputs

The live detector does not call back into FeatureEngineering for advanced FE outputs. It only consumes values already present in the features payload or reconstructs its own bar-derived state.

Structural inputs now are:

- price
- SMA short
- SMA long
- OHLC-derived true range
- ATR
- ATR baseline
- freshness / stale gate
- hysteresis / slope gate state

### 2.3 Existing FE feature surface not used by core regime

FeatureEngineering already computes many signals outside the detector:

- `obi`
- `tfi`
- `delta_price`
- `liquidity_kappa`
- `ema_bias`
- `volume_spike`
- `volatility_state`
- `depth_imbalance`
- `macro_sync`
- `macro_resid`
- `absorption`
- `volume_zscore`
- `large_trade_imbalance`
- `spread_bps`
- `funding_rate_normalized`
- `oi_delta_pct`

At bar close, FE also injects nested snapshots into `CMD:PROCESS_STRATEGY`:

- `features.volatility.{bar_range, bar_body, true_range, atr_14, range_pct, atr_pct, atr_ready}`
- `features.liquidity.obi_close`

These are available downstream, but they do not drive the live structural regime detector.

## 3. Current Consumers

### 3.1 FeatureEngineering consumer

FeatureEngineering listens to `EVT:REGIME_DETECTED`, caches regime per symbol, and injects it into `CMD:PROCESS_STRATEGY`. This makes regime part of the strategy command envelope, not just a side-channel event.

### 3.2 DecisionMaking core consumers

DecisionMaking does all of the following:

- stores shared `latest_regime`
- stores per-symbol regimes in `_per_symbol_regimes`
- uses regime warmup in `ReadinessGates`
- extracts per-symbol regime and confidence in `safety_gates`
- triggers `handle_regime_flip()` on every symbol regime update

This means regime is both:

- a readiness contract
- a directional sanity input
- a flip / close trigger

### 3.3 Aurora strategy consumer

AuroraHandler caches, per symbol:

- regime
- raw regime event
- regime confidence
- regime timestamp
- heartbeat timestamp
- effective regime after anti-churn inertia

Aurora decision flow then uses regime for:

- scoring threshold multipliers
- kill-switch style blocked-regime checks
- inception logic against raw vs stable regime
- objective engine inputs
- TP/SL behavior via effective regime
- regime liveness blocking

### 3.4 Mean Reversion consumer

MeanReversionHandler listens to `EVT:REGIME_DETECTED`, caches regime per symbol and passes it into the per-symbol strategy.

Mean Reversion regime semantics are not the same as Aurora regime semantics. It maps structural regime into flat-trading eligibility via `feature_engineering/regime_mapping.py`:

- `LOW_VOLATILITY -> FLAT_LOW`
- `MEAN_REVERSION + atr_pct -> FLAT_LOW / FLAT_NORMAL / FLAT_HIGH`
- `TREND_UP / TREND_DOWN / HIGH_VOLATILITY / UNCERTAIN -> no flat mapping`

This is a clean example of structural regime being transformed into a strategy-specific regime view.

### 3.5 MD_AMR consumer

MD_AMR keeps per-symbol:

- regime label
- regime timestamp
- regime confidence

It uses regime for:

- entry allowlist checks
- objective engine inputs
- regime-based TP/SL selection

### 3.6 StrategyGateway consumer

StrategyGateway reads regime from strategy scoring and can apply Aurora per-symbol regime sizing multipliers before intent sizing.

### 3.7 Execution / risk consumers

ExecutionPosition consumes regime in two distinct ways:

1. exposure adaptation
   - maps regime label to an execution bucket
   - updates ExposureGuard directional ratio

2. stale pending entry cancellation
   - on regime change, can cancel pending entries immediately
   - advanced mode further requires symbol, age and price-drift checks using cached features

### 3.8 Objective engine consumer

ObjectiveEngineRuntime listens to `EVT:REGIME_DETECTED` and stores regime per symbol in its snapshot registry for later realized-quality evaluation.

## 4. Failure Modes Of Current Global Logic

### 4.1 Global exposure adaptation from per-symbol regime events

This is the most important architecture mismatch.

The runtime computes regime per symbol, but `ExposureGuard.on_regime_changed(bucket)` mutates one shared directional ratio without symbol scoping. One symbol changing from calm to volatile can tighten or loosen execution limits that are then reused for other symbols.

This is genuine global behavior, not just a naming issue.

### 4.2 Shared `latest_regime` and `latest_warmup` are last-writer-wins

DecisionMaking stores one shared latest regime and one shared latest warmup in `_shared`. In a multi-symbol runtime this is not a reliable structural context object; it is only the most recent event that happened to arrive.

That creates an attractive nuisance for future code and weakens architecture clarity.

### 4.3 Regime flip enforcement is label-misaligned

`IntentEmitter.handle_regime_flip()` hard-codes:

- `BULL_TREND`
- `BEAR_TREND`
- `UNCERTAIN`

But the live detector emits:

- `TREND_UP`
- `TREND_DOWN`
- `MEAN_REVERSION`
- `HIGH_VOLATILITY`
- `LOW_VOLATILITY`
- `UNCERTAIN`

As a result, immediate trend-based closure on regime flip is not aligned with the current emitted vocabulary. Only the `UNCERTAIN` close path is clearly reachable from current detector labels.

### 4.4 Global execution adaptation hides symbol-specific structure

Mean Reversion and MD_AMR are explicitly per-symbol and regime-gated, but execution exposure adaptation is bucket-global. This mixes symbol-specific structure with system-level control.

### 4.5 Structural regime and execution urgency are conflated at the edge

Pending-entry stale cancel can be triggered by regime change and then refined using drift and ATR checks. That is good execution behavior, but it means execution urgency already depends on more than structural regime. Without explicit architecture separation, the system can drift toward using one label for too many jobs.

## 5. Pros / Cons Of Per-Symbol Structural Regime

### Pros

1. matches current detector implementation and state layout
2. matches strategy contracts already present in Aurora, Mean Reversion and MD_AMR
3. avoids cross-symbol leakage from one asset regime into another asset's signal policy
4. preserves symbol-specific ATR, SMA and warmup behavior
5. scales naturally to asset-level allowlists, regime sizing and TP/SL

### Cons

1. execution/risk layers must stop assuming one market-wide directional bucket
2. portfolio-level overlays need an additional layer if the system wants a market-wide backdrop
3. observability and reporting need to explicitly separate symbol regime from any market backdrop

## 6. Pros / Cons Of Microstructure-Aware Regime

### Pros

1. useful for execution timing
2. useful for maker/taker choice, cancel/replace aggressiveness and spread-aware gating
3. useful for detecting temporary venue-state deterioration that bars alone cannot see

### Cons

1. unstable as a structural state definition
2. strongly venue- and liquidity-dependent
3. higher readiness burden and more stale-data failure points
4. conflicts with the detector's deliberate bar-only clock discipline
5. risks label churn, overreaction and cross-layer feedback loops

Conclusion:

- microstructure-aware regime is valuable only as an execution layer
- it should not replace or directly pollute the core structural classifier

## 7. Recommended Layered Regime Architecture

### 7.1 Layer A: Global Backdrop Regime

Purpose:

- portfolio-wide market backdrop
- cross-symbol leverage / gross-exposure posture
- optional overlay for enabling or attenuating strategy families

Should stay bar-only.

Allowed inputs:

- HTF bar-derived market breadth / anchor bars / BTC backdrop bars
- slow macro state sampled on bar boundaries
- optional funding / OI only if explicitly lagged and sampled at bar close

Should not use tick/book microstructure.

### 7.2 Layer B: Per-Symbol Structural Regime

Purpose:

- symbol-level market structure used by strategies
- allowlists, threshold multipliers, structural TP/SL profiles, objective context

Should stay bar-only.

Allowed inputs:

- current detector inputs
- additional bar-derived realized-vol / slope / percentile context if later needed
- FE bar-derived snapshots if sampled at bar close and causally stable

Should not use:

- spread
- OBI
- TFI
- large-trade imbalance
- fast book-health signals

### 7.3 Layer C: Execution Micro Regime

Purpose:

- short-horizon execution state
- cancel/replace aggressiveness
- stale-entry handling
- maker-vs-taker posture
- temporary throttling under spread or order-book stress

This layer should not be bar-only.

It should be allowed to consume:

- spread_bps
- book health
- OBI / OBI-close
- trade-flow imbalance
- large-trade imbalance
- execution behavior counters such as cancel/replace bursts

But it must stay separate from structural regime labels.

### 7.4 Architectural decision

Recommended target:

- keep structural regime bar-only
- make it explicitly per-symbol
- add a separate execution micro regime
- optionally add a global bar-only backdrop above them

Smallest acceptable target subset if scope must stay tight:

1. per-symbol structural regime
2. execution micro regime

The global backdrop is recommended, but the immediate architectural repair is the separation between per-symbol structure and execution microstate.

## 8. What Should Stay Bar-Only And What Should Not

### Should stay bar-only

1. core structural regime classification
2. global market backdrop regime
3. structural strategy allowlists
4. regime confidence and hysteresis
5. structural TP/SL policy families

### Should not stay bar-only

1. stale pending-entry cancellation refinement
2. maker/taker routing posture
3. quote aggressiveness / cancel-replace logic
4. spread health blocks
5. short-horizon execution throttling

## 9. Migration Path

### Phase 1. Freeze structural semantics

Keep the current detector as the SSOT structural regime producer.

Immediate architecture actions:

1. treat current `EVT:REGIME_DETECTED` as structural regime, not generic all-purpose regime
2. stop using shared `latest_regime` for decision-critical logic
3. audit and remove any remaining global assumptions from execution/risk layers

### Phase 2. Repair global leakage

1. replace global exposure adaptation from per-symbol events with one of:
   - explicit global backdrop input, or
   - symbol-scoped exposure adaptation, or
   - both
2. align regime-flip enforcement with live detector labels and strategy contracts

### Phase 3. Introduce explicit execution micro regime

Build a separate execution-state classifier from already existing FE and execution signals:

- spread_bps
- book health
- liquidity snapshots
- large trade imbalance
- cancel/replace behavior

Use it only in:

- order placement aggressiveness
- stale-order cancellation
- execution throttling
- maker-only fallbacks

Do not feed it back into the structural regime detector.

### Phase 4. Add global backdrop only if needed

If the system needs market-wide posture control, add a separate backdrop regime computed from HTF bar-derived anchors and slow macro context. Use that for:

- portfolio gross-exposure posture
- family-level attenuation
- system-wide stress overlays

Do not let a single symbol structural regime mutate that backdrop.

### Phase 5. Tighten event naming and contracts

The runtime will become clearer if contracts distinguish:

- structural regime
- global backdrop regime
- execution micro regime

Even if implementation stays additive, the contract names should stop implying one monolithic regime concept.

## 10. Final Decision

Current live system already proves the right separation boundary:

- structural market state is bar-derived and per symbol
- execution context is faster and noisier and already lives outside the detector

Therefore the recommended target architecture is:

1. per-symbol structural regime as the main strategy regime
2. separate execution micro regime for order handling and stale-cancel logic
3. optional global bar-only backdrop regime for portfolio overlays

The system should not evolve toward one microstructure-aware core regime classifier.

It should evolve toward explicit layered regimes with different clocks and different responsibilities.
