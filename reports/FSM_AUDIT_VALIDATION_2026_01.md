# FSM.PY AUDIT VALIDATION REPORT

**Date**: 2026-01-26  
**File**: `apps/reference/domains/execution_position/fsm.py` (4380 lines)  
**Auditor**: Copilot Agent + External Review Cross-Validation

---

## EXECUTIVE SUMMARY

Проведено перехресну валідацію зовнішнього аудиту fsm.py. Знайдено **3 критичних**, **2 високих** та **5 середніх** проблем.

| Severity | Count | Status |
|----------|-------|--------|
| 🔴 CRITICAL | 3 | 1 partially fixed, 2 confirmed |
| 🟠 HIGH | 2 | Confirmed |
| 🟡 MEDIUM | 5 | Confirmed |

---

## 🔴 CRITICAL ISSUES

### P0-001: EVT:ORDER_FILL vs EVT:TRADE_EXECUTED Event Mismatch

**Location**: Line 315 (listener), Lines 1512-1620 (`_on_order_fill`)

**Problem**:
```
FSM registers:     bus.listen("EVT:ORDER_FILL", self._on_order_fill)
Watchdog emits:    "EVT:TRADE_EXECUTED" (watchdog.py:385)
WS Client emits:   "EVT:TRADE_EXECUTED" (binance_ws_client.py:384)
```

**Impact**: 
- Bus listener at L315 **NEVER FIRES** in production
- `_on_order_fill` only called via alternative path

**Mitigation Found** (PARTIAL FIX):
- Line 1739-1741: Adapter has `exec_fsm = self` direct reference
- Line 1880-1882: `handle()` routes `TRADE_EXECUTED` → `_on_order_fill(msg)`

**Status**: ⚠️ PARTIALLY FIXED - Works via `handle()` but bus listener is dead code

**Recommendation**:
```python
# Option A: Add second listener (additive, safe)
self.bus.listen("EVT:TRADE_EXECUTED", self._on_order_fill)

# Option B: Remove dead listener
# self.bus.listen("EVT:ORDER_FILL", ...)  # REMOVE - never fires
```

---

### P0-002: `_pending_brackets` - Volatile In-Memory State Loss

**Location**: 
- Declaration: Line 244
- Write: Line 3051
- Read: Line 1595

**Problem**:
```python
# Line 244 - volatile dict
self._pending_brackets: Dict[str, Dict[str, Any]] = {}

# Line 3051 - stores LIMIT entry pending TP/SL
self._pending_brackets[entry_order_id] = {
    "symbol": symbol, "side": side, "sl": sl, "tp": tp, ...
}

# Line 1595 - checks on fill
if order_id in self._pending_brackets:
    bracket_data = self._pending_brackets.pop(order_id)
```

**Impact**:
- On process restart, pending brackets **LOST**
- LIMIT entries that received FILL after restart → **NO TP/SL PLACED**
- Unprotected positions in production

**Hydration Check**:
```python
def hydrate(self, position_data):  # Line 1778
    # DOES NOT restore _pending_brackets!
    manage_flow.hydrate(position_data)
    close_flow.hydrate(position_data)
```

**Status**: 🔴 CONFIRMED - No persistence/rehydration

**Recommendation**:
1. Add `_pending_brackets` to WAL on write
2. Restore from WAL on startup via `hydrate()`
3. Or: Query open LIMIT orders from exchange on startup and rebuild state

---

### P0-003: `_pending_intent_data` - Volatile In-Memory State Loss

**Location**:
- Declaration: Line 241
- Write: Line 1873
- Read: Lines 1562-1579

**Problem**:
```python
# Line 241 - volatile dict
self._pending_intent_data: Dict[str, Dict[str, Any]] = {}

# Line 1873 - caches TP/SL intent from DEC:OPEN
self._pending_intent_data[result.rid] = intent_data

# Lines 1562-1579 - uses on fill to inject TP/SL
if rid in self._pending_intent_data:
    intent_data = self._pending_intent_data[rid]
```

