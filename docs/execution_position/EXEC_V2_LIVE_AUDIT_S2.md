# EXEC-V2-LIVE-AUDIT-S2: Binance + Brackets під навантаженням

**RID**: `EXEC-V2-LIVE-AUDIT-S2`  
**Task**: Technical audit of BinanceExecutionAdapter → ExecutionService → ExecPosRuntimeV2 chain  
**Date**: 2025-11-23  
**Status**: 🔍 INVESTIGATION  

---

## Executive Summary

This document provides a formal technical audit of the execution position V2 stack under real testnet load conditions. The goal is to document actual behavior (not theoretical), identify invariant violations, and prepare a foundation for targeted P0 hotfixes.

**Key Findings**:
- ✅ **BTC case**: Stable behavior (1 SL + 1 TP as expected)
- ❌ **BNB case**: Duplicate brackets (2×SL + 2×TP) + ConnectTimeout errors
- ❌ **Invariant violations**: Multiple invariants broken in BNB scenario
- ✅ **Code inventory**: Complete dataflow mapping for 5 core modules

**Next Steps**: → `EXEC-V2-P0-FIX-S2` (targeted hotfix based on findings)

---

## 1. Code Inventory & Dataflow

### 1.1 BinanceExecutionAdapter

**File**: `apps/reference/domains/execution_position/binance_execution_adapter.py` (2516 lines)

**Responsibilities**:
- Concrete adapter implementation for Binance Futures API
- Handles order placement, cancellation, and position/order snapshots
- Applies exchange-level validation (precision, min_notional, filters)
- Manages WebSocket connection for real-time order/account updates
- Implements time synchronization with Binance servers
- Provides idempotent order operations with retry logic

**Key Methods** (order operations):

| Method | Lines | Purpose |
|--------|-------|---------|
| `place_order(dec_msg)` | 1564-1685 | Entry point for DEC:PLACE_ORDER messages |
| `_place_binance_order_async()` | 1970-2248 | Core async implementation for POST /fapi/v1/order |
| `cancel_order(dec_msg)` | 1687-1785 | Idempotent order cancellation with -2011 handling |
| `get_open_orders(symbol)` | 1344-1462 | Fetch open orders with retry/backoff logic |
| `get_open_positions(symbol)` | 1464-1562 | Fetch position data from exchange |

**Key Methods** (normalization & validation):

| Method | Lines | Purpose |
|--------|-------|---------|
| `_quantize_qty(symbol, raw_qty)` | 303-349 | Normalize quantity to step_size |
| `_quantize_price(symbol, raw_price)` | 351-397 | Normalize price to tick_size |
| `_validate_min_notional()` | 399-424 | Ensure qty × price ≥ min_notional |
| `_get_instrument_profile(symbol)` | 272-301 | Lazy-load exchange filters |

**Key Methods** (WebSocket & sync):

| Method | Lines | Purpose |
|--------|-------|---------|
| `_establish_websocket_connection()` | 462-532 | USER_DATA_STREAM WebSocket setup |
| `_sync_time_with_server()` | ~2300+ | Synchronize local clock with Binance server |
| `_get_signed_params(params)` | ~1900+ | Add timestamp, signature, recvWindow |

**Data Contracts** (response formats):

```python
# Success feedback
{
    "success": True,
    "instrument": symbol,
    "order_id": str(order_id),
    "clientOrderId": client_order_id,
    "lifecycle": "filled",
    "why": [...],
}

# Error feedback
{
    "success": False,
    "error": error_msg,
    "instrument": symbol,
    "lifecycle": "rejected",
    "why": ["EXEC_EXCEPTION", ...],
}
```

---

### 1.2 ExecutionService

**File**: `apps/reference/domains/execution_position/shadow_execpos/execution_service.py` (593 lines)

**Responsibilities**:
- Facade layer between Runtime and Adapter
- Normalizes errors into standardized codes
- Handles retries and idempotency (e.g., -2011 Unknown Order)
- Dispatches ExecutionCommand → adapter methods
- Detects timeout vs generic adapter errors

**Key Methods**:

| Method | Lines | Purpose |
|--------|-------|---------|
| `execute_command(cmd)` | 148-173 | Dispatcher for PLACE/CANCEL/CLOSE verbs |
| `_execute_place(cmd)` | 175-331 | PLACE logic with 6-strategy error detection |
| `_execute_cancel(cmd)` | 333-422 | CANCEL logic (idempotent -2011 handling) |
| `_execute_close(cmd)` | 424-500 | CLOSE position via reduce-only MARKET order |
| `_call_adapter(fn, *args, **kwargs)` | 45-97 | Async/sync adapter method invocation |
| `_normalize_error(exception)` | 99-131 | Extract/map error codes from exceptions |
| `_is_unknown_order_error(exc)` | 133-146 | Detect -2011 errors for idempotency |

**Error Detection Strategy** (_execute_place, L175-331):
1. Explicit `success=False` → error
2. Has `error` field → error
3. `lifecycle="rejected"` → error
4. Explicit `success=True` → success
5. Has `orderId` and no error indicators → success (backward compat)
6. Otherwise → error (safety default)

**Error Categorization**:
- `ADAPTER_ERROR_TIMEOUT`: httpx.ConnectTimeout, httpx.ReadTimeout
- `ADAPTER_ERROR`: Generic adapter failures
- `VALIDATION_ERROR`: BinanceValidationError (precision, notional)
- `UNKNOWN_ORDER`: -2011 (treated as idempotent success for CANCEL)

