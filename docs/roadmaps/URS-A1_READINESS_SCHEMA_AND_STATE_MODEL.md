# URS-A1 Readiness Schema and State Model

Date: 2026-03-11
Package: URS-A1
Status: implementation in progress
Depends on: `docs/roadmaps/UNIFIED_RUNTIME_STANDARDIZATION_PLAN.md`

## Problem

Current runtime readiness is fragmented:

- FeatureEngineering publishes `warmup.full_ready`
- regime readiness lives in `EVT:REGIME_DETECTED.warmup`
- strategy handlers emit only `readiness.warmup_ok`
- gateway/execution permissions for protect-only vs open-new-risk are implicit

That makes restart honesty, per-strategy explanations, and protect-only behavior hard to reason about.

## Scope

URS-A1 standardizes the schema, not the full runtime behavior. This package introduces:

- canonical readiness state enum
- canonical readiness object shape
- explicit readiness scope owner map
- explicit runtime permissions split:
  - `can_manage_existing_risk`
  - `can_open_new_risk`
- additive signal-level payload surfaces for readiness and permissions

## Owner Domains

| Scope | SSOT owner |
| --- | --- |
| `basis_bar_ready` | `market_data` for continuity facts; `feature_engineering` only for strategy-facing sufficiency bridge |
| `regime_ready` | `regime_detector` |
| `quadratic_htf_ready` | `feature_engineering` |
| `microstructure_ready` | `feature_engineering` |
| `strategy_ready_per_symbol` | `decision_making` strategy-aware readiness evaluator |
| `execution_context_ready` | `execution_position` |
| `trading_ready` | final policy arbiter |

## In-Scope Files

- `apps/reference/contracts/runtime_readiness.py`
- strategy signal builders in Aurora, MR, and md_amr
- `apps/reference/domains/decision_making/strategy_gateway.py`
- additive schema documentation for strategy signals
- targeted tests for contract shape and protect-only/open-new-risk behavior

## Out of Scope

- startup hydration planner
- analytics restore
- canonical bar identity hardening
- gap invalidation policy
- Quadratic activation
- changing existing live gating defaults beyond explicit new-risk denial when a signal already carries that denial

## Canonical State Model

Each readiness scope uses this object shape:

- `state`
- `why`
- `updated_at`
- `source`
- `evidence_ref`

Enum:

- `READY`
- `COLD`
- `PARTIAL`
- `BLOCKED`
- `INVALIDATED_GAP`

Implementation rule for A1:

- `why` is represented as an ordered list of machine-readable reason tokens.
- The model is additive and can carry only the scopes a producer can honestly populate today.
- Missing scopes must not be fabricated as ready.

## Contract Surface Added in A1

Strategy signal payloads may now carry:

- `runtime_readiness`
- `runtime_permissions`

Legacy field preserved unchanged:

- `readiness.warmup_ok`

This keeps all existing gateway/tests compatible while exposing the adult runtime contract alongside it.

## Runtime Permission Rules

- `can_manage_existing_risk` governs reduce-only / protection / close management.
- `can_open_new_risk` governs entry/open risk.
- The two flags are independent.
- Gateway must respect an explicit `can_open_new_risk = false` even if legacy `warmup_ok = true`.

## Invariants Preserved

- Aurora live mode remains v2 by default.
- `mean_reversion` and `md_amr` keep working through legacy `readiness.warmup_ok`.
- No Quadratic-only readiness is added as a global prerequisite.
- No startup owner truth is moved into a planner.
- No god-object is introduced.

## Deliverables

- execution backlog artifact
- A1 implementation-facing package spec
- canonical readiness contract module
- additive signal payload fields
- gateway support for explicit protect-only / deny-open-risk mode

## Tests

- contract serialization and owner-map tests
- strategy signal schema additive test with runtime readiness fields
- gateway test: deny new risk when `runtime_permissions.can_open_new_risk = false`
- MR compatibility assertions
- md_amr close-path permissions assertions

## Rollback / Safety Constraints

- additive-only payload changes
- no config flip
- no broad refactor of FE/DM startup wiring
- no replacement of existing `readiness.warmup_ok` consumers in this package

## What Counts as Done

URS-A1 is done when:

- one reusable code contract exists for readiness states and permissions
- strategy signals can expose explicit runtime permissions without breaking current consumers
- gateway can honor protect-only semantics when a signal explicitly denies new risk
- MR and md_amr compatibility tests still pass

## Deferred to Later Packages

- full population of all canonical scopes for every runtime stage
- bar identity evidence hardening (`URS-A2`)
- gap invalidation and policy consequences (`URS-B1`)
- analytics restore or honest cold-state restore paths (`URS-B2`)
- startup planner role split (`URS-B3`)
- strategy compatibility matrix as a code-facing matrix (`URS-C1`)
- structural vs micro regime layer split (`URS-D1`)
- Quadratic rollout/rollback state machine (`URS-E1`)
