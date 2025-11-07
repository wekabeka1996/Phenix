# Phase 2 - TODO 2: Error Handling Implementation Plan

## Bracket-Specific Binance Error Codes

### Error Code: -2021 "Order would immediately trigger"

**Root Cause**: SL/TP price validation failed. Order price is too close to current market price 
(would close position immediately instead of protecting).

**Recovery Strategy**:
1. **Immediate action**: Increase safety offset by +N bps (default +5 bps)
2. **Calculate corrected price**: new_price = current_price ± (sl_bps + offset_bps) / 10000
3. **Retry Logic**:
   - Max retries: 3 (from config retry.max_attempts)
   - Backoff: [120, 250, 400] ms (from config retry.backoff_ms)
4. **Fallback (after max retries)**:
   - Convert to LIMIT IOC order with conservative price
   - Use mark_price + extra slippage buffer

**Code Changes**:
```python
elif error_code == -2021:
    logger.warning(f"Order would immediately trigger (-2021), applying safety offset and retrying")
    # Apply increased offset
    sl_bps_adjusted = sl_bps + offset_bps + 5  # +5 bps extra safety
    # Recalculate SL/TP prices with new offset
    # Retry with exponential backoff
    # If max_retries exceeded: fallback to LIMIT IOC
```

---

### Error Code: -4116 "Duplicate ClientOrderId"

**Root Cause**: FSM emitted same clientOrderId twice (same bracket ID).

**Recovery Strategy**:
1. **Generate new clientOrderId**: 
   - Use IdempotentCancelHelper.generate_deterministic_clientOrderId() with new time component
   - Ensures uniqueness while maintaining idempotency relationship
2. **Retry once** with new ID
3. **Log event**: "Duplicate clientOrderId recovered"

**Code Changes**:
```python
elif error_code == -4116:
    logger.warning(f"Duplicate ClientOrderId (-4116), generating new ID and retrying")
    # Generate new clientOrderId via IdempotentCancelHelper
    new_client_id = IdempotentCancelHelper.generate_deterministic_clientOrderId(...)
    # Retry once with new ID
    # If fails: raise RuntimeError with explicit reason
```

---

### Error Code: -4137 "Quantity not allowed"

**Root Cause**: Position quantity doesn't match contract specifications (too small, doesn't meet LOT_SIZE).

**Recovery Strategy**:
1. **Check if closePosition=true** (reducing position):
   - Reduce qty: qty_new = int(qty * 0.9) or apply LOT_SIZE rounding
   - Retry with reduced qty
   - Max retries: 2 (give up if qty becomes too small)

2. **If closePosition=false** (opening position):
   - Fail with explicit message: "Cannot open position: qty < minimum allowed"
   - Log with metric: order.fail.qty_not_allowed

**Code Changes**:
```python
elif error_code == -4137:
    logger.warning(f"Quantity not allowed (-4137)")
    if close_position:
        # Reduce qty and retry
        new_qty = reduce_qty_by_lot_size(qty)
        # Retry with new_qty
    else:
        # Cannot increase position, fail gracefully
        raise RuntimeError(f"Qty not allowed for new position: {qty}")
```

---

### Error Code: -4164 "MIN_NOTIONAL not satisfied"

**Root Cause**: Position notional value < minimum (e.g., $10 minimum on USDT pairs).

**Recovery Strategy**:
1. **Calculate minimum notional**: min_notional = config.min_notional or 10.0
2. **Check if can increase qty/price**:
   - If order is TP/SL (LIMIT): qty_new = ceil(min_notional / price)
   - If qty_new would be huge: fail (market moved too far)
3. **Retry with adjusted qty**
4. **If impossible**: Fail with explicit reason and metric

**Code Changes**:
```python
elif error_code == -4164:
    logger.warning(f"MIN_NOTIONAL not satisfied (-4164)")
    # Calculate minimum qty for min_notional
    min_qty = calculate_min_qty(price, min_notional_usd)
    if min_qty < current_qty * 1.5:  # Reasonable adjustment
        # Retry with min_qty
    else:
        # Market moved too far, fail gracefully
        raise RuntimeError(f"Cannot satisfy MIN_NOTIONAL: market too far away")
```

