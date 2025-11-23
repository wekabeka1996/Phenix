# Binance Execution Adapter — REST/WS Audit (S1)

## REST виклики (за кодом `binance_execution_adapter.py`)
- `GET /fapi/v1/time` — time sync перед стартом WS + періодичний resync кожні ~5 хв, retry після -1021.
- `GET /fapi/v2/positionRisk` — `get_open_positions()` з backoff/fallback mode; опціональний `symbol` фільтр.
- `GET /fapi/v1/openOrders` — `get_open_orders()` з backoff/fallback mode; опціональний `symbol` фільтр.
- `POST /fapi/v1/listenKey` / `PUT /fapi/v1/listenKey` — отримання/refresh WS listenKey.
- `POST /fapi/v1/order` — створення ордерів (MARKET/LIMIT/STOP_MARKET/TAKE_PROFIT_MARKET); `recvWindow=5000`.
- `DELETE /fapi/v1/order` (через `_place_binance_order_async` cancel path) — відміна ордерів; error handling для -2011/-2021/-4116/-4137/-4164/-429.
- `GET /fapi/v1/premiumIndex` — `_get_mark_price_async` для recovery -4024 (percent price band).

## WS обробники (USER_DATA_STREAM)
- `ORDER_TRADE_UPDATE`
  - Парсить `o` payload → кореляція з `fsm_core.order_index`.
  - Емісія `EVT:TRADE_EXECUTED` (коли `z/l` > 0) + `EVT:ORDER_STATE_CHANGED` (any status).
  - Статуси: NEW/PARTIALLY_FILLED/FILLED/CANCELED/REJECTED/EXPIRED (mapped).
  - Термінальні стани → `order_index.mark_terminal`, `observe_order_lifecycle`.
- `ACCOUNT_UPDATE`
  - Payload `a`: `B` (balances), `P` (positions).
  - Емісія `EVT:ACCOUNT_UPDATE_RECEIVED` із `positions`/`balances`.

## Time-sync / retry
- Старт: `_sync_time_with_server_blocking()` викликається перед WS запуском.
- `_get_signed_params`: `timestamp = now + server_time_offset`, `recvWindow=5000`.
- WS loop: resync кожні 300s (і на ping timeout).
- Retry -1021: резинх, rebuild підпису, повторний POST.
- Retry/autoheal для брекетів: -2021 (reprice), -4116 (new clientOrderId), -4137/-4164 (qty adjust), -4024 (mark price band), -429 (exponential backoff).

## Sequence sketches (як є)
1) **Відкриття ордера**
   - DEC:PLACE_ORDER → `BinanceExecutionAdapter.place_order()` → `POST /fapi/v1/order`.
   - WS `ORDER_TRADE_UPDATE` (NEW/PARTIALLY_FILLED/FILLED) → emit `EVT:TRADE_EXECUTED` (if qty>0) → runtime.
   - `EVT:ORDER_STATE_CHANGED` для синхронізації індексу/аудиту.

2) **Заповнення ордера**
   - PARTIALLY_FILLED/FILLED у WS → `_build_trade_executed_payload` бере `z` (cumQty) > `l`.
   - Runtime V2 застосовує fill (PositionState), WAL, exposure update, `BRACKETS` evaluate.

3) **Зміна позиції вручну (UI біржі)**
   - Binance генерує `ACCOUNT_UPDATE` з позицією `P`.
   - Адаптер емісить `EVT:ACCOUNT_UPDATE_RECEIVED`.
   - `V2RuntimeFacade.on_account_update` → REST `get_open_orders()` → `ORDERS_SNAPSHOT` + `POSITION_SYNC`.
   - Runtime виконує `_handle_position_sync` → `_evaluate_brackets(reason=account_update_sync)` (з throttling 3s).

## WS reconnection/backoff
- WS loop з exponential backoff (1s → 60s) на помилку/close.
- Ping keep-alive (30s timeout → ping).
- ListenKey refresh через `_refresh_listen_key`.