**Impact**:
- On restart, intent data **LOST**
- Orders placed before restart → **TP/SL values not available on fill**
- Manual intervention required to set TP/SL

**Status**: 🔴 CONFIRMED - No persistence/rehydration

**Recommendation**: Same as P0-002 - persist to WAL or rebuild from state

---

## 🟠 HIGH ISSUES

### P1-001: `_submit_async` Fire-and-Forget Pattern

**Location**: Lines 781-800

**Code**:
```python
def _submit_async(self, coro, loop=None) -> None:
    """Schedule coroutine on a target loop, thread-safe."""
    target_loop = loop or self._get_async_loop()
    if not target_loop:
        LOG.debug("No asyncio loop available...")  # Silent failure
        return

    if running_loop is target_loop:
        target_loop.create_task(coro)  # No error callback!
    else:
        asyncio.run_coroutine_threadsafe(coro, target_loop)  # Future ignored!
```

**Problems**:
1. Line 790: Missing loop → **silent return** (no error, no retry)
2. Line 798: `create_task()` without `add_done_callback()` → exceptions lost
3. Line 800: `run_coroutine_threadsafe()` returns Future but **result/exception ignored**

**Usage Count**: 19 call sites (grep result)

**Impact**:
- Async failures in bracket placement, order cancellation, cleanup → **silently lost**
- No retry mechanism
- No alerting on critical path failures

**Status**: 🟠 CONFIRMED

**Recommendation**:
```python
def _submit_async(self, coro, loop=None) -> None:
    target_loop = loop or self._get_async_loop()
    if not target_loop:
        LOG.error("CRITICAL: No asyncio loop for %r", coro)  # Upgrade to ERROR
        return

    def _on_done(fut):
        try:
            fut.result()  # Re-raise exception if any
        except asyncio.CancelledError:
            pass
        except Exception as e:
            LOG.error("Async task failed: %s", e, exc_info=True)
            # TODO: alerting/retry

    if running_loop is target_loop:
        task = target_loop.create_task(coro)
        task.add_done_callback(_on_done)
    else:
        fut = asyncio.run_coroutine_threadsafe(coro, target_loop)
        fut.add_done_callback(_on_done)
```

---

### P1-002: Dead Bus Listener (EVT:ORDER_FILL)

**Location**: Line 315

**Code**:
```python
self.bus.listen("EVT:ORDER_FILL", self._on_order_fill)
```

**Problem**: No producer emits `EVT:ORDER_FILL` in codebase (grep confirmed)

**Status**: 🟠 CONFIRMED - Dead code, listener never triggers

**Recommendation**: Remove or replace with `EVT:TRADE_EXECUTED`

---

## 🟡 MEDIUM ISSUES

### P2-001: `_supersede_queue` - Volatile State

**Location**: Line 248-250

```python
self._supersede_queue: Dict[str, Dict[str, Any]] = {}
self._supersede_canceling: set = set()
```

**Impact**: Supersede logic state lost on restart

---

### P2-002: Type Inconsistency in `_pending_brackets` Keys

**Location**: Lines 3051 vs 1595

```python
# Line 3051 - key is str(orderId)
entry_order_id = str(entry_resp["orderId"])
self._pending_brackets[entry_order_id] = {...}

# Line 1595 - order_id comes from event payload
order_id = payload.get("orderId")  # Could be int from exchange!
if order_id in self._pending_brackets:  # May fail due to type mismatch
```

**Risk**: If exchange returns `orderId` as `int`, lookup fails

**Recommendation**: Normalize to `str` consistently:
```python
order_id = str(payload.get("orderId"))
```

---

### P2-003: Missing Timeout for `_pending_intent_data`

**Location**: Line 1873

```python
intent_data = {
    "stop_price": ...,
    "timestamp": get_clock().now_sec()  # Saved but never used for cleanup
}
self._pending_intent_data[result.rid] = intent_data
```

**Problem**: No TTL/cleanup - memory leak for unmatched intents

