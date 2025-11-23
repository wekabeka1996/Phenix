# Legacy ExecPosFSM Purge Plan

**Document ID:** EP-LEGACY-PURGE-PLAN
**Date:** 2025-11-21
**Task:** EP-LEGACY-PURGE-S1
**Purpose:** Detailed plan for removing all legacy ExecPosFSM references

---

## Executive Summary

Based on **EP_LEGACY_PRESENCE_REPORT.md**, this plan classifies all legacy references and defines concrete actions for purge.

**Key Finding:** No legacy code exists to delete. All work is documentation updates and comment fixes.

---

## 1. Classification Summary

| Category | Count | Action | Phase |
|----------|-------|--------|-------|
| Legacy FSM code files | 0 | ❌ **NONE FOUND** | N/A |
| CI guard tests | 2 | ✅ **KEEP** (validate purge) | N/A |
| Historical incident reports | ~20 | ✅ **KEEP** (dated snapshots) | N/A |
| Archive folders | 2 | ✅ **KEEP** (historical archive) | N/A |
| Design/audit docs | 7 | 🔄 **UPDATE** (add historical note) | PHASE 3 |
| Active domain docs | 2 | 🔄 **UPDATE** (mark V2-only) | PHASE 3 |
| Code comments | 2 | 🔄 **UPDATE** (fix terminology) | PHASE 3 |
| Config files | 0 | ✅ **NO ACTION** (already V2-only) | N/A |

---

## 2. Detailed Action Plan

### PHASE 2.1: Move Helpers (KEEP_MOVE)

**Status:** ✅ **NO ACTION REQUIRED**

**Rationale:** No legacy code exists. All active code already uses ExecPosRuntimeV2.

**Verification:**
- ✅ No `apps/reference/domains/execution_position/fsm.py` exists
- ✅ No imports of legacy FSM in active code
- ✅ `runtime_factory.py` is V2-only

---

### PHASE 2.2: Delete Legacy Files (DELETE)

**Status:** ✅ **NO ACTION REQUIRED**

**Rationale:** No legacy files exist to delete.

**Files Checked:**
- ❌ `apps/reference/domains/execution_position/fsm.py` (does not exist)
- ✅ `apps/reference/domains/execution_position/runtime_factory.py` (V2-only, rejects legacy)
- ✅ `apps/reference/domains/execution_position/__init__.py` (no ExecPosFSM exports)

---

### PHASE 2.3: Clean Tests (DELETE/UPDATE)

**Status:** ✅ **NO ACTION REQUIRED**

**Rationale:** Existing tests are **CI guards** that validate legacy has been removed. They should remain.

**Test Files:**

| File | Purpose | Action |
|------|---------|--------|
| `tests/domains/execution_position/test_no_execpos_legacy_runtime.py` | CI guard: ensures legacy FSM cannot be imported and runtime_factory rejects legacy mode | ✅ **KEEP** |
| `tests/domains/execution_position/shadow_execpos/test_runtime_wiring.py` | Tests that runtime_factory rejects `runtime_mode="legacy"` | ✅ **KEEP** |

**Note:** These tests are **anti-regression guards**. They will fail if anyone tries to reintroduce legacy code.

---

### PHASE 3: Docs & Configs Alignment (UPDATE)

This is the **primary work phase** for EP-LEGACY-PURGE-S1.

#### 3.1 Historical Note Headers (Design/Audit Docs)

**Action:** Add historical note header to documents that describe legacy FSM as active.

**Target Files:**

1. `EXEC_POS_CRITICAL_AUDIT_REVIEW.md`
2. `EXEC_POS_GROUP_ANALYSIS.md`
3. `AUDITOR_RECOMMENDATIONS_ANALYSIS.md`
4. `AUDIT_VALIDATION_REPORT.md`
5. `CRITICAL_AUDIT_FIX_PLAN.md`
6. `EXEC_POS_REFACTOR_PLAN.md`
7. `EXEC_POS_REFACTOR_PLAN_VALIDATED.md`

**Header Template:**
```markdown
---
**HISTORICAL NOTE (2025-11-21 - EP-LEGACY-PURGE-S1)**

This document was written before legacy ExecPosFSM was removed.
ExecPosRuntimeV2 is now the only active execution runtime.
This document is preserved for historical context.

See: `docs/EXEC_POS_RUNTIME_STATE.md` for current state.
---
```

**Placement:** Top of file, after title/metadata, before first section.

