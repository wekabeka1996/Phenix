# AURORA TIMER GOVERNANCE T6A MARKET DATA TIMER TRUTH REPORT

AGENT_REPORT_V1

## Scope

- Mode: audit_only
- Code changes: none
- Config changes: none
- Runtime target: current Aurora/Phenix live wiring under `config/aurora`
- SSOT note: `Copilot_Master_Roadmap.md` was not present in this workspace. This report is anchored on live repo code, typed config models, retained logs, and tests.

## Verdict

`MARKET_DATA_TIMER_SYSTEM_FRAGMENTED`

The current live stack has real reconnect controls and real downstream stale-bar guards, but it is not a single coherent timer system.

The main reasons are:

1. Active live reconnect timers exist only on the multiprocessing path (`MarketDataProxy` + `MarketDataWorker`).
2. The producer domain does not TTL-gate emitted market data.
3. Bar staleness is guarded downstream in DecisionMaking and RegimeDetector, not in market_data.
4. `tick_ttl_ms` is declared but is not an effective protection for the current live bar-driven decision path.
5. Trade-flow degradation can propagate as zero-volume / zero-count data before reconnect forces recovery.
6. `trading.market_data.macro_sync.*` and `domains.feature_engineering.macro_sync.*` form a split-brain config surface.
7. A behavior-impacting 60 second market-data timer exists as a hardcoded runtime constant, not as YAML SSOT.

## Executive Truth

### Q1. Which market-data timers are active runtime controls in the current live system?

Active in the current live path:

- `system.market_data.ws_heartbeat_sec`
- `system.market_data.ws_receive_timeout_sec`
- `system.market_data.trade_silence_reconnect_sec`
- `trading.market_data.poll_interval_sec`
- `system.market_data.proxy_queue_get_timeout_sec`
- `system.market_data.proxy_idle_sleep_sec`
- `trading.market_data.bar_aggregator.timeframes_sec`
- hidden runtime timer: `WebSocketAggregator(window_seconds=60)`

Active downstream stale-data guards:

- `system.market_data.bar_ttl_ms`
- `system.market_data.bar_event_age_mode` (DecisionMaking only)
- `domains.feature_engineering.macro_sync.ttl_ms`
- `domains.feature_engineering.macro_sync.max_gap_bins`
- `domains.feature_engineering.macro_sync.max_late_ms`
- `domains.feature_engineering.macro_sync.time_diff_threshold_ms`

### Q2. Which timers trigger reconnect?

Reconnect is directly controlled by:

- `system.market_data.ws_heartbeat_sec` via `aiohttp` WebSocket heartbeat
- `system.market_data.ws_receive_timeout_sec` via `ws.receive(timeout=...)`
- `system.market_data.trade_silence_reconnect_sec` via explicit trade-silence watchdog

### Q3. Which timers protect against stale data?

There is no producer-domain TTL gate in `market_data`.

Stale protection exists downstream:

- DecisionMaking rejects stale bar features with `bar_ttl_ms` and `bar_event_age_mode`, plus an ancient-bar safety guard.
- RegimeDetector rejects stale bar features with `bar_ttl_ms`, emits `UNCERTAIN`, and does not update buffers.
- FeatureEngineering macro-sync has its own anchor freshness and gap timers, but those only protect the `macro_sync` sub-feature, not all feature emission.

### Q4. Which surfaces are fragmented or orphaned?

Fragmented or partially orphaned surfaces:

- `system.market_data.tick_ttl_ms`
- `trading.market_data.macro_sync.*` except `anchors`
- mode-dependent behavior between `MarketDataWorker` and legacy `MarketDataConnector`
- hidden hardcoded `WebSocketAggregator(window_seconds=60)`
- silent/default fallback paths in `BarAggregator`, DecisionMaking, and RegimeDetector

### Q5. Can stale market data reach trading decisions?

Yes, partially.

More precisely:

