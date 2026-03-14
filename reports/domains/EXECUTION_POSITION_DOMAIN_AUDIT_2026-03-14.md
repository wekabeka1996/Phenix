# Execution Position Domain Audit + Structural Cleanup Report

**Date:** 2026-03-14
**Package:** EP-DOMAIN-AUDIT
**Status:** COMPLETE

---

## 1. Executive Summary

The `execution_position` domain has been audited, documented, and structurally hardened.
The domain is large (40 live .py files, ~16,500 LOC, ~1,192 test functions across 147 test files)
and serves as the critical execution soldier layer. It translates trade intents into real exchange
orders through a well-structured 3-FSM architecture (Open → Manage → Close).

**Verdict:** Structurally sound but had significant ghost accumulation from past refactorings.
Score: **8/10** structural clarity (was ~5/10 before cleanup due to 38 ghost .pyc modules, 3 dead
packages, stale docs, no domain manifest).

---

## 2. Phase A: Context Map Findings

### File counts
- **40 live .py files** (38 source + 2 `__init__.py`)
- **11 JSON schemas** in `schemas/`
- **11 doc files** in `docs/` (7 active + 4 deprecated)
- **38 ghost .pyc modules** across 5 locations (cleaned)
- **3 entirely ghosted subpackages** (cleaned)
- **1 broken test fixture import** (fixed)
- **0 empty test files**

### State ownership
- **Order state:** `OrderIndex` (order_index.py) — runtime SSOT
- **Position state:** `ManageFlowFSM` (fsm_manage.py) — runtime SSOT
- **Exposure state:** Distributed across `ExposureGuard` + `ExposureManager`
- **Order persistence:** `OrderLedger` (infra/order_ledger.py) — SQLite

### Triple OrderStatus enum (intentionally layered)
| Layer | File | Count | Examples |
|-------|------|-------|----------|
| Domain contract | contracts.py | 7 | PENDING, PLACED, PARTIAL |
| Binance wire | idempotent_cancel.py | 6 | NEW, PARTIALLY_FILLED, CANCELED |
| Persistence | infra/order_ledger.py | 7 | PENDING, ACTIVE, UNKNOWN |

### Contract map
- **9 events consumed** (TRADE_INTENT_PROPOSED, ORDER_ACK, ORDER_FILL, etc.)
- **31 events emitted** (registered in verb_registry)
- **3 co-emitter gaps**: EVT:TRADE_INTENT_REJECTED, EVT:EXPOSURE_SUMMARY_UPDATED, EVT:TRADE_EXECUTED — EP emits these but registry owner is another domain

### Test coverage
- **147 test files**, **~1,192 test functions**
- Spread across 14 directories (domains/execution_position, integration, order_guardian, unit, units, e2e, vfoundation, config, contracts, runtime, etc.)

---

## 3. Audit Question Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Responsibility boundary | Execution soldier: receives intents, translates to orders, manages lifecycle, does NOT decide |
| 2 | Order state SSOT | `OrderIndex` (order_index.py) — runtime tracking |
| 3 | Position state SSOT | `ManageFlowFSM` (fsm_manage.py) — position_qty, entry_price, side, open_ts |
| 4 | Duplicate engines? | No — 3 FSMs are intentionally separate; cancel paths serve different layers; reconciliation hardened in P0 split-brain package |
| 5 | Domain isolation violations? | Single cross-domain import: `leverage_service.py` → `decision_making.NormalizedRejectReasons`. Heavy Binance adapter coupling (7 files). |
| 6 | Name/location mismatches? | 3 ghost packages, 38 ghost .pyc, broken conftest import — all cleaned |
| 7 | File classification | 40 ACTIVE, 38+ DEAD_SAFE_TO_REMOVE (cleaned), 1 DEAD_RISKY (conftest import, fixed) |
| 8 | Overlapping contracts? | 3 co-emitter gaps documented (EP emits events owned by other domains) |
| 9 | Timeout/cancel reasons? | Yes — `reasons.py` provides 12 typed constants, verified by guardrail test |

---

## 4. Changes Applied

### Cleanup
| Change | Impact |
|--------|--------|
| Deleted 3 ghost `__pycache__`-only packages | `aggregator_oco/`, `observability/`, `shadow_execpos/` (~38 ghost .pyc modules) |
| Deleted 6 ghost .pyc in root `__pycache__/` | binance_execution_adapter, brackets_config, config, internal_types, manage_config, runtime_factory |
| Deleted 6 ghost .pyc in `infra/__pycache__/` | adapter_factory, execution_adapter, idempotent_cancel, order_index, runtime_factory, utils |
| Cleaned stale test .pyc | Deleted cached .pyc for binance_execution_adapter tests |
| Fixed broken `tests/domains/conftest.py` | Removed `adapter_live` fixture referencing deleted `binance_execution_adapter` |

