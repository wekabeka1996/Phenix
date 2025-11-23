# ExecPosRuntimeV2 — Event Map (S1)

| Івент (name/kind) | Джерело | Куди потрапляє | Ефект у runtime | Коментарі |
| --- | --- | --- | --- | --- |
| `EVT:TRADE_EXECUTED` (Message) | Binance WS `_emit_trade_event` у `BinanceExecutionAdapter` (fallback коли order_index відсутній теж) | `V2RuntimeFacade.on_trade_executed` → RuntimeEvent `{kind:"TRADE_EXECUTED"}` | `_handle_trade_executed`: idempotency → enrich price → `apply_fill` (PositionState) → WAL (trade+position) → exposure emit → watchdog → trailing → `_evaluate_brackets(reason="trade_executed")` | `payload.qty/quantity/price/side` критичні; side upper-case |
| `EVT:ACCOUNT_UPDATE_RECEIVED` | Binance WS `_handle_account_update` | `V2RuntimeFacade.on_account_update` | Facade: якщо qty!=0 → `get_open_orders()` → emit `ORDERS_SNAPSHOT`; потім `POSITION_SYNC` per symbol | Triggers bracket eval with reason `account_update_sync` (throttled 3s) |
| `RuntimeEvent POSITION_SYNC` | Згенерований у facade з `EVT:ACCOUNT_UPDATE_RECEIVED` | `ExecPosRuntimeV2.handle` | `_handle_position_sync` → `_handle_single_position_update` (PositionState overwrite) → watchdog → `_evaluate_brackets` (if qty!=0, throttled) | Вхід payload `positions=[{symbol, qty, entry_price, ...}]` |
| `RuntimeEvent POSITION_SNAPSHOT` | `MessageToRuntimeEventAdapter` (EVT:PORTFOLIO_STATE_UPDATED / POSITION_SNAPSHOT / ACCOUNT_UPDATE) | Runtime | `_handle_position_snapshot` → `_handle_single_position_update` for each | Служить для DR/rehydrate або REST snapshot |
| `RuntimeEvent ORDERS_SNAPSHOT` | Facade після `get_open_orders()` або `MessageToRuntimeEventAdapter` (EVT:OPEN_ORDERS_UPDATED) | Runtime | `_handle_orders_snapshot`: очищує `_open_orders_by_symbol`, додає ордери, запускає watchdog, `bracket_recovery_pass` якщо ще не виконаний | Payload `orders=[{symbol, side, type, qty, stopPrice, reduceOnly,...}]` |
| `RuntimeEvent ENTRY_INTENT` | CMD:OPEN через `MessageToRuntimeEventAdapter` | Runtime | Gatekeeper -> ExecutionService.place_order -> додає в `_open_orders_by_symbol` | Зараз без bracket-side effects |
| `RuntimeEvent CANCEL_INTENT` | CMD:CANCEL/CANCEL_ORDER | Runtime | ExecutionService.cancel_order -> видаляє ордер з `_open_orders_by_symbol` | — |
| `RuntimeEvent CLOSE_INTENT` | CMD:CLOSE/FORCE_CLOSE | Runtime | CloseFlowService.plan_close -> ExecutionService.close_position; при FULL close PositionState скидається | — |
| `BRACKETS` (log event) | `_evaluate_brackets` після plan | `logging_v2.log_runtime_event` | Лише лог: `actions`, `severity`, `why` | Викликає `_apply_bracket_plan` |
| `BRACKETS_EXEC` | `_apply_bracket_plan` | Лог/guardian | Виконання плану: PLACE_SL/PLACE_TP/CANCEL/ADJUST через ExecutionService | Throttle timestamp оновлюється після успішної аплікації |
| `BRACKETS_RECOVERY_PLAN` | `_run_bracket_recovery_pass` | Лог/guardian | Одноразовий apply на стартапі після першого ORDERS_SNAPSHOT | — |
| `WATCHDOG_VIOLATION_DETECTED` | `_run_watchdog_analysis` (AggOcoWatchdogService.analyze) | Лог/metrics | Рахує порушення, але без авто-heal | Вихід `WatchdogRecommendation` (ALERT/WARN) |
| `TRAILING` | `_evaluate_trailing` | Лог | Лише лог/metrics | Немає викликів адаптера |

## Payload примітки
- TRADE_EXECUTED: очікує `symbol`, `side` (BUY/SELL), `quantity/qty`, `price`, optional `trade_id`, `clientOrderId`.
- POSITION_SYNC/SNAPSHOT: `positions` зі `symbol`, `qty`, `entry_price/entryPrice`, `unrealized_pnl`, `update_time/ts`.
- ORDERS_SNAPSHOT: `orders` з `symbol`, `side`, `type/order_type`, `quantity/origQty/qty`, `stopPrice`, `reduceOnly`, `status`.

