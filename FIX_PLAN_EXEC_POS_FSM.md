# Plan to Fix `apps/reference/domains/execution_position/fsm.py`

## 1. Immediate Fix: Remove Broken Tail Code
**Problem:** The file ends with a block of code (lines 2605-2688) that is not inside any function/method, causing a `NameError` on import because `self` is undefined at module level. This code appears to be a duplicate/broken version of `_startup_order_guardian_reconcile`.
**Action:** Delete lines 2605-2688.

## 2. Refactor Configuration to `AuroraConfig`
**Problem:** The class `ExecPosFSM` heavily relies on `isinstance(self.config, dict)` checks and manual traversal of nested dictionaries, which is "Config Hell".
**Action:**
- Update `__init__` to enforce `AuroraConfig` (or convert dict to `AuroraConfig` immediately).
- Replace all `self.config.get(...)` and `isinstance` checks with direct attribute access on `AuroraConfig` models.
- Ensure `AuroraConfig` has the necessary nested models (`ExecutionConfig`, `OrderGuardianConfig`, `WatchdogConfig`, `OrphanMonitorConfig`). *Note: I need to verify/add these models to `config_models.py` if missing.*

## 3. Remove Dead Code
**Problem:**
- `_preflight_position_check_nonzero` is unused.
- `_check_qty_step` / `_check_price_step` (if present in this file, though they were in `fsm_open.py`).
**Action:** Delete `_preflight_position_check_nonzero`.

## 4. Standardize Hardcoded Parameters
**Problem:** Many parameters have hardcoded defaults scattered throughout the code (e.g., `poll_interval_ms=500`, `cleanup_ttl_ms=6000`).
**Action:**
- Define constants at the top of the file for these defaults.
- Use `AuroraConfig` fields to override these defaults.

## 5. Test Coverage & Fixes
**Problem:** Existing tests likely use dict configs and will break when we enforce `AuroraConfig`.
**Action:**
- Update `tests/units/test_execution_position_fsm_unit.py` to use `AuroraConfig` objects.
- Add new tests to cover:
    - `_startup_order_guardian_reconcile`
    - `_check_exposure_fail_closed`
    - `_handle_order_timeout`
    - `_on_portfolio_state_updated`

## Execution Steps
1.  **Delete Tail Code:** Make the file importable.
2.  **Verify Config Models:** Check `apps/reference/config_models.py` and add missing models if needed.
3.  **Refactor `ExecPosFSM`:** Implement `AuroraConfig` usage.
4.  **Update Tests:** Fix and expand tests.
5.  **Verify:** Run `pytest`.