- fully silent WebSocket transport is bounded by the receive-timeout reconnect path;
- ancient bar payloads are blocked downstream;
- but trade-flow freshness is not fail-closed at the producer boundary.

If `bookTicker` remains alive while the trade stream silently dies, the system can continue building bars from fresh quote/mid data while propagating zero or stale trade-flow fields into FeatureEngineering and onward into trading decisions before reconnect triggers.

That means stale price transport is mostly bounded, but stale trade-flow context is not fully bounded.

## Runtime Control Map

### Live wiring truth

- `bootstrap/domain_builder.py` selects `MarketDataProxy` when `trading.market_data.use_multiprocessing=true` and `MarketDataConnector` otherwise.
- Current `config/aurora/trading.yaml` sets `use_multiprocessing: true`.
- Retained runtime logs prove the live path is `MarketDataProxy` and that `BarAggregator` is enabled.

Observed retained runtime markers:

- `logs/aurora_core.log.9:9491` `Using MarketDataProxy (multiprocessing mode)`
- `logs/aurora_core.log.9:9496` `BarAggregator enabled`
- `logs/aurora_core.log.9:9648` `Queue consumer thread started`
- same pattern also appears in `logs/aurora_core.log.11`, `.16`, and `.19`

Therefore the current live truth must be read through:

- `apps/reference/domains/market_data/proxy.py`
- `apps/reference/domains/market_data/worker.py`
- `apps/reference/domains/market_data/bar_aggregator.py`
- downstream consumers in FeatureEngineering, RegimeDetector, and DecisionMaking

`apps/reference/domains/market_data/market_data_connector.py` is a real but currently inactive legacy path.

## Timer Truth Matrix

