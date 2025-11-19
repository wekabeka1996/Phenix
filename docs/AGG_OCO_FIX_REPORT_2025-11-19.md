# AGG_OCO Fix Report - 2025-11-19

## Overview
This report details the resolution of two critical defects in the Aggregated OCO (One-Cancels-Other) logic within the `execution_position` domain.

## Defects Addressed

### 1. Startup Missing Brackets (Defect #1)
**Issue:** When the system restarted with an open position but no active orders (e.g., after a crash or manual cancellation), it failed to restore the necessary Stop Loss (SL) and Take Profit (TP) brackets.
**Root Cause:** The `_startup_order_guardian_reconcile` method in `ExecPosFSM` did not check for existing positions lacking brackets.
**Fix:**
- Modified `apps/reference/domains/execution_position/fsm.py`.
- Added `_ensure_brackets_for_existing_positions` method.
- This method iterates through all open positions on startup.
- It checks if `OrderGuardian` has active brackets for the position.
- If not, it triggers `_recalc_aggregated_brackets` to generate and place new brackets.
- **Verification:** `test_startup_missing_brackets_bug` in `tests/domains/execution_position/test_agg_oco_integration.py` now passes.

### 2. Recalc Duplication (Defect #6)
**Issue:** When a position size changed (e.g., scale-in), the system placed new brackets without cancelling the existing ones, leading to duplicate SL/TP orders and potential over-execution.
**Root Cause:** The `_recalc_aggregated_brackets` method in `ManageFlowFSM` generated new orders but did not explicitly request the cancellation of old ones.
**Fix:**
- Modified `apps/reference/domains/execution_position/fsm_manage.py`.
- Added `_cancel_active_brackets` helper method.
- Updated `_recalc_aggregated_brackets` to call `_cancel_active_brackets` before generating new placement decisions.
- The system now emits `CANCEL_ORDER` commands for existing SL/TP orders before placing new ones.
- **Verification:** `test_recalc_duplication_bug` in `tests/domains/execution_position/test_agg_oco_integration.py` now passes.

## Verification Summary

### Integration Tests
A new test suite `tests/domains/execution_position/test_agg_oco_integration.py` was created to reproduce and verify these defects.

| Test Case | Status | Notes |
|-----------|--------|-------|
| `test_nominal_flow_open_position` | PASSED | Baseline test for normal operation. |
| `test_startup_missing_brackets_bug` | PASSED | Verifies brackets are restored on startup. |
| `test_recalc_duplication_bug` | PASSED | Verifies old brackets are cancelled on recalc. |

### Regression Tests
Existing contract tests were run to ensure no side effects.

| Test Suite | Status |
|------------|--------|
| `tests/domains/execution_position/test_contract_aggregated_orders_mode.py` | PASSED (9/9) |

## Code Changes
- `apps/reference/domains/execution_position/fsm.py`: Added startup reconciliation logic.
- `apps/reference/domains/execution_position/fsm_manage.py`: Added cancellation logic to recalc flow.

## Next Steps
- Monitor logs for `[Startup] Restoring missing brackets` messages to confirm behavior in production.
- Ensure `OrderGuardian` state is accurately persisted to support this logic (already assumed by current implementation).
