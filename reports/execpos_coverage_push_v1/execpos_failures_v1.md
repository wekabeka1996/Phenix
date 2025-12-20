# Execution Position - Failures Report (Push v1)

## Summary of Failures
The following tests are currently failing, documenting critical bugs and architectural gaps in the `execution_position` domain.

| Test Case | Module | Failure Type | Root Cause (Bug Candidate) |
|-----------|--------|--------------|---------------------------|
| `test_manage_respects_reduce_only_on_close_intent` | `fsm_manage.py` | AssertionError | `DEC:CLOSE_POSITION` mission `reduce_only` field in payload. |
| `test_fsm_routes_ack_via_on_order_ack` | `fsm.py` | AssertionError | `EVT:ORDER_ACK` from bus is not routed to `watchdog.on_order_ack`. |
| `test_execpos_processed_events_unbounded_leak_risk` | `fsm.py` | Memory Leak | `_processed_events` set grows indefinitely without TTL or size capping. |
| `test_guard_deny_max_equity_utilization` | `exposure_guard.py` | Logic Error | Risk limit breach not detected by `can_open`. |
| `test_guard_deny_max_portfolio_fraction` | `exposure_guard.py` | Logic Error | Risk limit breach not detected by `can_open`. |
| `test_guard_deny_max_long_utilization` | `exposure_guard.py` | Logic Error | Risk limit breach not detected by `can_open`. |

## Detailed Bug Forensics

### 1. `fsm_manage.py`: Missing `reduce_only` [High Priority]
The FSM emits `CLOSE_POSITION` upon max hold time timeout but fails to include the `reduce_only` flag. This could lead to unwanted position flips if the position size is already reduced (e.g. by partial fill) when the market order is placed.
*   **Loc**: `fsm_manage.py:346 (_check_max_hold_time)`

### 2. `fsm.py`: Missing Watchdog Ack-Routing [Medium Priority]
The `ExecPosFSM` listens to `EVT:ORDER_ACK` on the bus but its internal handler `_on_order_ack` only releases pre-fill holds (in design, currently NOP) and doesn't notify the `OrderTimeoutWatchdog`. The watchdog is only notified if a REST response is processed directly in other parts of the code.
*   **Loc**: `fsm.py:750 (_on_order_ack)`

### 3. `fsm.py`: Memory Leak Risk (Unbounded Deduplication) [CRITICAL]
The `_processed_events` set in `ExecPosFSM` is used for idempotency but has no mechanism for expiration or pruning. In high-frequency environments, this will cause a slow memory leak as millions of order IDs are stored.
*   **Loc**: `fsm.py:100 (__init__)` -> `_processed_events` initialization.

### 4. `exposure_guard.py`: Risk Limit Breach Logic [High Priority]
Multiple limits (utilization, fraction, directional) failed to trigger `allowed=False` even when forced by test parameters. This suggests a logic error in `can_open()` or `Decimal` arithmetic within the guard.
*   **Loc**: `exposure_guard.py:660+ (can_open checks)`
