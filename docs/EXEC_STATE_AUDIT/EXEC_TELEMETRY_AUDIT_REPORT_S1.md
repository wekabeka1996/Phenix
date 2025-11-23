# EXEC-STATE-AUDIT-V2 — Зведений звіт (S1)

## Ланцюг «як є»
Binance WS/REST → `BinanceExecutionAdapter` (REST place/cancel; WS `ORDER_TRADE_UPDATE`/`ACCOUNT_UPDATE` → `EVT:*`) → FSMCore → `V2RuntimeFacade` (Message → RuntimeEvent, робить `get_open_orders()` на account update) → `ExecPosRuntimeV2` (держить `_positions_by_symbol`/`_open_orders_by_symbol`, викликає BracketService/Watchdog) → `BracketService`/`AggOcoWatchdogService` (детект/плани) → `ExecutionService` (PLACE_SL/TP/CANCEL) → логи `execpos_v2_runtime.jsonl` + metrics/audit.

## Проблемні точки (помічені в S1)
- `ORDERS_SNAPSHOT` TTL/empties: REST `get_open_orders()` повертає пусто → runtime очищує state → планує PLACE_SL/TP (`missing_sl|pos>0_sl_count=0`) навіть якщо SL існує на біржі.
- `BRACKETS_EXEC` без idempotency: кожен цикл APPLY робить нові clientOrderId, throttle працює тільки для `account_update_sync`, але не для інших причин.
- Відсутня перевірка свіжості snapshot перед bracket evaluate → `POSITION_SYNC` без ORDERS_SNAPSHOT може запустити PLACE_SL/TP.
- Watchdog (AggOco) лише детектує, не гальмує APPLY і не повертає блокувальні дії.
- Time-sync покритий, але recvWindow/offset не перевіряється перед кожним REST викликом (поле `server_time_offset` може застаріти >5m якщо WS немає).

## Мінімальний набір інваріантів (пропозиція)
- **PositionState**: перед PLACE_SL/TP повинна існувати остання `ORDERS_SNAPSHOT` не старша TTL (наприклад, 5s) або explicit “no snapshot” flag → тоді PLACE заборонити.
- **Bracket-state**: якщо `sl_count>0` для `(symbol, side)`, `missing_sl` план заборонений; якщо `sl_count=0` але останній snapshot пустий, потрібен повторний REST snapshot перед PLACE.
- **Order-mirror**: `ORDERS_SNAPSHOT` не очищує state, поки не отримано успішну відповідь (мердж/TTL замість `clear()`).
- **Time-sync/recvWindow**: якщо `abs(server_time_offset)>500ms` або останній sync >5m, перед REST викликом робити `_sync_time_with_server()`; recvWindow ≥5000ms для всіх POST/DELETE.

## Planned fixes implemented (P1)
- Snapshot TTL + no-clear-on-empty: ORDERS_SNAPSHOT зберігає mirror, stale → блок PLACE_SL/TP, з логом `stale_snapshot`.
- Idempotent brackets: duplicate SL/TP (side/qty/stopPrice) пропускаються, clientOrderId детермінований.
- Guard-loop 1 Hz: локальні інваріанти без REST, але з повагою до fresh snapshot.
- Watchdog integration: ALERT → тимчасове `BRACKETS_SUPPRESSED`; WARN → запит на оновлення snapshot.

## Пріоритизація
- **P0**: (1) PLACE_SL/TP без свіжого ORDERS_SNAPSHOT (прямий тригер спаму); (2) `clear()` на пустому snapshot; (3) Відсутність idempotency/TTL для bracket apply → масове створення ордерів; (4) Watchdog не блокує APPLY навіть при ALERT.
- **P1**: (1) Time-sync тільки кожні 5m/на ping — при WS даун/лонг-ран може накопичитись drift; (2) Відсутність мерджу позицій з WAL при POSITION_SYNC (можливі стрибки scale_in/out).
- **P2**: (1) Немає централізованих metrics по latency REST/WS; (2) Локальний event-bus не використовується; (3) Слабо документовані mapping-и reduceOnly/closePosition.
