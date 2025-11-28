# Execution Position Bounded Context (BC)

## 1. Core Responsibilities (The "Normal World")
The `execution_position` domain is strictly limited to the following 4 responsibilities. Anything else is considered auxiliary/observability.

### 1.1. Accept Intents
The domain accepts high-level trading intents from Decision/AuroraBridge.
*   **OPEN / INCREASE**: Open a new position or add to an existing one.
*   **REDUCE / CLOSE**: Close a position partially or fully.
*   **CANCEL**: Cancel specific orders (Entry or Brackets).

### 1.2. Maintain Local State
The domain maintains a "best-effort" local view of the world to make fast decisions.
*   **PositionModel**: Symbol, Side, Size, AvgEntryPrice, UnrealizedPnL.
*   **OrderModel**: Open orders by (Symbol, Side, Type).

### 1.3. Enforce Safety Invariants
The domain acts as the final safety gate before the exchange.
*   **Aggregated OCO**: Max 1 SL and 1 TP per (Symbol, Side).
*   **Fail-Closed**: If state is stale or ambiguous -> BLOCK action and log `why`.
*   **No Ghost Positions**: Do not open positions if snapshot is stale.

### 1.4. Exchange Communication (Adapter)
The domain talks to the exchange via a dumb adapter.
*   **Commands**: `place_order`, `cancel_order`.
*   **Queries**: `get_open_orders`, `get_positions`.
*   **Error Handling**: Handle standard Binance errors (-2010, -2021, -4116, -4137, -429).

### 1.5. Physical Structure
*   **Core**: `apps/reference/domains/execution_position/` (Root) + `shadow_execpos/` (V2 Runtime).
*   **Infra**: `apps/reference/domains/execution_position/infra/` (Factories, Adapters, Utils).
*   **Observability**: `apps/reference/domains/execution_position/observability/` (Metrics, Drift).

---

## 2. Out of Scope (Auxiliary)
These functions must be moved to separate modules (`observability`, `diagnostics`, `infra`).
*   **WAL (Write-Ahead Log)**: Recording events for replay.
*   **Metrics**: Prometheus/Grafana counters.
*   **Drift Monitoring**: Comparing local state vs exchange state (async).
*   **Replay / Backtest**: Re-running history.
*   **A/B Testing**: Experiment logic.

---

## 3. Event Contract

### 3.1. Inputs (Inbound Events/Intents)
| Event / Intent | Source | Description |
| :--- | :--- | :--- |
| `INTENT:OPEN` | Decision | Request to open/increase position. |
| `INTENT:CLOSE` | Decision | Request to close/reduce position. |
| `INTENT:CANCEL` | Decision | Request to cancel specific orders. |
| `EVT:TRADE_EXECUTED` | Adapter (WS) | Fill confirmation. |
| `EVT:ORDER_UPDATED` | Adapter (WS) | Order status change (New, Canceled, Rejected). |
| `EVT:ACCOUNT_UPDATE` | Adapter (WS) | Balance/Position update. |
| `EVT:SNAPSHOT_RECEIVED` | Adapter (REST) | Response to `get_open_orders` / `get_positions`. |

### 3.2. Outputs (Outbound Events/Commands)
| Event / Command | Destination | Description |
| :--- | :--- | :--- |
| `CMD:PLACE_ORDER` | Exchange | HTTP request to place order. |
| `CMD:CANCEL_ORDER` | Exchange | HTTP request to cancel order. |
| `EVT:POSITION_UPDATED` | Aurora | Local position state changed. |
| `EVT:BRACKETS_UPDATED` | Aurora | SL/TP orders updated. |
| `EVT:EXECUTION_ERROR` | Aurora | Critical error (e.g. API failure). |
| `EVT:GUARD_BLOCKED` | Aurora | Action blocked by safety invariant. |