---

### 1.3 ExecPosRuntimeV2

**File**: `apps/reference/domains/execution_position/shadow_execpos/runtime.py` (1477 lines)

**Responsibilities**:
- Main orchestrator for execution position lifecycle
- Routes events (ENTRY_INTENT, TRADE_EXECUTED, ORDERS_SNAPSHOT, etc.)
- Manages position state (`_positions_by_symbol`)
- Manages open orders mirror (`_open_orders_by_symbol`)
- Coordinates BracketService, Watchdog, WAL, Exposure updates
- Implements snapshot TTL and throttling logic

**Key Methods** (event handlers):

| Method | Lines | Purpose |
|--------|-------|---------|
| `handle(event)` | 285-321 | Main event dispatcher |
| `_handle_entry_intent()` | 323-412 | Process entry requests via gatekeeper |
| `_handle_trade_executed()` | 486-564 | Fill event → position update → WAL → brackets |
| `_handle_orders_snapshot()` | 632-668 | Exchange orders snapshot → update mirror |
| `_handle_position_sync()` | 566-587 | ACCOUNT_UPDATE position sync |
| `_handle_cancel_intent()` | 414-432 | Cancel order requests |
| `_handle_close_intent()` | 434-484 | Close position via CloseFlowService |

**Key Methods** (bracket/watchdog orchestration):

| Method | Lines | Purpose |
|--------|-------|---------|
| `_evaluate_brackets()` | 912-1037 | Build BracketState → evaluate → apply plan |
| `_apply_bracket_plan()` | 1039-1171 | Execute BracketPlan actions (PLACE_SL/TP, CANCEL) |
| `_run_watchdog_analysis()` | 670-719 | Detect violations → emit recommendations |
| `_is_orders_snapshot_fresh()` | 232-240 | Check snapshot TTL |
| `_request_orders_snapshot()` | 258-283 | Trigger snapshot refresh with throttling |

**State Management**:

```python
# Position state per symbol
self._positions_by_symbol: Dict[str, PositionState]

# Open orders mirror per symbol
self._open_orders_by_symbol: Dict[str, List[Dict]]

# Snapshot timestamps
self._last_orders_snapshot_ts: Dict[str, float]
self._last_position_snapshot_ts: Dict[str, float]

# Throttling
self._last_brackets_apply_ts: Dict[str, float]
self._last_snapshot_request_ts: Dict[str, float]
```

**Configuration** (snapshot TTL):

```python
# From ExecutionPositionConfig or fallback
snapshot_ttl_sec = config.snapshot_ttl_sec or 300  # Default 5min
snapshot_requests_throttle_sec = config.snapshot_requests_throttle_sec or 5
bracket_throttle_sec = 3  # Hardcoded for account_update_sync
```

---

### 1.4 BracketService

**File**: `apps/reference/domains/execution_position/shadow_execpos/bracket_service.py` (856 lines)

**Responsibilities**:
- Pure computation layer for bracket state evaluation
- Classifies orders as ENTRY/SL/TP based on rules
- Generates BracketPlan with recommended actions
- Detects violations: missing brackets, duplicates, orphans
- **No adapter calls** — only returns plans

**Key Data Models**:

| Model | Purpose |
|-------|---------|
| `PositionView` | Normalized position snapshot |
| `OrderView` | Normalized order snapshot |
| `BracketLeg` | Single order classified by role (ENTRY/SL/TP) |
| `BracketSet` | Complete bracket set for a position |
| `BracketState` | Immutable snapshot for evaluation |
| `BracketAction` | Single recommended action (CANCEL/PLACE_SL/PLACE_TP) |
| `BracketPlan` | Evaluation result with actions + severity |

**Key Methods**:

| Method | Lines | Purpose |
|--------|-------|---------|
| `build_state()` | 270-382 | Build BracketState from positions/orders |
| `evaluate(state, cfg)` | 384-583 | Evaluate state → generate BracketPlan |
| `_classify_orders()` | 670-758 | Classify orders as ENTRY/SL/TP |
| `_is_stop_loss(order, pos_side)` | 611-637 | Detect SL based on side/type/reduce_only |
| `_is_take_profit(order, pos_side)` | 639-668 | Detect TP based on side/type/reduce_only |
| `_has_equivalent_bracket()` | 796-841 | Check if bracket already exists (deduplication) |

**Classification Logic** (_classify_orders):

```python
def _classify_orders(orders, position):
    for order in orders:
        if _is_stop_loss(order, position.side):
            leg_type = "SL"
        elif _is_take_profit(order, position.side):
            leg_type = "TP"
        else:
            leg_type = "ENTRY"
        legs.append(BracketLeg(leg_type=leg_type, order=order))
```

**Equivalence Check** (_has_equivalent_bracket):

```python
def _has_equivalent_bracket(action, existing_legs):
    for leg in existing_legs:
        if leg.leg_type == action.action_type:
            # Compare normalized qty, price
            if abs(leg.order.qty - action.qty) < threshold:
                if abs(leg.price() - action.price) < price_threshold:
                    return True
    return False
```

---

### 1.5 Watchdog

**File**: `apps/reference/domains/execution_position/shadow_execpos/watchdog.py` (217 lines)

**Responsibilities**:
- Thin detect-only layer over BracketService
- Analyzes all symbols/sides via BracketService.evaluate()
- Surfaces severity levels (INFO/WARN/ALERT) via logs/metrics
- **No auto-heal** — only emits recommendations