#### 3.2 Active Domain Docs (V2-Only Statement)

**Target Files:**

1. `apps/reference/domains/execution_position/docs/EP_RUNTIME_SWITCH_PLAN.md`
2. `apps/reference/domains/execution_position/docs/EXECUTION_POSITION_V2_OBSERVABILITY.md`

**Action for EP_RUNTIME_SWITCH_PLAN.md:**
- Add section at top:
  ```markdown
  ## MIGRATION COMPLETE (2025-11-21)

  **Status:** Legacy `runtime_mode="legacy"` has been removed in EP-LEGACY-PURGE-S1.

  ExecPosRuntimeV2 is the only active runtime. Attempting to set `runtime_mode="legacy"`
  will raise a ValueError.

  This document is preserved for historical context on the migration strategy.
  ```

**Action for EXECUTION_POSITION_V2_OBSERVABILITY.md:**
- Update section 3 (or equivalent):
  ```markdown
  ## Runtime Configuration

  ExecPosRuntimeV2 is the only active execution runtime (as of 2025-11-21).

  The `runtime_mode` config key is no longer used. All execution flows through V2.

  Metrics are automatically included in `/metrics` endpoint under the `execpos_v2` section.
  ```

#### 3.3 Code Comments (Terminology Fix)

**Target Files:**

1. `apps/reference/adapters/binance_adapter.py` (line ~682)
2. `apps/reference/api/main.py` (line ~208)

**Action:**

**File 1: `binance_adapter.py`**
- Old: `"Used by ExecPosFSM for periodic safety audits."`
- New: `"Used by ExecPosRuntimeV2 for periodic safety audits."`

**File 2: `main.py`**
- Old: `"Merge ExecPosFSM and Guardian metrics (JSON)"`
- New: `"Merge ExecPosRuntimeV2 and Guardian metrics (JSON)"`

#### 3.4 Create EXEC_POS_RUNTIME_STATE.md

**Action:** Create new canonical document describing current V2-only runtime state.

**Path:** `docs/EXEC_POS_RUNTIME_STATE.md`

**Content:** See template in Section 3 below.

#### 3.5 Config Files

**Status:** ✅ **NO ACTION REQUIRED**

**Rationale:** `config/domains/execution.yaml` does not contain `runtime_mode` key. Factory defaults to `"v2"`.

---

## 3. New Document: EXEC_POS_RUNTIME_STATE.md

**Path:** `docs/EXEC_POS_RUNTIME_STATE.md`

**Content:**

```markdown
# Execution Position Runtime State

**Document ID:** EXEC-POS-RUNTIME-STATE
**Date:** 2025-11-21
**Last Updated:** 2025-11-21 (EP-LEGACY-PURGE-S1)
**Status:** Active

---

## Executive Summary

The execution_position domain uses **ExecPosRuntimeV2** as the sole active runtime.

Legacy `ExecPosFSM` and `runtime_mode="legacy"` have been removed (EP-LEGACY-PURGE-S1).

---

## 1. Active Runtime

**Component:** `ExecPosRuntimeV2` (Shadow V2 Runtime)

**Location:** `apps/reference/domains/execution_position/shadow_execpos/runtime.py`

**Factory:** `apps/reference/domains/execution_position/runtime_factory.py`

**Wiring:**
```
Events → MessageToRuntimeEventAdapter → ExecPosRuntimeV2 → Adapter (Binance/Simulated)
```

**Key Components:**
- **Gatekeeper:** Pre-execution safety checks (exposure, leverage, symbol state)
- **ExecutionService:** Order placement, management, idempotency
- **PositionService:** Position state tracking, reconciliation
- **Watchdog:** Timeout enforcement, bracket health checks
- **OrderGuardian:** Bracket lifecycle management (Aggregated OCO mode)

---

## 2. Configuration

**Config Path:** `config/domains/execution.yaml`

**Key:** `runtime_mode` is **not present** in config (no longer used).

**Behavior:** `runtime_factory.py` defaults to V2 and rejects legacy mode:
```python
if runtime_mode == "legacy":
    raise ValueError(
        "ExecPosFSM (legacy mode) has been removed. "
        "Please remove 'runtime_mode: legacy' from your configuration."
    )
