# Deep Investigation: Execution Position & Aggregator OCO

**Date:** 2025-11-30
**Subject:** Investigation of TP/SL placement failures for multiple positions (Aggregator OCO)
**Status:** CRITICAL FINDINGS

## Executive Summary

The investigation confirms that the system architecture has a critical bottleneck in the `ExecutorPoolV2` combined with the `ExecPosRuntimeV2` orchestration logic. When multiple positions are opened simultaneously (or in quick succession), the global rate limiter (8 orders/sec) in `ExecutorPoolV2` rejects subsequent bracket placement requests. The runtime **does not retry immediately** and instead relies on the `guard_loop` to heal the state. However, the `guard_loop` is throttled by default (5 seconds), causing a significant delay or apparent "ignoring" of TP/SL for secondary positions.

## Architecture Overview

### 1. Component Chain
1.  **Entry Intent:** `ExecPosRuntimeV2` receives `ENTRY_INTENT`.
2.  **Execution:** `ExecutorPoolV2.execute_entry()` places the entry order.
3.  **Fill Event:** `BinanceAdapter` emits `ORDER_TRADE_UPDATE` -> `TRADE_EXECUTED`.
4.  **Bracket Evaluation:** `ExecPosRuntimeV2._handle_trade_executed` calls `_evaluate_brackets`.
5.  **Planning:** `aggregator_oco.engine.compute_bracket_plan_core` calculates needed TP/SL.
6.  **Application:** `ExecPosRuntimeV2._apply_bracket_plan` executes the plan via `ExecutorPoolV2`.

### 2. Sync/Async Boundaries
*   **ExecPosRuntimeV2:** Fully **Async** (asyncio). Orchestrates events.
*   **ExecutorPoolV2:** **Synchronous** (threading). Designed to run in `ThreadPoolExecutor`.
*   **BinanceAdapter:** **Async** (httpx) but some methods are wrapped/called synchronously by `ExecutorPoolV2`.

## Critical Findings

### 1. Rate Limiting Drop (The "Ignore" Cause)
`ExecutorPoolV2` enforces a strict global rate limit:
```python
# ExecutorPoolV2
self._rate_limiter = RateLimiter(
    max_requests=max_orders_per_second, # Default 8
    window_seconds=1.0,
)
```
When `execute_bracket` is called, it checks `try_acquire()`. If it fails, it returns `success: False`.

In `ExecPosRuntimeV2._apply_bracket_plan`:
```python
# runtime.py
result = await loop.run_in_executor(
    self._executor_thread_pool,
    lambda: self.executor_pool.execute_bracket(...)
)

if isinstance(result, dict) and result.get("success") is False:
    # LOGS WARNING BUT CONTINUES!
    continue
```
**Impact:** If the rate limit is hit (which is easy with >1 position, as each needs 2 orders: SL + TP), the bracket placement is **dropped** for the current cycle.

### 2. Recovery Latency (The "Delay")
The system relies on `guard_loop` to fix missing brackets. However:
1.  `guard_loop` runs every 1s (`GUARD_LOOP_INTERVAL_SEC`).
2.  **CRITICAL:** It checks `_bracket_throttle_sec` (Default 5s).
```python
# runtime.py
effective_throttle = 2.0 if reason == "trade_executed" else self._bracket_throttle_sec
if elapsed < effective_throttle:
    return None
```
**Impact:** If the initial `trade_executed` bracket placement fails due to rate limits, the `guard_loop` will likely be throttled for 5 seconds before retrying. To the user, this looks like the system "ignored" the position.

### 3. Concurrency Bottleneck
The `ExecutorPoolV2` uses a `ThreadPoolExecutor` with `max_workers=8`. While this allows parallel execution, the **Global Rate Limiter** is the shared constraint. Increasing workers won't help; it will just hit the rate limit faster.

## Detailed Analysis of Functions

| Function | Type | Location | Issue |
| :--- | :--- | :--- | :--- |
| `_apply_bracket_plan` | Async | `runtime.py` | Drops actions on `success: False` from executor. No retry queue. |
| `execute_bracket` | Sync | `executor_pool.py` | Returns failure immediately on rate limit. |
| `guard_loop` | Async | `runtime.py` | Throttled by `_bracket_throttle_sec` (5s), too slow for recovery. |
| `_evaluate_brackets` | Async | `runtime.py` | Blocks if `awaiting_snapshot` is true, which can happen on timeouts. |

## Recommendations

1.  **Implement Retry Queue in Runtime:**
    Modify `_apply_bracket_plan` to handle `Rate limited` errors by scheduling a retry task with a short backoff (e.g., 100ms), rather than dropping the action.

2.  **Smart Throttling:**
    If `guard_loop` detects a *missing* bracket (Severity: ALERT), it should bypass the `_bracket_throttle_sec` or use a much shorter throttle (e.g., 0.5s).

3.  **Batch Execution:**
    Ensure `execute_batch` is used effectively. Currently `_apply_bracket_plan` iterates and calls `execute_bracket` individually (or via `execution_service` which might not use the batch optimization if not configured). `ExecutorPoolV2` has `execute_batch`, but `runtime.py` seems to call `execute_bracket` in a loop (or `execution_service.place_order`).

4.  **Rate Limit Tuning:**
    Consider increasing `max_orders_per_second` if the exchange tier allows, or implementing a "burst" capacity in `RateLimiter`.

## Conclusion
The system is behaving "correctly" according to its code (protecting against rate limits), but the user experience is broken because the "protection" simply drops the request and waits for a slow background process to pick it up.

**Immediate Fix:** Modify `runtime.py` to retry rate-limited bracket actions immediately with a backoff.
