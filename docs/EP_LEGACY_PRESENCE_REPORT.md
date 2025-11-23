# Legacy ExecPosFSM Presence Report

**Document ID:** EP-LEGACY-PRESENCE-REPORT
**Date:** 2025-11-21
**Task:** EP-LEGACY-PURGE-S1
**Purpose:** Inventory of all remaining legacy ExecPosFSM references in the repository

---

## Executive Summary

This report documents all remaining references to legacy `ExecPosFSM` and related artifacts in the repository. The scan covered:
- Direct imports and references to `ExecPosFSM`
- References to `execution_position/fsm.py`
- `runtime_mode` configuration flags
- Documentation describing legacy or dual-runtime behavior

**Key Findings:**
- **NO** legacy `fsm.py` file exists in `apps/reference/domains/execution_position/`
- `runtime_factory.py` already rejects `runtime_mode="legacy"` with ValueError
- All references to `ExecPosFSM` are in **documentation only** (no active code imports)
- Test suite includes CI guards to prevent legacy reintroduction
- ExecPosRuntimeV2 is the only active runtime

---

## 1. Code References

### 1.1 Core Runtime Implementation

| File | Line | Type | Reference | Status |
|------|------|------|-----------|--------|
| `apps/reference/domains/execution_position/runtime_factory.py` | 38-42 | CODE | Explicitly **rejects** `runtime_mode="legacy"` with ValueError | ✅ **V2-ONLY** |
| `apps/reference/domains/execution_position/runtime_factory.py` | 54-88 | CODE | `V2RuntimeFacade` wraps ExecPosRuntimeV2 | ✅ **V2-ONLY** |

**Finding:** No legacy FSM code exists. `runtime_factory.py` is V2-only with explicit legacy rejection.

### 1.2 Adapter References (Comments Only)

| File | Line | Type | Reference | Status |
|------|------|------|-----------|--------|
| `apps/reference/adapters/binance_adapter.py` | 682 | COMMENT | "Used by ExecPosFSM for periodic safety audits" | ⚠️ **UPDATE** |
| `apps/reference/api/main.py` | 208 | COMMENT | "Merge ExecPosFSM and Guardian metrics (JSON)" | ⚠️ **UPDATE** |

**Finding:** These are **outdated comments** in active code. The actual code calls ExecPosRuntimeV2, not legacy FSM.

---

## 2. Test Files

### 2.1 CI Guard Tests (Keep)

| File | Purpose | Status |
|------|---------|--------|
| `tests/domains/execution_position/test_no_execpos_legacy_runtime.py` | CI guard: ensures legacy FSM cannot be imported and runtime_factory rejects legacy mode | ✅ **KEEP** (validates purge success) |
| `tests/domains/execution_position/shadow_execpos/test_runtime_wiring.py` | Tests that runtime_factory rejects `runtime_mode="legacy"` | ✅ **KEEP** (validates purge success) |

**Finding:** These tests are **anti-regression guards** that validate legacy has been removed. They should remain.

---

## 3. Documentation Files

### 3.1 High-Level Design Docs (Historical Context)

| File | Type | Legacy References | Disposition |
|------|------|-------------------|-------------|
| `apps/reference/domains/execution_position/docs/EP_RUNTIME_SWITCH_PLAN.md` | DESIGN DOC | Describes `runtime_mode: legacy\|v2\|dual_future` as migration strategy | ⚠️ **UPDATE**: Mark as historical, add note that legacy was removed |
| `apps/reference/domains/execution_position/docs/EXECUTION_POSITION_V2_OBSERVABILITY.md` | OBSERVABILITY DOC | References `runtime_mode="v2"` context | ⚠️ **UPDATE**: Remove conditional language, state V2-only |

### 3.2 Root-Level Audit/Analysis Docs (Historical)

| File | Legacy References | Disposition |
|------|-------------------|-------------|
| `EXEC_POS_CRITICAL_AUDIT_REVIEW.md` | Lines 171, 303: discusses switching from Legacy to Shadow V2 | ⚠️ **MARK HISTORICAL**: Add header stating this was pre-purge analysis |
| `EXEC_POS_GROUP_ANALYSIS.md` | Lines 11, 74, 82: discusses "Legacy FSM Runtime (sm_*.py)" as active | ⚠️ **MARK HISTORICAL**: Add header stating this was pre-purge analysis |
| `EXEC_POS_REFACTOR_PLAN.md` | Line 67: task to remove `test_no_execpos_legacy_runtime.py` | ⚠️ **UPDATE**: Note that test was **kept** as CI guard |
| `EXEC_POS_REFACTOR_PLAN_VALIDATED.md` | Line 104: task to delete legacy test | ⚠️ **UPDATE**: Note that test was **kept** as CI guard |
| `AUDITOR_RECOMMENDATIONS_ANALYSIS.md` | Lines 46, 307: references "ExecPosFSM" in context of config parsing | ⚠️ **MARK HISTORICAL** |
| `AUDIT_VALIDATION_REPORT.md` | Lines 27, 35, 120, 213, 223, 234: extensive references to ExecPosFSM as orchestrator | ⚠️ **MARK HISTORICAL** |
| `CRITICAL_AUDIT_FIX_PLAN.md` | Line 136: code comment referencing ExecPosFSM in fsm.py | ⚠️ **MARK HISTORICAL** |

### 3.3 Investigation/Incident Reports (Historical Snapshots)