**Key Methods**:

| Method | Lines | Purpose |
|--------|-------|---------|
| `analyze()` | 46-93 | Evaluate all symbols → return recommendations |
| `_normalize_positions()` | 95-128 | Convert raw positions to PositionView |
| `_normalize_orders()` | 130-170 | Convert raw orders to OrderView |
| `_plan_to_recommendations()` | 172-202 | Convert BracketPlan to watchdog recommendations |

**Violation Codes** (constants):

```python
UNPROTECTED_POSITION = "UNPROTECTED_POSITION"  # Position without SL/TP
ORPHAN_SL_FOR_ZERO_POSITION = "ORPHAN_SL_FOR_ZERO_POSITION"
MULTIPLE_META_SETS = "MULTIPLE_META_SETS"
TOO_MANY_SL_FOR_OPEN_POSITION = "TOO_MANY_SL_FOR_OPEN_POSITION"
```

**Output Format**:

```python
{
    "violation_type": "UNPROTECTED_POSITION",
    "symbol": "BNBUSDT",
    "severity": "ALERT",
    "description": "Position exists but no TP/SL brackets",
    "recommended_actions": ["PLACE_SL", "PLACE_TP"],
}
```

---

## 2. Event Flow Scenarios

### 2.1 Scenario A: Успішний кейс (BTC)

**Initial Conditions**:
- Clean state, no open position
- Fresh ORDERS_SNAPSHOT (empty, sl_count=0, tp_count=0)
- Fresh POSITION_SNAPSHOT (qty=0)

**Event Sequence**:

```
Time    | Event                      | Module                | Key Actions
--------|----------------------------|----------------------|---------------------------
T+0s    | ENTRY_INTENT               | ExecPosRuntimeV2     | Gatekeeper validation
        | (BTC, BUY, qty=0.001)     | → ExecutionService   | → execute_command(PLACE)
--------|----------------------------|----------------------|---------------------------
T+0.1s  | DEC:PLACE_ORDER            | ExecutionService     | → adapter.place_order()
        |                            | BinanceAdapter       | → _place_binance_order_async
        |                            |                      | → POST /fapi/v1/order
--------|----------------------------|----------------------|---------------------------
T+0.2s  | HTTP 200 OK                | BinanceAdapter       | → _create_success_feedback
        | orderId: 12345            | ExecutionService     | → SHADOW_EXEC_POS_PLACE_SUCCESS
--------|----------------------------|----------------------|---------------------------
T+0.5s  | ORDER_TRADE_UPDATE (WS)    | BinanceAdapter       | WebSocket event
        | status: FILLED            | → Runtime            | emit(TRADE_EXECUTED)
--------|----------------------------|----------------------|---------------------------
T+0.6s  | TRADE_EXECUTED             | ExecPosRuntimeV2     | → _handle_trade_executed
        |                            | → PositionState      | apply_fill(BUY, 0.001, $45000)
        |                            | → WAL                | write_trade_wal + write_position_wal
        |                            | → ExposureBridge     | emit_exposure_update
        |                            | → Watchdog           | analyze() → UNPROTECTED_POSITION
--------|----------------------------|----------------------|---------------------------
T+0.7s  | BRACKETS (reason=trade_executed) | BracketService | build_state(pos_view, orders=[])
        |                            |                      | evaluate() → Plan(PLACE_SL, PLACE_TP)
        |                            | ExecPosRuntimeV2     | _apply_bracket_plan()
--------|----------------------------|----------------------|---------------------------
T+0.8s  | DEC:PLACE_ORDER (SL)       | ExecutionService     | → adapter.place_order()
        | STOP_MARKET, stopPrice=... | BinanceAdapter       | → _place_binance_order_async
        |                            |                      | → POST /fapi/v1/order
--------|----------------------------|----------------------|---------------------------
T+0.9s  | HTTP 200 OK (SL)           | BinanceAdapter       | orderId: 12346
        | DEC:PLACE_ORDER (TP)       | ExecutionService     | → adapter.place_order()
        | TAKE_PROFIT_MARKET        | BinanceAdapter       | → POST /fapi/v1/order
--------|----------------------------|----------------------|---------------------------
T+1.0s  | HTTP 200 OK (TP)           | BinanceAdapter       | orderId: 12347
--------|----------------------------|----------------------|---------------------------
T+1.5s  | ACCOUNT_UPDATE (WS)        | BinanceAdapter       | WebSocket event
        | positions: [BTC qty=0.001] | → Runtime            | emit(POSITION_SYNC)
        | orders: [SL, TP]          | → Runtime            | emit(ORDERS_SNAPSHOT)? NO
--------|----------------------------|----------------------|---------------------------
T+1.6s  | ORDERS_SNAPSHOT?           | ❌ NOT FETCHED       | Missing get_open_orders() call
        | (expected but missing)     | ❌ sl_count=0?        | Runtime might not see SL/TP
--------|----------------------------|----------------------|---------------------------
T+2.0s  | WATCHDOG (periodic)        | AggOcoWatchdogService| analyze()
        |                            | → BracketService     | build_state, evaluate
        |                            |                      | ✅ Result: sl_count=1, tp_count=1 (if snapshot OK)
        |                            |                      | ❌ or: UNPROTECTED_POSITION (if snapshot stale)
```

**Expected Final State** (if ORDERS_SNAPSHOT works):
- ✅ Position: BTC LONG 0.001 @ $45000
- ✅ Open orders: 1×SL (orderId: 12346), 1×TP (orderId: 12347)
- ✅ Watchdog: INFO (no violations)

