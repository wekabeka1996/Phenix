# Execution Position Diagnostic Report (V1)
**Date:** 2025-12-19
**Scope:** `execution_position` domain contracts.

## 🟢 Summary
Six (6) critical diagnostic contract tests were implemented and executed. **All tests PASSED**, confirming the following baseline behaviors are enforcing safety correctly in the current implementation.

## 📋 Test Results

| Test ID | Contract / Behavior | Status | Notes |
| :--- | :--- | :--- | :--- |
| `test_diag_fail_closed_missing_portfolio` | **Fail-Closed Safety**: Rejects OPEN if portfolio state/equity is unknown. | ✅ PASS | Verified `ExposureGuard` returns `allowed=False` on empty state. |
| `test_diag_reject_below_min_notional` | **Exchange Compliance**: Rejects orders < $5.00 (`MIN_NOTIONAL`). | ✅ PASS | Verified `OpenFlowFSM` emits `ERR:OPEN`. |
| `test_diag_idempotency_duplicate_open` | **Idempotency**: Duplicate `CMD:OPEN` with same key is rejected. | ✅ PASS | Second attempt returns `ERR:OPEN` (Duplicate). |
| `test_diag_partial_fill_accounting` | **State Consistency**: Partial fill keeps position `OPENED`. | ✅ PASS | Flow state remains active, preventing premature closure. |
| `test_diag_reduce_only_close_safety` | **Risk Control**: Closer orders must be `reduce_only=True`. | ✅ PASS | Verified `DEC:CLOSE` payload. |
| `test_diag_ttl_timeout_safety` | **Liveness**: Watchdog triggers timeout callback on TTL expiry. | ✅ PASS | Verified callback invocation with correct `OrderDeadline`. |

## 🔍 Observations & Risks
While the contracts hold, the test harness setup revealed several fragility points in the codebase:
1.  **Tight Coupling**: `ExecPosFSM` is tightly coupled to `BinanceAdapter` (direct import) and `sqlite3` (via `OrderGuardian`), making unit testing difficult without heavy mocking.
2.  **Config Fragility**: `AuroraConfig` requires a strictly populated environment (including `trading.risk` dictionary), or it fails hard.
3.  **Watchdog API**: The watchdog uses internal async loops (`_check_timeouts`) which are hard to test deterministically without `asyncio` manipulation.

## 🛠️ Next Steps
1.  **Refactor for Testability**: Dependency Injection for `OrderGuardian` and `BinanceAdapter` would simplify testing.
2.  **Expand Coverage**: Add tests for `fsm_manage.py` (TP/SL modification logic) which was not covered in this pass.
3.  **Memory Leak Test**: A long-running test for `_processed_events` set growth in `fsm.py` (identified in Risk Map) is still recommended.
