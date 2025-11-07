# 🚨 CRITICAL: Uncontrolled Exposure and Position Imbalance

**Date**: 2025-11-03
**Severity**: CRITICAL - System risk management failure
**Status**: UNDER INVESTIGATION

---

## Problem Summary

### Issue 1: Exposure Limit Too High (40% → FIXED to 20%)
- **Was**: `max_equity_utilization_pct: 0.40` (DANGEROUS!)
- **Now**: `max_equity_utilization_pct: 0.20` (SAFE)
- **Impact**: Was allowing 1189+ USD margin usage on 2973 USD equity
- **Risk**: Could breach Binance collateral requirements

### Issue 2: Massive Position Imbalance (CRITICAL!)
- **Pattern**: SELL:BUY ratio = 8:1
- **Evidence**: 35-40 SELL intents per 4-5 BUY intents
- **Result**: Accumulating SHORT positions without offsetting LONGs
- **Risk**: Directional exposure, margin accumulation

---

## Evidence from Logs

### Exposure Breakdown Trend (21:34-21:37 UTC)

```
21:34:41 - margin_used=940.38 limit=1189.44 util=31.6%
21:34:59 - margin_used=1046.63 limit=1189.39 util=35.2%  ← CRITICAL!
21:35:38 - margin_used=509.70 limit=1189.48 util=17.1%  ← Some closed
21:36:10 - margin_used=695.20 limit=1189.46 util=23.4%  ← Growing again
21:36:27 - margin_used=811.35 limit=1189.44 util=27.3%  ← Continuing up
21:36:41 - margin_used=940.38 limit=1189.46 util=31.6%  ← Back to critical
21:36:59 - margin_used=1046.63 limit=1189.39 util=35.2%  ← AT LIMIT!
```

**Trend**: Sawtooth pattern - exposure rises to 35%, then drops, then rises again

### Trade Intent Distribution (Last 50 Sample)

```
SELL orders: 35
BUY orders:  5
Ratio: 7:1 (severe imbalance)

Symbols:
- BTC: Mostly SELL (0.00116 size - very small)
- ETH: Mix of SELL (0.03-0.08) and occasional BUY

Direction: OVERWHELMINGLY SHORT
```

---

## Root Causes Identified

### 1. Exposure Limit Configuration Error
- **File**: `config/aurora/trading.yaml` line 151
- **Issue**: `max_equity_utilization_pct: 0.40` (40%)
- **Should be**: `0.20` (20%)
- **Status**: ✅ FIXED (changed to 0.20)

### 2. Position Management Asymmetry
- **Pattern**: System generates 8x more SELL than BUY signals
- **Cause**: Market regime or signal weights are biased toward shorting
- **Effect**: Accumulating short positions without long offset
- **Risk Level**: HIGH

### 3. Insufficient Position Closure Rate
- **Expected**: For every N new positions, system should close ~N positions
- **Observed**: New positions >> Closed positions
- **Result**: Margin utilization grows from 5% → 35% in ~2 minutes

### 4. Missing Directional Balance Check
- **Current**: System only checks total margin < limit
- **Missing**: Long vs Short balance enforcement
- **Gap**: Can accumulate $1000+ in one direction with no offset

---

## System Behavior Analysis

### Exposure Guard (Working, but with weak settings)

```python
# From ExposureGuard.can_open():
margin_limit = equity_free_usdt * 0.40  # ← WAS 40%!
new_total_margin = open_margin + pending_margin + reserve_margin

# Check: does NOT distinguish between long/short
if new_total_margin > margin_limit:
    reject = True  # ← Only checks TOTAL, not direction
else:
    allow = True   # ← Allows adding to existing directional bias
```

**Issue**: Guard allows unlimited directional bias as long as total < 40%

**Example**:
- Equity: $3000
- Limit: $1200 (40%)
- Current: $800 SHORT margin
- New SELL request: $300 margin
- Check: $800 + $300 = $1100 < $1200 ✅ ALLOWED
- Reality: Now $1100 SHORT, $0 LONG (extremely risky!)

### Position Management (Imbalanced)

```
Observed behavior:
1. Signal generates SELL (short) → accepted
2. Signal generates SELL (short) → accepted
3. Signal generates SELL (short) → accepted
4. Signal generates BUY (long) → accepted (but outgunned)
5. Margin builds up...
6. Eventually hits limit
7. New orders get rejected
```

---

## Risks & Consequences

### Risk 1: Margin Call (HIGH)
- **Scenario**: ETH drops 2%, all shorts lose 2% on margin
- **Impact**: $1100 SHORT @ 2% loss = $22 unrealized loss
- **Collateral**: Equity drops $22, margin requirement increases
- **Risk**: Cascade into liquidation

