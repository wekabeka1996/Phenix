# ExecPosRuntimeV2 — Component Inventory (S1)

| Модуль/клас | Відповідальність | Типи івентів / API | Коментарі |
| --- | --- | --- | --- |
| `apps/reference/domains/execution_position/binance_execution_adapter.py` (`BinanceExecutionAdapter`) | REST/WS зв’язок з Binance, емісія `EVT:*` у FSMCore | REST: `/fapi/v1/time`, `/fapi/v2/positionRisk`, `/fapi/v1/openOrders`, `/fapi/v1/order` (place/cancel), `/fapi/v1/listenKey`; WS: `ORDER_TRADE_UPDATE`, `ACCOUNT_UPDATE` → `EVT:TRADE_EXECUTED`/`EVT:ACCOUNT_UPDATE_RECEIVED` | Має time-sync, exponential WS reconnect, retry для -1021/-2021/-4116/-4137/-4164/-429 |
| `apps/reference/domains/execution_position/runtime_factory.py` (`V2RuntimeFacade`) | Адаптер між FSMCore і `ExecPosRuntimeV2`: підписки на `EVT:TRADE_EXECUTED`/`EVT:ACCOUNT_UPDATE_RECEIVED`, конвертація Message → RuntimeEvent, тригер `ORDERS_SNAPSHOT` | Runtime events: `TRADE_EXECUTED`, `POSITION_SYNC`, `ORDERS_SNAPSHOT` | В on_account_update робить REST `get_open_orders()` і емісію `ORDERS_SNAPSHOT` перед `POSITION_SYNC` |
| `apps/reference/domains/execution_position/shadow_execpos/runtime.py` (`ExecPosRuntimeV2`) | Оркестратор подій/стану V2; маршрутизує events → services, тримає позиції/ордера, викликає BracketService/Watchdog | Runtime events: `ENTRY_INTENT`, `CANCEL_INTENT`, `CLOSE_INTENT`, `TRADE_EXECUTED`, `POSITION_SYNC`, `POSITION_SNAPSHOT`, `ORDERS_SNAPSHOT`; внутрішні логи `BRACKETS`, `BRACKETS_EXEC`, `BRACKETS_RECOVERY_PLAN`, `TRAILING`, `WATCHDOG_VIOLATION_DETECTED` | Додає throttling 3s для `reason=account_update_sync` в `_evaluate_brackets`; зберігає `_positions_by_symbol`, `_open_orders_by_symbol`, `_trailing_state_by_symbol` |
| `apps/reference/domains/execution_position/shadow_execpos/event_adapter.py` (`MessageToRuntimeEventAdapter`) | Мапить legacy Message (CMD/EVT) у RuntimeEvent | Entry/cancel/close intents; `TRADE_EXECUTED`/`FILL`; `POSITION_SNAPSHOT`/`ACCOUNT_UPDATE`; `ORDERS_SNAPSHOT` | Нормалізує поля (qty/entry_price/stopPrice) для runtime |
| `apps/reference/domains/execution_position/shadow_execpos/execution_service.py` (`ExecutionService`) | Обгортка над адаптером: нормалізація команд PLACE/CANCEL/CLOSE, retry/error mapping | Виклики адаптера: `place_order(_v2)`, `cancel_order`, `close_position`, `get_open_orders` | Обробляє -2011/-2021/-4116/-4137/-4164; повертає `ExecutionResult` |
| `apps/reference/domains/execution_position/shadow_execpos/gatekeeper.py` (`ExecPosGatekeeper`) | Перевірки/нормалізації перед PLACE | — | Використовується в `_handle_entry_intent` |
| `apps/reference/domains/execution_position/shadow_execpos/price_enricher.py` (`PriceEnricher`) | Збагачення TRADE_EXECUTED валідною ціною | Input: trade payload; Output: enriched payload | Викликається в `_handle_trade_executed` |
| `apps/reference/domains/execution_position/shadow_execpos/idempotency.py` (`FillIdempotency`, `EventIdempotency`) | Відсів дублікатів TRADE_EXECUTED/подій | TRADE_EXECUTED filter | Використовується в `_handle_trade_executed` |
| `apps/reference/domains/execution_position/shadow_execpos/wal_writer.py` (`ExecPosWALWriter`) | WAL записи EXEC_TRADE/EXEC_POSITION | TRADE_EXECUTED/position updates | Викликається після оновлення позиції |
| `apps/reference/domains/execution_position/shadow_execpos/trailing.py` (`TrailingStopService`) | Обчислення трейлінгу (log-only) | Event-kind `TRAILING` лог | Викликається після TRADE_EXECUTED |
| `apps/reference/domains/execution_position/shadow_execpos/close_flow.py` (`CloseFlowService`) | Планування закриття позиції | CLOSE_INTENT → ExecutionService | Визначає qty/side для close |
| `apps/reference/domains/execution_position/shadow_execpos/bracket_service.py` | Чистий обчислювач стану/плану брекетів (SL/TP), класифікація ордерів | Plan actions: `PLACE_SL`, `PLACE_TP`, `CANCEL`, `ADJUST`; State props `sl_count`/`tp_count` | Без side effects; використовується runtime/watchdog |
| `vfoundation/apps/reference/domains/execution_position/bracket_aggregator.py` | Обчислення агрегованих рівнів TP/SL (agg OCO) | Input: qty/avg_entry_price/sl_pct/tp_rr | Викликається BracketService |
| `apps/reference/domains/execution_position/shadow_execpos/watchdog.py` (`AggOcoWatchdogService`) | Детект-only watchdog поверх BracketService | Повертає `WatchdogRecommendation` (severity WARN/ALERT) | Викликається `_run_watchdog_analysis` після POSITION/ORDERS updates |
| `apps/reference/domains/execution_position/watchdog.py` (`OrderTimeoutWatchdog`) | Legacy тайм-аут/REST polling watchdog для ордерів | Емісія `EVT:TRADE_EXECUTED`/`EVT:ORDER_STATE_CHANGED` через hooks | Не інтегрований у V2 runtime, але є в домені |
| `apps/reference/domains/execution_position/shadow_execpos/position_model.py` (`PositionState`, `apply_fill`) | Чисті моделі/математика позиції | Fields: `qty`, `avg_entry_price`, `realized_pnl`, `unrealized_pnl`, `side` | Використовується runtime для внутрішнього стану |
| `apps/reference/domains/execution_position/shadow_execpos/utils_event_bus.py` (`LocalBus`) | Локальний event-bus (фолбек) | Generic `emit/listen` | Не використовується у V2 runtime за замовчуванням |

## High-level потік
- Binance WS/REST → `BinanceExecutionAdapter` (normalize → emit `EVT:*`)
- FSMCore → `V2RuntimeFacade` (Message → RuntimeEvent, підписки на WS EVT)
- `ExecPosRuntimeV2` (state, bracket/trailing/watchdog)
- `BracketService`/`AggOcoWatchdogService` (детект, план, лог)
- Логи: `execpos_v2_runtime.jsonl`, audit_logger, metrics (`metrics_logger`, `telemetry.metrics`)

