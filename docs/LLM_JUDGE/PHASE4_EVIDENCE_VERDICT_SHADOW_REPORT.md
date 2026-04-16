# LLM Judge — Phase 4: Evidence Envelope + Deterministic Shadow Verdict

**Status**: COMPLETE
**Date**: 2026-04-15
**Branch**: Phenix_v2
**Test suite**: 356 tests, 0 failures

---

## 1. Summary

Phase 4 closes the LLM Judge shadow pipeline from expert output through to typed verdict. It adds two new modules — **envelope assembly** (packages chamber aggregate + context into a bounded evidence envelope) and **verdict synthesis** (deterministic mapping from chamber consensus to typed verdict). Both operate in **shadow-only posture**: `applied=False`, `authority_mode="shadow"` always. No decision-making, execution, or main orchestrator code was touched.

The full shadow pipeline is now:

```
Expert scoring (Phase 2, L1)
  → ExpertOutput bridge + emission (Phase 2, L2)
    → Chamber aggregation (Phase 3, L3)
      → Evidence envelope assembly (Phase 4, L4)
        → Deterministic verdict synthesis (Phase 4, L4)
```

All 6 shadow events are now emitted end-to-end in the backtest plugin orchestration loop.

---

## 2. Packages Delivered

### Package 4A: VerdictConfig + Cross-Config Invariant

**Files modified**:
- `apps/reference/domains/alpha_search/judge/config_models.py` — added `VerdictConfig` class + `verdict` field on `JudgeCortexConfig` + `validate_verdict_subset_of_chamber` model validator
- `config/alpha_search.yaml` — added `verdict:` block under `judge:`
- `tests/domains/alpha_search/judge/test_config.py` — 21 new tests (3 classes)

**Key decisions**:
- `VerdictConfig` fields: `entry_enabled`, `lifecycle_enabled`, `strategy_id`, `cortex_version`, `split_confidence_discount`
- Cross-config invariant: `verdict.*_enabled` must be subset of `chamber.*_enabled`; violation raises `ValueError` at config load (fail-closed)
- `split_confidence_discount` validated in `[0.0, 1.0]`
- `extra="forbid"`, `frozen=True` on VerdictConfig

**Tests**: 80 total in test_config.py (59 pre-existing + 21 new)

### Package 4B: Envelope Assembly Module

**Files created**:
- `apps/reference/domains/alpha_search/judge/envelope/__init__.py`
- `apps/reference/domains/alpha_search/judge/envelope/envelope_assembler.py`
- `tests/domains/alpha_search/judge/envelope/__init__.py`
- `tests/domains/alpha_search/judge/envelope/test_envelope_assembler.py`

**Key decisions**:
- `assemble_evidence_envelope()` is stateless, deterministic, side-effect-free
- `envelope_id` format: `env_{scope}_{symbol}_{ts_ms}`
- `features_ref` format: `bar:{symbol}:{tf_sec}:{bar_close_ts}` (bounded logical reference, not raw payload)
- `regime` / `regime_confidence`: optional non-blocking enrichment; absence does not affect admissibility or verdict
- `freshness_deadline_ms = ts_ms + chamber_config.max_staleness_ms`
- For LIFECYCLE scope, auto-creates `PositionContextSnapshot(has_position=False)` if none provided
- `provenance.assembly_source = "alpha_search_backtest_plugin"`

**Tests**: 14 (TestEnvelopeAssemblerEntry: 10, TestEnvelopeAssemblerLifecycle: 4)

### Package 4C: Verdict Synthesis Module

**Files created**:
- `apps/reference/domains/alpha_search/judge/verdict/__init__.py`
- `apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py`
- `tests/domains/alpha_search/judge/verdict/__init__.py`
- `tests/domains/alpha_search/judge/verdict/test_verdict_synthesizer.py`

**Key decisions**:
- `synthesize_verdict()` is stateless, deterministic, side-effect-free
- `verdict_id` format: `vrd_{scope}_{symbol}_{ts_ms}`
- Deterministic entry mapping:
  - ADMISSIBLE + LONG → OPEN_LONG
  - ADMISSIBLE + SHORT → OPEN_SHORT
  - ADMISSIBLE + NEUTRAL → NO_ENTRY
  - ADMISSIBLE + SPLIT → NO_ENTRY (confidence * split_confidence_discount, dissent=True)
  - ADMISSIBLE + None direction → UNKNOWN
  - INADMISSIBLE → UNKNOWN
  - QUORUM_INSUFFICIENT → UNKNOWN
- Lifecycle mapping mirrors entry vocabulary (HOLD/EXIT); always QUORUM_INSUFFICIENT → UNKNOWN in Phase 4
- Dissent detection: any expert output direction != consensus direction → dissent=True
- Always: `authority_mode="shadow"`, `applied=False`, `suppression_reason=None`