| File | Legacy References | Disposition |
|------|-------------------|-------------|
| `INVESTIGATION_AGGREGATED_OCO.md` | Lines 248, 256, 319, 400, 440, 444, 517, 534, 565, 593, 736, 776, 1313, 1376, 1581, 1582, 1889: extensive ExecPosFSM references | ✅ **KEEP AS-IS** (historical incident snapshot, dated) |
| `docs/AGG_OCO_*.md` (multiple files) | References to ExecPosFSM in AGG_OCO investigation/fix reports | ✅ **KEEP AS-IS** (historical incident snapshots) |
| `docs/Хазяйство/таски_від_гпт.md` | Multiple references to `execution_position/fsm.py` | ✅ **KEEP AS-IS** (historical tasks in archive folder) |
| `docs/Хазяйство/Плани_Клода/*.md` | References to ExecPosFSM in Ukrainian planning docs | ✅ **KEEP AS-IS** (historical planning docs in archive folder) |

**Finding:** Incident/investigation reports are **dated historical snapshots**. They should remain unchanged as they document the state at the time of the incident.

---

## 4. Configuration Files

### 4.1 Active Config

| File | Key | Value | Status |
|------|-----|-------|--------|
| `config/domains/execution.yaml` | N/A | No `runtime_mode` key present | ✅ **V2-ONLY** (defaults to v2 in factory) |

**Finding:** Configuration does not contain any `runtime_mode` key. Factory defaults to `"v2"`.

---

## 5. Summary by Category

### 5.1 Files to Keep (No Changes)

**Category: CI Guards**
- `tests/domains/execution_position/test_no_execpos_legacy_runtime.py`
- `tests/domains/execution_position/shadow_execpos/test_runtime_wiring.py`

**Category: Historical Snapshots (Dated Incident Reports)**
- All files in `INVESTIGATION_*.md`
- All files in `docs/AGG_OCO_*.md`
- All files in `docs/Хазяйство/` (archive folder)
- All files in `docs_arhive/` (archive folder)

**Rationale:** These documents are timestamped historical records that should not be retroactively edited.

### 5.2 Files to Update (Mark Historical or Fix Comments)

**Category: Design/Planning Docs Needing Historical Marker**
- `EXEC_POS_CRITICAL_AUDIT_REVIEW.md`
- `EXEC_POS_GROUP_ANALYSIS.md`
- `AUDITOR_RECOMMENDATIONS_ANALYSIS.md`
- `AUDIT_VALIDATION_REPORT.md`
- `CRITICAL_AUDIT_FIX_PLAN.md`
- `EXEC_POS_REFACTOR_PLAN.md`
- `EXEC_POS_REFACTOR_PLAN_VALIDATED.md`

**Update:** Add header stating:
```markdown
> **HISTORICAL NOTE (2025-11-21):** This document was written before EP-LEGACY-PURGE-S1.
> Legacy ExecPosFSM has been fully removed. ExecPosRuntimeV2 is the only active runtime.
> This document is preserved for historical context only.
```

**Category: Active Docs Needing V2-Only Statement**
- `apps/reference/domains/execution_position/docs/EP_RUNTIME_SWITCH_PLAN.md`
- `apps/reference/domains/execution_position/docs/EXECUTION_POSITION_V2_OBSERVABILITY.md`

**Update:** Add section stating legacy mode was removed and V2 is the only runtime.

**Category: Code Comments**
- `apps/reference/adapters/binance_adapter.py:682`
- `apps/reference/api/main.py:208`

**Update:** Replace "ExecPosFSM" with "ExecPosRuntimeV2" in comments.

### 5.3 Files to Delete

**Category: Legacy FSM Code**
- ❌ **NONE FOUND** (already removed)

**Category: Legacy-Only Tests**
- ❌ **NONE FOUND** (test_no_execpos_legacy_runtime.py is a CI guard, not a legacy test)

---

## 6. Verification Checklist

- [x] No `apps/reference/domains/execution_position/fsm.py` exists
- [x] No imports of `ExecPosFSM` in active code
- [x] `runtime_factory.py` rejects `runtime_mode="legacy"`
- [x] CI guard tests exist to prevent legacy reintroduction
- [x] Config does not contain `runtime_mode: legacy`
- [x] All ExecPosFSM references are in documentation only

---

## 7. Recommendations for PHASE 1

### 7.1 Classification

| File/Reference | Classification | Action |
|----------------|----------------|--------|
| CI guard tests | **KEEP** | No changes |
| Historical incident reports | **KEEP** | No changes (dated snapshots) |
| Archive folders (docs/Хазяйство/, docs_arhive/) | **KEEP** | No changes (historical archive) |
| Design/audit docs (EXEC_POS_*.md, etc.) | **UPDATE** | Add historical note header |
| Active domain docs (EP_RUNTIME_SWITCH_PLAN.md, etc.) | **UPDATE** | Mark legacy as removed, state V2-only |
| Code comments (binance_adapter.py, main.py) | **UPDATE** | Replace "ExecPosFSM" → "ExecPosRuntimeV2" |
| Config files | **NO ACTION** | Already V2-only |

### 7.2 No Code Deletion Required

**Finding:** No legacy FSM code exists to delete. All ExecPosFSM references are in documentation only.

### 7.3 No Helper Migration Required

**Finding:** All active code already uses ExecPosRuntimeV2. No legacy helpers need to be moved.

---

## 8. Next Steps

1. Create **EP_LEGACY_PURGE_PLAN.md** based on this inventory
2. Update documentation with historical notes (PHASE 3)
3. Fix code comments (PHASE 3)
4. Create **EXEC_POS_RUNTIME_STATE.md** documenting V2-only state (PHASE 3)
5. Run tests to verify no legacy imports (PHASE 4)
6. Update JOURNAL (PHASE 5)

---

**Document Owner:** Engineering Team
**Last Updated:** 2025-11-21
**Status:** Complete