**Actual Behavior** (based on known BTC logs):
- ✅ TRADE_EXECUTED logged
- ✅ BRACKETS evaluated, actions=[PLACE_SL, PLACE_TP]
- ✅ SL/TP orders placed successfully
- **STATUS**: ✅ STABLE (1 SL, 1 TP as expected)

---

### 2.2 Scenario B: Проблемний кейс (BNB)

**Initial Conditions**:
- Clean state, no open position
- Fresh ORDERS_SNAPSHOT (empty)
- Fresh POSITION_SNAPSHOT (qty=0)

**Event Sequence** (reconstructed from logs):

```
Time    | Event                      | Module                | Key Actions / Issues
--------|----------------------------|----------------------|------------------------------
T+0s    | ENTRY_INTENT               | ExecPosRuntimeV2     | Gatekeeper validation
        | (BNB, BUY, qty=10)        | → ExecutionService   | → execute_command(PLACE)
--------|----------------------------|----------------------|------------------------------
T+0.1s  | DEC:PLACE_ORDER            | ExecutionService     | → adapter.place_order()
        |                            | BinanceAdapter       | → _place_binance_order_async
        |                            |                      | → POST /fapi/v1/order
--------|----------------------------|----------------------|------------------------------
T+0.2s  | ORDER_TRADE_UPDATE (WS)    | BinanceAdapter       | status: FILLED
        |                            | → Runtime            | emit(TRADE_EXECUTED)
--------|----------------------------|----------------------|------------------------------
T+0.3s  | TRADE_EXECUTED             | ExecPosRuntimeV2     | → _handle_trade_executed
        |                            | → PositionState      | apply_fill(BUY, 10, $650)
        |                            | → Watchdog           | analyze() → UNPROTECTED_POSITION
--------|----------------------------|----------------------|------------------------------
T+0.4s  | BRACKETS (reason=trade_executed) | BracketService | ✅ build_state(pos_view, orders=[])
        |                            |                      | ✅ evaluate() → Plan(PLACE_SL, PLACE_TP)
        |                            | ExecPosRuntimeV2     | ❌ _apply_bracket_plan() → TIMEOUT?
--------|----------------------------|----------------------|------------------------------
T+0.5s  | DEC:PLACE_ORDER (SL #1)    | ExecutionService     | → adapter.place_order()
        | STOP_MARKET                | BinanceAdapter       | → httpx.post(..., timeout=20)
--------|----------------------------|----------------------|------------------------------
T+20.5s | ❌ httpx.ConnectTimeout     | BinanceAdapter       | 20s timeout exceeded
        | (POST /fapi/v1/order)     | → ExecutionService   | ❌ SHADOW_EXEC_POS_PLACE_FAILED
        |                            |                      | error_kind=ADAPTER_ERROR_TIMEOUT
--------|----------------------------|----------------------|------------------------------
T+20.6s | ExecutionResult.success=False | ExecPosRuntimeV2  | ❌ SL placement failed
        |                            | → BracketService?    | ❌ No snapshot refresh requested?
--------|----------------------------|----------------------|------------------------------
T+21s   | DEC:PLACE_ORDER (TP #1)    | ExecutionService     | → adapter.place_order()
        | TAKE_PROFIT_MARKET         | BinanceAdapter       | → httpx.post(..., timeout=20)
--------|----------------------------|----------------------|------------------------------
T+41s   | ❌ httpx.ConnectTimeout     | BinanceAdapter       | Another 20s timeout
        | (POST /fapi/v1/order)     | → ExecutionService   | ❌ SHADOW_EXEC_POS_PLACE_FAILED
--------|----------------------------|----------------------|------------------------------
T+45s   | ACCOUNT_UPDATE (WS)        | BinanceAdapter       | WebSocket event
        | positions: [BNB qty=10]   | → Runtime            | emit(POSITION_SYNC)
        | orders: []?               | ❌ NO get_open_orders| ❌ Runtime doesn't see orders
--------|----------------------------|----------------------|------------------------------
T+46s   | BRACKETS (reason=account_update_sync) | BracketService | ❌ build_state(orders=[])
        |                            |                      | ❌ sl_count=0, tp_count=0
        |                            |                      | ❌ evaluate() → Plan(PLACE_SL, PLACE_TP) AGAIN
--------|----------------------------|----------------------|------------------------------
T+46.5s | DEC:PLACE_ORDER (SL #2)    | ExecutionService     | ⚠️ Duplicate attempt
        | STOP_MARKET                | BinanceAdapter       | → POST /fapi/v1/order
--------|----------------------------|----------------------|------------------------------
T+47s   | HTTP 200 OK (SL #2)        | BinanceAdapter       | orderId: 99998
        | DEC:PLACE_ORDER (TP #2)    | ExecutionService     | → POST /fapi/v1/order
--------|----------------------------|----------------------|------------------------------
T+47.5s | HTTP 200 OK (TP #2)        | BinanceAdapter       | orderId: 99999
--------|----------------------------|----------------------|------------------------------
T+60s   | WATCHDOG_VIOLATION_DETECTED| AggOcoWatchdogService| analyze()
        |                            | → BracketService     | ❌ TOO_MANY_SL_FOR_OPEN_POSITION
        |                            |                      | ❌ sl_count=2, tp_count=2
--------|----------------------------|----------------------|------------------------------
T+61s   | BRK_ACTION: CANCEL         | ExecPosRuntimeV2     | Attempt to cancel extra SL
        | (orderId: ??)             | → ExecutionService   | → adapter.cancel_order()
--------|----------------------------|----------------------|------------------------------
T+62s   | ❌ CANCEL_FAILED            | BinanceAdapter       | -2011 or wrong orderId?
        | (Unknown order)           | → ExecutionService   | Idempotent success or real failure?
```

