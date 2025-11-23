# Execution Position FSM Event Map

> Canonical runtime behavior and flow details are in `docs/EXEC_POS_V2_RUNTIME_SPEC.md`.  
> This file summarizes how legacy Messages are mapped into ExecPosRuntimeV2 events (actual adapters in `shadow_execpos/event_adapter.py`).

## Legacy FSM Events (Historical)

Legacy Open/Manage/Close FSM flows are kept only for history; they are not active when `runtime_mode="v2"` (current default).

## Message → RuntimeEvent Mapping (V2 runtime)

`MessageToRuntimeEventAdapter` translates legacy `vfoundation` messages into `RuntimeEvent` objects for `ExecPosRuntimeV2`.

| Legacy Message | RuntimeEvent Kind | Key Payload Fields | Notes |
| :--- | :--- | :--- | :--- |
| `CMD:OPEN` | `ENTRY_INTENT` | `symbol`, `side`, `quantity`, `price`, `order_type` | Entry request |
| `CMD:CANCEL` | `CANCEL_INTENT` | `symbol`, `order_id`, `client_order_id` | Cancel request |
| `CMD:CLOSE` | `CLOSE_INTENT` | `symbol`, `quantity`, `reason` | Close position request |
| `CMD:FORCE_CLOSE` | `CLOSE_INTENT` | `symbol`, `quantity`, `reason="force_close"`, `is_force=True` | Risk management force close |
| `EVT:TRADE_EXECUTED` | `TRADE_EXECUTED` | `symbol`, `side`, `quantity`, `price`, `role`, `trade_id` | Fill event |
| `EVT:FILL` | `TRADE_EXECUTED` | `symbol`, `side`, `quantity`, `price`, `role`, `trade_id` | Fill event (alias) |
| `EVT:POSITION_SNAPSHOT` | `POSITION_SNAPSHOT` | `positions` (list of normalized dicts) | Full position state |
| `EVT:ACCOUNT_UPDATE` | `POSITION_SNAPSHOT` | `positions` (list of normalized dicts) | Account update (mapped to snapshot) |
| `EVT:ORDERS_SNAPSHOT` | `ORDERS_SNAPSHOT` | `orders` (list of normalized dicts) | Open orders state |

### Normalization
- **Positions**: Normalized to `{symbol, qty, entry_price, side, unrealized_pnl, update_time}`.
- **Orders**: Normalized to `{order_id, client_order_id, symbol, side, type, quantity, price, stop_price, reduce_only, status}`.
- **Types**: Quantities and prices are converted to `float` where possible.