**Tests**: 19 (TestEntryVerdictMapping: 8, TestEntryVerdictMetadata: 7, TestEntryDissentDetection: 2, TestLifecycleVerdict: 2)

### Package 4D: Orchestration Integration + Bridge Extension

**Files modified**:
- `apps/reference/domains/alpha_search/backtest_plugin.py` — added `_assemble_and_emit_verdict()` method, wired into `_run_chamber_aggregation()` call sites, passed features dict for regime extraction
- `apps/reference/domains/alpha_search/judge/experts/expert_output_bridge.py` — added `write_jsonl_envelope_log()` and `write_jsonl_verdict_log()` JSONL writers
- `tests/domains/alpha_search/judge/test_expert_provider_integration.py` — 10 new integration tests (5 classes)

**Key decisions**:
- `_assemble_and_emit_verdict()` is fail-closed: entire method wrapped in try/except, logs WARNING on failure, no verdict emitted without valid envelope
- Regime/regime_confidence extracted from features dict if available (optional enrichment)
- `features_ref` built as `bar:{symbol}:{tf_sec}:{bar_close_ts}` from cache context
- Event emission order enforced: EVT:JUDGE_EVIDENCE_ASSEMBLED_V1 → EVT:JUDGE_ENTRY_VERDICT_V1 (or LIFECYCLE)
- JSONL logs: `envelope_{symbol}_{date}.jsonl`, `verdict_{symbol}_{date}.jsonl`

**Tests**: 32 total in test_expert_provider_integration.py (22 pre-existing + 10 new)

### Package 4E: Domain Dict + Verb Registry Update

**Files modified**:
- `apps/reference/domains/alpha_search/domain_dict.json` — updated description (Phase 4), event export descriptions, 4 new components, ssot_notes with phase4 blueprint + status
- `apps/reference/dictionaries/verb_registry_v1.yaml` — updated notes for JUDGE_ENTRY_VERDICT_V1, JUDGE_LIFECYCLE_VERDICT_V1, JUDGE_EVIDENCE_ASSEMBLED_V1 to reflect Phase 4 shadow emission status

---

## 3. Architecture Decisions (23 Frozen Decisions Honored)

| # | Decision | Status |
|---|----------|--------|
| 1 | contracts.py FROZEN — zero edits | Honored |
| 2 | Shadow-only: applied=False, authority_mode="shadow" always | Honored |
| 3 | No decision_making domain changes | Honored |
| 4 | No execution_position domain changes | Honored |
| 5 | No main.py changes | Honored |
| 6 | No config_loader.py changes | Honored |
| 7 | VerdictConfig: extra=forbid, frozen=True | Honored |
| 8 | Cross-config invariant: verdict ⊆ chamber | Honored |
| 9 | split_confidence_discount in [0.0, 1.0] | Honored |
| 10 | envelope_id format: env_{scope}_{symbol}_{ts_ms} | Honored |
| 11 | verdict_id format: vrd_{scope}_{symbol}_{ts_ms} | Honored |
| 12 | features_ref: bounded logical ref, not raw payload | Honored |
| 13 | regime/regime_confidence: optional non-blocking enrichment | Honored |
| 14 | Deterministic verdict mapping (no ML, no LLM call) | Honored |
| 15 | SPLIT → NO_ENTRY with confidence discount + dissent=True | Honored |
| 16 | INADMISSIBLE/QUORUM_INSUFFICIENT → UNKNOWN | Honored |
| 17 | Lifecycle always UNKNOWN in Phase 4 (no lifecycle experts active) | Honored |
| 18 | Fail-closed envelope/verdict: exception → WARNING log → no emission | Honored |
| 19 | Layer separation: L1 scoring, L2 bridge, L3 chamber, L4 envelope/verdict | Honored |
| 20 | Roster-truth: disabled expert NOT solicited | Honored |
| 21 | Event order: expert → chamber → envelope → verdict | Honored |
| 22 | JSONL shadow logs for envelope and verdict | Honored |
| 23 | provenance.assembly_source = "alpha_search_backtest_plugin" | Honored |

---

## 4. Files Modified

