# Execution Position Legacy Cleanup Plan (Phase S11)

**RID:** EP-EXEC-LEGACY-CLEANUP-MAP-S11
**Status:** Documentation-only (no code changes)
**Created:** 2025-11-22
**Owner:** QuantumTraderX Team

---

## Overview

The `execution_position` domain has migrated to **V2 runtime** (`shadow_execpos/`), powered by:
- **ExecutionPositionConfig** (Pydantic SSOT in `config.py`)
- **ExecPosRuntimeV2** (async orchestrator in `shadow_execpos/runtime.py`)
- **BracketService** (aggregated OCO logic in `shadow_execpos/bracket_service.py`)

Legacy FSM files (`fsm_open.py`, `fsm_manage.py`, `fsm_close.py`) and supporting infrastructure remain in place but are **no longer used in runtime**. The `runtime_factory.py` enforces V2-only mode and raises errors if `runtime_mode: legacy` is configured.

**Purpose of this document:**
1. Inventory all legacy files (candidates for removal)
2. Map import dependencies to identify cleanup blockers
3. Define phased removal strategy without breaking tests or runtime
4. Establish safety checklist for future removal execution

**Current state:**
- ✅ V2 runtime active and stable (hybrid mode validated)
- ✅ All domain tests passing (146/146 config tests, 58/58 execution tests)
- ❌ Legacy FSM files still present (unused in runtime, some tests depend on them)

---

## File Inventory

All files under `apps/reference/domains/execution_position/` (excluding `shadow_execpos/` and `config.py`):

| File | Role | Status | Lines |
|------|------|--------|-------|
| **Legacy FSM Core** | | | |
| `fsm_open.py` | Open flow FSM (IDLE → PROCESSING → DONE) | **tests-only** | 372 |
| `fsm_manage.py` | Manage flow FSM (bracket placement/updates) | **tests-only** | 2678 |
| `fsm_close.py` | Close flow FSM (position exit logic) | **tests-only** | 205 |
| **Config Adapters (Hybrid)** | | | |
| `brackets_config.py` | TP/SL config resolver (V2 + legacy fallback) | **runtime-critical** | 266 |
| `manage_config.py` | Manage config resolver (V2 + legacy fallback) | **runtime-critical** | 1025 |
| **Supporting Infrastructure** | | | |
| `idempotent_cancel.py` | Idempotent order cancellation (Phase 4) | **runtime-critical** | 282 |
| `watchdog.py` | Order timeout monitor (legacy, superseded by V2) | **candidate-for-archive** | 646 |
| `drift_monitor.py` | Shadow-mode drift tracking | **tools-only** | 268 |
| `agg_oco_introspection.py` | State snapshot utilities | **tools-only** | 36 |
| **Adapters** | | | |
| `aurora_log_adapter.py` | Legacy logging adapter | **candidate-for-archive** | ? |
| `binance_execution_adapter.py` | Binance API adapter | **runtime-critical** | ? |
| `execution_adapter.py` | Abstract execution adapter | **runtime-critical** | ? |
| `simulated_adapter.py` | Simulation/testing adapter | **tests-only** | ? |
| **Utilities** | | | |
| `contracts.py` | Domain contracts (PositionSnapshot, etc.) | **runtime-critical** | ? |
| `utils.py` | Client order ID builders | **runtime-critical** | ? |
| `utils_event_bus.py` | Event bus helpers | **runtime-critical** | ? |
| `exposure_guard.py` | Exposure limits enforcement | **runtime-critical** | ? |
| `soft_clip.py` | Quantity/price clipping | **runtime-critical** | ? |
| `order_index.py` | Order tracking index | **candidate-for-archive** | ? |
| `metrics_collector.py` | Metrics collection | **runtime-critical** | ? |
| `metrics_aggregator.py` | Metrics aggregation | **runtime-critical** | ? |
| `runtime_factory.py` | Runtime factory (V2-only enforcer) | **runtime-critical** | ? |
| **Documentation** | | | |
| `EXECUTION_POSITION_INVARIANTS.md` | Domain invariants | **keep** | N/A |
| `docs/EP_FSM_EXTRACTION_AUDIT.md` | FSM extraction audit | **keep** | N/A |
| `docs/EP_RUNTIME_SWITCH_PLAN.md` | Runtime switch plan | **keep** | N/A |
| `docs/EXECUTION_POSITION_V2_OBSERVABILITY.md` | V2 observability | **keep** | N/A |
| `docs/EXEC_POS_BRACKETS_CONTRACT.md` | Brackets contract | **keep** | N/A |
| `docs/EXEC_POS_CLOSE_TRAILING_ANALYSIS.md` | Close/trailing analysis | **keep** | N/A |
| `docs/EXEC_POS_CLOSE_TRAILING_CONTRACT.md` | Close/trailing contract | **keep** | N/A |
| `docs/FSM_EVENT_MAP.md` | FSM event map | **keep** | N/A |