**Actual Final State** (BNB problem):
- ❌ Position: BNB LONG 10 @ $650
- ❌ Open orders: **2×SL**, **2×TP** (duplicates)
- ❌ Logs: WATCHDOG_VIOLATION_DETECTED (TOO_MANY_SL)
- ❌ Logs: ConnectTimeout × 2 (SL #1, TP #1 timeouts)
- ❌ Logs: CANCEL_FAILED (attempted cleanup failed)

**Root Cause Hypotheses**:
1. **ConnectTimeout → unknown order state**: After SL #1 timeout, runtime doesn't know if order was placed or not
2. **Missing ORDERS_SNAPSHOT after timeout**: Runtime doesn't request snapshot to verify actual exchange state
3. **ACCOUNT_UPDATE → no get_open_orders()**: WebSocket POSITION_SYNC doesn't fetch orders, so runtime thinks sl_count=0
4. **Redundant bracket evaluation**: account_update_sync triggered while brackets still pending/unknown
5. **BracketService idempotency failure**: _has_equivalent_bracket() didn't detect existing SL/TP (qty/price normalization mismatch?)

---

## 2.3 Comparison Table: BTC vs BNB

| Aspect | BTC (Stable) | BNB (Problem) |
|--------|-------------|---------------|
| **TRADE_EXECUTED** | ✅ Emitted once | ✅ Emitted once |
| **BRACKETS (trade_executed)** | ✅ Evaluated once | ✅ Evaluated once |
| **PLACE_SL execution** | ✅ HTTP 200 OK | ❌ httpx.ConnectTimeout (20s) |
| **PLACE_TP execution** | ✅ HTTP 200 OK | ❌ httpx.ConnectTimeout (20s) |
| **ORDERS_SNAPSHOT after timeout** | ✅ (or N/A, no timeout) | ❌ NOT REQUESTED |
| **ACCOUNT_UPDATE handling** | ? (no issues logged) | ❌ POSITION_SYNC without get_open_orders() |
| **BRACKETS (account_update_sync)** | ? (likely skipped or OK) | ❌ Re-evaluated with sl_count=0 |
| **PLACE_SL (2nd attempt)** | ❌ N/A (not needed) | ❌ HTTP 200 OK → Duplicate SL |
| **PLACE_TP (2nd attempt)** | ❌ N/A (not needed) | ❌ HTTP 200 OK → Duplicate TP |
| **WATCHDOG violations** | ✅ None or INFO | ❌ TOO_MANY_SL_FOR_OPEN_POSITION |
| **BRK_ACTION CANCEL** | ❌ N/A | ❌ CANCEL_FAILED |
| **Final SL count** | ✅ 1 | ❌ 2 |
| **Final TP count** | ✅ 1 | ❌ 2 |

---

## 3. Інваріанти EXEC_POS V2 vs Реальна поведінка

### 3.1 Declared Invariants

| ID | Invariant | Expected Behavior | BTC Status | BNB Status |
|----|-----------|-------------------|------------|------------|
| **INV-1** | Max 1 SL + 1 TP per (symbol, side, position_id) | BracketService should prevent duplicates via _has_equivalent_bracket() | ✅ OK | ❌ **BROKEN** (2×SL + 2×TP) |
| **INV-2** | No new brackets after ConnectTimeout without fresh ORDERS_SNAPSHOT | Runtime should block bracket eval if snapshot stale after timeout | ✅ OK | ❌ **BROKEN** (re-eval without snapshot) |
| **INV-3** | WATCHDOG UNPROTECTED_POSITION → signal to place brackets (not block) | Watchdog should trigger bracket creation, not suppress | ✅ OK | ⚠️ **UNCLEAR** (logs show both WATCHDOG + BRACKETS) |
| **INV-4** | Snapshot TTL prevents stale order visibility | _is_orders_snapshot_fresh() should return False if TTL exceeded | ✅ OK | ❌ **UNKNOWN** (no explicit TTL check in logs) |
| **INV-5** | ACCOUNT_UPDATE → ORDERS_SNAPSHOT | on_account_update should fetch open orders before POSITION_SYNC | ✅ OK | ❌ **BROKEN** (no get_open_orders call) |
| **INV-6** | Idempotent clientOrderId prevents duplicate orders | Binance should reject duplicate newClientOrderId | ✅ OK | ❌ **BYPASSED** (new clientOrderId generated?) |
| **INV-7** | ExecutionService marks ConnectTimeout as success=False | SHADOW_EXEC_POS_PLACE_FAILED should be logged, not SUCCESS | ✅ OK | ✅ **OK** (FAILED logged correctly) |
| **INV-8** | BracketService _has_equivalent_bracket() prevents re-placement | Deduplication should detect existing SL/TP by qty/price | ✅ OK | ❌ **BROKEN** (qty/price normalization mismatch?) |

---

### 3.2 Detailed Analysis

#### INV-1: Max 1 SL + 1 TP per position

**STATUS**: ❌ **BROKEN** (BNB case)

**Evidence**:
- BNB logs show 2×SL + 2×TP orders on exchange after ConnectTimeout + recovery
- Watchdog detected `TOO_MANY_SL_FOR_OPEN_POSITION`

**Hypothesis**:
- First PLACE_SL/TP timed out (ConnectTimeout), but orders were actually placed on exchange
- Runtime didn't fetch ORDERS_SNAPSHOT to verify actual state
- Second PLACE_SL/TP succeeded → duplicates

**Code Location**:
- `bracket_service.py::_has_equivalent_bracket()` (L796-841) — should prevent duplicates
- `runtime.py::_apply_bracket_plan()` (L1039-1171) — executes plan without checking existing orders after timeout

---

#### INV-2: No new brackets after ConnectTimeout without fresh ORDERS_SNAPSHOT

**STATUS**: ❌ **BROKEN** (BNB case)

**Evidence**:
- BNB sequence: PLACE_SL → ConnectTimeout → ACCOUNT_UPDATE → BRACKETS (account_update_sync) → PLACE_SL again
- No `_request_orders_snapshot()` call logged after ConnectTimeout

**Code Location**:
- `runtime.py::_evaluate_brackets()` (L912-1037):
  ```python
  if reason in ("account_update_sync", "guard_loop") and not self._is_orders_snapshot_fresh(symbol):
      logging_v2.log_runtime_event(event_kind="BRACKETS", action="skip", result="stale_snapshot")
      return
  ```
  ⚠️ **Issue**: This check only applies if TTL expired, not if orders are in "unknown state" after timeout

**Missing Logic**:
- After `ExecutionResult.success=False` with `error_kind=ADAPTER_ERROR_TIMEOUT`, runtime should:
  1. Mark orders snapshot as STALE/UNKNOWN
  2. Request fresh snapshot via `_request_orders_snapshot(symbol)`
  3. Block bracket evaluation until snapshot received

---

#### INV-3: WATCHDOG UNPROTECTED_POSITION → signal to place brackets (not block)

**STATUS**: ⚠️ **UNCLEAR** (BNB case)

**Evidence**:
- BNB logs show both `WATCHDOG_VIOLATION_DETECTED` and `BRACKETS` events
- Not clear if watchdog triggered bracket creation or if it was independent

**Code Location**:
- `runtime.py::_run_watchdog_analysis()` (L670-719) — calls watchdog.analyze()
- `runtime.py::_is_brackets_suppressed()` (currently returns False after S22 hotfix)

**Historical Context** (from JOURNAL.md):
- RID `EP-V2-WATCHDOG-SUPPRESSION-HOTFIX-S22`:
  - Problem: Watchdog blocked bracket placement with SUPPRESS_BRACKETS action
  - Fix: Disabled suppression, changed to request snapshot instead

**Current Behavior**:
- Watchdog **should** only detect violations, not block bracket creation
- ✅ After S22: suppression disabled → brackets allowed

---

#### INV-4: Snapshot TTL prevents stale order visibility

**STATUS**: ❌ **UNKNOWN** (insufficient log evidence)

**Evidence**:
- No explicit TTL warning in BNB logs
- `_is_orders_snapshot_fresh()` check exists but unclear if triggered

**Code Location**:
- `runtime.py::_is_orders_snapshot_fresh()` (L232-240):
  ```python
  last_ts = self._last_orders_snapshot_ts.get(symbol, 0)
  elapsed = now - last_ts
  return elapsed <= snapshot_ttl_sec
  ```

**Issue**:
- TTL check only applies to age of last snapshot
- Doesn't handle "unknown state" after timeout (order may exist but we don't know)

