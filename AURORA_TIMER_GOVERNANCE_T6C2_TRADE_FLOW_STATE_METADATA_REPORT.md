AGENT_REPORT_V1

task: AURORA_TIMER_GOVERNANCE_T6C2_TRADE_FLOW_STATE_METADATA
verdict: METADATA_PROPAGATED_AND_VALIDATED
report_path: AURORA_TIMER_GOVERNANCE_T6C2_TRADE_FLOW_STATE_METADATA_REPORT.md

problem:
- T6A/T6C0 proved that bookTicker can remain fresh while trade/aggTrade flow goes silent.
- WebSocketAggregator(window_seconds=60) can emit quote-fresh zero-flow ticks before trade_silence_reconnect_sec forces reconnect.
- BarAggregator, FeatureEngineering, and DecisionMaking previously had no explicit trade-flow freshness metadata to distinguish valid zero flow from expired trade flow.

facts:
- source state calculation: WebSocketAggregator now emits trade_flow_state, trade_flow_age_ms, trade_flow_last_trade_ts_ms, and trade_flow_window_sec from last_trade_ts_ms versus the current quote/trade timestamp.
- source semantics: unknown means no trade timestamp is known; fresh means age <= window_seconds; degraded means age > window_seconds; stale means age > trade_silence_reconnect_sec when that threshold is supplied.
- payload fields added: flat optional fields named trade_flow_state, trade_flow_age_ms, trade_flow_last_trade_ts_ms, trade_flow_window_sec.
- schemas updated: schemas/market_tick_received_v1.json, schemas/bar_closed_v1.json, apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json, apps/reference/domains/feature_engineering/schemas/tick_features_calculated_v1.json, apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json, and FE Pydantic contracts.
- propagation path: WebSocketAggregator -> MarketDataWorker/MarketDataConnector -> MarketDataProxy -> BarAggregator -> FeatureEngineering feature payload -> CMD:PROCESS_STRATEGY -> DecisionMaking cached features.
- decision visibility: DMEventHandlers caches trade_flow_* fields in symbol_states[symbol]["features"], and ReadinessGates can receive them in the features event.

inferences:
- RegimeDetector receives EVT:FEATURES_CALCULATED payloads and would see the additive fields through the same event surface, but no RegimeDetector behavior was changed in T6C2.
- The existing degraded-context gate remains the future T6C3 control point; T6C2 only makes the required state observable.

assumptions:
- Flat top-level metadata is the least disruptive shape because existing market tick, bar, FE, and CMD payloads already use flat additive operational fields.
- Existing legacy schema fallback in market-data emitters is retained for backward compatibility with old runtime schema snapshots.

unknowns:
- live frequency of partial Binance trade-stream stalls.
- economic impact of stale trade-flow intervals.
- T6C3 strategy-aware degraded-entry behavior.

implementation:
- files changed:
  - apps/reference/domains/market_data/websocket_aggregator.py
  - apps/reference/domains/market_data/worker.py
  - apps/reference/domains/market_data/proxy.py
  - apps/reference/domains/market_data/market_data_connector.py
  - apps/reference/domains/market_data/bar_aggregator.py
  - apps/reference/domains/feature_engineering/bar_resampler.py
  - apps/reference/domains/feature_engineering/feature_engineering.py
  - apps/reference/domains/feature_engineering/contracts.py
  - schemas/market_tick_received_v1.json
  - schemas/bar_closed_v1.json
  - apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json
  - apps/reference/domains/feature_engineering/schemas/tick_features_calculated_v1.json
  - apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json
  - tests/domains/market_data/test_trade_flow_state_metadata.py
  - tests/domains/feature_engineering/test_trade_flow_state_propagation.py
  - tests/domains/decision_making/test_trade_flow_state_visibility.py
  - AURORA_TIMER_GOVERNANCE_T6C2_TRADE_FLOW_STATE_METADATA_REPORT.md
- metadata shape:
  - trade_flow_state: "unknown" | "fresh" | "degraded" | "stale"
  - trade_flow_age_ms: integer or null
  - trade_flow_last_trade_ts_ms: integer or null
  - trade_flow_window_sec: integer
- state semantics:
  - unknown: no trade has ever been observed for the symbol.
  - fresh: last trade age is within the active WebSocketAggregator window.
  - degraded: quote/tick can still be fresh, but last trade age exceeds the active trade-flow window.
  - stale: last trade age exceeds the configured trade_silence_reconnect_sec when that threshold is known to the aggregator.
- bar aggregation rule:
  - trade_flow_state uses worst observed state in the interval with severity fresh < degraded < stale < unknown.
  - trade_flow_age_ms uses max observed age in the interval.
  - trade_flow_last_trade_ts_ms uses latest known last-trade timestamp observed in the interval.
  - trade_flow_window_sec carries the observed window value.
- behavior changed:
  - metadata only; no reconnect, bar close, feature formula, decision, strategy, order, or execution behavior was intentionally changed.

tests_added:
- tests/domains/market_data/test_trade_flow_state_metadata.py
- tests/domains/feature_engineering/test_trade_flow_state_propagation.py
- tests/domains/decision_making/test_trade_flow_state_visibility.py

validation:
- pytest new tests:
  - .\.venv\Scripts\python.exe -m pytest tests/domains/market_data/test_trade_flow_state_metadata.py -q: 4 passed
  - .\.venv\Scripts\python.exe -m pytest tests/domains/feature_engineering/test_trade_flow_state_propagation.py -q: 2 passed
  - .\.venv\Scripts\python.exe -m pytest tests/domains/decision_making/test_trade_flow_state_visibility.py -q: 2 passed
- related market_data tests:
  - .\.venv\Scripts\python.exe -m pytest tests/domains/market_data -q: 62 passed
- related feature_engineering tests:
  - .\.venv\Scripts\python.exe -m pytest tests/domains/feature_engineering -q: 194 passed
- related decision_making tests:
  - .\.venv\Scripts\python.exe -m pytest tests/domains/decision_making -q: failed after 5 unrelated failures in existing strategy/arbitration tests; 261 passed, 4 skipped, 1 deselected before stop.
  - failing tests: test_arbitration_atomic_commit.py::test_precheck_does_not_mutate_window, test_arbitration_atomic_commit.py::test_failed_candidate_does_not_create_sticky_winner, test_arbitration_atomic_commit.py::test_deterministic_competing_strategy_behavior, test_aurora_scoring_truth_discriminator.py::test_live_decision_geometry_linear_admission_quadratic_sizing, test_aurora_tpsl_fallback_validation.py::test_aurora_success_path_keeps_regime_tpsl_as_final_owner.
- pytest command note:
  - plain pytest was not available on PATH in this shell, so validation used the repo venv via .\.venv\Scripts\python.exe -m pytest.
- git diff --stat:
  - plain git diff --stat is polluted by pre-existing unrelated worktree changes: 103 tracked files changed, 3503 insertions, 287 deletions.
  - scoped T6C2 tracked diff: 13 tracked files changed, 332 insertions, 5 deletions.
  - new T6C2 untracked files: three test files and this report.
- git diff --name-only:
  - plain git diff --name-only is polluted by pre-existing unrelated changes.
  - scoped tracked name-only includes the 13 T6C2 modified code/schema files listed above; git status also shows the three new T6C2 tests and this report as untracked.

runtime_behavior_change:
- metadata only; no decision gating.

config_changes:
- NONE

unproven:
- live frequency
- economic impact
- T6C3 gating behavior

next_recommended_package:
- T6C3 strategy-aware degraded-entry gate