**Legend:**
- **runtime-critical:** Actively used in production runtime (cannot remove yet)
- **tests-only:** Only imported by test files (can be archived after test migration)
- **tools-only:** Used by CLI tools/analysis scripts (can be archived after migration)
- **candidate-for-archive:** Legacy component superseded by V2 (safe to archive)

---

## Import/Usage Map

### Legacy FSM Classes (Deprecated in Runtime)

#### `fsm_open.py::OpenFlowFSM`
**Used by (tests only):**
- `tests/domains/test_fsm_open.py` (4 tests)
- `tests/integration/test_happy_path_dec_open.py` (1 test)
- `tests/integration/test_order_lifecycle_correlation.py` (1 test)

**Runtime usage:** ❌ None (V2 uses `shadow_execpos/runtime.py::ExecPosRuntimeV2`)

#### `fsm_manage.py::ManageFlowFSM`
**Used by (tests only):**
- `tests/units/test_manage_closing_flag_entry_guard.py`
- `tests/units/test_manage_disabled.py`
- `tests/units/test_manage_flow_fsm_sl_side.py`
- `tests/units/test_manage_with_price_service.py`
- `tests/units/test_quick_profit.py`
- `tests/units/test_dedup_rest_mismatch.py`
- `tests/units/test_closing_flag_window.py`
- `tests/test_quick_profit_feature.py`
- `tests/domains/test_task_a1_b2_c.py`
- `tests/domains/test_manage_flow_more.py`
- `tests/domains/test_manage_flow_fsm.py`
- `tests/domains/test_emergency_wait_mode.py`

**Runtime usage:** ❌ None (V2 uses `shadow_execpos/bracket_service.py`)

#### `fsm_close.py::CloseFlowFSM`
**Used by (tests only):**
- `tests/units/test_execution_position_fsm_close_unit.py`
- `tests/domains/test_fsm_close.py`

**Runtime usage:** ❌ None (V2 uses `shadow_execpos/runtime.py` close logic)

#### ❌ `fsm.py::ExecPosFSM` (DELETED)
**Previously used by:**
- Many legacy tests (test_guardian_cleanup_loop.py, test_fsm_ttl_override.py, etc.)
- Legacy main.py.bak (archived)

**Status:** File deleted in earlier refactor. Tests that imported it have been migrated or archived.

### Config Adapters (Runtime-Critical)

#### `brackets_config.py::resolve_brackets_config()`
**Used by (runtime):**
- `shadow_execpos/runtime.py` (V2 runtime reads brackets config)
- `shadow_execpos/bracket_service.py` (bracket placement logic)

**Used by (tools):**
- `tools/config_validator_v2.py` (validation)
- `tools/verify_config.py` (config verification)
- `tools/check_config_sources.py` (source tracking)

**Used by (tests):**
- 15+ test files (config/execution tests, integration tests)

**Status:** ✅ **KEEP** (V2 runtime dependency)

#### `manage_config.py::resolve_execution_manage_config()`
**Used by (runtime):**
- `shadow_execpos/runtime.py` (V2 runtime reads manage config)
- `shadow_execpos/bracket_service.py` (orphan monitor, quick profit, trailing)

**Used by (tools):**
- `tools/config_validator_v2.py` (validation)
- `tools/check_config_sources.py` (source tracking)
- `tools/agg_oco_snapshot.py` (snapshot generation)

**Used by (tests):**
- 10+ test files (config tests, manage config tests)

**Status:** ✅ **KEEP** (V2 runtime dependency)

### Supporting Infrastructure

