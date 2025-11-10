# GAPS — прогалини у спостережуваності та артефактах (READ‑ONLY аудит)

## Відсутні/недостатні сигнали
- Ретраї TP/SL: немає подій `TP_SL_RETRY_-2021`, `TP_SL_RETRY_-4116` з attempt №, CID, причиною.
- WS‑lag: не вимірюється різниця `updateTime` (Binance) ↔ локальний час обробки в listener’ах.
- Reconcile‑on‑Close: немає явних логів про послідовність `CLOSE → openOrders(scan) → cancel(all) → openOrders=0`.
- Орфан‑метрики: немає лічильників `orphaned_brackets_total`, `reconcile_cancels_total`, `cancel_on_close_total`.
- Ledger по `newClientOrderId`: не логуються `{CID, symbol, side, notional, retry_reason, ts}` для діагностики ‑4116.
- REST account/openOrders снапшоти на ключових етапах (після CLOSE, після orphan‑cleanup) відсутні.

## Що додати у логування (без змін коду — як вимога до наступних сесій)
- Події рівня FSM/Adapter:
  - `TP_SL_RETRY_-2021 {attempt, cid, stopPrice_before/after, delta_bps}`
  - `TP_SL_RETRY_-4116 {attempt, cid_old, cid_new, exists_on_exchange}`
  - `CANCEL_ON_CLOSE_START/END {symbol, cancelled=N, duration_ms}`
  - `RECONCILE_SCAN {symbol, open_orders=N} / RECONCILE_CANCEL {orderId, type}`
- Метрики:
  - `retry_2021_total`, `retry_4116_total`, `cancel_on_close_total`, `orphan_cleanup_total`
  - `ws_lag_ms` (percentiles), `avg_reconcile_duration_ms`

## Які READ‑артефакти потрібні для повної валідації DoD
- Серії REST:
  - `GET /fapi/v1/openOrders?symbol=SYMBOL` одразу після CLOSE до `0` ордерів.
  - `GET /fapi/v3/account` (поле `totalOpenOrderInitialMargin`) до/після CLEANUP.
  - `GET /fapi/v1/openOrder?symbol=SYMBOL&origClientOrderId=CID` при ‑4116.
- WS журнали `CONDITIONAL_ORDER_*` (включно з `TRIGGER_REJECT`) із таймстемпами Binance і локальними.

## Узагальнення
Наявні логи дозволили підтвердити ключові корені (частковий cancel‑on‑close, відсутність pre‑flight, відсутність backoff/‑4116 обробки). Для остаточного PASS по DoD потрібні цільові логи ретраїв, reconcile‑послідовності та REST‑снапшоти.