| Surface | Declared in | Live consumer(s) | Current live status | Classification | Proof | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `trading.market_data.use_multiprocessing` | `config/aurora/trading.yaml` | `bootstrap/domain_builder.py` | active | `LIVE_PATH_SWITCH` | `CFG+CODE+LOG` | Controls whether system timers are honored by worker path or bypassed by legacy connector path. |
| `system.market_data.ws_heartbeat_sec` | `config/aurora/system.yaml`, typed `SystemMarketDataConfig` | `market_data/worker.py` -> `ws_connect(... heartbeat=...)` | active | `ACTIVE_RUNTIME_RECONNECT_CONTROL` | `CFG+CODE+TEST` | Real transport keepalive on current live path. Ignored by legacy connector. |
| `system.market_data.ws_receive_timeout_sec` | same | `market_data/worker.py` -> `ws.receive(timeout=...)` | active | `ACTIVE_RUNTIME_RECONNECT_CONTROL` | `CFG+CODE+TEST` | On timeout worker logs warning and reconnects. No retained timeout warning found in scanned logs. |
| `system.market_data.trade_silence_reconnect_sec` | same | `market_data/worker.py` explicit trade-silence watchdog | active | `ACTIVE_RUNTIME_RECONNECT_CONTROL` | `CFG+CODE+TEST` | Protects against silent loss of trade stream while `bookTicker` still flows. No retained warning hit found in scanned logs. |
| `trading.market_data.poll_interval_sec` | `config/aurora/trading.yaml`, typed `MarketDataConfig` | `market_data/worker.py` periodic emit, `market_data_connector.py` periodic emit | active | `ACTIVE_EMIT_CADENCE_CONTROL` | `CFG+CODE+TEST` | Drives how often aggregated ticks are emitted downstream. Not a stale guard. |
| `system.market_data.proxy_queue_get_timeout_sec` | `config/aurora/system.yaml` | `market_data/proxy.py` -> `queue.get(timeout=...)` | active | `ACTIVE_INFRA_TIMER` | `CFG+CODE+TEST` | Controls IPC responsiveness and idle wake-up cadence. |
| `system.market_data.proxy_idle_sleep_sec` | same | `market_data/proxy.py` -> `time.sleep(...)` when queue empty | active | `ACTIVE_INFRA_TIMER` | `CFG+CODE+TEST` | CPU/latency tradeoff only. Not a stale-data guard. |
| `trading.market_data.bar_aggregator.timeframes_sec` | `config/aurora/trading.yaml` | `bootstrap/domain_builder.py`, `market_data/bar_aggregator.py` | active | `ACTIVE_BAR_EMIT_CADENCE` | `CFG+CODE+LOG` | Current live timeframes are `[180, 300, 900, 14400, 86400]`. |
| `system.market_data.bar_ttl_ms` | `config/aurora/system.yaml` | `decision_making/gates/readiness_gates.py`, `decision_making/gates/ttl_gate.py`, `regime_detector/regime_detector.py` | active downstream | `ACTIVE_DOWNSTREAM_STALE_GUARD` | `CFG+CODE+TEST` | Not enforced in market_data domain; enforced only after FE emits features. |
| `system.market_data.bar_event_age_mode` | same | `decision_making/gates/readiness_gates.py` | active downstream | `ACTIVE_DOWNSTREAM_STALE_GUARD_DM_ONLY` | `CFG+CODE+TEST` | DM supports `received` vs `close_ts`; RD does not consume this field, so semantics are fragmented. |
| `system.market_data.tick_ttl_ms` | same | `regime_detector/regime_detector.py` tick path only | partial / effectively dormant for live bar path | `DECLARED_PARTIAL_NOT_EFFECTIVE_FOR_CURRENT_PATH` | `CFG+CODE+TEST` | RD immediately ignores `tf_sec==0` events; DM tick path uses `domains.decision_making.features.ttl_sec`, not this field. |
| `trading.market_data.macro_sync.anchors` | `config/aurora/trading.yaml` | `market_data/worker.py`, `market_data_connector.py` | active | `ACTIVE_UPSTREAM_ANCHOR_SUBSCRIPTION` | `CFG+CODE+TEST` | This is the only clearly live-consumed part of `trading.market_data.macro_sync.*`. |
| `trading.market_data.macro_sync.enabled` | same | no consumer found in `apps/reference` | declared only | `DECLARED_NO_CONSUMER_FOUND` | `CFG+SEARCH` | Market-data worker subscribes anchors regardless; no active branch was found for this flag. |
| `trading.market_data.macro_sync.window` | same | no market_data consumer found | declared only | `DECLARED_NO_CONSUMER_FOUND` | `CFG+SEARCH` | Not the same contract as FE `macro_sync.window`. |
| `trading.market_data.macro_sync.emit_abs` | same | no consumer found | declared only | `DECLARED_NO_CONSUMER_FOUND` | `CFG+SEARCH` | Explicitly documented as deprecated / not implemented in typed model. |
| `trading.market_data.macro_sync.align_mode` | same | no market_data consumer found | declared only | `DECLARED_NO_CONSUMER_FOUND` | `CFG+SEARCH` | Real active align-mode consumer is FeatureEngineering config, not this surface. |
| `trading.market_data.macro_sync.min_buffer_size` | same | no market_data consumer found | declared only | `DECLARED_NO_CONSUMER_FOUND` | `CFG+SEARCH` | Real active consumer is FeatureEngineering config. |
| `trading.market_data.macro_sync.time_diff_threshold_ms` | same | no market_data consumer found | declared only | `DECLARED_NO_CONSUMER_FOUND` | `CFG+SEARCH` | Real active consumer is FeatureEngineering config. |
| `trading.market_data.macro_sync.anchor_update_from_ticks` | same | no market_data consumer found | declared only | `DECLARED_NO_CONSUMER_FOUND` | `CFG+SEARCH` | Conflicts with live FE value in `domains.yaml`; current worker path does not use it. |
| `domains.feature_engineering.macro_sync.ttl_ms` | `config/aurora/domains.yaml` | `feature_engineering/calculation_engine.py`, `macro_sync_resampler.py` | active downstream | `ACTIVE_SUBFEATURE_FRESHNESS_GUARD` | `CFG+CODE` | Protects macro-sync anchor freshness only; not a whole-market-data TTL gate. |
| `domains.feature_engineering.macro_sync.time_diff_threshold_ms` | same | `feature_engineering/calculation_engine.py` | active downstream | `ACTIVE_SUBFEATURE_ALIGNMENT_GUARD` | `CFG+CODE` | Caps tick-to-tick delta used for return calculation. |
| `domains.feature_engineering.macro_sync.max_gap_bins` | same | `feature_engineering/macro_sync_resampler.py` | active downstream | `ACTIVE_SUBFEATURE_GAP_GUARD` | `CFG+CODE` | Fails macro-sync readiness on anchor/bin gaps. |
| `domains.feature_engineering.macro_sync.max_late_ms` | same | `feature_engineering/macro_sync_resampler.py` | active downstream | `ACTIVE_SUBFEATURE_OOO_GUARD` | `CFG+CODE` | Controls late out-of-order tolerance for macro-sync bins. |
| hidden `WebSocketAggregator(window_seconds=60)` | hardcoded in `worker.py` and `market_data_connector.py` | `websocket_aggregator.py` | active | `HIDDEN_RUNTIME_TIMER_BEHAVIORAL` | `CODE+TEST` | After trade-window expiry, aggregator emits schema-valid zero-volume ticks. This is not YAML-governed. |
| hidden `_MARKET_DATA_TELEMETRY_HEARTBEAT_INTERVAL_SEC=5` | hardcoded in `worker.py` | worker heartbeat loop | active | `HIDDEN_RUNTIME_TIMER_OBSERVABILITY` | `CODE+TEST` | Observability-only timer; explicitly separate from `ws_heartbeat_sec`. |
| hidden worker summary interval `30.0` | hardcoded in `worker.py` | aggtrade summary logs | active | `HIDDEN_RUNTIME_TIMER_OBSERVABILITY` | `CODE` | Observability-only. |
| hidden proxy summary interval `30.0` | hardcoded in `proxy.py` | proxy trade summary logs | active | `HIDDEN_RUNTIME_TIMER_OBSERVABILITY` | `CODE+LOG` | Observability-only. |

