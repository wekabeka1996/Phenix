# URS-B3 Startup Hydration Planner Design

Date: 2026-03-11
Package: URS-B3
Status: implemented as additive planner/report layer
Depends on:
- `docs/roadmaps/UNIFIED_RUNTIME_STANDARDIZATION_PLAN.md`
- `docs/roadmaps/UNIFIED_RUNTIME_EXECUTION_BACKLOG.md`
- `docs/roadmaps/URS-B2_ANALYTICS_RESTORE.md`

## Problem

Startup knows too much in the wrong places:

- execution restore happens in `main.py`
- md_amr performs local REST hydration inside its handler
- Aurora Quadratic HTF backfill contracts exist, but startup has no explicit planner artifact

That makes it easy to slide into a monolith that fetches data, replays state, decides readiness, and grants trading permission in one place.

## Scope

URS-B3 introduces a planner that only calculates hydration work. It does not:

- fetch data
- replay runtime state
- own readiness truth
- set final trading permissions

It produces deterministic, code-facing plans by strategy-symbol pair from:

- active assignments
- strategy-specific requirements
- analytics restore truth from URS-B2

## Roles

Planner responsibilities:

- know active strategies
- know active symbols
- know basis timeframe and minimum bar counts
- know Quadratic HTF requirements when the active strategy config truly needs them
- know what analytics restore scopes are cold/partial/restored
- emit hydration actions without executing them

Non-responsibilities:

- Hydrator/Importer owns fetch/import execution
- Replayer owns replay
- Readiness evaluator owns scope truth
- Policy arbiter owns final trading permissions

## In-Scope Files

- `apps/reference/bootstrap/startup_hydration_planner.py`
- `apps/reference/main.py` for additive startup report logging only
- planner tests and package spec

## Out of Scope

- executing hydration actions
- replacing md_amr local hydration
- strategy compatibility matrix formalization (`URS-C1`)
- Quadratic rollout activation (`URS-E1`)

## Planner Contract

Planner output is a report of per-strategy-symbol plans containing:

- requirement block
- analytics restore rollup state
- ordered hydration actions

Action examples:

- `RESTORE_OR_REPLAY_BASIS_BARS`
- `RESTORE_FEATURE_LAST_BAR`
- `RESTORE_FEATURE_CACHE`
- `RESTORE_REGIME_STATE`
- `RESTORE_STRATEGY_LOCAL_STATE`
- `USE_STRATEGY_LOCAL_HYDRATION`
- `IMPORT_HTF_BARS`
- `REPAIR_GAP`

## Strategy-Specific Rules in B3

- Aurora v2 uses 5m basis and regime warmup requirements, but does not inherit Quadratic HTF actions while `scoring_version: "v2"` remains active.
- Mean reversion uses its own 5m basis/min-bars contract and receives no Quadratic HTF actions by default.
- md_amr uses 15m basis and retains its local REST hydration contract as a planner action, not as planner-owned execution logic.

## Backward Compatibility

- no config flip to Quadratic
- no startup fetch/import execution added
- no new readiness owner introduced
- no change to MR or md_amr execution semantics

## Invariants Preserved

- planner is not a god-object
- planner does not block unrelated strategies on unrelated scopes
- md_amr is not forced under Quadratic-only prerequisites
- MR remains isolated from Quadratic HTF requirements by default

## Deliverables

- implementation-facing B3 spec
- pure startup hydration planner module
- additive startup plan report in `main.py`
- deterministic planner tests

## Tests

- planner does not block MR on absent Quadratic HTF scope
- planner preserves md_amr local hydration action
- planner emits HTF imports only when Aurora is actually in Quadratic mode
- planner output is deterministic for identical inputs

## Deferred

- executing hydration actions through dedicated hydrator/importer roles
- richer gap-fed planning after broader restore/import plumbing
