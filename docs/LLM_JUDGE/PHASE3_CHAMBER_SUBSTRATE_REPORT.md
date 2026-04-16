# LLM Judge Phase 3 — Chamber Substrate Report

**Date**: 2026-04-15
**Status**: COMPLETE
**Branch**: Phenix_v2
**Test count**: 292 judge tests (0 failures)

---

## Summary

Phase 3 implements the **Chamber Aggregation Substrate** — the intermediate layer between individual expert outputs (Phase 2) and future verdict synthesis (Phase 4+). Chambers collect expert outputs, evaluate admissibility, compute consensus, and emit shadow telemetry. All emission is shadow-only; no decision_making or execution_position domains are touched.

## Packages Delivered

### Package 3A: Chamber Config
- **`judge/config_models.py`**: Added `ChamberConfig` (min_quorum, max_staleness_ms, entry_enabled, lifecycle_enabled) with field validators and frozen+forbid model config
- **`config/alpha_search.yaml`**: Added `chamber:` block under `judge:` with production defaults
- **Tests**: 14 config tests (defaults, validation, backward compat, YAML round-trip)

### Package 3B: Chamber Aggregation Module
- **`judge/chamber/__init__.py`**: Sub-package exporting `ChamberAggregator`, `evaluate_admissibility`
- **`judge/chamber/admissibility.py`**: Stateless `evaluate_admissibility()` implementing 5 rules:
  - R1: Quorum (`responding_count < min_quorum → QUORUM_INSUFFICIENT`)
  - R2: Silent failure (`len(outputs) < expected_expert_count → INADMISSIBLE`)
  - R2.5: Duplicate expert_id (`len(set(ids)) < len(ids) → INADMISSIBLE`)
  - R3: Freshness (`ts_ms < cycle_ts - max_staleness → INADMISSIBLE`)
  - R4: Scope mismatch (entry-only output in LIFECYCLE → INADMISSIBLE)
  - R5: Default ADMISSIBLE
- **`judge/chamber/chamber_aggregator.py`**: Stateless `ChamberAggregator` parameterized by verdict_scope:
  - **Roster-truth accounting**: `expert_count` from `expected_expert_ids` (solicited), not returned outputs
  - `abstaining_count = expert_count - responding_count`
  - Consensus direction: majority vote (LONG/SHORT/SPLIT/NEUTRAL)
  - Consensus strength: mean confidence of responding experts
  - chamber_id: `{scope}_{symbol}_{ts_ms}`
- **Tests**: 34 chamber tests (aggregation, admissibility, roster truth, consensus, lifecycle stub, serialization)

### Package 3C: Orchestration Integration
- **`backtest_plugin.py`**:
  - `_on_decision_score()`: Builds solicited roster from provider configs BEFORE loop, collects `judge_expert_outputs` during loop, calls `_run_chamber_aggregation()` after loop
  - `_resolve_judge_expert_id()`: Maps `expert_type` → actual `expert_id` from judge config
  - `_run_chamber_aggregation()`: Runs entry + lifecycle chambers, emits `EVT:JUDGE_CHAMBER_AGGREGATED_V1`, writes JSONL
  - `_process_judge_expert_score()` now returns `Optional[ExpertOutput]` for collection
- **`judge/experts/expert_output_bridge.py`**: Added `write_jsonl_chamber_log()` for chamber JSONL shadow log
- **Tests**: 10 new integration tests (chamber event emission, payload validity, lifecycle stub, roster truth, JSONL log)

### Package 3D: Domain Dict + Registry
- **`domain_dict.json`**: Updated description (Phase 3), chamber event status (shadow emission), 3 new chamber components, phase 3 SSOT notes
- **`verb_registry_v1.yaml`**: Updated `JUDGE_CHAMBER_AGGREGATED_V1` note from "Phase 1 contract registration only" to "Phase 3 shadow emission"

### Package 3E: Test Suite Validation
- **292 judge tests pass** (0 failures, 0 regressions)
- Breakdown:
  - Phase 1 contracts/schemas/serialization: ~80 tests
  - Phase 2 expert/bridge/integration: ~70 tests
  - Phase 3 config: 14, admissibility: 14, aggregator: 20, integration: 10 → **58 new Phase 3 tests**
  - Registry + mode admission: ~24 tests