### Production code
| File | Action | Package |
|------|--------|---------|
| `apps/reference/domains/alpha_search/judge/config_models.py` | Modified | 4A |
| `config/alpha_search.yaml` | Modified | 4A |
| `apps/reference/domains/alpha_search/judge/envelope/__init__.py` | Created | 4B |
| `apps/reference/domains/alpha_search/judge/envelope/envelope_assembler.py` | Created | 4B |
| `apps/reference/domains/alpha_search/judge/verdict/__init__.py` | Created | 4C |
| `apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py` | Created | 4C |
| `apps/reference/domains/alpha_search/backtest_plugin.py` | Modified | 4D |
| `apps/reference/domains/alpha_search/judge/experts/expert_output_bridge.py` | Modified | 4D |
| `apps/reference/domains/alpha_search/domain_dict.json` | Modified | 4E |
| `apps/reference/dictionaries/verb_registry_v1.yaml` | Modified | 4E |

### Test code
| File | Tests | Package |
|------|-------|---------|
| `tests/domains/alpha_search/judge/test_config.py` | 80 (21 new) | 4A |
| `tests/domains/alpha_search/judge/envelope/__init__.py` | — | 4B |
| `tests/domains/alpha_search/judge/envelope/test_envelope_assembler.py` | 14 (all new) | 4B |
| `tests/domains/alpha_search/judge/verdict/__init__.py` | — | 4C |
| `tests/domains/alpha_search/judge/verdict/test_verdict_synthesizer.py` | 19 (all new) | 4C |
| `tests/domains/alpha_search/judge/test_expert_provider_integration.py` | 32 (10 new) | 4D |

### Files NOT touched (frozen constraints)
- `apps/reference/domains/alpha_search/judge/contracts.py` — frozen, zero edits
- `apps/reference/domains/decision_making/` — no files touched
- `apps/reference/domains/execution_position/` — no files touched
- `apps/reference/main.py` — not touched
- `apps/reference/config_loader.py` — not touched

---

## 5. Test Suite Summary

**Total judge tests: 356 passed, 0 failed** (pytest 8.4.2, Python 3.14.3)

| Test file | Count |
|-----------|-------|
| test_config.py | 80 |
| test_contracts.py | 48 |
| test_expert_provider_integration.py | 32 |
| test_registry.py | 29 |
| test_schemas.py | 24 |
| chamber/test_chamber_aggregator.py | 20 |
| verdict/test_verdict_synthesizer.py | 19 |
| experts/test_signal_weights_expert.py | 18 |
| experts/test_feature_neutrals_expert.py | 16 |
| envelope/test_envelope_assembler.py | 14 |
| chamber/test_admissibility.py | 14 |
| test_serialization.py | 12 |
| experts/test_expert_output_bridge.py | 12 |
| test_shadow_mode_admission.py | 9 |
| test_no_live_aurora_regression.py | 9 |

**Phase 4 new tests: 64** (21 config + 14 envelope + 19 verdict + 10 integration)

---

## 6. Shadow Event Pipeline (End-to-End)

```
EVT:JUDGE_EXPERT_PRODUCED_V1       (Phase 2) — per expert, per symbol/tf
EVT:JUDGE_CHAMBER_AGGREGATED_V1    (Phase 3) — per chamber pass
EVT:JUDGE_EVIDENCE_ASSEMBLED_V1    (Phase 4) — envelope packaging
EVT:JUDGE_ENTRY_VERDICT_V1         (Phase 4) — entry verdict (when entry_enabled)
EVT:JUDGE_LIFECYCLE_VERDICT_V1     (Phase 4) — lifecycle verdict (when lifecycle_enabled; always UNKNOWN in Phase 4)
```

All events: `target_domains: []`, shadow-only, never consumed by decision_making.

---

## 7. JSONL Shadow Log Files

| Log file pattern | Content | Phase |
|-----------------|---------|-------|
| `{expert_id}_{symbol}_{date}.jsonl` | ExpertOutput | 2 |
| `chamber_{symbol}_{date}.jsonl` | ChamberAggregate | 3 |
| `envelope_{symbol}_{date}.jsonl` | JudgeEvidenceEnvelope | 4 |
| `verdict_{symbol}_{date}.jsonl` | JudgeVerdict | 4 |

All written to `judge.shadow_log.log_dir` (default: `logs/judge_shadow/`).

---

## 8. Next Phase Notes

Phase 5 candidates (not started, not committed):

1. **Lifecycle expert activation**: Wire lifecycle experts, produce non-UNKNOWN lifecycle verdicts. Requires lifecycle_enabled=true in chamber + verdict config.
2. **Verdict consumption gate**: decision_making reads JUDGE_ENTRY_VERDICT_V1 as advisory signal. Requires new mode beyond "shadow" (e.g. "advisory").
3. **Backtest verdict replay**: Load verdict JSONL logs for offline analysis and parameter sweep.
4. **Confidence calibration**: Use objective feedback (EVT:OBJECTIVE_REALIZED_V1) to calibrate split_confidence_discount and expert weights.
5. **Multi-strategy verdict**: Extend verdict config per strategy_id; currently hardcoded to "aurora".
