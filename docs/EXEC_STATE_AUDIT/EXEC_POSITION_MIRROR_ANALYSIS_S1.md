# Execution Position Mirror — Position/Orders Snapshot Audit (S1)

## Моделі стану
- `PositionState` (`shadow_execpos/position_model.py`): поля `qty` (signed), `avg_entry_price`, `realized_pnl`, `unrealized_pnl`, `side` (derived), `last_update_time`, counters `scale_in/out`.
- `_open_orders_by_symbol` (runtime state): список сирих ордерів з REST/WS (`order_id`, `client_order_id`, `side`, `type`, `qty`, `price`, `stop_price`, `reduce_only`, `status`, timestamps).
- `BracketService` класифікація → `BracketState` з `sl_count`/`tp_count`, `sl_legs`/`tp_legs`.

## Як оновлюється позиція (`POSITION_SYNC`)
1) Джерело: `EVT:ACCOUNT_UPDATE_RECEIVED` → facade → RuntimeEvent `POSITION_SYNC` (per symbol).
2) `_handle_single_position_update`:
   - `qty` з `qty`/`positionAmt`, `entry_price` з `entryPrice`.
   - Повністю перезаписує `PositionState` для symbol (без мерджу з попереднім WAL).
   - Тригерить `_run_watchdog_analysis`.
3) `_handle_position_sync` після оновлення одразу викликає `_evaluate_brackets(reason="account_update_sync")` якщо `abs(qty)>0` (з 3s throttle).

## Як оновлюються відкриті ордери (`ORDERS_SNAPSHOT`)
1) Джерело: `V2RuntimeFacade.on_account_update` викликає `adapter.get_open_orders()` → emit `ORDERS_SNAPSHOT`.
2) Runtime `_handle_orders_snapshot`:
   - `self._open_orders_by_symbol.clear()` (повне скидання, потім додає всі ордери).
   - watchodg → `_run_bracket_recovery_pass()` якщо ще не виконаний.
3) BracketService класифікує SL/TP: шукає `reduce_only`/`stopPrice`/`order_type` (`STOP_MARKET`/`TAKE_PROFIT_MARKET`), `closePosition`.

## Спостереження з діагностики (`diagnostics_tp_spam_ETHUSDT_20251123_003144.txt`)
- `BRACKETS`/`BRACKETS_EXEC` для `ETHUSDT` повторюються кожні ~30-40с з `why=missing_sl|pos>0_sl_count=0` і діями `['PLACE_SL', 'PLACE_TP']` (приклади: 20:44:16.99, 20:45:21.01, 20:45:22.65, 20:45:54.73, 20:46:59.07, 20:48:04.97, 20:49:09.92).
- Це означає: runtime бачить `pos>0` але `sl_count=0`, тобто ORDERS_SNAPSHOT або неправильно класифікує SL/TP, або не надходить.
- Під час циклів `BRACKETS_EXEC` → `BRACKETS plan` → `BRACKETS_EXEC` (reason `brackets_account_update_sync`) без підтверджених ORDERS_SNAPSHOT для ETHUSDT у логах.

## Поточні розриви
- `ORDERS_SNAPSHOT` видаляє всі попередні ордери перед додаванням; якщо REST повернув порожній список (тимчасово) або виклик не відбувся, `sl_count` падає до 0 → план `PLACE_SL/TP`.
- Класифікація SL/TP покладається на `reduceOnly`/`stopPrice`/`order_type`; якщо REST віддає статуси/поля інакше (наприклад, без `reduceOnly`), класифікація може не спрацювати.
- `POSITION_SYNC` не перевіряє узгодженість з ORDERS_SNAPSHOT (немає інваріанта “не ставити SL, якщо snapshot відсутній”).

## Snapshot freshness & TTL (нова логіка)
- `ExecPosRuntimeV2` тримає `self._last_orders_snapshot_ts` / `self._last_position_snapshot_ts` і конфіг `snapshot.orders_ttl_sec/position_ttl_sec`.
- Порожній `ORDERS_SNAPSHOT` більше не очищує `_open_orders_by_symbol`; mirror зберігається, але вважається stale (блок для PLACE).
- `_is_orders_snapshot_fresh(symbol)` → якщо stale, `_evaluate_brackets(reason=account_update_sync|guard_loop)` пропускає PLACE_SL/TP і логить `stale_snapshot`.
- Bracket apply перевіряє еквівалентні SL/TP у mirror перед PLACE (idempotent guard).

## Інваріанти, що мають триматися
- Якщо на біржі існують SL/TP для `(symbol, side)`, класифікація повинна дати `sl_count>0`/`tp_count>0`; `ORDERS_SNAPSHOT` не може занулювати рахунок без перевірки часу/версії.
- `POSITION_SYNC` не має генерувати `PLACE_SL/PLACE_TP`, поки немає свіжого `ORDERS_SNAPSHOT` (або поки snapshot не старший за TTL).
- `ORDERS_SNAPSHOT` не повинен очищати `_open_orders_by_symbol` без захисного мерджу/TTL, якщо REST повернув пусто (rate limit / network gap).
- `brackets_account_update_sync` повинні мати anti-loop guard: якщо останній `ORDERS_SNAPSHOT` старіший за N секунд або має `sl_count>0`, план PLACE_SL/TP заборонений.
