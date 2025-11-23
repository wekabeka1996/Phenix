# Watchdog & Anti-Spam Audit (S1)

## Що робить watchdog зараз
- Викликається з `_run_watchdog_analysis()` після `POSITION_SYNC`, `POSITION_SNAPSHOT`, `ORDERS_SNAPSHOT`.
- Будує нормалізовані позиції/ордера → `AggOcoWatchdogService.analyze()` → `BracketService.evaluate_all()`.
- Повертає `WatchdogRecommendation` (severity WARN/ALERT). **ALERT→SUPPRESS_BRACKETS**, WARN/ALERT можуть ставити `FORCE_SNAPSHOT` → runtime викликає facade → `get_open_orders(symbol)` → `ORDERS_SNAPSHOT` (throttle ~5s).
- Внутрішній набір інваріантів = ті самі, що в `BracketService` (SL/TP presence/consistency).

## Виклики `_evaluate_brackets`
- Тригериться у `_handle_trade_executed` (reason `trade_executed`), `_handle_position_sync` (reason `account_update_sync`, throttled 3s), `_run_bracket_recovery_pass` (one-shot after first `ORDERS_SNAPSHOT`).
- Throttle: для `account_update_sync` 3 секунди між APPLY; для `guard_loop` теж спирається на snapshot TTL. Інші reason (TRADE_EXECUTED) не дроселюються.
- `_evaluate_brackets` тепер перевіряє `orders_snapshot_fresh`; якщо stale → SKIP `stale_snapshot`. `_apply_bracket_plan` перевіряє duplicate SL/TP у mirror та пропускає їх (idempotent).

## Обмеження антиспаму
- Snapshot TTL введено; порожній `ORDERS_SNAPSHOT` не чистить mirror, але stale блокує PLACE.
- Idempotency: duplicate reduceOnly SL/TP (side/qty/price) пропускаються; clientOrderId детермінований.
- Watchdog ALERT може тимчасово suppress brackets, WARN/ALERT може запитати форсований snapshot (throttle).

## Патерн спаму з діагностичного логу
- Повторювані цикли для ETHUSDT (2025-11-22 20:44–20:49):
  - `POSITION_SYNC` → `BRACKETS plan result=alert why=missing_sl|pos>0_sl_count=0 actions=['PLACE_SL','PLACE_TP']`
  - `BRACKETS_EXEC apply result=alert why=brackets_account_update_sync actions=['PLACE_SL','PLACE_TP']`
  - Через ~30-40s цикл повторюється без змін `sl_count` → ознака, що ORDERS_SNAPSHOT або не приходить, або очищає state.
- WATCHDOG не блокує: `WATCHDOG_VIOLATION_DETECTED` лог лише інкрементує metrics, не перериває _apply_bracket_plan.

## Слабкі місця
- Відсутній “double-check” перед APPLY: runtime не перевіряє чи вже є SL/TP на біржі перед PLACE_SL/TP (покладається на snapshot, який може бути пустим).
- `_open_orders_by_symbol.clear()` без TTL робить state вразливим до transient пустих відповідей → cascade PLACE.
- Немає глобального backoff/idem для PLACE_SL/TP на той самий symbol/side (throttle 3s може не спрацювати, якщо ACCOUNT_UPDATE прийшло після 3s).
- Watchdog не повертає/не застосовує дії (немає autoheal або suppression), лише сигналізує.
