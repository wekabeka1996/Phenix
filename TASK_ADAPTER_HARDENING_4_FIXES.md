# TASK: Adapter Hardening - 4 Critical Fixes

**Created**: 2025-11-27
**Priority**: P0 (Production-blocking issues)
**Source**: Log analysis from `logs/aurora_core.log` 00:41:45-00:42:17

---

## Executive Summary

Analysis of `aurora_core.log` revealed 4 interconnected issues in `binance_execution_adapter.py`:

1. **MIN_NOTIONAL (-4164)**: BTCUSDT order rejected because notional ~99.24 < 100 USDT
2. **ExecutionService logs SUCCESS on timeout**: `SHADOW_EXEC_POS_PLACE_SUCCESS` logged despite `ConnectTimeout`
3. **Time sync + -1021 handling**: Mixed mainnet/testnet endpoints, aggressive `recvWindow=5000`
4. **Missing telemetry**: No visibility into bracket error patterns

---

## TASK 1: Update MIN_NOTIONAL and Pre-flight Validation

### Problem
- BTCUSDT `min_notional=10.0` in config, but Binance requires **100 USDT** for BTCUSDT futures
- Order: `qty=0.0011 * price=90215.70 = 99.24 USDT` → rejected with -4164
- `_validate_min_notional()` passed because local config has stale value

### Solution

1. **Update `system_config.yaml` instruments section**:
   - BTCUSDT: `min_notional: 100.0`
   - ETHUSDT: `min_notional: 20.0` (verify current Binance value)
   - SOLUSDT: `min_notional: 5.0` (verify current Binance value)
   - BNBUSDT: `min_notional: 20.0` (verify current Binance value)

2. **Enhance `_handle_bracket_error()` logging for -4164**:
   ```python
   # Log: symbol, qty, price, notional, min_notional, mark_price
   logger.warning(
       "[BinanceAdapter] MIN_NOTIONAL violation",
       extra={
           "symbol": symbol,
           "qty": qty,
           "price": price,
           "notional": qty * price,
           "min_notional": profile.min_notional,
           "mark_price": mark_price,
       }
   )
   ```

3. **Add unit test for MIN_NOTIONAL edge case**:
   - Test: BTCUSDT order with notional=99.23 → must fail in `_validate_min_notional()`

### Files to Modify
- `system_config.yaml` (instruments.BTCUSDT.limits.min_notional)
- `binance_execution_adapter.py` (_handle_bracket_error, _validate_min_notional)
- `tests/domains/execution_position/test_min_notional_validation.py` (new)

---

## TASK 2: Fix ExecutionService Timeout Logging

### Problem
- Log shows `SHADOW_EXEC_POS_PLACE_SUCCESS` for BNB brackets
- But adapter threw `ConnectTimeout`
- Root cause: adapter returns success=True before exception path kicks in

### Analysis
- `execution_service.py` correctly logs `SHADOW_EXEC_POS_PLACE_FAILED` for exceptions
- But adapter's `_place_binance_order_async()` has a mixed success/error return path
- When adapter catches `ConnectTimeout`, it returns `{"success": False, "error": ..., "error_kind": "ADAPTER_ERROR_TIMEOUT"}`
- This IS correct behavior - the SUCCESS log must be coming from a different code path

### Verify
- Check if `SHADOW_EXEC_POS_PLACE_SUCCESS` is logged anywhere else besides `execution_service.py`
- The log shows SUCCESS immediately after timeout exception - suspect race or parallel call

### Solution
1. Add `is_timeout` field check before logging SUCCESS
2. Ensure no SUCCESS log without explicit `response.get("success") == True`
3. Add test: mock `ConnectTimeout` → verify only FAILED logged, never SUCCESS

### Files to Modify
- `execution_service.py` (review _execute_place success path)
- `tests/domains/execution_position/shadow_execpos/test_execution_service_timeout_only_failed.py` (new)

---

## TASK 3: Harden get_open_orders + Time Sync for Testnet

### Problem
- `ConnectTimeout` on `get_open_orders` → 3 retries → `ADAPTER_GET_OPEN_ORDERS_FAILED`
- Then `-1021` timestamp error on retry
- Mixed endpoints: testnet for orders, mainnet for time sync

### Analysis
1. BASE_URL = `testnet.binancefuture.com` (deprecated, should be `demo-fapi.binance.com`)
2. `_sync_time_with_server()` uses same BASE_URL (good)
3. But `recvWindow=5000` is aggressive for unstable testnet

### Solution
1. **Update BASE_URL default**:
   ```python
   BASE_URL = os.environ.get("BINANCE_FUTURES_BASE_URL",
                             "https://demo-fapi.binance.com")  # Updated testnet URL
   ```

2. **Increase recvWindow for testnet**:
   - `get_open_orders`: 5000 → 20000 (testnet only)
   - `_get_signed_params`: add testnet detection

3. **Softer fallback for -1021**:
   - Don't throw RuntimeError on -1021 after 3 attempts
   - Enter fallback mode and return `[]` (already implemented, verify)
   - Don't trigger WATCHDOG_VIOLATION for time sync issues alone

4. **Add test for -1021 fallback**:
   - Mock -1021 response 3 times → verify returns `[]`, enters fallback mode, no RuntimeError

### Files to Modify
- `binance_execution_adapter.py` (BASE_URL, recvWindow, _sync_time_with_server)
- `tests/domains/execution_position/test_binance_adapter_time_sync.py` (extend)

---

## TASK 4: Telemetry for Bracket Errors

### Problem
- No aggregated visibility into how often we hit -4164, -2021, -429, etc.
- Can't track recovery success rate

### Solution
1. **Add bracket error metrics logging**:
   ```python
   # In _handle_bracket_error() - log to dedicated JSONL
   bracket_error_logger.log({
       "ts_ms": int(time.time() * 1000),
       "symbol": symbol,
       "error_code": error_code,
       "qty_before": original_qty,
       "qty_after": adjusted_qty,
       "notional_before": original_qty * price,
       "notional_after": adjusted_qty * price,
       "recovered": success,
       "attempt": attempt,
   })
   ```

2. **Create `logs/bracket_errors.jsonl`**:
   - One line per bracket error attempt
   - Include recovery outcome

3. **Add `/debug/bracket_errors` endpoint** (optional FastAPI):
   - Show last 100 errors
   - Show error_code distribution

### Files to Modify
- `binance_execution_adapter.py` (_handle_bracket_error)
- `apps/reference/domains/execution_position/bracket_telemetry.py` (new)

---

## Implementation Order

1. **TASK 1** (highest impact): Fix MIN_NOTIONAL to prevent -4164
2. **TASK 3** (stability): Update testnet URL and recvWindow
3. **TASK 2** (correctness): Fix SUCCESS/FAILED logging
4. **TASK 4** (observability): Add telemetry

---

## Acceptance Criteria

- [x] BTCUSDT min_notional=100.0 in config
- [x] Test: order with notional=99.23 fails pre-flight validation
- [x] No `SHADOW_EXEC_POS_PLACE_SUCCESS` when adapter returns timeout
- [x] BASE_URL default is `demo-fapi.binance.com`
- [x] recvWindow=20000 for testnet get_open_orders
- [ ] Bracket errors logged to `logs/bracket_errors.jsonl` (TASK 4 - deferred)

---

## References

- [Binance Error Codes](https://developers.binance.com/docs/derivatives/portfolio-margin/error-code)
- [Binance USDT-M Testnet](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info)
- Log: `logs/aurora_core.log` 2025-11-27 00:42:16