## Stale-Data Truth Map

### 1. Producer domain (`market_data`)

Producer truth:

- There is no TTL enforcement in the market_data domain.
- `MarketDataWorker` and `MarketDataConnector` emit raw aggregated ticks.
- `BarAggregator` is a passive observer of emitted ticks.

Important nuance:

- `BarAggregator.on_market_tick()` prefers `mid`, then bid/ask average, then last price.
- That means bars can stay quote-fresh even if the trade stream is degraded, as long as `bookTicker` keeps arriving.

### 2. Trade-flow degradation path

`WebSocketAggregator.get_market_tick()` intentionally emits a zero-volume tick after the rolling trade window has fully cleaned up.

This creates a specific runtime sequence:

1. `bookTicker` keeps updating quote freshness.
2. trade events stop arriving.
3. after hidden `window_seconds=60`, aggregated tick output carries zero trade counts and zero trade volumes.
4. `trade_silence_reconnect_sec=120` has not fired yet.
5. bars and features can still continue downstream on fresh quote timestamps.

This is the core fragmentation finding.

### 3. FeatureEngineering

FeatureEngineering truth:

- It consumes market ticks and bar-close payloads.
- Bar features inherit `buy_volume`, `sell_volume`, `buy_count`, and `sell_count` from the bar/tick payload.
- `warmup.full_ready` is explicit and DecisionMaking is intended to fail closed until full readiness, but trade-flow zero values do not by themselves mark the system stale.
- `macro_sync_not_ready` can hold back `macro_sync`, but that is one feature component, not a global producer freshness gate.

### 4. RegimeDetector

RegimeDetector truth:

- It ignores `tf_sec==0` tick features.
- For bar features it uses `bar_ttl_ms`.
- On stale features it emits `UNCERTAIN` and does not update buffers.