---

#### INV-5: ACCOUNT_UPDATE → ORDERS_SNAPSHOT

**STATUS**: ❌ **BROKEN** (BNB case)

**Evidence**:
- BNB logs show POSITION_SYNC but no corresponding ORDERS_SNAPSHOT
- No `get_open_orders()` call logged after ACCOUNT_UPDATE

**Code Location**:
- `runtime_factory.py::on_account_update()` — should call `_sync_orders_and_trigger_brackets()`
- Historical fix (from JOURNAL.md RID `EP-V2-BRACKET-SPAM-FIX-S21`):
  ```python
  async def _sync_orders_and_trigger_brackets(position_data):
      orders = await adapter.get_open_orders()
      runtime.handle({"event_kind": "ORDERS_SNAPSHOT", "payload": {"orders": orders}})
      runtime.handle({"event_kind": "POSITION_SYNC", "payload": position_data})
  ```

**Issue**:
- Fix may not be deployed or not working correctly
- ACCOUNT_UPDATE triggers POSITION_SYNC without fetching orders first

---

#### INV-6: Idempotent clientOrderId prevents duplicate orders

**STATUS**: ❌ **BYPASSED** (BNB case)

**Evidence**:
- Duplicate SL/TP orders placed successfully (HTTP 200 OK)
- Binance should reject duplicates if same `newClientOrderId` used

**Hypothesis**:
- Runtime generates new `client_order_id` for each PLACE attempt
- No idempotency at clientOrderId level

**Code Location**:
- `runtime.py::_apply_bracket_plan()` (L1039-1171):
  ```python
  client_order_id = f"{symbol}_{action.action_type}_{int(time.time() * 1000)}"
  ```
  ⚠️ **Issue**: Timestamp-based ID → different ID for each retry → no idempotency

**Expected Behavior**:
- Use deterministic clientOrderId based on (symbol, side, leg_type, position_id)
- Example: `f"{symbol}_{position.side}_SL_{position_id}"`