## Architecture Decisions

1. **Roster-truth over returned-output counting**: `expert_count` comes from `expected_expert_ids` passed to chamber. Missing experts are counted as abstaining. This catches silent failures.
2. **Lifecycle stub contradiction resolved**: `lifecycle_enabled: false` by default. Lifecycle chamber only runs when explicitly opted in. No "runs by default" ambiguity.
3. **Duplicate expert_id → INADMISSIBLE**: Hardened to fail-closed. Not QUORUM_INSUFFICIENT (which implies "try again with more experts"), but INADMISSIBLE (which implies "this cycle is corrupted").
4. **Layer separation preserved**: Layer 1 (pure scoring in experts/) → Layer 2 (bridge/emission in expert_output_bridge.py) → Layer 3 (aggregation in chamber/). No layer-crossing.
5. **JudgeExpertProviderConfig → expert_type pointer**: `expert_type` is a selector ("signal_weights"), not an expert_id. Actual expert_id lives in `judge.experts.{type}.expert_id`. Resolver method bridges the gap.

## Files Modified (Phase 3)

| File | Change |
|------|--------|
| `apps/reference/domains/alpha_search/judge/config_models.py` | Added `ChamberConfig` class, extended `JudgeCortexConfig` |
| `apps/reference/domains/alpha_search/judge/chamber/__init__.py` | NEW — sub-package |
| `apps/reference/domains/alpha_search/judge/chamber/admissibility.py` | NEW — admissibility filter (R1-R5) |
| `apps/reference/domains/alpha_search/judge/chamber/chamber_aggregator.py` | NEW — stateless aggregator |
| `apps/reference/domains/alpha_search/judge/experts/expert_output_bridge.py` | Added `write_jsonl_chamber_log()` |
| `apps/reference/domains/alpha_search/backtest_plugin.py` | Orchestration: roster build, collection, chamber call |
| `config/alpha_search.yaml` | Added `chamber:` block |
| `apps/reference/domains/alpha_search/domain_dict.json` | Phase 3 components + status |
| `apps/reference/dictionaries/verb_registry_v1.yaml` | Updated chamber verb note |

## Files NOT Touched (by constraint)

- `contracts.py` — frozen Phase 1, no modifications
- `main.py`, `config_loader.py` — out of scope
- `decision_making/`, `execution_position/` domains — no cross-domain leakage
- Schemas — no schema modifications needed

## Test Files (Phase 3)

| File | Test Count |
|------|-----------|
| `tests/domains/alpha_search/judge/test_config.py` | 14 new (config + chamber config) |
| `tests/domains/alpha_search/judge/chamber/test_admissibility.py` | 14 |
| `tests/domains/alpha_search/judge/chamber/test_chamber_aggregator.py` | 20 |
| `tests/domains/alpha_search/judge/test_expert_provider_integration.py` | 10 new (22 total) |

## Frozen Constraints Honored

All 19 frozen constraints from AGENT_TASK_PROMPT_V1 verified:
1. contracts.py untouched
2. Shadow-only posture — EVT:JUDGE_CHAMBER_AGGREGATED_V1 never consumed
3. extra="forbid" + frozen=True on ChamberConfig
4. No main.py / config_loader.py / decision_making / execution_position changes
5. ChamberAggregate contract shape unchanged
6. Phase 3 blueprint SSOT followed exactly
7. Layer separation: scoring → bridge → aggregation
8. Admissibility rules R1-R5 as specified
9. Roster-truth accounting (solicited, not returned)
10. Lifecycle stub: default off, explicit opt-in only

## Next Phase

Phase 4+ will add:
- Evidence envelope assembly (collecting chamber aggregates + raw features)
- Verdict synthesis (consuming chamber outputs to produce entry/lifecycle verdicts)
- Power mode progression (shadow → hybrid_advisory → guarded_entry)

The chamber substrate is the foundation. All future verdict logic consumes `ChamberAggregate` — the contract is frozen and tested.
