# URS-C1 Strategy Compatibility and Isolation Matrix

Date: 2026-03-11
Package: URS-C1
Status: implemented as additive strategy-compatibility SSOT
Depends on:
- `docs/roadmaps/UNIFIED_RUNTIME_STANDARDIZATION_PLAN.md`
- `docs/roadmaps/UNIFIED_RUNTIME_EXECUTION_BACKLOG.md`
- `docs/roadmaps/URS-A1_READINESS_SCHEMA_AND_STATE_MODEL.md`
- `docs/roadmaps/URS-B3_STARTUP_HYDRATION_PLANNER.md`
- `docs/audits/md_amr_mean_reversion_impact_under_quadratic_rollout_2026-03-11.md`

## Problem

Shared runtime contracts already exist for:

- startup restore
- startup hydration planning
- readiness surfaces
- shared gateway policy

Without one code-facing compatibility artifact, those contracts can silently drift toward Aurora-only assumptions and reintroduce bleed-through:

- mean_reversion inheriting Quadratic HTF sufficiency
- md_amr being double-gated by shared bootstrap plus local warmup
- Aurora Quadratic bypassing HTF prerequisites by living only in prose

## Scope

URS-C1 introduces one additive matrix that defines strategy compatibility truth for:

- `aurora_v2`
- `aurora_quadratic`
- `mean_reversion`
- `md_amr`

The matrix is consumed by startup hydration planning and operator-visible startup telemetry. It is intentionally not a new runtime owner for:

- final readiness truth
- final trading permissions
- execution restore ownership

## Owner Domains

- `decision_making`: strategy compatibility truth and consumer contracts
- `bootstrap`: reads compatibility profiles, does not own truth
- `feature_engineering` / `regime_detector`: upstream requirements only by declared profile dependency

## In-Scope Files

- `apps/reference/contracts/strategy_compatibility_matrix.py`
- `apps/reference/bootstrap/startup_hydration_planner.py`
- `apps/reference/main.py`
- package tests and this spec

## Out Of Scope

- changing FE warmup required-ready keys
- changing strategy-local math
- changing regime semantics
- enabling Quadratic live rollout
- changing final gateway trading policy

## Matrix Contract

Each compatibility profile declares:

- `profile_id`
- `strategy_id`
- `active`
- `active_symbols`
- `required_basis_tf_sec`
- `basis_required_bars`
- `required_htf`
- `needs_regime`
- `needs_microstructure`
- `needs_execution_context`
- `local_hydration_contract`
- `degraded_mode_allowance`
- `protect_only_capability`
- `quadratic_readiness_blocks_by_default`

Important semantics:

- `aurora_v2` and `aurora_quadratic` are separate profiles for the same strategy id
- only one Aurora profile is active at once
- `mean_reversion` and `md_amr` never inherit Quadratic HTF requirements by default
- md_amr keeps `md_amr_rest_hydration` as its local hydration contract

## Planner Integration

The startup hydration planner now derives requirements from the matrix instead of hardcoded per-strategy branches.

This means:

- the planner becomes a consumer of compatibility truth rather than its author
- Quadratic-only HTF imports appear only when the active Aurora profile is `aurora_quadratic`
- MR and md_amr remain isolated from unrelated Aurora requirements

## Observability

Startup now logs one additive operator-visible compatibility payload:

- `STRATEGY_COMPATIBILITY_MATRIX`

This is not final operator UX, but it makes the compatibility contract visible in runtime logs without changing live behavior.

## Backward Compatibility

- no config flip to Quadratic
- no change to live Aurora v2 truth
- no new gateway rejection path
- no replacement of md_amr local hydration
- no new shared mutable SSOT

## Invariants Preserved

- MR is not blocked by absent Quadratic HTF scope by default
- md_amr is not double-gated by shared startup planner
- Aurora Quadratic retains explicit HTF prerequisites
- URS-A1 additive readiness surfaces remain untouched

## Deliverables

- implementation-facing C1 spec
- code-facing strategy compatibility matrix
- planner consumption of compatibility profiles
- startup telemetry for active compatibility profiles
- compatibility tests for Aurora v2, Aurora Quadratic, MR, md_amr

## Tests

- matrix marks only Quadratic Aurora as HTF-dependent
- MR profile stays HTF-free even when Aurora Quadratic is active
- md_amr profile keeps strategy-local hydration contract and protect-only capability
- planner output uses the active compatibility profile deterministically

## Deferred

- FE warmup required-ready enforcement directly keyed from compatibility matrix
- strategy profile tagging inside every runtime signal payload
- stronger gateway/runtime assertions derived from compatibility profiles
