# Runtime Bar Consumption Audit 2026-03-11

## Scope

Read-only audit of active runtime bar consumption semantics across:

- live startup
- steady-state live operation
- restart / DR / snapshot / WAL replay
- warmup / replay hooks that can affect bar-derived state
- gap, duplicate, out-of-order, stale, and partial-bar conditions

Evidence was taken from active code, not from prose docs. Primary files inspected:

- apps/reference/main.py
- vfoundation/dr/dr_loader.py
- apps/reference/domains/market_data/bar_aggregator.py
- apps/reference/domains/market_data/market_data_connector.py
- apps/reference/domains/market_data/proxy.py
- apps/reference/domains/feature_engineering/feature_engineering.py
- apps/reference/domains/regime_detector/regime_detector.py
- apps/reference/domains/decision_making/aurora_handler.py
- apps/reference/domains/decision_making/aurora_scoring_helpers.py
- apps/reference/domains/decision_making/mean_reversion_handler.py
- apps/reference/domains/decision_making/event_handlers.py
- apps/reference/domains/decision_making/readiness_gates.py
- apps/reference/domains/decision_making/md_amr_handler.py
- apps/reference/domains/execution_position/event_handlers.py
- apps/reference/domains/execution_position/fsm.py
- tests/domains/market_data/test_bar_aggregator_ssot.py
- tests/integration/test_obs03_wal_bar_ssot.py
- tests/domains/regime_detector/test_reg_fix_01_bar_only.py
- tests/integration/test_bar_ssot_wiring.py
- tests/integration/test_fe_emits_cmd_process_strategy.py
- tests/domains/test_dm_bar_ttl_preemit.py
- tests/sim/test_bar_ttl_freshness.py

## Executive Verdict

The active runtime has a clear single-process bar SSOT, but it is not restart-safe as an analytics pipeline.

- Bar production itself is deterministic inside one process as long as tick arrival order is monotonic per symbol and timeframe. Evidence: BarAggregator._process_tick_for_tf in apps/reference/domains/market_data/bar_aggregator.py drops any tick where ts_ms <= last_ts for the key, aligns bar starts with floor(timeframe), and closes bars at boundary minus 1 ms.
- Downstream consumption is only partially deterministic because some strategy behavior still depends on cached side-channel feature state rather than the bar-trigger command payload alone. Evidence: Aurora scoring helper fallback in apps/reference/domains/decision_making/aurora_scoring_helpers.py reads cached price_motion from EVT:FEATURES_CALCULATED state when CMD:PROCESS_STRATEGY does not carry it.
- Restart recovery is position-safe to a degree, but not bar-state-safe or feature-state-safe. Evidence: apps/reference/main.py replays WAL only into position_tracking, and vfoundation/dr/dr_loader.py replays only TRADE_EXECUTED and ACCOUNT_UPDATE_RECEIVED. BAR_CLOSED WAL records exist but are not replayed into FeatureEngineering, RegimeDetector, or DecisionMaking caches.
- Live and replay/warmup semantics are not proven identical. The live producer path is EVT:BAR_CLOSED from BarAggregator. Warmup-specific gating exists in FeatureEngineering via _warmup_bar, but active producer code for that flag was not found in runtime search. HTF hydration hooks exist, but startup wiring does not invoke them.

Bottom line:

- deterministic for single-process live bar formation: mostly yes
- deterministic for full decision behavior across cold restart: no
- restart-safe for positions and fills: partially yes
- restart-safe for analytics, warmup context, and bar-derived strategy state: no

## End-to-End Bar Lifecycle

### 1. Live tick ingress

Market data enters through the market data domain and is adapted into tick payloads consumed by the bar SSOT.

- Evidence: apps/reference/domains/market_data/bar_aggregator.py, BarAggregator.on_market_tick
- Accepted timestamp fields: ts, ts_ms, timestamp
- Accepted price fields: mid, bid/ask average fallback, then price, last_price, close

This means live bar formation already depends on adapter normalization before any bar exists.

### 2. Bar construction SSOT

BarAggregator is the only confirmed active runtime bar builder.

- Evidence: apps/reference/domains/market_data/bar_aggregator.py, BarAggregator._process_tick_for_tf
- Configured active timeframes come from config/aurora/trading.yaml: 180, 300, 900, 14400, 86400

Confirmed semantics:

- First tick for a key creates the current bar with start_ts_ms aligned by floor(ts_ms / tf_ms) * tf_ms.
- Current bar closes only when a later tick arrives with ts_ms >= current.start_ts_ms + tf_ms.
- Closed bar end_ts_ms is forced to boundary - 1 ms, not the triggering tick timestamp.
- The tick that triggers close belongs to the next bar.
- No filler bars are created for missing intervals.
- On a gap, the next created bar is marked with gap_bars_skipped and is_gap_bar.
- Any tick with ts_ms <= last_ts for the same symbol and timeframe is dropped.