This is a real downstream stale-data protection for bar-driven regime inference.

### 5. DecisionMaking

DecisionMaking truth:

- For bar features it uses `bar_ttl_ms` plus `bar_event_age_mode`.
- Even in `received` mode it still has an ancient-bar safety guard `max(tf_sec * 1000, bar_ttl_ms)`.
- For tick features it uses `domains.decision_making.features.ttl_sec`, not `system.market_data.tick_ttl_ms`.

This means stale ancient bars are blocked, but trade-flow freshness is not independently gated when quote timestamps remain fresh.

## Reconnect Truth Map

### Active reconnect chain on current live path

Current live reconnect protection is layered as follows:

1. `ws_heartbeat_sec` keeps the transport connection alive.
2. `ws_receive_timeout_sec` detects silent transport stalls.
3. `trade_silence_reconnect_sec` detects partial stream failure where text frames keep arriving but trades do not.

This is real and important. It is not dead code.

### Mode-dependent weakness

The same reconnect model does not exist on `MarketDataConnector`.

Legacy connector truth:

- uses `poll_interval_sec`
- uses `websocket_streams`
- does not wire `ws_heartbeat_sec`
- does not wire `ws_receive_timeout_sec`
- does not wire `trade_silence_reconnect_sec`

Therefore reconnect behavior is mode-dependent.

Current live config is safe only because `use_multiprocessing=true` and logs confirm that mode is active.

## SSOT Conflicts And Debt

### 1. Macro-sync split brain

There are two different config surfaces for macro-sync semantics:

- `trading.market_data.macro_sync.*`
- `domains.feature_engineering.macro_sync.*`

Truth after code inspection:

- market_data currently consumes only `trading.market_data.macro_sync.anchors`
- FeatureEngineering consumes the actual timing / freshness / alignment controls from `domains.feature_engineering.macro_sync.*`

This means most of `trading.market_data.macro_sync.*` is a declared surface without a live consumer.

### 2. Silent-default debt

Current live config is explicit, but runtime debt still exists:

- `BarAggregator.__init__()` defaults to `[180, 300]`
- `bootstrap/domain_builder.py` falls back to `[60, 300]` if `timeframes_sec` is empty
- DecisionMaking reads `bar_ttl_ms` / `bar_event_age_mode` through permissive `getattr(..., default)`
- RegimeDetector reads `bar_ttl_ms` through permissive `getattr(..., default)`

These defaults do not change current live behavior because the active YAML is explicit, but they are still timer-governance debt.

### 3. Adjacent dead config fields near this surface

Not timer-specific, but important nearby contract debt:

- `system.market_data.local_queue_maxsize`
- `system.market_data.emit_workers`

No active runtime consumer was found for either field in `apps/reference`.

## Risk Register

| ID | Risk | Severity | Why it matters |
| --- | --- | --- | --- |
| `T6A-R1` | stale trade-flow can reach FE/DM before reconnect | `HIGH` | Hidden `60s` zero-volume window plus configured `120s` reconnect threshold creates a partial-staleness corridor while quotes remain fresh. |
| `T6A-R2` | reconnect semantics are mode-dependent | `MEDIUM_HIGH` | Flipping `use_multiprocessing=false` would silently bypass active `ws_*` and trade-silence timers. |
| `T6A-R3` | hardcoded behavioral timer not in YAML SSOT | `MEDIUM_HIGH` | `WebSocketAggregator(window_seconds=60)` materially affects downstream data quality but is not operator-visible. |
| `T6A-R4` | `tick_ttl_ms` gives false confidence | `MEDIUM` | Declared as a stale-tick control, but it is not an effective protection for the current bar-driven live decision path. |
| `T6A-R5` | macro-sync config split brain | `MEDIUM` | Upstream and downstream macro-sync semantics live in different config trees, with partially orphaned declarations. |
| `T6A-R6` | retained logs do not prove reconnect/stale-reject branches fired recently | `MEDIUM` | Current evidence for reconnect branches is code + tests, not fresh retained runtime warnings. |
| `T6A-R7` | silent-default timer debt remains in code | `MEDIUM` | Today harmless with explicit YAML, but still violates strict timer governance expectations. |

