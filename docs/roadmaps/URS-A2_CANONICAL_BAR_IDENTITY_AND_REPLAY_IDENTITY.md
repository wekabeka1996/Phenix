# URS-A2 Canonical Bar Identity and Replay Identity

Date: 2026-03-11
Status: implemented as additive contract foundation
Depends on: `docs/roadmaps/URS-A1_READINESS_SCHEMA_AND_STATE_MODEL.md`

## Problem

Aurora runtime still mixes multiple timestamp meanings:

- `bar_end_ts_ms`
- `bar_close_ts`
- `close_ts`
- event `ts_ms`
- downstream-extracted timestamps from nested bar payloads

That ambiguity makes startup, replay, warmup import, and strategy consumers disagree about which bar they are processing.

## Scope

URS-A2 standardizes one canonical bar identity and one canonical replay identity across:

- live bar close flow
- replayed WAL flow
- `CMD:PROCESS_STRATEGY` flow
- strategy signal payloads
- HTF warmup import consumers

## Owner Domains

- `market_data`: canonical bar identity production for closed bars
- `feature_engineering`: propagation across FE and CMD payloads
- `decision_making`: consumption and signal-level propagation
- `vfoundation.dr`: replay identity meaning and parity with live payloads

## Canonical Contract

Canonical bar identity:

- `symbol`
- `timeframe_sec`
- `bar_start_ts_ms`
- `bar_end_ts_ms`
- `close_boundary_ts_ms`
- `source_mode`

Canonical replay identity:

- `symbol`
- `timeframe_sec`
- `close_boundary_ts_ms`
- `source_mode`
- `replay_generation`

`source_mode` enum:

- `live`
- `replay`
- `warmup_import`
- `synthetic_repair`

## Compatibility Rule

`bar_close_ts` remains an additive migration bridge only.

- In current live runtime it stays a legacy alias for `bar_end_ts_ms`.
- New code must treat `bar_identity.close_boundary_ts_ms` as the canonical close boundary.
- Event `ts_ms` remains event-emission time and must not be treated as bar identity.

## In-Scope Files

- `apps/reference/contracts/runtime_bar_identity.py`
- `apps/reference/domains/market_data/bar_aggregator.py`
- `apps/reference/domains/feature_engineering/feature_engineering.py`
- `apps/reference/domains/decision_making/aurora_decision.py`
- `apps/reference/domains/decision_making/aurora_handler.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `apps/reference/domains/decision_making/md_amr_handler.py`
- `schemas/bar_closed_v1.json`
- `schemas/htf_bars_imported_v1.json`
- `apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json`
- `schemas/strategy_signal_produced_v1.json`

## Out of Scope

- gap policy consequences
- analytics restore
- startup planner orchestration
- Quadratic rollout activation
- broad replay engine redesign

## Deliverables

- shared runtime bar/replay identity contract helpers
- additive producer wiring for `EVT:BAR_CLOSED`
- additive propagation through FE, CMD, and strategy signals
- HTF import consumer compatibility with canonical identities
- contract tests for live/replay/warmup parity

## Tests

- canonical identity round-trip tests
- live vs replay downstream meaning parity tests
- bar aggregator payload contract tests
- schema validation tests for additive fields
- Aurora/MR/md_amr compatibility verification via targeted tests

## Rollback and Safety Constraints

- no config flip to Quadratic
- no removal of URS-A1 additive readiness surfaces
- no semantic change to current MR or md_amr gating
- no reinterpretation of legacy `bar_close_ts` in existing live gateways

## Done

URS-A2 is done when:

- closed bars publish one canonical `bar_identity`
- replay uses the same canonical meaning via `replay_identity`
- FE and strategy consumers stop inferring identity from mixed timestamp aliases
- live, replay, and warmup import paths have one code-facing identity contract

## Preserved Invariants

- Aurora v2 remains live truth
- `bar_close_ts` backward compatibility is preserved for existing consumers
- URS-A1 readiness and runtime permission surfaces remain additive and unchanged
- MR and md_amr are not blocked by Quadratic-only requirements

## Deferred

- gap invalidation based on canonical identities moves to URS-B1
- analytics restore keyed by replay identity moves to URS-B2
- planner-owned hydration action graphs move to URS-B3
