# URS-D1 Regime Layering

Date: 2026-03-11
Package: URS-D1
Status: implemented as additive layered-regime contract
Depends on:
- `docs/roadmaps/UNIFIED_RUNTIME_STANDARDIZATION_PLAN.md`
- `docs/roadmaps/UNIFIED_RUNTIME_EXECUTION_BACKLOG.md`
- `docs/audits/regime_architecture_decision_audit_2026-03-11.md`
- `docs/audits/md_amr_mean_reversion_impact_under_quadratic_rollout_2026-03-11.md`

## Problem

The live classifier is already bar-driven and per-symbol, but downstream consumers still blur three different concerns:

- structural regime
- execution micro regime
- global execution adaptation

The worst current leakage is `ExecPosFSM` treating per-symbol structural `EVT:REGIME_DETECTED` as a global exposure-adaptation signal.

## Scope

URS-D1 formalizes:

- current `EVT:REGIME_DETECTED` as `structural`
- structural scope as `per_symbol`
- structural clock as `bar`
- execution/global consumers as separate, explicit layers

This package does not add a live execution-micro producer. It adds the contract split and updates consumers to respect it.

## Owner Domains

- `regime_detector`: structural regime producer
- `decision_making` / strategies: structural regime consumers
- `execution_position`: may consume only explicit global execution-layer regime for portfolio-wide exposure adaptation

## In-Scope Files

- `apps/reference/contracts/runtime_regime_layers.py`
- `apps/reference/domains/regime_detector/regime_detector.py`
- `apps/reference/domains/regime_detector/schemas/regime_detected_v1.json`
- regime consumers in FE / DM / Aurora / MR / md_amr / execution
- package tests and this spec

## Out Of Scope

- building the execution micro regime classifier itself
- changing structural classifier math
- introducing a global backdrop producer
- changing Quadratic rollout policy

## Contract

Structural regime now carries additive metadata:

- `regime_layer = structural`
- `regime_scope = per_symbol`
- `regime_clock = bar`
- `regime_owner = regime_detector`
- `structural_regime_ref`

Backward compatibility rule:

- missing metadata defaults to structural/per-symbol/bar for older payloads

## Consumer Rules

- `FeatureEngineering` caches only structural regime events for `CMD:PROCESS_STRATEGY`
- strategy handlers cache only structural regime events
- `DecisionMaking` stores per-symbol structural regime truth and marks shared latest-regime slots as debug-only last-writer snapshots
- `ExecutionPosition` no longer mutates global exposure limits from structural per-symbol regime events

That last change is the core leakage repair in D1.

## Regime Flip Vocabulary

`IntentEmitter.handle_regime_flip()` now aligns with the live detector vocabulary:

- `TREND_UP`
- `TREND_DOWN`
- `UNCERTAIN`

Legacy aliases `BULL_TREND` and `BEAR_TREND` are normalized additively.

## Observability

Structural regime payloads now expose layer/scope/clock explicitly, so operators can distinguish:

- structural regime freshness
- any future execution-micro regime source

This package does not yet add a separate execution-micro telemetry stream; that remains deferred.

## Backward Compatibility

- structural detector math unchanged
- strategy consumers keep reading the same regime labels
- older regime payloads still default to structural semantics
- no Quadratic config flip

## Invariants Preserved

- structural regime remains bar-driven
- structural regime remains per-symbol
- microstructure is not injected into the structural classifier
- MR and md_amr keep their current structural regime semantics

## Deliverables

- implementation-facing D1 spec
- layered regime contract module
- structural-regime metadata on live detector emissions
- consumer filtering by regime layer
- removal of structural-regime -> global-exposure adaptation leak

## Tests

- regime detector emits structural/per-symbol/bar metadata
- structural payloads remain backward-compatible by default
- structural regime no longer triggers global exposure adaptation
- explicit global execution-layer regime can still adapt exposure
- regime-flip enforcement understands `TREND_UP` / `TREND_DOWN`

## Deferred

- explicit execution-micro regime producer and event schema
- global backdrop regime producer
- broader removal of shared debug-only `latest_regime` surfaces