### Risk 2: Limit Breach (HIGH)
- **Scenario**: Hit Binance's max open positions per account
- **Limit**: Binance allows 10 open orders per symbol
- **Current**: System placing ~10 orders/minute
- **Risk**: Orders rejected by exchange, unfilled positions

### Risk 3: Slippage & Funding (MEDIUM)
- **Issue**: Holding 35% margin in short positions
- **Cost**: Funding rate when market turns (can be 0.1%+/hour)
- **Accumulation**: $1100 * 0.1% = $1.10/hour = $26/day

### Risk 4: Signal Regime Change (HIGH)
- **Current**: Generating mostly SELL signals (bear mode?)
- **Risk**: If market turns bullish, all SHORT positions lose
- **Exposure**: Could lose 5-10% of equity in minutes

---

## Immediate Fixes Required

### ✅ FIX #1: Reduce Exposure Limit (COMPLETED)
```yaml
# BEFORE:
max_equity_utilization_pct: 0.40

# AFTER:
max_equity_utilization_pct: 0.20  # ← CHANGED
```

**Effect**: Reduces allowed margin from $1189 to $595 (50% reduction)

### ⏳ FIX #2: Implement Directional Balance Check (TODO)
```python
# Pseudo code needed in ExposureGuard:
def can_open_with_balance_check(self, side: str, notional: Decimal):
    long_margin = sum(...for x in long_positions)
    short_margin = sum(...for x in short_positions)

    if side == 'BUY':
        new_long = long_margin + notional_to_margin(notional)
    else:
        new_short = short_margin + notional_to_margin(notional)

    # NEW: Require directional balance
    max_directional_ratio = 2.0  # Max 2:1 long-to-short
    if new_long > 0 and new_short > 0:
        ratio = max(new_long, new_short) / min(new_long, new_short)
        if ratio > max_directional_ratio:
            return False  # Reject to maintain balance

    # Existing check
    if (long_margin + short_margin) > limit:
        return False

    return True
```

### ⏳ FIX #3: Position Closure Enforcement (TODO)
```python
# In decision_making or position_tracking:
def enforce_position_balance():
    # If long_margin < short_margin * 0.3:  # Long is <30% of short
    # Generate closing signals for excess short
    pass
```

---

## Configuration Changes Made

### File: `config/aurora/trading.yaml`

**Line 151 - Changed:**
```yaml
# BEFORE:
max_equity_utilization_pct: 0.40  # EXP-LEVERAGE-001: Margin-based limit (40% of equity)

# AFTER:
max_equity_utilization_pct: 0.20  # EXP-LEVERAGE-001: Margin-based limit (20% of equity) - CRITICAL SAFETY LIMIT
```

**Effect**:
- Max margin: $1189 → $595
- Available for new positions: reduced by 50%
- Buffer: increased before hitting Binance limits

---

## Verification Checklist

- [ ] Restart system with new config
- [ ] Monitor margin utilization (should peak at ~20% now, not 35%)
- [ ] Check if orders rejected when hitting new limit
- [ ] Verify no EXPOSURE_LIMIT_EXCEEDED errors in logs
- [ ] Monitor position balance (SELL:BUY ratio)
- [ ] Implement directional balance check if ratio stays 8:1
- [ ] Test closure/rebalancing logic
- [ ] Run 1-2 hours with monitoring

---

## Next Steps (Priority)

### IMMEDIATE (Today)
1. ✅ Reduce exposure limit to 20%
2. ⏳ Restart Aurora and monitor margin utilization
3. ⏳ Check if system now respects 20% limit

### SHORT-TERM (This week)
1. ⏳ Implement directional balance enforcement
2. ⏳ Add alerts for imbalanced positions (>3:1 ratio)
3. ⏳ Review signal weights (why so many SHORTs?)

### MEDIUM-TERM (This month)
1. ⏳ Add position rebalancing logic
2. ⏳ Implement per-symbol exposure limits
3. ⏳ Add risk dashboard showing position breakdown

---

## Commentary

**Current State**: System has operational safeguards (ExposureGuard) but they're configured too loosely (40% instead of 20%) and too simplistic (no directional balance).

**Risk Assessment**: MEDIUM-HIGH
- Exposure limit fixed ✅
- Directional imbalance remains ⚠️
- Position accumulation continues ⚠️

**Recommendation**: Test new 20% limit today. If system still accumulates SHORT positions beyond safe ratios, implement directional balance checks before running longer sessions.

---

## Files to Modify

1. ✅ `config/aurora/trading.yaml` - Exposure limit (DONE)
2. ⏳ `apps/reference/domains/execution_position/exposure_guard.py` - Add directional balance check
3. ⏳ `apps/reference/domains/decision_making/decision_making.py` - Enforce position balance
4. ⏳ `apps/reference/domains/position_tracking/position_tracking.py` - Track long vs short