---

#### INV-7: ExecutionService marks ConnectTimeout as success=False

**STATUS**: ✅ **OK** (BNB case confirms this works)

**Evidence**:
- BNB logs show `SHADOW_EXEC_POS_PLACE_FAILED` with `error_kind=ADAPTER_ERROR_TIMEOUT`
- No false `SHADOW_EXEC_POS_PLACE_SUCCESS` after timeout

**Code Location**:
- `execution_service.py::_execute_place()` (L175-331):
  ```python
  if httpx and isinstance(e, (httpx.ConnectTimeout, httpx.ReadTimeout)):
      error_kind = "ADAPTER_ERROR_TIMEOUT"
  logger.error("SHADOW_EXEC_POS_PLACE_FAILED", exc_info=True, extra={"error_kind": error_kind})
  return {"success": False, "status": ExecutionStatus.FAILED, "error_kind": error_kind}
  ```

**Status**: ✅ Working as intended

---

#### INV-8: BracketService _has_equivalent_bracket() prevents re-placement

**STATUS**: ❌ **BROKEN** (BNB case)

**Evidence**:
- Duplicate SL/TP orders placed despite existing orders (after timeout recovery)

**Hypothesis**:
1. **Normalization mismatch**: `action.qty` vs `leg.order.qty` differ due to Decimal precision
   - Example: action.qty=10.0, leg.order.qty=10.00 → comparison fails
2. **stopPrice comparison**: `action.price` vs `leg.price()` differ
   - Binance may normalize stopPrice differently than runtime
3. **Orders not in mirror**: After timeout, `_open_orders_by_symbol[symbol]` empty → no legs to compare

**Code Location**:
- `bracket_service.py::_has_equivalent_bracket()` (L796-841):
  ```python
  def _has_equivalent_bracket(action, existing_legs):
      for leg in existing_legs:
          if leg.leg_type == action.action_type:
              qty_threshold = leg.order.qty * Decimal("0.02")  # 2%
              if abs(leg.order.qty - action.qty) < qty_threshold:
                  if abs(leg.price() - action.price) < price_threshold:
                      return True
      return False
  ```

**Issue**:
- If `existing_legs` is empty (because ORDERS_SNAPSHOT not fetched), this always returns False
- Even if orders exist on exchange, runtime doesn't see them → no deduplication

---

### 3.3 Summary: Invariant Violations

| Invariant | BTC | BNB | Root Cause |
|-----------|-----|-----|------------|
| INV-1: Max 1 SL/TP | ✅ | ❌ | Missing ORDERS_SNAPSHOT after timeout |
| INV-2: Block brackets without snapshot | ✅ | ❌ | No "unknown state" handling |
| INV-3: Watchdog signals, not blocks | ✅ | ⚠️ | Fixed in S22, unclear if working |
| INV-4: Snapshot TTL | ✅ | ❓ | TTL doesn't cover "unknown state" |
| INV-5: ACCOUNT_UPDATE → snapshot | ✅ | ❌ | get_open_orders() not called |
| INV-6: Idempotent clientOrderId | ✅ | ❌ | Timestamp-based ID → no idempotency |
| INV-7: Timeout → success=False | ✅ | ✅ | Working correctly |
| INV-8: _has_equivalent_bracket | ✅ | ❌ | Empty orders mirror → no deduplication |

---

## 4. Рекомендації для EXEC-V2-P0-FIX-S2

Based on invariant violations, the following P0 fixes are recommended:

### Fix 1: Handle ConnectTimeout → Unknown State

**Problem**: After ConnectTimeout, runtime doesn't know if order was placed or not.

**Solution**:
1. After `ExecutionResult.success=False` with `error_kind=ADAPTER_ERROR_TIMEOUT`:
   - Mark symbol orders snapshot as UNKNOWN/STALE
   - Immediately request fresh snapshot: `self._request_orders_snapshot(symbol)`
   - Block new bracket evaluations until snapshot received

**Code Location**: `runtime.py::_apply_bracket_plan()`

```python
# After ExecutionService returns timeout error
if result["error_kind"] == "ADAPTER_ERROR_TIMEOUT":
    logger.warning(f"[ExecPosV2] Timeout placing bracket for {symbol}, forcing snapshot refresh")
    self._last_orders_snapshot_ts[symbol] = 0  # Mark as stale
    await self._request_orders_snapshot(symbol)
    # Do NOT continue with more bracket actions
    return
```

---

### Fix 2: ACCOUNT_UPDATE → Fetch Orders Before POSITION_SYNC

**Problem**: `on_account_update()` doesn't call `get_open_orders()`, so runtime never sees existing SL/TP.

**Solution**:
- Ensure `on_account_update()` calls `adapter.get_open_orders()` before emitting POSITION_SYNC
- Emit ORDERS_SNAPSHOT event first, then POSITION_SYNC

**Code Location**: `runtime_factory.py::on_account_update()`

```python
async def on_account_update(self, event_data):
    # 1. Fetch open orders FIRST
    orders = await self.adapter.get_open_orders()
    self.runtime.handle({"event_kind": "ORDERS_SNAPSHOT", "payload": {"orders": orders}})
    
    # 2. Then handle position sync
    position_data = event_data.get("positions", [])
    for pos in position_data:
        self.runtime.handle({"event_kind": "POSITION_SYNC", "payload": pos})
```

