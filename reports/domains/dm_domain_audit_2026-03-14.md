# Decision Making Domain Audit + Structural Cleanup Report

**Date:** 2026-03-14
**Package:** DM-DOMAIN-AUDIT
**Status:** COMPLETE

---

## 1. Executive Summary

The `decision_making` domain has been audited, documented, and structurally hardened.
The domain is large (37 live .py files, ~98 test files) but well-structured as a flat module
with clear responsibilities. Full file reorganization (moving to `logic/`, `services/`, etc.)
was **not** applied because the blast radius (~98 test files, 4+ production cross-domain consumers)
far exceeds the marginal benefit. Instead: fix the rot, don't move the furniture.

Score: **8/10** structural clarity (was ~5/10 before cleanup due to stale docs, ghost pycache, stale domain_dict).

---

## 2. Phase A: Context Map Findings

### File counts
- **37 live .py files** (excluding shields subpackage)
- **5 shields/*.py** files
- **3 JSON schemas** in schemas/
- **12 doc files** in docs/ (auto-generated, partially stale)
- **5 stale pycache ghosts** (deleted source files had leftover .pyc)
- **1 empty test file** (0 bytes)

### Contract map
- **13 events consumed** (CMD:PROCESS_STRATEGY, EVT:FEATURES_CALCULATED, etc.)
- **12 events emitted** (EVT:TRADE_INTENT_PROPOSED, EVT:STRATEGY_SIGNAL_PRODUCED, etc.)
- All DM-owned events are registered in `verb_registry_v1.yaml`
- EVT:TICK_RECEIVED was already marked deprecated in preceding contract audit

### Dependency graph
- **9 files** import from `vfoundation/` (core bus, config, protocol, why_codes)
- **3 files** import from other domains (feature_engineering: MR strategy, regime_allowlist: allowlist contract)
- **4 production files** import FROM decision_making externally (main.py, strategy plugin, alpha_search adapter, objective_engine)
- **~98 test files** import from decision_making

### SSOT alignment
- WhyCode: **ALIGNED** — re-export shim from vfoundation (per SSOT consolidation)
- NRR: **ALIGNED** — canonical source lives here
- Events: **ALIGNED** — all registered in verb_registry

---

## 3. Audit Question Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Responsibility boundary | Receives upstream data, dispatches to strategy handlers, produces trade intents. Owns: strategy dispatch, intent construction, safety gating, sizing, flip orchestration, QoS, NRR |
| 2 | Core vs helper vs legacy | 12 core runtime, 15 helpers/utils, 7 gates/shields, 4 observability, 2 schemas, 0 live legacy (5 pycache ghosts cleaned) |
| 3 | Duplicate logic? | No — WhyCode fork resolved, contracts.py deleted, no duplicate NRR |
| 4 | Domain isolation violations? | No — regime_allowlist is a legitimate separate domain; feature_engineering import is legitimate strategy plugin |
| 5 | Name/location mismatches? | Minor: `schemas.py` (Pydantic models) vs `schemas/` (JSON schemas) — documented, not worth renaming |
| 6 | Proposed directory split? | Not justified — 98 test files would break. Flat structure is acceptable for this domain size |
| 7 | Dead/risky files? | 5 pycache ghosts (cleaned), 1 empty test (deleted), 12 stale docs (annotated) |

---

## 4. Changes Applied

### Cleanup
| Change | Impact |
|--------|--------|
| Deleted 5 stale __pycache__ ghosts | aurora_scoring_kernel, contracts, portfolio_provider, scoring_direction_strength_v1, signal_score_v2 |
| Deleted empty test file | `test_mean_reversion_emit_trade_intent_mode.py` (0 bytes) |
| Fixed docs/ATLAS.md | Removed reference to deleted `aurora_scoring_kernel.py`, updated why_codes SSOT note |
| Fixed docs/README.md | Updated `aurora_scoring_kernel.py` → `quadratic_scoring_kernel.py`, added staleness note |

### Documentation
| Change | File |
|--------|------|
| Created authoritative domain README | `apps/reference/domains/decision_making/README.md` |
| Updated domain_dict.json | Version 2.0.0, full 13 imports + 12 exports, ssot_notes section |
| Updated __init__.py | Version 2.0.0, updated docstring (components, no stale events) |

### Tests
| Change | File |
|--------|------|
| 8 guardrail tests | `tests/domains/decision_making/test_dm_domain_structural_guardrails.py` |

---

## 5. Guardrail Tests Added

**File:** `tests/domains/decision_making/test_dm_domain_structural_guardrails.py` — 8 tests

| Test Class | Count | What it guards |
|------------|-------|---------------|
| `TestNoPycacheGhosts` | 1 | No stale .pyc files for deleted sources |
| `TestWhyCodeReExport` | 2 | DM WhyCode is re-export (not fork), identity check |
| `TestNoDeletedModuleImports` | 1 | No live file imports deleted modules |
| `TestDomainDictConsistency` | 3 | Version matches __init__, ssot_notes present, critical exports in domain_dict |
| `TestNoEmptyTestFiles` | 1 | No 0-byte test files |

---

## 6. Files Changed

| File | Action |
|------|--------|
| `apps/reference/domains/decision_making/__init__.py` | Updated docstring, version 2.0.0 |
| `apps/reference/domains/decision_making/README.md` | **NEW** — authoritative domain documentation |
| `apps/reference/domains/decision_making/domain_dict.json` | Full rewrite: 13 imports, 12 exports, ssot_notes |
| `apps/reference/domains/decision_making/docs/ATLAS.md` | Fixed deleted file references, SSOT annotation |
| `apps/reference/domains/decision_making/docs/README.md` | Fixed deleted file reference, staleness note |
| `tests/domains/decision_making/test_dm_domain_structural_guardrails.py` | **NEW** — 8 guardrail tests |
| `tests/domains/decision_making/test_mean_reversion_emit_trade_intent_mode.py` | **DELETED** — empty 0-byte file |
| `apps/reference/domains/decision_making/__pycache__/*.pyc` | **DELETED** — 5 stale ghost entries |

---

## 7. Follow-up Candidates (not in scope)

| Priority | Item | Risk |
|----------|------|------|
| P3 | Consolidate `schemas.py` + `schemas_decision_blocked.py` into `models.py` or single file | Low |
| P3 | Migrate all `from .why_codes import` to `from vfoundation.core.why_codes import` | Low |
| P3 | Purge or refresh auto-generated docs in `docs/` subdirectory | Low |
| P3 | Rename `schemas.py` to `models.py` to avoid confusion with JSON `schemas/` dir | Low |
| P4 | Consider shields/ → safety/ rename for clarity | Very low |
