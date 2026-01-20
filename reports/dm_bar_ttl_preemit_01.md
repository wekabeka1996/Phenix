# DM-BAR-TTL-PREEMIT-01: Fix Report

## Summary
Fixed the `features_stale` block in `DecisionMaking._features_ready` to use bar-aware TTL logic, mirroring the existing Gate 5 implementation.

---

## 1. Root Cause (Localized)

**File**: `apps/reference/domains/decision_making/decision_making.py`
**Method**: `_features_ready` (lines 2251-2321)
**Called by**: `_warmup_gate_before_trade_intent` (line ~2330)

### Before (Broken)
```python
def _features_ready(self, symbol: str, features_data: dict) -> bool:
    """Check if features are fresh within TTL."""
    # ...
    now_ts = self._clock.now_ms()
    features_ts = features_data["ts"]  # bar_close_ts for bars
    lag_ms = now_ts - features_ts
    ttl_ms = self.features_ttl_sec * 1000  # 30s default - TOO STRICT for bars!
    
    is_ready = lag_ms <= ttl_ms
    return is_ready
```

**Problem**: For 5-min bars, `features_ts` = `bar_close_ts`. When the bar arrives 81 seconds after close (normal), lag=81s > 30s TTL → **STALE rejection**.

---

## 2. Fix Applied

### After (Fixed)
The new `_features_ready` method now:
1. **Distinguishes bars from ticks** via `tf_sec`
2. **Uses `bar_ttl_ms`** (10s) for bars instead of `features_ttl_sec` (30s)
3. **Supports `bar_event_age_mode`**:
   - `received`: Age calculated from `_received_ts` (lenient)
   - `close_ts`: Age calculated from `bar_close_ts` (strict)
4. **Safety Guard**: Rejects bars older than `max(tf_sec*1000, bar_ttl_ms)` even in received mode to prevent ancient data leakage.

---

## 3. Test Coverage (5 tests, all passing)

| Test | Scenario | Expected | Status |
|------|----------|----------|--------|
| `test_bar_not_stale_received_mode` | Bar 81s old, received 1s ago | PASS (use received_ts) | ✅ |
| `test_ancient_bar_rejected_even_in_received_mode` | Bar 20min old, received 1s ago | REJECT (safety guard) | ✅ |
| `test_tick_remains_strict` | Tick 3s old, TTL=2s | REJECT (strict) | ✅ |
| `test_bar_close_ts_mode` | Bar 5s old, TTL=10s | PASS | ✅ |
| `test_bar_close_ts_mode_stale` | Bar 15s old, TTL=10s | REJECT | ✅ |

---

## 4. ARBITRATION_BLOCKED Note

The `ARBITRATION_BLOCKED` rejections for DOGE/XRP are expected and not related to TTL:
- **Cause**: Aurora strategy generates signals for symbols that are assigned to MR strategy in config.
- **Result**: Arbitration gate correctly blocks aurora signals for MR symbols.
- **Impact**: No action needed; this is correct isolation behavior.

---

## 5. Expected Behavior After Restart

After applying this fix and restarting the application:

1. **`features_stale` rejections for bars should STOP**
2. Once `ticks >= 11` (regime fully ready), flow should proceed:
   - `TRADE_INTENT_PROPOSED` > 0
   - `CMD:OPEN` > 0
   - `ORDER_PLACED` or `ORDER_REJECTED` (exchange interaction)

---

## Files Modified

1. `apps/reference/domains/decision_making/decision_making.py` (lines 2251-2321)
2. `apps/reference/domains/regime_detector/regime_detector.py` (lines 237-256) - BAR-TTL-REFORM-02

## Files Created

1. `tests/domains/test_dm_bar_ttl_preemit.py` - 5 test cases