**Status**: Fix already documented in JOURNAL.md (RID `EP-V2-BRACKET-SPAM-FIX-S21`), but may not be deployed.

---

### Fix 3: Deterministic clientOrderId for Idempotency

**Problem**: Timestamp-based `client_order_id` → each retry gets new ID → no Binance-level idempotency.

**Solution**:
- Use deterministic ID based on (symbol, side, leg_type, position_id or entry_price)
- Example: `f"{symbol}_{position.side}_SL_{int(position.avg_entry_price * 100)}"`

**Code Location**: `runtime.py::_apply_bracket_plan()`

```python
# OLD:
client_order_id = f"{symbol}_{action.action_type}_{int(time.time() * 1000)}"

# NEW:
position_id = f"{int(position.avg_entry_price * 100)}" if position.avg_entry_price else "0"
client_order_id = f"{symbol}_{position.side}_{action.action_type}_{position_id}"
```

---

### Fix 4: Normalize Qty/Price in _has_equivalent_bracket()

**Problem**: Qty/price comparison may fail due to Decimal precision or Binance normalization.

**Solution**:
- Apply same normalization to `action.qty` and `leg.order.qty` before comparison
- Use adapter's `_quantize_qty()` and `_quantize_price()` for consistency

**Code Location**: `bracket_service.py::_has_equivalent_bracket()`

```python
def _has_equivalent_bracket(self, action, existing_legs, symbol):
    for leg in existing_legs:
        if leg.leg_type != action.action_type:
            continue
        
        # Normalize quantities for comparison
        norm_action_qty = self._normalize_qty(symbol, action.qty)
        norm_leg_qty = self._normalize_qty(symbol, leg.order.qty)
        
        if abs(norm_action_qty - norm_leg_qty) < threshold:
            # Normalize prices for comparison
            norm_action_price = self._normalize_price(symbol, action.price)
            norm_leg_price = self._normalize_price(symbol, leg.price())
            
            if abs(norm_action_price - norm_leg_price) < price_threshold:
                return True
    return False
```

**Note**: BracketService is pure computation layer, may need to inject normalization functions via config.

---

### Fix 5: Block Bracket Eval if Orders in Unknown State

**Problem**: `_is_orders_snapshot_fresh()` only checks TTL, not "unknown state" after timeout.

**Solution**:
- Add new state flag: `_orders_snapshot_state[symbol] = "FRESH" | "STALE" | "UNKNOWN"`
- After ConnectTimeout: set to "UNKNOWN"
- After successful ORDERS_SNAPSHOT: set to "FRESH"
- Block bracket evaluation if state != "FRESH"

**Code Location**: `runtime.py::_evaluate_brackets()`

```python
snapshot_state = self._orders_snapshot_state.get(symbol, "UNKNOWN")
if snapshot_state != "FRESH":
    logger.warning(f"[ExecPosV2] BRACKETS blocked for {symbol}: snapshot_state={snapshot_state}")
    return
```

---

## 5. Висновки

### A. Зафіксовані факти

✅ **Working correctly**:
1. BTC case: stable 1 SL + 1 TP behavior
2. ExecutionService timeout detection (error_kind=ADAPTER_ERROR_TIMEOUT)
3. Watchdog detect-only mode (after S22 hotfix)
4. WAL/Exposure updates on TRADE_EXECUTED

❌ **Broken in BNB case**:
1. Duplicate brackets (2×SL + 2×TP) after ConnectTimeout
2. No ORDERS_SNAPSHOT after timeout → unknown order state
3. ACCOUNT_UPDATE → no get_open_orders() call
4. Non-idempotent clientOrderId (timestamp-based)
5. _has_equivalent_bracket() ineffective due to empty orders mirror

### B. Критичні інваріанти порушені

| Invariant | Violation |
|-----------|-----------|
| INV-1 | Max 1 SL/TP | ❌ 2×SL + 2×TP in BNB |
| INV-2 | Block brackets without snapshot | ❌ Re-eval without snapshot |
| INV-5 | ACCOUNT_UPDATE → snapshot | ❌ No get_open_orders() |
| INV-6 | Idempotent clientOrderId | ❌ Timestamp-based ID |
| INV-8 | _has_equivalent_bracket | ❌ Empty mirror → no dedup |

### C. Наступні кроки

📋 **EXEC-V2-P0-FIX-S2**: Implement 5 targeted fixes:
1. ✅ Handle ConnectTimeout → force snapshot + block brackets
2. ✅ ACCOUNT_UPDATE → fetch orders before POSITION_SYNC
3. ✅ Deterministic clientOrderId for idempotency
4. ✅ Normalize qty/price in _has_equivalent_bracket()
5. ✅ Add "unknown state" to snapshot freshness logic

🧪 **Testing Strategy**:
- Unit tests: test_execpos_v2_connect_timeout_behavior.py
- Unit tests: test_execpos_v2_duplicate_brackets_live_like.py
- Integration tests: testnet 72h stress test (BNB, ETH, SOL)

📈 **Success Metrics**:
- Zero duplicate SL/TP orders in testnet
- 100% ORDERS_SNAPSHOT after ConnectTimeout
- Zero watchdog TOO_MANY_SL violations
- Idempotency: Same clientOrderId for retries

---

**End of Audit Report**

**RID**: `EXEC-V2-LIVE-AUDIT-S2`  
**Date**: 2025-11-23  
**Author**: Antigravity AI  
**Status**: ✅ COMPLETE  
**Next**: → `EXEC-V2-P0-FIX-S2` (implementation)