### Documentation
| Change | File |
|--------|------|
| Created authoritative domain README | `apps/reference/domains/execution_position/README.md` |
| Created domain manifest | `apps/reference/domains/execution_position/domain_dict.json` (9 imports, 31 exports, 19 components, ssot_notes) |
| Updated docs/ATLAS.md | Added staleness note pointing to authoritative README |
| Updated docs/README.md | Added staleness note pointing to authoritative README |

### Tests
| Change | File |
|--------|------|
| 13 guardrail tests | `tests/domains/execution_position/test_ep_domain_structural_guardrails.py` |

---

## 5. Guardrail Tests Added

**File:** `tests/domains/execution_position/test_ep_domain_structural_guardrails.py` — 13 tests

| Test Class | Count | What it guards |
|------------|-------|---------------|
| `TestNoPycacheGhosts` | 2 | No stale .pyc in root and infra __pycache__ |
| `TestNoGhostSubpackages` | 1 | Deleted packages (aggregator_oco, observability, shadow_execpos) stay deleted |
| `TestNoDeletedModuleImports` | 1 | No live file imports 6 known deleted modules |
| `TestDomainDictConsistency` | 3 | domain_dict.json exists, has ssot_notes, has critical exports |
| `TestTripleOrderStatusLayered` | 4 | 3 OrderStatus enums exist separately and are distinct |
| `TestReasonsCompleteness` | 1 | reasons.py ALL_REASONS matches defined constants |
| `TestNoEmptyTestFiles` | 1 | No 0-byte test files |

---

## 6. Files Changed

| File | Action |
|------|--------|
| `apps/reference/domains/execution_position/README.md` | **NEW** — authoritative domain documentation |
| `apps/reference/domains/execution_position/domain_dict.json` | **NEW** — domain manifest with full imports/exports/ssot_notes |
| `apps/reference/domains/execution_position/docs/ATLAS.md` | Updated — staleness note added |
| `apps/reference/domains/execution_position/docs/README.md` | Updated — staleness note added |
| `tests/domains/execution_position/test_ep_domain_structural_guardrails.py` | **NEW** — 13 guardrail tests |
| `tests/domains/conftest.py` | Fixed — removed broken `adapter_live` fixture |
| `apps/reference/domains/execution_position/aggregator_oco/` | **DELETED** — ghost pycache-only package |
| `apps/reference/domains/execution_position/observability/` | **DELETED** — ghost pycache-only package |
| `apps/reference/domains/execution_position/shadow_execpos/` | **DELETED** — ghost pycache-only package |
| Various `__pycache__/*.pyc` | **DELETED** — 38+ ghost .pyc entries across root, infra, test dirs |

---

## 7. Follow-up Candidates (not in scope)

| Priority | Item | Risk |
|----------|------|------|
| P2 | Registry co-emitter annotation: EP emits EVT:TRADE_INTENT_REJECTED, EVT:EXPOSURE_SUMMARY_UPDATED, EVT:TRADE_EXECUTED but isn't shown as co-emitter | Medium |
| P3 | Consolidate triple OrderStatus into domain canonical + adapter mapping functions | Low (blast radius ~1,192 tests) |
| P3 | Add schemas for 20 events with `schema: null` in registry | Low |
| P3 | Reduce Binance adapter coupling (extract adapter protocol interface) | Low |
| P3 | Purge or refresh auto-generated docs in `docs/` subdirectory | Low |
| P3 | Migrate `leverage_service.py` NRR import to a domain-neutral interface | Low |
| P4 | Evaluate splitting fsm.py (2,056 LOC) into smaller orchestration units | Very low |

---

## 8. Structural Findings

### Architecture strength
- Clean 3-FSM separation (Open/Manage/Close) with `ExecPosFSM` orchestrator
- Event-driven communication with decision_making (no direct imports)
- Fail-closed policy consistently applied across config, exposure, and validation
- Well-typed reason constants via `reasons.py`
- Comprehensive test coverage (~1,192 functions)

### Architecture risks
- Heavy Binance adapter coupling (7 files import directly) — acceptable for single-exchange architecture
- Triple OrderStatus enum creates mapping complexity but serves clear layering purpose
- `fsm.py` at 2,056 LOC is at the upper limit of single-file cohesion
- 3 co-emitter gaps mean the registry doesn't fully reflect who emits what
