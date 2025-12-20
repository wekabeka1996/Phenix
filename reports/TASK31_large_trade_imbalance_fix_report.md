# TASK31-I — Fix Large Trade Imbalance (Volume-weighted, no lost quantity, deterministic)

## Summary (Before/After)

**Before**
- `WebSocketAggregator` зберігав у `trades_window` лише `(time, is_buyer_maker, trade_id)` і рахував `buy_volume/sell_volume` як **count**, тому quantity (`q`) фактично губився для downstream.
- `large_trade_imbalance` у `FeatureCalculationEngine.compute_large_trade_imbalance()` був **count/avg-size based** і в реальному runtime часто деградував у “тихий нейтрал” (бо `buy_count/sell_count` не приходили або даних було недостатньо).
- У WS path були wallclock fallback-и (`time.time()` / `datetime.now()`) для timestamp.

**After**
- `WebSocketAggregator.on_trade()` зберігає **exchange ts_ms + qty + side (+ optional price/notional)** у `trades_window` і веде O(1) rolling sums:
  - `buy_volume/sell_volume` = **sum(qty)** (або notional, якщо потрібно)
  - `buy_count/sell_count` = **trade counts**
- `large_trade_imbalance` тепер **volume-weighted**:
  - `imb = (buy - sell) / (buy + sell + eps)` ∈ [-1, 1]
  - `phi = (imb + 1) / 2` ∈ [0, 1]
- Детермінізм/якість даних:
  - out-of-order trade (by `ts_ms`) → **drop** + `trades_dropped_out_of_order++`
  - wallclock fallback прибрано для trade/book timestamps у WS path (missing ts → skip/drop)
- Fail-closed:
  - якщо немає достатньо trades або немає quantity/count metadata → `large_trade_imbalance_ready=false` + explicit reason (без “тихих нейтралів”)

---

## Changed / Added Files

**Config**
- `apps/reference/config_models.py` — додано `LargeTradeImbalanceConfig(window_ms,min_trades,eps,use_notional)`.
- `config/aurora/domains.yaml` — додано `feature_engineering.large_trade_imbalance.*`.

**Market data (qty + determinism)**
- `apps/reference/domains/market_data/websocket_aggregator.py` — `trades_window` тепер зберігає `TradeTick(ts_ms, qty, side, price, trade_id)`, а також rolling sums/counts + `trades_dropped_out_of_order`.
- `apps/reference/domains/market_data/market_data_connector.py` — прибрано wallclock fallback для `E/T` (missing → skip); tick payload тепер включає `buy_count/sell_count` (+ optional notional + dropped counter).
- `apps/reference/domains/market_data/worker.py` — прибрано wallclock fallback для `E/T` (missing → skip).
- `apps/reference/domains/market_data/proxy.py` — proxy зберігає trade metadata fields у `EVT:MARKET_TICK_RECEIVED`.

**Feature engineering (LTI V2 + readiness)**
- `apps/reference/domains/feature_engineering/large_trade_imbalance.py` — новий calculator + `LargeTradeImbalanceResult` (ready/reason/metrics).
- `apps/reference/domains/feature_engineering/calculation_engine.py` — `compute_large_trade_imbalance(..., state=HotState)` тепер volume-weighted + set readiness fields.
- `apps/reference/domains/feature_engineering/types.py` — додано `HotState.large_trade_imbalance_*` поля + typed config accessors.
- `apps/reference/domains/feature_engineering/feature_engineering.py` — прокинуто `state` у compute; у `warmup` payload додано:
  - `large_trade_imbalance_ready`
  - `large_trade_imbalance_not_ready_reason`
  - `large_trade_imbalance_trades_used`
  - `large_trade_imbalance_dropped_out_of_order`

**Tests**
- `tests/domains/feature_engineering/test_task31_large_trade_imbalance_math.py` — unit math + out-of-order counter.
- `tests/domains/market_data/test_task31_ws_aggregator_trade_qty_preserved.py` — інтеграція: qty зберігається + imbalance реагує на volume, не на count.
- `tests/e2e/test_s7_large_trade_imbalance_block_trade.py` — regression: “1 block trade ≠ 100 dust”.

---

## Side Mapping (Binance aggTrade, USDT-M)

Binance `aggTrade.m` = `isBuyerMaker`:
- `m == True` → buyer is maker → aggressor **SELL**
- `m == False` → aggressor **BUY**

В `WebSocketAggregator` зберігається aggressor side: `"buy"` / `"sell"`.

---

## Test Outputs (required)

Command:
`pytest -q tests/domains/feature_engineering/test_task31_large_trade_imbalance_math.py tests/domains/market_data/test_task31_ws_aggregator_trade_qty_preserved.py`

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.1, pluggy-1.6.0
rootdir: /home/wekabeka/Музыка/Phenix
configfile: pytest.ini
collected 7 items

tests/domains/feature_engineering/test_task31_large_trade_imbalance_math.py . [ 14%]
....                                                                     [ 71%]
tests/domains/market_data/test_task31_ws_aggregator_trade_qty_preserved.py . [ 85%]
.                                                                        [100%]

============================== 7 passed in 0.06s ===============================
```

Additional sanity (impacted areas):
`pytest -q tests/test_market_data_worker.py tests/test_market_data_proxy.py tests/runtime/test_task24_feature_engineering_correctness.py tests/e2e/test_s7_large_trade_imbalance_block_trade.py`

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.1, pluggy-1.6.0
rootdir: /home/wekabeka/Музыка/Phenix
configfile: pytest.ini
collected 32 items

tests/test_market_data_worker.py ..........                              [ 31%]
tests/test_market_data_proxy.py ...........                              [ 65%]
tests/runtime/test_task24_feature_engineering_correctness.py ..........  [ 96%]
tests/e2e/test_s7_large_trade_imbalance_block_trade.py .                 [100%]

============================== 32 passed in 0.15s ==============================
```