```

---

## 3. Historical Context

**Legacy Runtime:** `ExecPosFSM` (monolithic state machine)

**Legacy Files:** `apps/reference/domains/execution_position/fsm.py` (removed)

**Migration:** EP-RUNTIME-WIRING-V2-S1 → EP-LEGACY-PURGE-S1

**Timeline:**
- 2025-11-15: ExecPosRuntimeV2 wired as active runtime
- 2025-11-21: Legacy ExecPosFSM fully removed (EP-LEGACY-PURGE-S1)

**See Also:**
- `apps/reference/domains/execution_position/docs/EP_RUNTIME_SWITCH_PLAN.md` (historical migration plan)
- `docs/EP_LEGACY_PRESENCE_REPORT.md` (inventory of legacy references pre-purge)
- `docs/EP_LEGACY_PURGE_PLAN.md` (purge execution plan)

---

## 4. CI Guards

**Tests:** `tests/domains/execution_position/test_no_execpos_legacy_runtime.py`

**Purpose:** Prevent legacy reintroduction (fail CI if legacy code added).

**Checks:**
- Ensure `apps.reference.domains.execution_position.fsm` cannot be imported
- Ensure `runtime_factory` rejects `runtime_mode="legacy"`
- Ensure config does not contain `runtime_mode: legacy`

---

## 5. Observability

**Metrics Endpoint:** `/metrics` → `execpos_v2` section

**Key Metrics:**
- `execpos_v2_events_processed`
- `execpos_v2_orders_placed`
- `execpos_v2_gatekeeper_rejections`
- `execpos_v2_watchdog_violations`

**Logs:** All ExecPosRuntimeV2 activity logged with structured JSONL.

**See:** `apps/reference/domains/execution_position/docs/EXECUTION_POSITION_V2_OBSERVABILITY.md`

---

## 6. Next Steps / Future Work

- Continue stabilizing V2 runtime on testnet
- Expand test coverage for edge cases (bracket management, concurrency)
- Monitor drift metrics (shadow vs. real adapter behavior)

---

**Document Owner:** Engineering Team
**Maintainer:** Execution Domain Team
```

---

## 4. Files NOT to Modify

### 4.1 Keep As-Is (Historical Snapshots)

**Rationale:** These are **dated incident reports** or **archived planning docs**. They should remain unchanged as historical records.

**Files:**
- All `INVESTIGATION_*.md` (root level)
- All `docs/AGG_OCO_*.md` (incident investigation reports)
- All files in `docs/Хазяйство/` (Ukrainian planning archive)
- All files in `docs_arhive/` (historical archive)

**Example:**
- `INVESTIGATION_AGGREGATED_OCO.md` (dated incident report, should not be edited)
- `docs/AGG_OCO_BRACKETS_MISMATCH_INVESTIGATION_2025-11-19.md` (dated 2025-11-19, snapshot)

### 4.2 Keep As-Is (CI Guards)

**Files:**
- `tests/domains/execution_position/test_no_execpos_legacy_runtime.py`
- `tests/domains/execution_position/shadow_execpos/test_runtime_wiring.py`

**Rationale:** These are **anti-regression tests** that validate the purge was successful.

---

## 5. Execution Order

**Phase 3.1-3.3:** Doc/comment updates (parallel batches)

**Batch 1: Historical Note Headers**
- Edit 7 design/audit docs in parallel (add historical note)

**Batch 2: Active Domain Docs**
- Edit 2 domain docs in parallel (mark V2-only)

**Batch 3: Code Comments**
- Edit 2 files in parallel (fix terminology)

**Batch 4: New Doc**
- Create `EXEC_POS_RUNTIME_STATE.md`

**Phase 4:** Run tests and verify

**Phase 5:** Update JOURNAL

---

## 6. Success Criteria

- [x] All legacy code references identified (PHASE 0)
- [x] All actions classified (PHASE 1)
- [ ] Historical notes added to design/audit docs (PHASE 3)
- [ ] Active domain docs updated to V2-only (PHASE 3)
- [ ] Code comments fixed (PHASE 3)
- [ ] EXEC_POS_RUNTIME_STATE.md created (PHASE 3)
- [ ] All tests pass (PHASE 4)
- [ ] JOURNAL updated (PHASE 5)

---

## 7. Risk Assessment

**Risk:** ⚠️ **LOW**

**Rationale:**
- No code changes required (only doc/comment updates)
- No config changes required (already V2-only)
- No test deletion required (existing tests are CI guards)
- All changes are additive or clarifying

**Rollback:** N/A (doc changes can be reverted if needed)

---

**Document Owner:** Engineering Team
**Last Updated:** 2025-11-21
**Status:** Ready for Execution
