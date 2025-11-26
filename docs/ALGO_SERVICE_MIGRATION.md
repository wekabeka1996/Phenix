# Binance Algo Service Migration Blueprint

## 1. Problem Statement
Current implementation places conditional orders (STOP, TAKE_PROFIT, TRAILING_STOP) via the legacy `POST /fapi/v1/order` endpoint.
Binance documentation and best practices recommend using the dedicated Algo Service endpoints (`/fapi/v1/algoOrder`) for these order types to ensure better reliability and separation of concerns.
Continuing to use `/fapi/v1/order` for conditionals poses risks of:
- Potential duplicate handling if mixed with Algo Service in the future.
- Violation of "Aggregated OCO" invariants if state is not tracked correctly.
- Future deprecation of legacy behavior.

## 2. Scope
- **Domains**: `execution_position`
- **Components**:
    - `ExecPosRuntimeV2`
    - `BracketService` (Aggregated OCO logic)
    - `BinanceExecutionAdapterV2`

## 3. Design Goals
- **Fail-closed**: If Algo Service fails, do NOT fallback to legacy endpoint silently.
- **Config-driven**: Controlled via `use_algo_service_for_conditionals` feature flag.
- **No external contract changes**: The `DEC` (Decision) and `CMD` (Command) interfaces remain unchanged.
- **Idempotency**: Ensure `clientAlgoOrderId` is used correctly.

## 4. Endpoint Mapping

| Order Type | Current Endpoint | Future Endpoint (Flag ON) |
| :--- | :--- | :--- |
| LIMIT / MARKET | `POST /fapi/v1/order` | `POST /fapi/v1/order` (Unchanged) |
| STOP / STOP_MARKET | `POST /fapi/v1/order` | `POST /fapi/v1/algoOrder` |
| TAKE_PROFIT / TP_MARKET | `POST /fapi/v1/order` | `POST /fapi/v1/algoOrder` |
| TRAILING_STOP_MARKET | `POST /fapi/v1/order` | `POST /fapi/v1/algoOrder` |

Future phases will adopt:
- `DELETE /fapi/v1/algoOrder`
- `GET /fapi/v1/openAlgoOrders`

## 5. Internal Contract for Conditional Orders
The adapter will normalize conditional order parameters into a structure like:

```python
@dataclass
class ConditionalOrderContract:
    symbol: str
    side: str
    quantity: Decimal
    trigger_price: Decimal
    algo_type: str  # STOP, TAKE_PROFIT, TRAILING_STOP
    working_type: str  # MARK_PRICE, CONTRACT_PRICE
    reduce_only: bool
    time_in_force: str
    client_order_id: str
```

Mapping to `/fapi/v1/algoOrder`:
- `symbol` -> `symbol`
- `side` -> `side`
- `quantity` -> `quantity`
- `trigger_price` -> `stopPrice` (for STOP/TP) or `activationPrice` (for Trailing)
- `algo_type` -> `type` (STOP_MARKET, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET)
- `working_type` -> `workingType`
- `reduce_only` -> `reduceOnly`

## 6. Failure Modes & Safety
New error kind: `ADAPTER_ERROR_ALGO_SERVICE`.

**Rules:**
1. **Flag OFF**: Always use `_place_conditional_via_rest` (`/fapi/v1/order`).
2. **Flag ON**: Always use `_place_conditional_via_algo_service` (`/fapi/v1/algoOrder`).
3. **Failure**: If `/fapi/v1/algoOrder` returns error (non-200), return `ExecutionResult(success=False, error_kind=ADAPTER_ERROR_ALGO_SERVICE)`. **NO FALLBACK**.

## 7. Rollout Plan
- **Phase 0 (Current)**: Blueprint, Feature Flag, Skeleton Implementation, Tests.
- **Phase 1**: Enable flag on Testnet for SL/TP. Verify execution.
- **Phase 2**: Migrate Cancel logic and Snapshot logic (openAlgoOrders).
- **Phase 3**: Enable default on Mainnet.

## 8. State Model & Events (Phase 1)

### 8.1. AlgoOrderState
Internal representation of an Algo Order's lifecycle.

```python
@dataclass
class AlgoOrderState:
    algo_order_id: str          # Binance-assigned ID
    client_algo_order_id: str   # Our ID
    symbol: str
    side: str                   # BUY/SELL
    algo_type: str              # STOP_MARKET, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET
    status: str                 # NEW, WORKING, FILLED, CANCELED, REJECTED
    quantity: Decimal
    trigger_price: Decimal
    position_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
```

### 8.2. Internal Events
Generated from `ALGO_UPDATE` user stream events.

- `EVT:ALGO_ORDER_NEW`: Order accepted by engine.
- `EVT:ALGO_ORDER_WORKING`: Order triggered or active.
- `EVT:ALGO_ORDER_FILLED`: Order executed (fully or partially).
- `EVT:ALGO_ORDER_CANCELED`: Order canceled by user or system.
- `EVT:ALGO_ORDER_REJECTED`: Order rejected.

### 8.3. Integration
- **AlgoOrderIndex**: In-memory store for `AlgoOrderState`, indexed by `client_algo_order_id` and `algo_order_id`.
- **BracketService**: Receives Algo Orders as `BracketLeg`s (via `OrderView` adaptation) to maintain Aggregated OCO invariants.

## 9. Phase 2: Lifecycle Management (Cancel & Snapshot)

### 9.1. Cancellation
- **Endpoint**: `DELETE /fapi/v1/algoOrder`
- **Logic**:
    - If `use_algo_service_for_conditionals` is ON:
        - Use `DELETE /fapi/v1/algoOrder` for orders identified as Algo Orders.
        - **Idempotency**: Handle "Unknown Order" (-2011) as success.
        - **Batch Cancel**: `DELETE /fapi/v1/allOpenAlgoOrders` (optional, for cleanup).

### 9.2. Startup Snapshot
- **Endpoint**: `GET /fapi/v1/openAlgoOrders`
- **Logic**:
    - On `ExecPosRuntimeV2` startup:
        - Call `adapter.load_open_algo_orders_snapshot()`.
        - Fetch open Algo Orders.
        - Populate `AlgoOrderIndex`.
        - Merge into runtime's `_open_orders_by_symbol` or ensure `BracketService` can see them.
    - **Normalization**: Algo Orders must be converted to a format compatible with `BracketOrderView` so the runtime recognizes them as valid brackets.

### 9.3. Runtime Integration
- `ExecPosRuntimeV2` startup sequence:
    1. `adapter.start()` (WS connection)
    2. `adapter.load_open_algo_orders_snapshot()` (Populate Index)
    3. `adapter.get_open_orders()` (Standard orders)
    4. `adapter.get_open_positions()`
- **Unified View**: The runtime must see a unified view of "active orders" (Standard + Algo) to correctly evaluate brackets.

## 10. Testnet Rollout Config

To enable Algo Service on Testnet, use a dedicated configuration file (e.g., `configs/execution_testnet_algo.yaml`) with the following override:

```yaml
trading:
  execution:
    use_algo_service_for_conditionals: true
```

**WARNING**: Never turn this ON in mainnet configs until the Go/No-Go checklist is green.

### 10.1. Isolation
- Ensure `trading_env` is set to `"test"`.
- Limit symbols to a small subset (e.g., `BTCUSDT`, `ETHUSDT`) to reduce noise.
- Verify that `BinanceExecutionAdapter` logs `[BinanceAdapter] Algo Service for conditionals: True` on startup.
