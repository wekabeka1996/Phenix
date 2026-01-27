# Backtest report v2 (Phenix)

## Problem (why the old report felt “empty”)

Раніше `reports/backtests/backtest_*.json` містив тільки:
- `metadata` (dates/symbols/timeframe/balance)
- `metrics` (PnL/ROI/DD/trades/win_rate)
- агреговані `regimes` + `features`

Але у звіті **не було**:
- на яких **стратегіях** реально генерувались інтенти (`strategy_id`)
- в якому **режимі** відкривались ордери (LIMIT/MARKET, TIF/GTX post-only, maker/taker)
- **причин закриття** (TP / SL / FLIP / EXIT / CANCEL reason codes)

## What is implemented now (v2.0.0)

Backtest звіт будується через `backtest_engine/reporting.py` і генерується в `apps/reference/main.py` (функція `run_backtest_simulation()`).

### Key additions in JSON

- `report_version`, `run_id`
- `strategies.registry` — snapshot `config/aurora/strategies.yaml` (assignments + arbitration)
- `intents[]` — всі `EVT:TRADE_INTENT_PROPOSED` з полем `strategy` + `rid` і stamped `emitted_ts_ms`
- `orders[]` — всі ордери з `MockBroker` + `open_mode` + (де можливо) `rid` і `strategy`
- `fills[]` — список fill-подій (orderId/ts/qty/price/role/fee)
- `trades[]` — реконструйовані **закриті** позиції (round-trip) з:
  - `entry.open_mode`
  - `exit.open_mode`
  - `close_reason`: `SL` / `TP` / `FLIP` / `EXIT` / `UNKNOWN`
- `open_trades[]` + `positions_end[]` — якщо backtest закінчився з відкритими позиціями
- `artifacts.order_log_jsonl` — run-scoped order log (див. нижче)

### Open mode (як читати)

`orders[].open_mode`, `trades[].entry.open_mode`, `trades[].exit.open_mode` — це короткий рядок:

- приклади:
  - `LIMIT|TIF=GTX|POST_ONLY|MAKER`
  - `MARKET|TAKER`
  - `STOP_MARKET|TAKER`
  - `TAKE_PROFIT_MARKET|TAKER`

### Close reason (як визначається)

`trades[].close_reason` класифікується **без змін ядра**, тільки з даних `MockBroker`:

- `SL` якщо exit order type == `STOP_MARKET` або `client_order_id` починається з `SL-`
- `TP` якщо exit order type == `TAKE_PROFIT_MARKET` або `client_order_id` починається з `TP-`
- `FLIP` якщо fill перевернув позицію (sign змінився, не закрившись в 0)
- `EXIT` якщо reduceOnly/closePosition (але не TP/SL)
- `UNKNOWN` fallback

## Backtest-only artifact: separate order log per run

Щоб мати можливість **джоїнити** `order_id -> rid` (а потім `rid -> strategy`), в backtest режимі `OrderLoggerV1`
перенаправляється в окремий файл:

`logs/backtests/order_log_{run_id}.jsonl`

Шлях зберігається в `report.artifacts.order_log_jsonl`.

## How to run quickly (dev)

Є dev-прапор для швидкої валідації:

`BACKTEST_MAX_TICKS=400 PYTHONPATH=. python3 -m apps.reference.main`

Це не змінює “ядро”, тільки обмежує кількість тиків, які проганяє `BacktestEngine.run(max_ticks=...)`.

## Next plan (without touching core domains)

Це список покращень, які логічно додати наступними кроками (тільки backtest/репортинг/телеметрія):

1) **Per-symbol/per-strategy analytics**
   - PnL, win_rate, DD, trades count по `symbol` і `strategy`
   - “top losers/winners” trades

2) **Equity curve + drawdown curve**
   - `equity_history[]` (з MockBroker) у звіт, або стиснутий (downsample)

3) **Cancel/Reject visibility**
   - summary по `ORDER_CANCELLED.reason`
   - summary по `ORDER_REJECTED.nrr_code` / adapter errors

4) **Bracket placement observability**
   - counts: created STOP/TP orders, filled/cancelled
   - per trade: attach bracket order ids if possible (best-effort by time proximity)

5) **Data coverage diagnostics**
   - rows processed, symbols with missing parquet, gaps, warmup readiness ratios per tf

6) **Schema stabilization**
   - add `schemas/backtest_report_v2.json`
   - include `schema_ref` and contract tests for report builder

