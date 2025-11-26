# Execution Position & Binance Adapter Audit

**Date:** 2025-11-26
**Scope:** `apps/reference/domains/execution_position`, `binance_execution_adapter.py`
**Objective:** Comprehensive technical audit of the execution domain and its interaction with Binance adapters.

## 1. Entry Points and Runtime Modes

The `execution_position` domain is the central authority for managing position lifecycles and order execution. It operates primarily in **V2 Runtime Mode**.

### 1.1 Runtime Mode Resolution
*   **Config Path:** `execution_position.runtime_mode`
*   **Default:** `"v2"`
*   **Legacy Support:** Explicitly removed. Setting `runtime_mode: legacy` raises `ValueError`.
*   **Implementation:** `apps/reference/domains/execution_position/runtime_factory.py`

### 1.2 Entry Points

| Entry Point | Source | Event/Command | Handler | Payload Key Fields |
| :--- | :--- | :--- | :--- | :--- |
| **Trade Intent** | `DecisionMaking` | `EVT:TRADE_INTENT_PROPOSED` | `V2RuntimeFacade.on_trade_intent_proposed` | `symbol`, `side`, `qty`/`quantity`, `price` |
| **Manual Open** | `AuroraBridge` | `CMD:OPEN` | `V2RuntimeFacade.handle` -> `EventAdapter` | `symbol`, `side`, `qty`, `order_type` |
| **Manual Close** | `AuroraBridge` | `CMD:CLOSE` | `V2RuntimeFacade.handle` -> `EventAdapter` | `symbol`, `qty` (optional) |
| **Cancel Order** | `AuroraBridge` | `CMD:CANCEL` | `V2RuntimeFacade.handle` -> `EventAdapter` | `order_id` |
| **Trade Fill** | `BinanceAdapter` (WS) | `EVT:TRADE_EXECUTED` | `V2RuntimeFacade.on_trade_executed` | `symbol`, `side`, `qty`, `price`, `order_id` |
| **Account Update** | `BinanceAdapter` (WS) | `EVT:ACCOUNT_UPDATE_RECEIVED` | `V2RuntimeFacade.on_account_update` | `positions` (list), `balances` |

## 2. Payload Contracts (Hop-by-Hop)

Tracing the `CMD:OPEN` / `TRADE_INTENT` flow to Binance execution.

### 2.1 Flow: `TRADE_INTENT` -> Binance API

| Stage | Component | Payload Structure | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **1. Source** | `DecisionMaking` | `{"symbol": "BTCUSDT", "side": "BUY", "qty": 0.1}` | ✅ OK | `qty` or `quantity` accepted. |
| **2. Facade** | `V2RuntimeFacade` | `RuntimeEvent(kind="ENTRY_INTENT", payload={...})` | ✅ OK | Normalizes to `quantity`. |
| **3. Runtime** | `ExecPosRuntimeV2` | `payload={"symbol": "...", "side": "...", "quantity": ...}` | ✅ OK | Calls `gatekeeper` then `execution_service`. |
| **4. Service** | `ExecutionService` | `place_order(symbol, side, quantity, ...)` | ✅ OK | Prefers `place_order_v2` on adapter. |
| **5. Adapter V2** | `BinanceAdapter.place_order_v2` | `Message(op="DEC", verb="PLACE_ORDER", pld={...})` | ⚠️ **Legacy Wrap** | Wraps args into legacy `DEC` message. |
| **6. Adapter V1** | `BinanceAdapter.place_order` | `pld={"symbol": "...", "qty": "...", ...}` | ✅ OK | Normalizes `qty` (str/decimal). |
| **7. API Call** | `_place_binance_order_async` | `params={"quantity": "0.100", ...}` | ✅ OK | formatting ensures precision. |