---

### P2-004: `LOG.debug` on Critical Path Failures

**Location**: Line 790

```python
if not target_loop:
    LOG.debug("No asyncio loop available...")  # Should be ERROR
    return
```

**Impact**: Critical failures logged at DEBUG level - invisible in production

---

### P2-005: No Idempotency in `_on_order_fill` ✅ FALSE POSITIVE

**Location**: Lines 1531-1534

**Actual Code** (idempotency EXISTS):
```python
# 🔄 IDEMPOTENT: Check if this event was already processed
event_key = f"fill_{order_id}_{symbol}"
if not self._mark_processed_event(event_key):
    LOG.debug(f"[FILL] Skipping duplicate FILL for {symbol} order {order_id}")
    return
```

**Status**: ✅ FALSE POSITIVE - idempotency already implemented

---

## SUMMARY TABLE

| ID | Severity | Issue | Lines | Status |
|----|----------|-------|-------|--------|
| P0-001 | 🔴 CRITICAL | EVT:ORDER_FILL vs TRADE_EXECUTED mismatch | 315, 1512-1620 | Partial fix exists |
| P0-002 | 🔴 CRITICAL | `_pending_brackets` volatile | 244, 1595, 3051 | Confirmed |
| P0-003 | 🔴 CRITICAL | `_pending_intent_data` volatile | 241, 1562-1579, 1873 | Confirmed |
| P1-001 | 🟠 HIGH | `_submit_async` fire-and-forget | 781-800 | Confirmed |
| P1-002 | 🟠 HIGH | Dead EVT:ORDER_FILL listener | 315 | Confirmed |
| P2-001 | 🟡 MEDIUM | `_supersede_queue` volatile | 248-250 | Confirmed |
| P2-002 | 🟡 MEDIUM | Type inconsistency orderId | 3051, 1595 | Confirmed |
| P2-003 | 🟡 MEDIUM | No TTL for `_pending_intent_data` | 1873 | Confirmed |
| P2-004 | 🟡 MEDIUM | LOG.debug on critical failures | 790 | Confirmed |
| P2-005 | 🟡 MEDIUM | No idempotency in `_on_order_fill` | 1531-1534 | ❌ FALSE POSITIVE |

**Final Score**: 9/10 issues confirmed, 1/10 false positive (idempotency exists at L1531-1534)

---

## RECOMMENDED FIX PRIORITY

1. **P0-001** → Add `EVT:TRADE_EXECUTED` listener (1 line change) - SAFE: idempotency exists
2. **P1-001** → Add error callback to `_submit_async` (10 lines)
3. **P2-002** → Type normalization `str(order_id)` at L1595 (1 line)
4. **P0-002/P0-003** → Persistence strategy decision (architectural)
5. ~~**P2-005**~~ → NOT NEEDED - idempotency already exists at L1531-1534

---

## CROSS-REFERENCES

- Previous documentation: `reports/order_lifecycle_legacy_deadmap_01.md`
  - Already noted: "нема явного producer для EVT:ORDER_ACK/EVT:ORDER_FILL"
- Related: `reports/VF-VERB-REG-06.md` - EVT:ORDER_FILL listed as "unknown owner"

---

## APPENDIX: GREP EVIDENCE

### EVT:ORDER_FILL Listeners (no emitters found)
```
fsm.py:315: self.bus.listen("EVT:ORDER_FILL", self._on_order_fill)
```

### EVT:TRADE_EXECUTED Emitters
```
watchdog.py:385:    await self.emit_fn("EVT:TRADE_EXECUTED", fill_payload)
binance_ws_client.py:384:    event_name = "EVT:TRADE_EXECUTED"
```

### `_submit_async` Call Sites (19 total)
```
fsm.py:815, 816, 839, 972, 1068, 1383, 1421, 1463, 1604, 1617, 
1639, 1653, 1927, 1936, 2390, 3758, 3892, 3961
```

---

*Report generated by automated audit validation*