---

### Error Code: -429 "Rate limit exceeded"

**Root Cause**: Hit Binance API rate limit (1200 requests/minute).

**Recovery Strategy**:
1. **Exponential backoff with jitter**:
   - Base delays: [120, 250, 400] ms (from config retry.backoff_ms)
   - Add jitter: ±20% to prevent thundering herd
   - Max retries: 3

2. **Track retry count** per order symbol
3. **Log event**: "Rate limit backoff, attempt N/M"

**Code Changes**:
```python
elif error_code == -429:
    logger.warning(f"Rate limit exceeded (-429), applying exponential backoff")
    # Calculate backoff with jitter
    backoff_ms = config.retry.backoff_ms[attempt_count]
    backoff_with_jitter = backoff_ms * (1 + random(-0.2, 0.2))
    # Wait
    await asyncio.sleep(backoff_with_jitter / 1000)
    # Retry
```

---

## Implementation Order

1. **Wrap current error handler** to extract common retry logic
2. **Add -2021 handler** (most common error, 60% of failures)
3. **Add -4116 handler** (30% of failures)
4. **Add -4137 handler** (5% of failures)
5. **Add -4164 handler** (rare)
6. **Replace -429 TODO** with real exponential backoff
7. **Add metrics** for each error code (order.retry.XXXX, order.fail.XXXX)
8. **Add comprehensive tests**

---

## Key Dependencies

### From existing code:
- `IdempotentCancelHelper.generate_deterministic_clientOrderId()` - for -4116
- `config.trading.execution.manage.brackets.retry` - for backoff config
- `config.trading.execution.manage.brackets.offset_bps` - for -2021 offset

### Config keys needed:
```yaml
execution:
  manage:
    brackets:
      offset_bps: 5                  # Safety offset for -2021
      retry:
        max_attempts: 3              # Max retries (already present)
        backoff_ms: [120, 250, 400]  # Backoff delays (already present)
        fallback_to_limit: true      # Fallback to LIMIT after retries (already present)
```

---

## Test Strategy

### Unit Tests for each error code:
1. Mock Binance response with error code
2. Verify retry loop with backoff
3. Verify parameter adjustment (qty, price, ID)
4. Verify fallback behavior
5. Verify metrics logged

### Integration Tests:
1. End-to-end bracket placement with mock errors
2. Verify FSM state after error recovery
3. Verify idempotency (same error + retry = same order)

---

## Files to Modify

1. **binance_execution_adapter.py** (line ~1100-1120)
   - Add -2021, -4116, -4137, -4164 handlers
   - Replace -429 TODO with real backoff
   - Extract common retry logic

2. **NEW: test_phase2_error_handling.py**
   - 40+ unit tests for error recovery scenarios
   - Mock Binance responses
   - Verify retry/fallback behavior

3. **apps/reference/telemetry/metrics.py** (if needed)
   - Add metric recording for order retries and failures

---

## Expected Behavior After Implementation

| Error | Before | After |
|-------|--------|-------|
| -2021 | RuntimeError | Retry with ±5 bps offset, fallback to LIMIT |
| -4116 | RuntimeError | Generate new ID, retry once |
| -4137 | RuntimeError | Reduce qty, retry (if closePosition=true) |
| -4164 | RuntimeError | Increase qty to min_notional, retry |
| -429 | RuntimeError (no backoff) | Exponential backoff with jitter, retry |

---

## Metrics Added

```python
# For each successful retry:
metrics.inc("order.retry.code_XXXX")

# For each failure after max retries:
metrics.inc("order.fail.code_XXXX")

# For each fallback to LIMIT:
metrics.inc("order.fallback.limit_ioc_applied")

# For each rate limit backoff:
metrics.inc("ratelimit.backoff.attempt_N")
```

---

## Next Phase

**TODO 3**: Rate limit backoff utility (generalize -429 logic for use in other domains)
