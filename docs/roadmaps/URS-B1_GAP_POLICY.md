# URS-B1 Gap Policy

Date: 2026-03-11  
Status: implemented as additive gap-policy foundation

## Problem

Gap detection existed as `gap_bars_skipped` / `is_gap_bar`, but continuity loss was mostly informational. Downstream runtime surfaces could still treat the first post-gap closed bar as tradeable unless each consumer re-invented gap handling.

## Scope

- Canonical gap contract with explicit `gap_state` and `gap_policy_action`
- Default fail-closed policy for live/replay gap bars: `DEGRADE_TO_NON_TRADING`
- Additive propagation through `EVT:BAR_CLOSED`, `EVT:FEATURES_CALCULATED`, `CMD:PROCESS_STRATEGY`, and `EVT:STRATEGY_SIGNAL_PRODUCED`
- Readiness / permission consequence wiring for Aurora, mean_reversion, and md_amr

## Owner Domains

- `market_data`: continuity facts (`gap_bars_skipped`, `is_gap_bar`, canonical gap payload)
- `decision_making`: trading consequence projection into `runtime_readiness` and `runtime_permissions`
- `policy_arbiter`: still owns final gateway enforcement through existing permission gates

## In-Scope Files

- `apps/reference/contracts/runtime_gap_policy.py`
- `apps/reference/domains/market_data/bar_aggregator.py`
- `apps/reference/domains/feature_engineering/feature_engineering.py`
- `apps/reference/domains/decision_making/aurora_decision.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `apps/reference/domains/decision_making/md_amr_handler.py`
- bar / command / signal schemas
- package tests

## Out Of Scope

- Real gap repair execution
- Restart analytics restore
- Startup hydration planning
- Quadratic rollout enablement

## Canonical Contract

`gap_state`
- `CLEAR`
- `GAP_DETECTED`
- `REPAIRED`
- `INVALIDATED`

`gap_policy_action`
- `NONE`
- `REPAIR`
- `INVALIDATE`
- `DEGRADE_TO_NON_TRADING`

Default live/replay behavior in this package:
- contiguous bar -> `CLEAR` + `NONE`
- gap bar -> `GAP_DETECTED` + `DEGRADE_TO_NON_TRADING`
- repaired continuity is reserved for later packages and must be explicit, not inferred

## Runtime Consequences

- `basis_bar_ready` becomes `INVALIDATED_GAP` for gap-affected bars
- `trading_ready` becomes `BLOCKED`
- `can_manage_existing_risk` stays separate from `can_open_new_risk`
- default consequence is protect-only, not silent reopen

For md_amr:
- close / scale-out paths keep `can_manage_existing_risk=True`
- entry paths become protect-only under gap

For Aurora v2 and mean_reversion:
- signals remain additive for observability
- gateway blocks new risk via `runtime_permissions.can_open_new_risk=False`

## Invariants Preserved

- No Quadratic config flip
- No new hydration god-object
- URS-A1 additive readiness / permission surfaces remain intact
- Quadratic-only readiness is still not a global prerequisite
- MR and md_amr keep strategy-local behavior outside gap consequence wiring

## Deliverables

- Shared gap contract module
- Additive gap payloads on bar/command/signal surfaces
- Basis-bar invalidation and protect-only policy mapping
- Tests for gap contract, emitted gap payloads, and Aurora protect-only semantics

## Tests

- contract extraction / readiness consequence tests
- schema acceptance for gap fields
- `BarAggregator` emitted gap-policy payload test
- Aurora runtime protect-only gap test
- compatibility verification with existing MR / md_amr tests

## Rollback / Safety

- Fail-closed on ambiguous gap classification
- Keep legacy `gap_bars_skipped` / `is_gap_bar` fields
- Use additive `gap` payloads and existing gateway permissions instead of replacing live execution flow

## Done

URS-B1 is done when a gap is no longer log-only:

- canonical gap state is emitted
- downstream surfaces do not guess consequence from ad-hoc flags
- runtime readiness shows basis invalidation explicitly
- open-new-risk is blocked while protect-existing-risk remains available

## Deferred

- actual repair path and repaired replay proof
- restart-after-gap analytics restore
- hydration planner ownership of repair work
- operator aggregation counters / metrics beyond the additive payload surface
