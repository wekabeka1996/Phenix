# ExecPosRuntimeV2 Behavior Specification

> **Status:** Canonical (Default Runtime)
> **Source:** `docs/EXEC_POS_V2_RUNTIME_SPEC.md`
> **Legacy Note:** The split-FSM architecture (`OpenFlowFSM`, `ManageFlowFSM`, `CloseFlowFSM`) is deprecated.

## 1. Overview
`ExecPosRuntimeV2` is a unified, event-driven runtime that manages execution state (`_positions_by_symbol`, `_open_orders_by_symbol`) in memory. It replaces the complex multi-FSM coordination with a linear pipeline:
`Event` → `Idempotency` → `Enrichment` → `State Update` → `WAL` → `Exposure` → `Watchdog`.

## 2. Core Capabilities
- **Entry/Cancel/Close:** Supports `ENTRY_INTENT` (Open), `CANCEL_INTENT` (Cancel), `CLOSE_INTENT` (Close Position).
- **State Tracking:** Maintains real-time position quantity, side, and entry price. Tracks open orders.
- **Idempotency:** Deduplicates fills based on `order_id` + `cumulative_qty`.
- **Persistence:** Writes `EXEC_TRADE` and `EXEC_POSITION` events to a Write-Ahead Log (WAL) for recovery.
- **Safety:** `Gatekeeper` validates intents before execution. `Watchdog` detects invariants (detect-only).

## 3. Key Limitations (Current V2)
- **Stubbed Close:** `CLOSE_INTENT` simply zeros the position state and sends a market close order; it does not manage complex close flows.
- **No Trailing Stop (Active):** Trailing logic is evaluated (`_evaluate_trailing`) and logged, but currently **does not** execute stop updates (log-only mode).

## 4. Bracket Management (Aggregated OCO)
V2 Runtime implements **Aggregated OCO** logic via `BracketService` and a background `Guard Loop`.
- **Trigger:** Brackets are evaluated on `TRADE_EXECUTED`, `POSITION_SYNC`, and periodically via `Guard Loop` (1s interval).
- **Logic:** `BracketService` calculates required TP/SL orders based on net position size and `aggregated_oco` config.
- **Execution:** `_apply_bracket_plan` executes `PLACE_SL`, `PLACE_TP`, `CANCEL` actions to align open orders with the plan.
- **Safety:** `Guard Loop` ensures brackets exist even if the initial placement fails (eventual consistency).

## 5. Event Flow
### 5.1 ENTRY_INTENT
1. **Gatekeeper:** Checks min_qty, min_notional, step_size, cooldown.
2. **Execution:** Calls `ExecutionService.place_order`.
3. **State:** Adds to `_open_orders_by_symbol`.

### 5.2 TRADE_EXECUTED (Fill)
1. **Idempotency:** Checks if fill was already processed.
2. **Enrichment:** Adds price/symbol details.
3. **State Update:** Updates `_positions_by_symbol` (qty, side, entry_price).
4. **WAL:** Writes trade and position update.
5. **Exposure:** Emits `EVT:EXEC_POS_EXPOSURE_UPDATED`.
6. **Brackets:** Triggers `_evaluate_brackets` -> `_apply_bracket_plan` (places TP/SL).
7. **Watchdog:** Analyzes state for violations.

### 5.3 CLOSE_INTENT
1. **Execution:** Calls `ExecutionService.close_position`.
2. **State:** Zeros out position in `_positions_by_symbol`.

## 6. State Model
- **Positions:** `{symbol: {qty, side, entry_price}}`.
  - *Note:* `entry_price` is set on first open; averaging on scale-in is not yet implemented in runtime state.
- **Orders:** List of open orders per symbol.

## 7. Observability
- **Metrics:** Counters for events, fills, gatekeeper decisions, watchdog violations, bracket alerts.
- **Logs:** Structured JSON logs for all intents, state changes, and bracket plans (`BRACKETS`, `BRACKETS_EXEC`).