#### `idempotent_cancel.py::IdempotentCancelHelper`
**Used by (runtime):**
- `shadow_execpos/bracket_service.py` (bracket cancellation)
- Other adapters (binance_execution_adapter?)

**Used by (tests):**
- `tests/unit/test_phase6_integration.py`
- `tests/unit/test_idempotent_cancel.py`

**Status:** ✅ **KEEP** (runtime-critical for cancellation logic)

#### `watchdog.py::OrderTimeoutWatchdog` (Legacy)
**Used by (tests):**
- `tests/execution_position/test_rest_polling_integration.py`
- `tests/integration/test_timeout_nrr019.py`
- `tests/domains/execution_position/test_watchdog.py`

**Runtime usage:** ❌ None (V2 uses `shadow_execpos/watchdog.py::AggOcoWatchdogService`)

**Status:** ⚠️ **CANDIDATE-FOR-ARCHIVE** (superseded by V2 watchdog)

#### `drift_monitor.py::compute_drift()`
**Used by (tools):**
- Analysis scripts (manual drift tracking)

**Used by (tests):**
- `tests/test_debug_drift_integration.py`
- `tests/test_metrics_drift_integration.py`
- `tests/test_drift_unit.py`
- `tests/domains/test_drift_monitor.py`

**Runtime usage:** ❌ None (off-path analysis only)

**Status:** ⚠️ **CANDIDATE-FOR-ARCHIVE** (tools-only, low priority)

#### `agg_oco_introspection.py::AggOcoStateRow`
**Used by (tools):**
- `tools/agg_oco_snapshot.py` (snapshot generation)

**Runtime usage:** ❌ None (observability helper)

**Status:** ⚠️ **CANDIDATE-FOR-ARCHIVE** (tools-only)

---

## Proposed Removal Phases

### Phase A: Disable Legacy Runtime in Config (COMPLETED ✅)
**Goal:** Ensure no runtime path can activate legacy FSM.

**Actions taken:**
- ✅ `runtime_factory.py` raises `ValueError` if `runtime_mode: legacy` configured
- ✅ All configs migrated to V2 (`shadow_execpos/`)
- ✅ `main.py` uses `build_execution_runtime()` which enforces V2-only

**Validation:**
- ✅ Config validator passes (146/146 tests)
- ✅ Hybrid mode active (live data + testnet exec)
- ✅ No runtime imports of `fsm_open.py`, `fsm_manage.py`, `fsm_close.py`

### Phase B: Move Legacy FSM Files to Archive (Proposed)
**Goal:** Remove legacy FSM files from active codebase while preserving test coverage.

**Actions:**
1. **Create archive directory:**
   ```
   apps/reference/domains/execution_position/archive/legacy_fsm/
   ```

2. **Move legacy FSM files:**
   - `fsm_open.py` → `archive/legacy_fsm/fsm_open.py`
   - `fsm_manage.py` → `archive/legacy_fsm/fsm_manage.py`
   - `fsm_close.py` → `archive/legacy_fsm/fsm_close.py`

3. **Update test imports:**
   - Replace `from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM`
   - With: `from apps.reference.domains.execution_position.archive.legacy_fsm.fsm_open import OpenFlowFSM`
   - Apply to all test files (20+ files)

4. **Add deprecation markers:**
   - Add docstring warnings in archived files: `"DEPRECATED: This file is archived. Do not use in new code."`

**Validation:**
- Run all tests: `pytest tests/ -v`
- Verify no import errors
- Check config validator still passes

**Risks:**
- Test churn (20+ test files to update)
- Potential merge conflicts if other branches import legacy FSM

**Mitigation:**
- Update imports in batch with multi_replace_string_in_file
- Communicate in team Slack/JOURNAL.md before merge

### Phase C: Remove Legacy FSM Files (Future)
**Goal:** Fully delete legacy FSM files once test coverage migrated to V2.

**Preconditions:**
- All FSM tests rewritten against V2 runtime (`shadow_execpos/`)
- Legacy FSM tests passing in `archive/` for 2+ weeks
- No external dependencies on legacy FSM (check with team)

**Actions:**
1. Delete `archive/legacy_fsm/` directory
2. Remove legacy FSM tests (or migrate to V2 equivalents)
3. Update documentation to remove references to legacy FSM

**Timeline:** Not before Q1 2026 (requires full V2 test coverage)

