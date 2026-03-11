# URS-B2 Analytics Restore

Date: 2026-03-11
Package: URS-B2
Status: implemented as additive cold-truth and restore-contract layer
Depends on:
- `docs/roadmaps/UNIFIED_RUNTIME_STANDARDIZATION_PLAN.md`
- `docs/roadmaps/UNIFIED_RUNTIME_EXECUTION_BACKLOG.md`
- `docs/roadmaps/URS-A1_READINESS_SCHEMA_AND_STATE_MODEL.md`
- `docs/roadmaps/URS-A2_CANONICAL_BAR_IDENTITY_AND_REPLAY_IDENTITY.md`
- `docs/roadmaps/URS-B1_GAP_POLICY.md`

## Problem

Execution restart is better than analytics restart. The live runtime can recover positions and hydrate execution FSMs, but it still lacks one honest contract for analytics continuity across:

- completed bars
- current partial bar truth
- FeatureEngineering caches
- regime detector state
- pillar state
- decision caches
- strategy-local startup state

Without that contract, a restart can look "safe" from the execution side while analytics is still cold or partial.

## Scope

URS-B2 standardizes the runtime truth for analytics restore. This package introduces:

- canonical analytics restore schema and rollup state
- startup restore evaluator that publishes restore/cold/partial truth per strategy-symbol pair
- explicit protect-only semantics when execution is restored but analytics is not
- additive `analytics_restore` signal payload surface
- gateway support for reduce/manage-existing-risk paths during cold restart

URS-B2 does not introduce a global restore blob or claim full multi-domain snapshot persistence is already complete.

## Owner Domains

| Scope | SSOT owner |
| --- | --- |
| `bars` | market-data/startup restore evidence |
| `partial_bar` | market-data/startup restore evidence |
| `feature_engineering_last_bar` | `feature_engineering` |
| `feature_engineering_cache` | `feature_engineering` |
| `regime_detector_state` | `regime_detector` |
| `pillar_state` | `feature_engineering` |
| `decision_cache` | `decision_making` |
| `strategy_local_state` | strategy handler / local strategy runtime |
| `execution_state` | execution restore path |

## In-Scope Files

- `apps/reference/contracts/runtime_analytics_restore.py`
- `apps/reference/bootstrap/runtime_analytics_restore.py`
- `apps/reference/main.py`
- strategy handlers and gateway surfaces that need protect-only analytics truth
- additive schema updates for emitted strategy signals
- targeted restore/restart tests

## Out of Scope

- startup hydration planning and fetch orchestration (`URS-B3`)
- gap policy design (`URS-B1` already owns it)
- full multi-domain snapshot scheduler redesign
- Quadratic rollout activation

## Canonical Restore State Model

Each restore scope uses this object shape:

- `state`
- `why`
- `updated_at`
- `source`
- `evidence_ref`

Enum:

- `RESTORED`
- `COLD`
- `PARTIAL`
- `INVALIDATED_DUE_TO_GAP`

Rollup rule:

- `RESTORED` only when all required scopes for the strategy-symbol pair are restored.
- `PARTIAL` when at least one analytics scope has evidence, but the pair is not yet safe for new risk.
- `COLD` when analytics restore evidence is absent.
- `INVALIDATED_DUE_TO_GAP` when continuity was explicitly invalidated.

## Runtime Permission Rules

- execution restore is not proof of analytics restore
- if execution is restored and analytics is not, runtime must publish protect-only semantics
- reduce/manage-existing-risk paths may proceed when explicit permissions allow it
- new risk remains blocked until analytics rollup becomes `RESTORED`

## Runtime Behavior Added

Startup now computes an additive analytics restore report by strategy-symbol pair.

Inputs:

- assigned strategies
- restored/open positions
- optional explicit analytics restore payload from snapshot
- strategy-local restore hints, currently including md_amr REST hydration state

Outputs:

- `analytics_restore` snapshot on emitted strategy signals
- rollup state: restored/cold/partial/invalidated
- blocking reason chain for analytics restore
- protect-only vs open-new-risk permissions derived from restore truth

## Backward Compatibility

- no Quadratic config flip
- URS-A1 readiness/permission surfaces remain additive and intact
- legacy `readiness.warmup_ok` is preserved
- MR and md_amr stay strategy-specific; Quadratic readiness is not made global

## Invariants Preserved

- `can_manage_existing_risk` and `can_open_new_risk` remain separate
- execution-safe restart is not treated as analytics-safe restart
- md_amr local hydration is not replaced by Aurora bootstrap logic
- no planner or new god-object owns readiness, hydration, replay, and policy at once

## Deliverables

- implementation-facing analytics restore spec
- shared restore contract
- startup restore evaluator with report payload
- signal-level `analytics_restore` payload surface
- protect-only gateway allowance for reduce paths during cold analytics restart

## Tests

- analytics restore contract serialization and rollup tests
- startup restore evaluator tests:
  - execution restored + analytics cold
  - execution restored + analytics restored
  - md_amr local restore remains visible but does not unblock unrelated scopes
- gateway test:
  - reduce path allowed with `warmup_ok=false` when explicit runtime permissions permit manage-existing-risk only
- Aurora signal test:
  - analytics cold restart forces protect-only/open-new-risk block

## Rollback / Safety Constraints

- additive-only runtime payloads
- fail closed to `COLD` or `PARTIAL` when restore evidence is missing
- no new shared mutable cache becomes SSOT
- startup evaluator may read explicit restore evidence but does not fetch data or replay runtime

## What Counts as Done

URS-B2 is done when:

- startup can publish honest analytics restore truth per strategy-symbol pair
- restart with open positions can enter protect-only mode without claiming analytics continuity
- strategy signals can carry restore truth and block new risk when analytics is cold or partial
- MR and md_amr compatibility remains intact

## Deferred

- full domain snapshot persistence/export wiring for FE/regime/decision owner caches
- canonical planner-driven startup restore sequencing (`URS-B3`)
- broader operator persistence beyond log/debug payload/report surfaces
