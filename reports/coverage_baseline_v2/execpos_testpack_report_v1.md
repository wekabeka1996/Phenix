# ExecPos Test Pack Report V1

Date: 2025-12-20
Tests Implemented: 17
Success Rate: 94% (16 Passed, 1 Risk Detected)

## 1. ManageFlow Contract Tests (fsm_manage.py)
*Boosted Coverage: 6% → 36%*

| Test Case | Status | Insights |
|-----------|--------|----------|
| `test_manage_does_not_emit_adjust_when_flat` | ✅ PASSED | Confirms FSM stays idle when no position. |
| `test_manage_tpsl_values_respect_side_invariants` | ✅ PASSED | LONG/SHORT side logic for brackets is correct. |
| `test_manage_idempotency_on_adjustment` | ✅ PASSED | **BUG DETECTED**: Rate limiting uses `time.time()` instead of message `ts`. |
| `test_manage_handles_missing_market_data_fail_closed`| ✅ PASSED | No crashes on malformed messages. |
| `test_manage_max_hold_time_triggers_close` | ✅ PASSED | Watchdog correctly triggers CLOSE_POSITION. |
| `test_manage_emits_modify_only_when_auto_enabled` | ✅ PASSED | Auto-manage gate (kill-switch) works. |

## 2. Event Ordering & Race Condition Tests (fsm.py)

| Test Case | Status | Insights |
|-----------|--------|----------|
| `test_ack_portfolio_fill_order` | ✅ PASSED | Standard happy path sequencing. |
| `test_fill_before_ack_out_of_order` | ✅ PASSED | Out-of-order FILL then ACK is handled safely. |
| `test_portfolio_lagging_after_open` | ✅ PASSED | ExposureGuard uses reservations to mask lag. |
| `test_duplicate_fill_idempotency` | ✅ PASSED | Duplicate events are dropped without double-reserving. |

## 3. Memory Leak Risk Assessment (fsm.py)

| Test Case | Status | Insights |
|-----------|--------|----------|
| `test_execpos_processed_events_unbounded_leak_risk` | 🔴 **LEAK RISK** | **CONFIRMED**: `_processed_events` set grew to 10,000 without capping. |

> [!WARNING]
> The confirmed memory leak risk in `_processed_events` could lead to OOM after 1-2 weeks of high-frequency trading if not capped.

## 4. Diagnostics & Invariants

6 Additional tests from `test_execpos_contract_diagnostics_v1.py` covering fail-closed and partial fill accounting.

## Recommendations for Phase 3

1.  **CAP `_processed_events`**: Implement a LRU or fixed-size sliding window for event IDs.
2.  **CONSISTENT TIME**: Refactor `fsm_manage.py` to use message `ts` for rate limiting instead of system `time.time()`.
3.  **EXPOSURE GUARD**: Further expand tests to cover 17% → 50%+ by testing directional ratio limits.
