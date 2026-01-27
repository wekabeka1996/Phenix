# FORENSIC: Watchdog ACK + Portfolio Equity Контрактні Розриви

**Дата**: 2026-01-26  
**Severity**: 🔴 CRITICAL (P0)  
**Scope**: watchdog.py, position_tracking.py, exposure_guard.py

---

## EXECUTIVE SUMMARY

Виявлено **2 критичних контрактних розриви**:

| ID | Проблема | Impact |
|----|----------|--------|
| **WD-001** | Дубльований ACK шлях + відсутній tracking для SL/TP | False "unknown order" warnings |
| **PT-001** | `equity_free_usdt` відсутній в portfolio після trade | ExposureGuard блокує ВСІ ордери |
| **PT-002** | `time.time()` замість `get_clock()` | Backtest timebase mismatch |

---

## 🔴 WD-001: Watchdog "ACK received for unknown order"

### Root Cause Analysis

**Шлях ACK для Entry ордерів**:

```
1. fsm.py:2969 - track_order_placed(entry_order_id)    → pending_orders[entry_order_id]
2. fsm.py:3045 - watchdog.on_order_ack(entry_order_id) → pending_orders → acked_orders
3. fsm.py:1508 - watchdog.on_order_ack(order_id)       → pending_orders.get() = NOT FOUND!
                                                        → LOG.warning("unknown order")
```

**Причина**: FSM викликає `on_order_ack()` ДВІЧІ:
1. Одразу після `place_*` (L3045) - переносить в `acked_orders`
2. Коли приходить реальний `EVT:ORDER_ACK` (L1508) - але ордер вже НЕ в `pending_orders`

**Для SL/TP ордерів — ще гірше**:

```python
# Єдиний виклик track_order_placed():
fsm.py:2969: self.watchdog.track_order_placed(order_id=entry_order_id, ...)

# SL/TP ордери НЕ трекаються!
# Коли приходить їх ACK → ЗАВЖДИ "unknown order"
```

### Evidence

```
watchdog.py:226-229:
    def on_order_ack(self, order_id: str):
        if order_id not in self.pending_orders:
            LOG.warning(f"ACK received for unknown order {order_id}")
            return
```

### Impact

- **False positives**: Логи забруднені "unknown order" warnings
- **Missing timeout tracking**: SL/TP ордери НЕ відслідковуються на ACK/FILL timeout
- **Operational noise**: Важко відрізнити справжні проблеми від фальшивих warnings

### Fix Options

#### Option A: Idempotent `on_order_ack` (Minimal Change)

```python
def on_order_ack(self, order_id: str):
    """Mark order as acknowledged, start FILL timeout tracking."""
    # Already acked? Skip silently
    if order_id in self.acked_orders:
        LOG.debug(f"Order {order_id} already ACKed, skipping")
        return
    
    if order_id not in self.pending_orders:
        LOG.debug(f"ACK received for untracked order {order_id}")  # DEBUG not WARNING
        return
    # ... rest unchanged
```

#### Option B: Track SL/TP orders (Comprehensive)

```python
# В fsm.py після place_sl_tp():
if sl_order_id:
    self.watchdog.track_order_placed(
        order_id=sl_order_id,
        client_order_id=None,
        symbol=symbol,
        corr_id=corr_id,
        rid=rid,
        order_type="SL"  # New field for categorization
    )
```

**Рекомендація**: Option A для швидкого фіксу, Option B як Phase 2.

---

## 🔴 PT-001: `equity_free_usdt` Missing in Portfolio After Trade

### Root Cause Analysis

**Контракт ExposureGuard** (exposure_guard.py:470-472):

```python
equity_free_usdt = _d(portfolio_state.get("equity_free_usdt", "0"))
if "equity_free_usdt" not in portfolio_state or equity_free_usdt <= Decimal("0"):
    return {"allowed": False, "reason": "EQUITY_UNKNOWN", "why": "exposure_guard_no_equity"}
```

**Порівняння portfolio payloads**:

| Path | `equity_free_usdt` | Lines |
|------|---------------------|-------|
| `on_account_update()` | ✅ Included | L407-408 |
| `on_trade_executed()` | ❌ **MISSING** | L241-265 |
| `on_equity_update()` | ✅ Included | L499-500 |

### Evidence

**Log proof** (domain_execution_position.log:207):
```
ON_PORTFOLIO_DEBUG: received portfolio_keys=['ts', 'equity', 'realized_pnl', 
'unrealized_pnl', 'positions', 'open_positions_usd', 'open_positions_margin_usd', 
'positions_by_side', 'positions_last_ts_ms'], equity_raw=MISSING, ...
```

**Missing key**: `equity_free_usdt` NOT in `portfolio_keys`!