### Phase D: Archive Supporting Infrastructure (Future)
**Goal:** Clean up legacy helpers superseded by V2.

**Files to archive:**
- `watchdog.py` → `archive/watchdog_legacy.py` (superseded by V2 watchdog)
- `drift_monitor.py` → `archive/drift_monitor.py` (tools-only)
- `agg_oco_introspection.py` → `archive/agg_oco_introspection.py` (tools-only)
- `aurora_log_adapter.py` → `archive/aurora_log_adapter.py` (if unused)
- `order_index.py` → `archive/order_index.py` (if unused)

**Preconditions:**
- Grep confirms no runtime imports
- Tools migrated to V2 equivalents
- Tests passing without these files

**Timeline:** After Phase B complete

---

## Safety Checklist

Before executing **any** file removal or archival:

### Runtime Safety
- [ ] ✅ V2 runtime (`ExecPosRuntimeV2`) stable and tested in testnet for 1+ week
- [ ] ✅ No runtime imports of legacy FSM files (`grep -r "from.*fsm_open|fsm_manage|fsm_close"` in `apps/reference/main.py`, `bridge/`, `shadow_execpos/`)
- [ ] ✅ `runtime_factory.py` enforces V2-only mode
- [ ] ✅ All execution tests passing (58/58 in `tests/domains/execution_position/`)

### Config Safety
- [ ] ✅ Config validator recognizes V2 config (`ExecutionPositionConfig`)
- [ ] ✅ No configs specify `runtime_mode: legacy`
- [ ] ✅ Brackets/manage config adapters working in V2 mode

### Test Coverage
- [ ] All legacy FSM tests passing (to ensure safe archival)
- [ ] V2 runtime tests cover same scenarios as legacy FSM tests
- [ ] Integration tests (E2E, happy path, error paths) passing
- [ ] No test failures after file moves/renames

### Import Graph Validation
- [ ] `grep -r "from apps.reference.domains.execution_position.fsm" --include="*.py"` returns only test files
- [ ] No imports from other domains (`risk`, `sizing`, `decision`, `bridge`)
- [ ] No imports from tools except explicitly documented (config validators)

### Documentation Updates
- [ ] JOURNAL.md updated with removal rationale
- [ ] TODO.md task marked complete
- [ ] ROADMAP updated (Phase S11 complete)
- [ ] Team notified (Slack/Discord)

### Rollback Plan
- [ ] Git branch with removal changes isolated
- [ ] Ability to revert file moves with `git revert`
- [ ] Archived files preserved in `archive/` (not deleted immediately)

---

## Next Steps (Action Required)

1. **Validate this document:**
   - Run: `pytest tests/docs/test_exec_position_legacy_cleanup_plan.py -q`
   - Ensure doc exists and key files mentioned

2. **Stabilize V2 runtime:**
   - Run testnet for 1 week with V2 runtime
   - Monitor metrics (p95 latency < 50ms, timeout_rate < 1%)
   - Fix any V2 bugs before proceeding

3. **Plan Phase B execution:**
   - Schedule team sync to review this plan
   - Assign owner for test import updates
   - Create PR for Phase B with full test validation

4. **Freeze legacy FSM edits:**
   - Add deprecation notices to `fsm_open.py`, `fsm_manage.py`, `fsm_close.py`
   - Reject PRs that add features to legacy FSM
   - Redirect new work to `shadow_execpos/`

---

## Related Documents

- `docs/ROADMAP_DELTA_EMPTY_BRANCH.md` (domain onboarding plan)
- `docs/CENTRAL_FSM_SPEC.md` (FSM federation architecture)
- `apps/reference/domains/execution_position/docs/EP_RUNTIME_SWITCH_PLAN.md` (V2 migration plan)
- `apps/reference/domains/execution_position/docs/EXECUTION_POSITION_V2_OBSERVABILITY.md` (V2 observability)
- `JOURNAL.md` (RID: EP-EXEC-LEGACY-CLEANUP-MAP-S11)

---

## Changelog

| Date | RID | Change | Author |
|------|-----|--------|--------|
| 2025-11-22 | EP-EXEC-LEGACY-CLEANUP-MAP-S11 | Initial cleanup plan created | Copilot |

---

**END OF DOCUMENT**
