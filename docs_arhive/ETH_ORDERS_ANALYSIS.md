# 🔍 ETH Orders Missing on Binance - Root Cause Analysis

## Problem Observed
- ✅ BTC: 1 open position on Binance testnet
- ❌ ETH: 0 open positions despite `SUCCESS_ORDER_PLACED` logs

## Root Cause Identified

### Timeline of Events
1. ✅ TRADE INTENT generated: "sell 0.067 ETHUSDT"
2. ✅ BRIDGE: "Converting to CMD:OPEN"
3. ✅ SUCCESS_ORDER_PLACED: logged (seems successful)
4. ❌ Watchdog: "Order timeout: fill_timeout" after ~10 seconds
5. ❌ Circuit breaker: triggered for ETHUSDT

### The Real Issue: `httpx.ReadTimeout`

**Evidence in logs:**
```
httpcore.ReadTimeout
httpx.ReadTimeout
```

**What's happening:**
1. MARKET order sent to Binance ✅
2. Order successfully placed on exchange ✅
3. System waits for fill confirmation (status check)
4. Binance takes >10 seconds to respond with fill status ❌
5. httpx client times out (timeout=10.0 seconds)
6. System thinks order failed and cancels it
7. Order remains on Binance but not managed by Aurora

### Why BTC Works, ETH Doesn't

**Speculation:**
- ETH orders might be hitting rate limits on Binance testnet
- ETH market may have slower fill times than BTC
- Some orders fill instantly, others take >10 seconds
- Once timeout occurs, circuit breaker triggers, blocking further attempts

## Configuration Issue

**File**: `vfoundation/adapters/binance_adapter.py`
**Line**: 80
**Current Setting**: `timeout: float = 10.0` (10 seconds)

This timeout applies to:
- Connection establishment
- Fill status checks
- Order cancellation requests
- Balance queries

### Why 10 Seconds is Too Short

1. **Fill operations**: Require querying Binance for position status
2. **Testnet delays**: Can be slower than production
3. **Network latency**: ~0.5-2 seconds for each round trip
4. **Binance API latency**: 1-3 seconds for order status queries

**Total typical time**: 2-5 seconds, but can exceed 10s under load

## Solution Options

### Option 1: Increase Global Timeout (Quick Fix)
```python
# binance_adapter.py line 80
timeout: float = 20.0  # Increased from 10.0
```

**Pros**: Simple, one-line fix
**Cons**: May cause system to wait too long on network errors

### Option 2: Differentiated Timeouts (Better)
```python
# Different timeouts for different operations:
connect_timeout: float = 5.0      # Initial connection
read_timeout: float = 20.0        # Status checks, fills
write_timeout: float = 10.0       # Send order
```

### Option 3: Retry Logic with Exponential Backoff (Best)
```python
# For fill status checks:
1st attempt: timeout=10s
2nd attempt: timeout=15s (if 1st times out)
3rd attempt: timeout=20s (if 2nd times out)

Max retries: 3-5 times
```

### Option 4: Circuit Breaker Recovery (Production-Grade)
```python
# Current: Circuit breaker triggers on 2+ errors and stays active
# Better: Add recovery period
- When triggered: stop placing new orders for symbol
- After 30-60 seconds: try again with increased timeout
- If successful: reset error counter
```

## Implementation Priority

**Immediate** (prevent ETH orders being stuck):
1. Increase timeout to 20-30 seconds
2. Verify ETH orders now place successfully

**Short-term** (robustness):
1. Add fill retry logic
2. Implement circuit breaker recovery
3. Add monitoring dashboard for timeout events

**Long-term** (architecture):
1. Separate connection/read/write timeouts
2. Per-symbol timeout configuration
3. Adaptive timeout based on historical latency

## Verification Steps

After implementing fix:
```bash
1. Restart Aurora Core
2. Check logs for "Order timeout: fill_timeout"
3. Verify ETH orders appear on Binance testnet
4. Monitor circuit breaker triggers (should decrease)
5. Check fill times in logs (should be <15s)
```

## Evidence from Current System

**ETH Timeout Pattern** (every ~60 seconds):
```
21:17:33,387 - SUCCESS_ORDER_PLACED: ETHUSDT side=sell qty=0.034
21:17:48,889 - Circuit breaker alert triggered for ETHUSDT
21:17:48 - Reason: timeout on fill confirmation (~15 seconds elapsed)
```

**BTC Working Pattern**:
```
21:20:54,802 - MARKET entry placed: BTCUSDT (successful)
21:20:54,818 - Status confirmed (fill check completed in ~0.016 seconds)
```

**Difference**: BTC happens to fill fast, ETH times out waiting for fill status.

## Next Steps

1. ✅ Identify root cause: httpx timeout on fill status checks
2. ⏳ Increase timeout value (20-30 seconds)
3. ⏳ Test system with new timeout
4. ⏳ Verify ETH orders now stay on Binance
5. ⏳ Monitor for any other timeout-related issues