### Impact

- **CRITICAL**: Після кожного trade, ExposureGuard блокує НАСТУПНИЙ ордер з `EQUITY_UNKNOWN`
- **Race condition**: Якщо `on_trade_executed` emit прийде перед `on_account_update`, система "заїдає"
- **Backtest affected**: Synthetic fills завжди йдуть через `on_trade_executed`

### Fix (1 line)

```python
# position_tracking.py:241-265, add after "equity":
portfolio_payload = {
    "ts": ts,
    "equity": str(self._equity),
    "equity_free_usdt": str(self._equity),  # <-- ADD THIS LINE
    "realized_pnl": str(self._realized_pnl),
    # ... rest unchanged
}
```

---

## 🟠 PT-002: Timebase Mismatch (`time.time()` vs `get_clock()`)

### Root Cause Analysis

**Inconsistent time source in position_tracking.py**:

| Line | Time Source | Context |
|------|-------------|---------|
| L174 | `get_clock().now_ms()` ✅ | WAL timestamp |
| L238 | `time.time()` ❌ | `on_trade_executed` |
| L401 | `time.time()` ❌ | `on_account_update` |
| L405 | `time.time()` ❌ | portfolio `ts` field |
| L493 | `time.time()` ❌ | `on_equity_update` |
| L497 | `time.time()` ❌ | portfolio `ts` field |
| L681 | `get_clock().now_ms()` ✅ | stale check |
| L746 | `get_clock().now_ms()` ✅ | position update |

### Impact

- **Backtest non-determinism**: Wall-clock timestamps mixed with simulated time
- **Staleness checks fail**: `positions_last_ts_ms` = 2026 wallclock, but `get_clock()` = 2024 backtest epoch
- **Log confusion**: Timestamps in different timebases

### Log Evidence

```
ts_raw=1769433622811  # Wall-clock 2026-01-26 13:20:22
vs
Backtest epoch should be ~168403... (simulated date)
```

### Fix Pattern

Replace all `time.time()` with `get_clock().now_ms()` in position_tracking.py:

```python
# L238, L401, L405, L493, L497:
# BEFORE:
positions_last_ts_ms = int(time.time() * 1000)

# AFTER:
positions_last_ts_ms = get_clock().now_ms()
```

---

## FIX PRIORITY

| Priority | Fix | Risk | Effort |
|----------|-----|------|--------|
| **P0** | PT-001: Add `equity_free_usdt` | 🟢 LOW | 1 line |
| **P1** | WD-001: Idempotent `on_order_ack` | 🟢 LOW | 5 lines |
| **P1** | PT-002: Replace `time.time()` | 🟢 LOW | 5 lines |
| **P2** | WD-002: Track SL/TP orders | 🟡 MEDIUM | 20+ lines |

---

## IMMEDIATE ACTIONS

### Fix 1: Add `equity_free_usdt` to `on_trade_executed` (PT-001)

**File**: `apps/reference/domains/position_tracking/position_tracking.py`  
**Line**: ~244 (after `"equity": str(self._equity),`)

```python
"equity_free_usdt": str(self._equity),  # EXP-FIX: Required by ExposureGuard
```

### Fix 2: Make `on_order_ack` idempotent (WD-001)

**File**: `apps/reference/domains/execution_position/watchdog.py`  
**Line**: ~226-229

```python
def on_order_ack(self, order_id: str):
    """Mark order as acknowledged, start FILL timeout tracking."""
    # Idempotency: already acked
    if order_id in self.acked_orders:
        LOG.debug(f"Order {order_id} already ACKed, skipping duplicate")
        return
    
    if order_id not in self.pending_orders:
        LOG.debug(f"ACK received for untracked order {order_id} (SL/TP or external)")
        return
    # ... rest unchanged
```

### Fix 3: Use `get_clock()` consistently (PT-002)

**File**: `apps/reference/domains/position_tracking/position_tracking.py`  
**Lines**: 238, 401, 405, 493, 497

Replace `int(time.time() * 1000)` with `get_clock().now_ms()`

---

## TEST VERIFICATION

```bash
# After fixes:
pytest tests/domains/position_tracking/ -v
pytest tests/domains/execution_position/ -v
pytest tests/integration/ -v -k "exposure or portfolio"
```

---

## CROSS-REFERENCES

- Related: `reports/FSM_AUDIT_VALIDATION_2026_01.md` - P0-001 event mismatch
- Related: `reports/FSM_FIX_PLAN_2026_01.md` - Phase 1 fixes
- Contract: `schemas/portfolio_state_v1.json` (if exists)
- Governance: `vfoundation/dictionaries/domains/domain_position_tracking.yaml`

---

*Report generated: 2026-01-26*