The tests in tests/domains/market_data/test_bar_aggregator_ssot.py confirm duplicate timestamp drops, out-of-order drops, boundary close behavior, and gap flags.

### 3. BAR_CLOSED emission and persistence

When a bar closes, the runtime emits EVT:BAR_CLOSED and appends a WAL record.

- Evidence: apps/reference/domains/market_data/bar_aggregator.py, BarAggregator._emit_bar_closed
- Event payload fields: symbol, ts_ms, tf_sec, bar_close_ts, bar
- WAL rid format: bar:{symbol}:{timeframe_sec}:{end_ts_ms}

Important timestamp detail:

- bar_close_ts in the event payload is emitted from the bar identity used by the aggregator, not from wall-clock time.
- However, schema tests in tests/vfoundation/core/test_schema_validator.py use end_ts_ms equal to bar_close_ts, while the active aggregator closes bars at boundary - 1 ms. That is a contract ambiguity, not a runtime crash, but it shows two notions of close timestamp exist in the codebase.

The WAL contract is covered by tests/integration/test_obs03_wal_bar_ssot.py.

### 4. FeatureEngineering consumption

FeatureEngineering is the first major bar consumer.

- Evidence: apps/reference/domains/feature_engineering/feature_engineering.py
- Event listeners: EVT:MARKET_TICK_RECEIVED, EVT:BAR_CLOSED, EVT:HTF_BARS_IMPORTED, EVT:ANCHOR_UPDATED, EVT:REGIME_DETECTED
- Primary bar path: FeatureEngineering.on_bar_closed

Confirmed semantics:

- Bar payload is stored as last_bar[(symbol, tf_sec)].
- A synthetic current tick is built from the bar close plus cached latest side data.
- A synthetic previous tick is created at bar_ts - 1 to avoid zero or negative dt in feature calculations.
- Pillar timeframes can be processed as internal-only updates without emitting strategy commands.
- CMD:PROCESS_STRATEGY is emitted only when tf_sec >= 60, warmup exists, warmup passes policy, _warmup_bar is not true, is_candidate is not false, and bar_close_ts plus OHLCV are present.

Critical audit note:

- The only active runtime reference to _warmup_bar found by repo search is the skip gate inside FeatureEngineering._calculate_and_emit_features_for_tf.
- No active producer for _warmup_bar was found in the searched runtime code.
- Therefore warmup-bar semantics exist as a consumer-side branch, but are not proven to be exercised by the active startup path.

### 5. RegimeDetector consumption

RegimeDetector is bar-only by design in active runtime.

- Evidence: apps/reference/domains/regime_detector/regime_detector.py, RegimeDetector.handle_event

Confirmed semantics:

- It subscribes to EVT:FEATURES_CALCULATED, not to EVT:BAR_CLOSED directly.
- It ignores tick-level feature events where tf_sec <= 0.
- It ignores all feature events outside basis_tf_sec.
- Active basis_tf_sec is 300 from config/aurora/regime.yaml.

This makes regime detection dependent on FeatureEngineering's basis-timeframe feature emission, not on raw bars.

### 6. DecisionMaking and strategy consumption

Decision-making logic does not directly trade off EVT:BAR_CLOSED. It trades off a later command layer.

- Evidence: apps/reference/domains/decision_making/mean_reversion_handler.py, apps/reference/domains/decision_making/aurora_handler.py

Confirmed semantics:

- MeanReversionHandler primary trigger is CMD:PROCESS_STRATEGY.
- MeanReversionHandler keeps EVT:BAR_CLOSED as a data-only compatibility hook and currently no-ops there.
- AuroraHandler primary trigger is CMD:PROCESS_STRATEGY.
- Both handlers reject missing bar_close_ts and wrong timeframe.

DecisionMaking shared-state layer:

- Evidence: apps/reference/domains/decision_making/event_handlers.py
- Accepted FEATURES_CALCULATED payloads are cached in symbol_states[symbol]["features"] and stamped with _received_ts.
- Tick-level features are explicitly ignored.

Freshness layer:

- Evidence: apps/reference/domains/decision_making/readiness_gates.py
- features_ready uses bar-aware TTL modes and an ancient-bar guard.
- In received mode it still compares received time with bar age to reject stale bars.

Determinism caveat:

- Aurora scoring can fall back to cached price_motion from EVT:FEATURES_CALCULATED if the command payload lacks it.
- Evidence: apps/reference/domains/decision_making/aurora_scoring_helpers.py
- This means the same CMD:PROCESS_STRATEGY payload can score differently depending on whether prior FEATURES_CALCULATED cache survived or was lost.

### 7. ExecutionPosition consumption

ExecutionPosition does not consume raw bars directly.

