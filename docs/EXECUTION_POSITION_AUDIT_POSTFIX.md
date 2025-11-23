# EXECUTION_POSITION Domain Post-Audit Report

**Date:** 2025-11-20
**Auditor:** GitHub Copilot (Agent 2)
**Scope:** `apps/reference/domains/execution_position/` (FSM, ManageFlow, Watchdog)

## 1. Regression Audit (Fixed Problems Verification)

| Issue | Status | Findings |
| :--- | :--- | :--- |
| **NO_SL Auto-heal** | **VERIFIED** | `_heal_no_sl_for_open_position` is removed. Watchdog now only logs `NO_SL_FOR_OPEN_POSITION` via `_record_no_sl_watchdog_observation`. No automatic order placement occurs. |
| **Entry Price Fallback** | **VERIFIED** | `ManageFlowFSM._ensure_position_entry_price` correctly attempts fallback to `price_service`. If it fails, it returns `False`, causing `_compute_aggregated_bracket_levels` to return `None` (fail-closed). |
| **Price Enrichment** | **VERIFIED** | `ExecPosFSM._enrich_fill_price` is enforced in `_on_trade_executed` and `_emit_watchdog_event`. It checks `manage_flow`, `ws_cache`, and `price_service`. Events without valid price are dropped. |
| **Idempotency** | **VERIFIED** | `_should_process_fill` correctly filters duplicate fills using `_seen_fills` and `cum_qty`. `_processed_events` prevents duplicate event processing. `_cleanup_idempotency_store` manages memory. |
| **Auto-heal ORPHAN/TOO_MANY** | **VERIFIED** | `_heal_orphan_sl_for_zero_position` and `_heal_too_many_sl_for_open_position` only invoke `OrderGuardian` cleanup methods (cancels/clears). No new orders are created. |
| **Async Handling** | **VERIFIED** | `_submit_async` is consistently used for background tasks. `shutdown()` correctly stops `watchdog` and `order_guardian`. |

## 2. New Potential Risks & Bugs

### P1: Strict Pre-flight Check in `_handle_place_order_decision`
*   **Location:** `fsm.py` lines 4583-4596.
*   **Issue:** Before placing SL/TP, the FSM calls `await self._call_adapter_fn("get_open_positions", symbol=symbol)`. If this returns empty (e.g., due to REST latency or race condition where position is not yet visible in REST), the bracket placement is skipped with `TP_SL_SKIPPED_NO_POSITION`.
*   **Impact:**
    *   **Tests:** Causes multiple regression tests to fail (`test_agg_oco_runtime_pipeline_places_brackets`, etc.) because mocks don't simulate this REST call.
    *   **Production:** Adds a dependency on REST API reliability for *every* bracket placement. If Binance REST is lagging behind WS, we might skip SL placement.
*   **Recommendation:** Consider if `ManageFlowFSM`'s internal state tracking is sufficient for this check, or make the REST check optional/soft (warn but proceed if internal state says we have a position).

### P2: `ExecPosFSM` Complexity
*   **Issue:** `fsm.py` is ~5800 lines long. It mixes high-level event routing with low-level adapter calls, retry logic, and watchdog coordination.
*   **Impact:** Hard to maintain and test. High risk of regression during future changes.

## 3. Technical Debt Assessment (`fsm.py`)

**"Cluttered" Zones:**
1.  **`_handle_place_order_decision`**: Mixes decision parsing, pre-flight checks, retry logic (for -2021 error), and adapter calls.
2.  **`_on_trade_executed`**: Handles logging, enrichment, idempotency, exposure guard updates, order guardian updates, and delayed cleanup.
3.  **`_run_agg_oco_watchdog_once`**: Contains complex logic for fetching state, normalizing, validating, and triggering auto-heal.

**Refactoring Proposals (Future):**
1.  **`ExecPosIdempotency`**: Extract `_seen_fills`, `_processed_events`, `_should_process_fill`, `_cleanup_idempotency_store` into a dedicated helper class.
2.  **`ExecPosAsync`**: Extract `_bg_tasks`, `_submit_async`, `_await_tasks_blocking` into a task manager.
3.  **`ExecPosWatchdogCoordinator`**: Move the aggregated watchdog loop and `_run_agg_oco_watchdog_once` logic to a separate class (e.g., `AggOcoWatchdogService`).
4.  **`PriceEnricher`**: Move `_enrich_fill_price` logic to a standalone service or helper.

## 4. Test Results
*   **Command:** `pytest tests/domains/execution_position -q`
*   **Result:** **FAILED** (5 failures, 111 passed).
*   **Cause:** The new pre-flight position check in `_handle_place_order_decision` fails in tests because mocks do not return open positions.
*   **Action Required:** Update tests to mock `get_open_positions` response, or relax the pre-flight check.

## 5. Conclusion
The targeted fixes (NO_SL, Idempotency, etc.) are **correctly implemented and verified**. The system is safer against infinite loops and duplicate orders. However, the strict "pre-flight check" introduced for safety has broken existing tests and introduces a potential liveness risk if REST API is degraded. This should be addressed in the next iteration.