### 2.2 Key Observations
*   **Quantity Normalization**: The system robustly handles `qty` vs `quantity` and float vs str vs Decimal. `BinanceAdapter` ensures final formatting.
*   **Legacy Wrapper**: `place_order_v2` exists solely to wrap V2 arguments into a legacy `Message` object for `place_order`. This is a minor inefficiency but safe.
*   **Symbol Handling**: `_adapt_symbol` assumes input is a string. `place_order` checks `if not symbol`, but a non-string `symbol` (e.g. `None` passed earlier) could cause issues if not caught by Pydantic/Type checks.

## 3. Behavioral Invariants

| ID | Invariant | Status | Evidence |
| :--- | :--- | :--- | :--- |
| **INV-01** | **Reduce-Only Brackets**: All TP/SL orders must be `reduceOnly=True`. | ✅ OK | `BracketService` sets `reduce_only=True`. `BinanceAdapter` respects it. |
| **INV-02** | **Quantity Precision**: Quantities sent to Binance must match step-size. | ✅ OK | `_quantize_qty` in adapter handles this. |
| **INV-03** | **Idempotency**: Duplicate `clientOrderId` must not create new orders. | ✅ OK | `ExecutionService` and `BinanceAdapter` handle `-4116` (Duplicate ID) by checking existence. |
| **INV-04** | **Single Source of Truth**: Runtime state must reflect Exchange state. | ✅ OK | `ORDERS_SNAPSHOT` and `POSITION_SYNC` events update runtime state. |

## 4. Specific Issues ("Known Issues")

| ID | Severity | Name | Description | Location |
| :--- | :--- | :--- | :--- | :--- |
| **EP-001** | P2 | **Symbol None Check** | `place_order` checks `if not symbol` but `_adapt_symbol` assumes string. Potential `AttributeError` if `None` passes through. | `binance_execution_adapter.py` |
| **EP-002** | P1 | **Connect Timeout Handling** | `httpx` timeouts return a generic error dict. `ExecutionService` must explicitly handle `ADAPTER_ERROR_TIMEOUT` to prevent retry storms or state confusion. | `execution_service.py` / `binance_execution_adapter.py` |
| **EP-003** | P2 | **Algo Endpoint Risk** | Adapter uses `/fapi/v1/order` for all orders. While `STOP_MARKET` works there, Binance recommends `/fapi/v1/algoOrder` for some advanced types. Low risk for current simple TP/SL. | `binance_execution_adapter.py` |
| **EP-004** | P0 | **Entry Price WS Keys** | **(FIXED)** Binance WS sends short keys (`ep`). Adapter now normalizes them to `entryPrice`. | `binance_execution_adapter.py` |

## 5. Suspected Weak Spots

1.  **Naming Drift**: The codebase mixes `qty` and `quantity`. While currently handled, it adds cognitive load and risk of regression if a new component misses a mapping.
2.  **Error Propagation**: The chain `Adapter -> Service -> Runtime` relies on dictionary returns for success/failure. A structured `ExecutionResult` object (used in Service) is better, but Adapter returns raw dicts or `exec_feedback` dicts.
3.  **Timeout/Retry Policy**: Retry logic is split between `BinanceAdapter` (for specific codes like -2021) and `ExecutionService` (generic retries). This split responsibility can lead to gaps or double-retries.

## 6. Tests Inventory

### 6.1 Test Suite: `tests/domains/execution_position`

*   **Adapters**: `test_binance_adapter_duplicate_idempotency.py`, `test_binance_adapter_time_sync.py`, `test_adapter_precision_guards.py`
*   **Runtime/Logic**: `test_agg_oco_races_guard_loop_vs_trade.py`, `test_agg_oco_size_sync.py`, `test_bracket_state_divergence.py`
*   **Logging/Observability**: `test_bracket_eval_snapshot_logging.py`, `test_oco_snapshot_logging.py`, `test_execpos_metrics_fills.py`
*   **Configuration**: `test_brackets_config.py`, `test_manage_config_hybrid.py`
*   **Safety**: `test_exposure_guard.py`, `test_guardian_no_autoheal_v2.py`

### 6.2 Failing Tests (Audit Phase)
*   *None identified in this static audit phase. Dynamic execution required for full verification.*
