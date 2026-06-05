AGENT_REPORT_V1

task: AURORA_TIMER_GOVERNANCE_T6C1_TRADE_FLOW_FRESHNESS_POLICY
verdict: POLICY_DESIGNED
report_path: AURORA_TIMER_GOVERNANCE_T6C1_TRADE_FLOW_FRESHNESS_POLICY_REPORT.md

problem:
- The confirmed T6C-0 corridor allows quote-fresh ticks and bars to continue while trade-flow fields degrade to zeros before trade_silence_reconnect_sec fires.
- The policy question is not whether the gap exists; it is how to contain it without breaking safe closes, risk reduction, reconciliation, or quote-driven decision paths.
- The repository already has a latent degraded-context gate in DecisionMaking, but it is disabled in current config and does not yet carry explicit trade-flow state.

facts:
- confirmed corridor: [config/aurora/system.yaml](config/aurora/system.yaml#L8-L13) sets bar_ttl_ms=10000, ws_receive_timeout_sec=60.0, and trade_silence_reconnect_sec=120.0; [apps/reference/domains/market_data/websocket_aggregator.py](apps/reference/domains/market_data/websocket_aggregator.py) and [apps/reference/domains/market_data/worker.py](apps/reference/domains/market_data/worker.py) together reproduce the 60s trade-window expiry before reconnect.
- affected fields: buy_volume, sell_volume, buy_count, sell_count, tfi, absorption, and any downstream feature built from trade-flow history; quote-derived fields such as obi and liquidity_kappa can remain fresh while trade-flow is stale.
- affected components: [apps/reference/domains/market_data/proxy.py](apps/reference/domains/market_data/proxy.py), [apps/reference/domains/market_data/bar_aggregator.py](apps/reference/domains/market_data/bar_aggregator.py), [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py), [apps/reference/domains/decision_making/gates/readiness_gates.py](apps/reference/domains/decision_making/gates/readiness_gates.py), and [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py).
- strategy sensitivity: Aurora is TRADE_FLOW_AWARE and has an active liquidity gate plus signal weights on obi and tfi in [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L276-L305); mean_reversion is TRADE_FLOW_AWARE by code but its current SSOT leaves microstructure_veto disabled and liquidity_gate null in [config/aurora/strategies/mean_reversion.yaml](config/aurora/strategies/mean_reversion.yaml#L265-L280); md_amr is QUOTE_ONLY_OR_LOW_DEPENDENCY and currently appears as a legacy or fallback runtime path with obi_close support in [apps/reference/domains/strategies/runtimes/md_amr/handler.py](apps/reference/domains/strategies/runtimes/md_amr/handler.py); llm_microstructure is UNPROVEN locally because [apps/reference/domains/strategies/plugins/llm_microstructure.py](apps/reference/domains/strategies/plugins/llm_microstructure.py) is only a bridge-driven sentinel and [config/aurora/strategies/llm_microstructure.yaml](config/aurora/strategies/llm_microstructure.yaml) defines an external_intent contract.
- DecisionMaking freshness checks are timestamp-driven for bars and do not inspect trade-flow degradation; the existing degraded-context gate is present in [apps/reference/domains/decision_making/gates/readiness_gates.py](apps/reference/domains/decision_making/gates/readiness_gates.py) and wired through [apps/reference/domains/decision_making/core/config_spec.py](apps/reference/domains/decision_making/core/config_spec.py), but [config/aurora/domains.yaml](config/aurora/domains.yaml#L237-L240) keeps fail_closed_on_degraded_context=false with empty critical-key sets.

inferences:
- The repo truth supports a strategy-scoped policy rather than a global producer fail-close, because quote-only paths and safe closes must remain available.
- The smallest safe control point is the existing DecisionMaking degraded-context seam, but it needs explicit trade-flow metadata to become actionable.
- Adding an observable degraded flag without any downstream gating would document the problem but would not materially reduce decision risk.
- Aligning reconnect timing with the 60s trade window may reduce the corridor, but it is a separate operational study because it can raise reconnect churn and low-liquidity false positives.

assumptions:
- Current main-branch config is the operational reference for the policy design.
- The live live-data path remains multiprocessing through MarketDataProxy and MarketDataWorker.
- No hidden external consumer is already carrying trade_flow_state outside the local repository evidence.

unknowns:
- Live frequency of partial trade stalls on Binance streams.
- Exact PnL or fill-quality impact of quote-fresh / trade-stale intervals.
- Whether mean_reversion will actually run with its flow-sensitive hooks enabled in a given deployment, since current main config disables them.
- Whether md_amr is materially active in the target deployment, since the current registry and config evidence suggest it is mostly legacy or fallback.
- Bridge-side behavior for llm_microstructure beyond the local sentinel plugin.

data_propagation_map:
- WebSocketAggregator: receives bookTicker and trade/aggTrade, emits schema-valid ticks with bid/ask/mid and buy/sell volumes and counts; it does not emit an explicit trade_flow_state, so stale flow is inferred only from zero-valued fields and timestamps.
- MarketDataWorker / MarketDataProxy: forwards the aggregated tick fields unchanged; both surfaces preserve zero-flow output and do not add a degraded flag.
- BarAggregator: consumes price and volume, accepts zero-volume ticks, and closes bars normally; it carries the degraded trade-flow values forward as ordinary bar state.
- FeatureEngineering: consumes the tick or bar payload and computes tfi, absorption, liquidity_kappa, obi, and other features; it can represent zero flow as valid zero-valued features, but it does not know that trade flow is stale unless metadata is added.
- DecisionMaking: features_ready uses bar_ttl_ms and bar_event_age_mode for bars and a separate tick TTL for ticks; it does not inspect flow degradation. The degraded-context gate exists, but it is disabled by config and currently has no trade-flow contract.
- Strategy handlers and gates: Aurora already consumes trade-flow-sensitive microstructure features; mean_reversion has explicit microstructure veto and liquidity gate call sites; md_amr is oriented around obi_close and liquidity payloads; llm_microstructure is driven outside the local market-data chain.

policy_options:
- option: Observability only
  pros: zero runtime behavior change; immediate visibility into stale flow; lowest deployment risk.
  cons: leaves the gap open for decision paths that already treat zero-flow as valid; no admission control.
  risk: false sense of safety if treated as a complete fix.
  implementation_scope: T6C2 telemetry and payload metadata only.
  rejected_or_accepted: accepted as a first slice, not sufficient alone.
- option: Producer degraded flag
  pros: makes the state explicit at the source without blocking quote-fresh emissions.
  cons: still needs downstream consumers to honor the signal.
  risk: additive metadata can be ignored if the downstream contract is not updated.
  implementation_scope: T6C2 market_data and feature payload plumbing.
  rejected_or_accepted: accepted.
- option: Feature-level degradation flag
  pros: reaches DecisionMaking and strategy code through an additive, inspectable field; can be scoped by strategy.
  cons: requires schema and propagation work across multiple domains.
  risk: partial rollout could create inconsistent behavior if some consumers honor the flag and others do not.
  implementation_scope: T6C2 plus T6C3 plumbing.
  rejected_or_accepted: accepted and preferred.
- option: Decision entry block
  pros: directly protects new positions from stale trade-flow signals.
  cons: must be carefully scoped so closes, risk reduction, emergency exits, and reconciliation are preserved.
  risk: a global block would be too broad for quote-only or low-dependency strategies.
  implementation_scope: T6C3 using the existing degraded-context seam.
  rejected_or_accepted: accepted only as a strategy-scoped open-entry gate.
- option: Strategy-conditional block
  pros: matches repository truth and the existing per-strategy contract model; avoids blocking strategies that do not depend on trade-flow.
  cons: requires accurate sensitivity inventory and careful config hygiene.
  risk: false negatives if a sensitive strategy is omitted from the contract list.
  implementation_scope: T6C3 for configured trade-flow-sensitive strategies.
  rejected_or_accepted: accepted and preferred.
- option: Reconnect threshold alignment
  pros: can shrink the 60s-to-120s corridor from the producer side.
  cons: can increase reconnect storms, especially on low-liquidity symbols or partial exchange stalls.
  risk: operational churn and unnecessary reconnects.
  implementation_scope: T6C4 study only.
  rejected_or_accepted: not accepted as the immediate policy.
- option: Producer fail-closed
  pros: strongest safety posture.
  cons: would also block quote-driven bars, safe closes, and reconciliation flows.
  risk: excessive operational harm and loss of valid actions.
  implementation_scope: none for T6C1.
  rejected_or_accepted: rejected.

recommended_policy:
- policy class: HYBRID_POLICY
- exact behavior: keep quote-fresh emissions observable, add explicit trade_flow_state and trade_flow_age metadata, then use the existing DecisionMaking degraded-context seam to block only new-entry decisions for strategies that declare trade-flow-sensitive critical keys; preserve reduce-only closes, position management, emergency exits, and reconciliation.
- what is blocked: open-entry and new-position intents for strategies that opt into trade-flow sensitivity and whose configured flow-derived keys are stale or degraded.
- what is not blocked: reduce-only closes, emergency exits, risk-reduction actions, reconciliation, and quote-only or low-dependency strategies.
- what is only observed: the producer-side zero-flow condition, trade_flow age metrics, and the transition from fresh to degraded to stale.
- config fields required: none in T6C1; later packages should reuse the existing degraded_context contracts in DecisionMaking rather than introducing a broad global fail-close switch.
- event/schema fields required: trade_flow_state, trade_flow_age_ms, trade_flow_last_trade_ts_ms, and trade_flow_window_sec as additive market tick / bar / feature metadata.

implementation_plan:
- T6C2: add additive observability and metadata propagation from market_data through bar, feature, and decision payloads.
- T6C3: wire a strategy-aware degraded-entry gate in DecisionMaking using the existing degraded-context contract path; scope it to open-entry only and preserve closes.
- T6C4: run a reconnect/window alignment study and low-liquidity false-positive audit before changing timers.

tests_required:
- producer-to-feature propagation tests for trade_flow_state and trade_flow_age metadata.
- DecisionMaking gate tests that block only new entries for configured trade-flow-sensitive strategies.
- regression tests proving reduce-only closes and emergency exits still pass.
- reconnect-alignment tests only if T6C4 becomes an implementation package.

risk_register:
- overblocking valid low-liquidity markets.
- accidentally blocking reduce-only or emergency-exit flows.
- false negatives if a trade-flow-sensitive strategy is omitted from the contract inventory.
- reconnect churn if timer alignment is made too aggressive.
- schema drift if additive metadata is not versioned consistently.

runtime_behavior_change:
- NONE

config_changes:
- NONE

validation:
- git diff --stat: the working tree already contains many unrelated tracked changes, so the plain diff is not an isolation-friendly signal for this package and does not include the new untracked report file.
- git diff --name-only: the output is a long unrelated file list from the existing dirty tree; AURORA_TIMER_GOVERNANCE_T6C1_TRADE_FLOW_FRESHNESS_POLICY_REPORT.md is not listed because it is untracked.