## Observability Gaps

Observed in retained logs:

- active `MarketDataProxy` runtime
- active `BarAggregator`
- proxy queue consumer startup
- proxy trade summaries
- FeatureEngineering trade summaries
- RegimeDetector heartbeat-style `REGIME_AUDIT` bar-close emissions

Not observed in retained logs during this audit:

- `No WS messages ... reconnecting`
- `No trade event ... forcing reconnect`
- DecisionMaking `BAR_TOO_OLD` rejection lines
- explicit RegimeDetector stale-feature warnings in current retained slice

Conclusion:

The live path is runtime-observed, but the critical reconnect and stale-reject branches are only code/test-confirmed in the retained slice.

## Direct Answers

### Which timers are truly live runtime controls?

On the current live runtime:

- `ws_heartbeat_sec`
- `ws_receive_timeout_sec`
- `trade_silence_reconnect_sec`
- `poll_interval_sec`
- `proxy_queue_get_timeout_sec`
- `proxy_idle_sleep_sec`
- `bar_aggregator.timeframes_sec`
- hidden `window_seconds=60`

### Which timers are truly protecting against stale bars?

- `bar_ttl_ms`
- `bar_event_age_mode` (DecisionMaking only)
- ancient-bar guard in DecisionMaking
- `bar_ttl_ms` stale-feature gate in RegimeDetector

### Which timers are not truly protecting the current live decision path?

- `tick_ttl_ms`
- most of `trading.market_data.macro_sync.*`

### Can stale market data reach trading decisions?

Answer: `PARTIAL_YES`.

Ancient bars are blocked. Fully silent transport is bounded. But stale trade-flow can still propagate as zero-volume / zero-count market context while quote timestamps remain fresh enough for downstream bar and readiness gates.

## Recommended Follow-Up Packages

### T6B: Timer SSOT Reduction Pack

Goal:

- eliminate orphaned timer/config surfaces
- remove silent-default timer behavior
- reconcile `trading.market_data.macro_sync.*` vs `domains.feature_engineering.macro_sync.*`

Minimum scope:

- decide which macro-sync tree is canonical
- remove or wire orphaned fields
- make bar-aggregator timeframe behavior explicit only through YAML

### T6C: Trade-Flow Freshness Guard Pack

Goal:

- make trade-flow freshness explicit instead of implicit
- close the `60s zero-volume` to `120s reconnect` corridor

Minimum scope:

- promote hidden trade-window timer to explicit governance surface or policy constant with audit justification
- define whether zero-volume trade-flow should be `valid`, `degraded`, or `fail_closed`
- add a downstream guard or explicit penalty path for stale trade-flow if strategy quality depends on TFI / trade counts

### T6D: Reconnect And Stale Observability Pack

Goal:

- make runtime proofs cheap and unambiguous

Minimum scope:

- structured counters/logs for receive-timeout reconnects
- structured counters/logs for trade-silence reconnects
- structured logs when zero-volume window is entered/exited
- structured logs when DM or RD reject stale bars/features

### T6E: Legacy Path Parity Or Retirement Pack

Goal:

- prevent hidden mode-dependent timer semantics

Minimum scope:

- either teach `MarketDataConnector` to honor the same reconnect timers as the worker path
- or formally deprecate / remove the legacy single-process path from live-governed configs

## Final Assessment

The current live system is not timer-dead. It has real reconnect protection and real stale-bar protection.

But it is fragmented:

- producer freshness and downstream freshness are split across domains
- trade-flow freshness is weaker than quote/bar freshness
- some config surfaces are orphaned
- one important behavioral timer is hardcoded and hidden from SSOT

Operationally, this means the system is usable, but it is not yet governed as a single coherent market-data timer contract.
