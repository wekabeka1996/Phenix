# ExecPosRuntimeV2 Event Map

> **Status:** Canonical (Default Runtime)
> **Source:** `docs/EXEC_POS_V2_RUNTIME_SPEC.md`

## 1. Runtime Events (Input)
These events are dispatched to `ExecPosRuntimeV2.handle()`.

| Event Kind | Source | Payload | Description |
|---|---|---|---|
| `ENTRY_INTENT` | `CMD:OPEN` | `symbol`, `side`, `qty`, `price`, `order_type` | Request to open a position. Validated by Gatekeeper. |
| `CANCEL_INTENT` | `CMD:CANCEL` | `symbol`, `order_id` | Request to cancel an open order. |
| `CLOSE_INTENT` | `CMD:CLOSE` | `symbol`, `qty` (optional) | Request to close a position (market). |
| `TRADE_EXECUTED` | `EVT:TRADE` | `symbol`, `price`, `qty`, `side`, `order_id` | Fill confirmation. Updates position state. |
| `POSITION_SNAPSHOT` | `EVT:PORTFOLIO` | `positions: List[Position]` | Full state sync from exchange/portfolio. |
| `ORDERS_SNAPSHOT` | `EVT:OPEN_ORDERS` | `orders: List[Order]` | Full open orders sync. |

## 2. Runtime Actions (Output)
These actions are performed by `ExecutionService` or emitted as events.

| Action / Event | Trigger | Description |
|---|---|---|
| `ExecutionService.place_order` | `ENTRY_INTENT` | Sends order to exchange adapter. |
| `ExecutionService.cancel_order` | `CANCEL_INTENT` | Cancels order on exchange. |
| `ExecutionService.close_position` | `CLOSE_INTENT` | Sends market close order. |
| `EVT:EXEC_POS_EXPOSURE_UPDATED` | `TRADE_EXECUTED` | Emitted via `ExposureBridge` to notify risk/portfolio. |
| `WAL Write` | `TRADE_EXECUTED` | Persists `EXEC_TRADE` and `EXEC_POSITION` to disk. |
| `BRACKETS_EXEC` | `TRADE_EXECUTED` / `Guard Loop` | Logs bracket plan execution (PLACE_SL, PLACE_TP, CANCEL). |

## 3. State Transitions
State is managed in `_positions_by_symbol` and `_open_orders_by_symbol`.

- **On `ENTRY_INTENT` (Success):** Add to `_open_orders_by_symbol`.
- **On `TRADE_EXECUTED`:**
    - Update `_positions_by_symbol` (qty += fill_qty, entry_price set on first open).
    - Remove from `_open_orders_by_symbol` (if fully filled).
    - **Trigger Brackets:** Evaluate and apply TP/SL orders via `BracketService`.
- **On `CLOSE_INTENT` (Success):** Set `_positions_by_symbol[symbol]` to zero/flat.

## 4. Legacy/Deprecated Events
The following events are **NOT** handled by V2 Runtime (or handled only for logging):
- `EVT:PARTIAL_FILL` (normalized to `TRADE_EXECUTED`)
- `EVT:ORDER_UPDATED` (normalized to `ORDERS_SNAPSHOT` or ignored)
- `DEC:PLACE_ORDER` (internal FSM event, replaced by direct service calls)
- `DEC:ADJUST` (ManageFlowFSM event, not in V2)