- Evidence: apps/reference/domains/execution_position/event_handlers.py and apps/reference/domains/execution_position/fsm.py

Confirmed semantics:

- It caches the latest FEATURES_CALCULATED payload per symbol.
- It consumes REGIME_DETECTED for exposure changes and pending-entry cancellation logic.
- It does not subscribe directly to BAR_CLOSED.

This domain is therefore exposed to stale or missing bar-derived context indirectly through feature and regime caches.

## Domain Consumption Matrix

| Domain | Direct input | Direct bar consumer | Duplicate protection | Missing/gap handling | Restart-safe state | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| market_data / BarAggregator | normalized ticks | yes | strong for ts_ms <= last_ts per key | gap flags only, no filler repair | no confirmed bar-state restore | Single-process bar SSOT |
| FeatureEngineering | BAR_CLOSED + ticks + HTF hooks | yes | tick dt degrade path, but depends on upstream bar uniqueness | accepts gap bars as marked bars; no repair path confirmed | no | also keeps side caches such as last_bar and tick context |
| RegimeDetector | FEATURES_CALCULATED | no, indirect | relies on FE event stream | basis-tf only; no independent gap repair | no | bar-only by tf gate, not by direct bar subscription |
| DecisionMaking shared state | FEATURES_CALCULATED | no, indirect | ignores tick-level features; no independent bar dedup | TTL gate can reject stale bars | no | cache survives only in memory |
| AuroraHandler | CMD:PROCESS_STRATEGY | indirect | command-level gating only | rejects missing bar_close_ts, wrong tf | no | may use cached price_motion side channel |
| MeanReversionHandler | CMD:PROCESS_STRATEGY | indirect | command-level gating only | rejects missing bar_close_ts, wrong tf | no | EVT:BAR_CLOSED hook is data-only no-op |
| md_amr_handler | CMD:PROCESS_STRATEGY plus event ts extraction | indirect | explicit duplicate live-event suppression | depends on extracted event/bar ts | no | only audited as a specialized duplicate-suppression path |
| execution_position | FEATURES_CALCULATED + REGIME_DETECTED | no, indirect | none at bar layer | no gap repair; reacts to latest derived state | partial only for position state | feature/regime caches are not restored |

## Confirmed Current-State Invariants

### Duplicate bars

The active runtime prevents duplicate bars at the producer only as a consequence of duplicate/out-of-order tick dropping.

- Evidence: BarAggregator._process_tick_for_tf in apps/reference/domains/market_data/bar_aggregator.py
- If the same tick timestamp arrives twice for a key, the second is dropped before it can mutate the bar.

There is no general downstream BAR_CLOSED replay dedup pipeline in active startup recovery.

### Skipped bars

Skipped intervals are represented only as metadata on the next created bar.

- Evidence: gap_bars_skipped and is_gap_bar in BarAggregator._process_tick_for_tf
- No backfill or synthetic filler emission was found in the active startup wiring.

Therefore consumers can observe a valid closed bar stream that silently jumps over missing intervals except for gap metadata on the next bar.

### Out-of-order bars

Out-of-order tick ingress is fail-closed at the aggregator.

- Evidence: ts_ms <= last_ts drop in BarAggregator._process_tick_for_tf

However, if a stale bar-derived feature event is already in memory, downstream domains can still act on stale analytics until a fresher bar-derived event replaces it or a TTL gate blocks it.

### Partial bars

The runtime strategy path is intended to consume closed bars only.

- Evidence: EVT:BAR_CLOSED originates only when a timeframe boundary is crossed in BarAggregator.
- FeatureEngineering emits CMD:PROCESS_STRATEGY only after bar_close_ts extraction from bar data.

This is a strong invariant for live bars, but it does not prove warmup/replay paths obey the same contract because no active _warmup_bar producer was found.

### Stale bars after restart

Cold restart resets analytics memory while leaving WAL BAR_CLOSED history on disk unused for replay.

- Evidence: apps/reference/main.py restores snapshot into position_tracking, replays WAL into position_tracking only, then hydrates execution_position from restored positions.
- Evidence: vfoundation/dr/dr_loader.py replays only TRADE_EXECUTED and ACCOUNT_UPDATE_RECEIVED.

Therefore stale or missing analytics state after restart is a confirmed behavior, not a hypothetical one.

## Confirmed Bugs and High-Confidence Risks

### Confirmed: analytics amnesia on restart

Confirmed bug.

- BAR_CLOSED is persisted to WAL.
- BAR_CLOSED is not replayed into FeatureEngineering, RegimeDetector, or DecisionMaking caches after restart.
- Snapshot hydration restores positions, not bar/feature/regime buffers.

Impact:

- After cold restart, open positions may be restored while analytics context, recent bars, feature freshness state, and regime state are empty or divergent.

### Confirmed: gap metadata without repair

Confirmed behavior with operational risk.

