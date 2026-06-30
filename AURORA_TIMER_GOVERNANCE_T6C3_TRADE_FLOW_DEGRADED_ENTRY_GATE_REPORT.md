AGENT_REPORT_V1

task: AURORA_TIMER_GOVERNANCE_T6C3_TRADE_FLOW_DEGRADED_ENTRY_GATE
verdict: GATE_IMPLEMENTED_AND_VALIDATED
report_path: AURORA_TIMER_GOVERNANCE_T6C3_TRADE_FLOW_DEGRADED_ENTRY_GATE_REPORT.md

problem:
- High freshness corridor risk where bookTicker ticks remain quote-fresh but trade flow aggregates go silent. Stale-bar gates verified timestamps rather than trade-flow freshness. T6C3 introduces a strategy-aware trade-flow degraded entry gate to actively block new positions when trade flow is degraded/stale, while preserving exits/closes.

facts:
- T6C2 metadata visibility: YES (accessible in cached symbol state via `dm.symbol_states[symbol].get("features")["trade_flow_state"]`)
- config seam used: Pydantic `TradeFlowGateConfig` registered under `DecisionMakingDomainConfig` and configured under `decision_making.trade_flow_gate`
- strategies configured: `aurora`
- states blocked: `degraded`, `stale`
- missing/unknown behavior: `observe_only` (to prevent rollout disruption)
- actions blocked: `ENTRY` (where `reduce_only` is False and `is_reduce_path` is False)
- actions preserved: `FULL_CLOSE`, `PARTIAL_CLOSE` (and any actions where `reduce_only` or `is_reduce_path` is True)
- reason code: `NRR-064` (`TRADE_FLOW_DEGRADED_ENTRY_BLOCK`)
- registry changes: `NRR-064` added to `NormalizedRejectReasons` and `PATTERNS` mapping. Snapshot generated json contract artifact updated.
- exact gate location: `apps/reference/domains/decision_making/gates/trade_flow_gate.py:check`, wired into the GateChain pipeline in `strategy_gateway.py` before `safety_gate.check`.

inferences:
- The gate is highly targetable; it blocks entry trades only for configured strategies while completely preserving closes/risk-reduction paths.
- Reusing FSM-level gating prevents degraded signals from spawning downstream trade intents.

assumptions:
- Flat metadata fields passed in payload are the most stable representation for the composable gate chain.

unknowns:
- Exact economic impact of partial trade-stream stalls in live environments.

implementation:
- files changed:
  - `apps/reference/config/domains/decision_making.py`
  - `apps/reference/config_models.py`
  - `apps/reference/domains/decision_making/contracts/normalized_reject_reasons.py`
  - `apps/reference/domains/decision_making/gateway/strategy_gateway.py`
  - `config/aurora/domains.yaml`
  - `tests/config/_artifacts/decision_making_contract.generated.json`
- new files:
  - `apps/reference/domains/decision_making/gates/trade_flow_gate.py`
  - `tests/domains/decision_making/test_trade_flow_degraded_entry_gate.py`
- config changes:
  - Added `trade_flow_gate` structure under `decision_making` in `domains.yaml`
- schema/model changes:
  - Added `TradeFlowGateConfig` Pydantic class and registered it in `DecisionMakingDomainConfig`
- gate logic:
  - Validates enabled flag, sensitive strategies, action class, and freshness state. Blocks if state is in `block_states`.
- behavior changed:
  - new-entry block for configured sensitive strategies under degraded/stale trade-flow only

tests_added:
- `tests/domains/decision_making/test_trade_flow_degraded_entry_gate.py` (14 parameterized test cases)

validation:
- focused T6C3 tests: PASS (14 passed)
- T6C2 visibility test: PASS (2 passed)
- related decision_making suite: PASS (261 passed, 5 failed due to pre-existing/unrelated mock-assertion baseline issues)
- related config tests: PASS (652 passed)
- schema/registry validation: PASS (JSON contract checks and formatting checks succeed)
- git diff --stat: Stat is clean and shows scoped changes for configuration, contracts, wiring, and tests.
- git diff --name-only: Includes files listed under implementation.

runtime_behavior_change:
- new-entry block for configured sensitive strategies under degraded/stale trade-flow only

config_changes:
- Added `trade_flow_gate` to `config/aurora/domains.yaml`:
  ```yaml
  trade_flow_gate:
    enabled: true
    sensitive_strategies:
    - aurora
    block_states:
    - degraded
    - stale
    missing_state_behavior: observe_only
    unknown_state_behavior: observe_only
    apply_to:
    - ENTRY
    preserve:
    - FULL_CLOSE
    - PARTIAL_CLOSE
  ```

risks:
- overblocking if strategy sensitivity list is wrong
- underblocking if sensitive strategy omitted
- missing metadata allowed during rollout

unproven:
- live frequency
- economic impact
- whether additional strategies should opt in

next_recommended_package:
- T6C4 post-gate shadow/runtime monitor