- Gap intervals only mark the next bar via gap_bars_skipped and is_gap_bar.
- No startup repair or synthetic bar fill was found in active live wiring.

Impact:

- Consumers may treat the first post-gap bar as just another bar unless they explicitly inspect gap metadata.

### Confirmed: command scoring is not fully self-contained

Confirmed determinism leak.

- Aurora scoring helper can read cached price_motion from FEATURES_CALCULATED state when the command payload does not carry it.

Impact:

- Strategy outcome can differ between identical bar-command sequences depending on prior feature cache availability.

### High confidence: live/replay parity is incomplete or dead-code-fragmented

High-confidence risk.

- FeatureEngineering contains _warmup_bar skip logic.
- HTF_BARS_IMPORTED and ANCHOR_UPDATED listeners exist.
- Repo search found the _warmup_bar reference only in the FE consumer gate and did not find an active live producer in the searched runtime code.
- Startup in apps/reference/main.py starts market_data and feature_engineering directly and does not show an HTF import or analytics-bar replay stage before live operation.

Impact:

- The codebase contains replay and hydration concepts, but active startup does not prove that warmup bars enter downstream consumers under the same semantics as live BAR_CLOSED bars.

### High confidence: BAR_CLOSED close-time contract is semantically ambiguous

High-confidence contract risk.

- Active aggregator sets closed bar end_ts_ms to boundary - 1 ms.
- Schema test fixtures model bar_close_ts and bar.end_ts_ms differently from some runtime expectations.
- Multiple consumers treat bar_close_ts, end_ts_ms, close_ts, and event ts as closely related but not formally identical.

Impact:

- This is survivable in current code, but it increases the risk of duplicate suppression mismatches, stale checks, and replay identity mismatches when new consumers are added.

## Determinism Assessment

### Single-process live runtime

Conditionally deterministic.

It is deterministic if all of the following hold:

- tick order per symbol and timeframe is monotonic
- the same normalized tick stream reaches BarAggregator
- process memory is not reset mid-sequence
- side-channel caches such as cached price_motion are populated in the same order

This is not pure event determinism, because strategy behavior can still depend on in-memory caches outside the command payload.

### Restart / replay determinism

Not deterministic enough to be called restart-safe.

Reasons:

- WAL replay does not reconstruct analytics state from BAR_CLOSED.
- Snapshot hydration restores execution-position state only.
- no confirmed active replay path rebuilds FeatureEngineering last_bar, RegimeDetector buffers, or DecisionMaking feature caches before live ticks resume.

## Must-Fix Before Relying On Startup Hydration

1. Add an explicit analytics restore path for bars, features, and regimes, not only positions.
   Evidence: apps/reference/main.py and vfoundation/dr/dr_loader.py currently restore only position-related state.

2. Decide and enforce one canonical bar identity contract.
   Evidence: active code mixes event ts, bar_close_ts, end_ts_ms, and close_ts across producer and consumers.

3. Remove or explicitly formalize Aurora's dependency on cached feature side channels during command scoring.
   Evidence: apps/reference/domains/decision_making/aurora_scoring_helpers.py.

4. Either wire real warmup/replay bar production into startup or remove dead consumer branches that imply it exists.
   Evidence: _warmup_bar gate exists in FeatureEngineering, but active producer wiring was not found.

5. Add explicit consumer handling for gap bars or perform gap repair upstream.
   Evidence: current runtime only flags gaps; it does not repair them.

6. Add restart tests that assert analytics parity, not only position parity.
   Evidence: current inspected tests cover aggregator SSOT, WAL BAR_CLOSED persistence, and regime bar-only gating, but no end-to-end restart rebuild of analytics state was confirmed.

## Evidence Summary By Key Question

### Are live bars produced from Binance ticks and routed consistently?

Yes, inside the active process.

- Producer SSOT is BarAggregator.
- BAR_CLOSED feeds FeatureEngineering.
- FeatureEngineering feeds RegimeDetector and strategy command emission.

### Can domains consume duplicated bars?

Producer-side duplicate tick timestamps are dropped, so duplicate live closed bars are strongly suppressed at source. There is no equivalent confirmed restart replay dedup for analytics state.

### Can domains consume skipped bars?

Yes, in the sense that they will consume the next post-gap bar while missing intervals are only represented as metadata.

### Can domains consume out-of-order bars?

Live out-of-order ticks are dropped before bar mutation. Post-restart stale analytics is still possible because analytics state is not rebuilt from WAL.

### Can domains consume partial bars?

Active live strategy flow is based on closed-bar emission, not partial bars. Warmup/replay parity for this invariant was not proven.

### Is runtime bar consumption deterministic and restart-safe?

No, not as a full system. It is reasonably deterministic for live single-process bar formation, but not restart-safe for analytics state and not fully self-contained at the strategy-scoring layer.
