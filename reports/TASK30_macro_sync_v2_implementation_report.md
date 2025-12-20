# TASK30-I — Macro Sync V2 Implementation Report

## Summary (Before/After)

**Before**
- Anchor updates могли приходити без exchange timestamp end-to-end: worker ставив `time.time()` для anchor `ts`, proxy не передавав timestamp у `EVT:ANCHOR_UPDATED`, а `FeatureEngineering.update_anchor_price()` робив wallclock fallback (`time.time()`).
- `macro_sync` рахувався по **індексах** (tail vectors) з **price-only** anchor deque (без ts), що не прибирає асинхронність (Epps).

**After**
- Anchor updates несуть **exchange-derived `ts_ms`** end-to-end (worker → proxy → FeatureEngineering); wallclock fallback прибрано/заборонено.
- `macro_sync` V2 обчислюється через **time-grid resampling** (bin_ms), **log-returns**, **alignment by bin intersection**, Pearson corr; деградація fail-closed через `macro_sync_ready=false` + explicit reason.

---

## Changed / Added Files

**Config**
- `apps/reference/config_models.py` — додано `MacroSyncMetricsConfig.bin_ms`, `max_gap_bins`, `eps` (typed bounds).
- `config/aurora/domains.yaml` — додано `feature_engineering.macro_sync.{bin_ms,max_gap_bins,eps}`.

**MarketData (anchor ts SSOT)**
- `apps/reference/domains/market_data/websocket_aggregator.py` — додано `last_price_ts_ms` (exchange ts) та передача `ts_ms` у anchor callback.
- `apps/reference/domains/market_data/worker.py` — anchor msg тепер містить `ts_ms` із exchange (`last_price_ts_ms`), без `time.time()`.
- `apps/reference/domains/market_data/proxy.py` — proxy більше не “дропає” ts: `EVT:ANCHOR_UPDATED` payload містить `ts_ms`.
- `apps/reference/domains/market_data/market_data_connector.py` — anchor emit тепер включає `ts_ms`.

**FeatureEngineering (Macro Sync V2)**
- `apps/reference/domains/feature_engineering/macro_sync_resampler.py` — новий time-grid resampler + correlation (V2).
- `apps/reference/domains/feature_engineering/types.py` — додано доступори `macro_sync_bin_ms/max_gap_bins/eps`.
- `apps/reference/domains/feature_engineering/feature_engineering.py` — інтеграція resampler; `update_anchor_price()` більше не має wallclock fallback (missing ts → `ConfigContractError`).
- `apps/reference/domains/feature_engineering/calculation_engine.py` — додано `compute_macro_sync_v2()` (sets `macro_sync_ready` + reason).

**Tests**
- `tests/domains/feature_engineering/test_task30_macro_sync_resampler_math.py` — unit тести математики/деградації V2.
- `tests/domains/market_data/test_task30_anchor_ts_propagation.py` — інтеграційний тест `ts_ms` propagation + rejection on missing ts.
- `tests/test_market_data_worker.py` — anchor msg key updated to `ts_ms`.
- `tests/test_market_data_proxy.py` — asserts `ts_ms` preserved.

---

## Contract / Fallback Removal (what changed)

- Worker anchor timestamp:
  - **Removed:** `ts=int(time.time()*1000)` для anchor updates.
  - **Now:** `ts_ms` береться з exchange-derived `last_price_ts_ms` (trade event ts).

- Proxy anchor timestamp:
  - **Removed:** dropping anchor ts when emitting `EVT:ANCHOR_UPDATED`.
  - **Now:** payload має `ts_ms` (int ms).

- FeatureEngineering anchor timestamp:
  - **Removed:** `time.time()` fallback у `update_anchor_price()`.
  - **Now:** missing/invalid `ts_ms` → `ConfigContractError` (fail-closed), anchor series не оновлюється.

---

## Test Outputs (required)

Command:
`pytest -q tests/domains/feature_engineering/test_task30_macro_sync_resampler_math.py tests/domains/market_data/test_task30_anchor_ts_propagation.py`

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.1, pluggy-1.6.0
rootdir: /home/wekabeka/Музыка/Phenix
configfile: pytest.ini
collected 7 items

tests/domains/feature_engineering/test_task30_macro_sync_resampler_math.py . [ 14%]
....                                                                     [ 71%]
tests/domains/market_data/test_task30_anchor_ts_propagation.py ..        [100%]

============================== 7 passed in 0.11s ===============================
```

Additional sanity (impacted areas):
- `pytest -q tests/test_market_data_worker.py tests/test_market_data_proxy.py tests/e2e/test_s2_macro_sync_async.py tests/runtime/test_task24_feature_engineering_correctness.py tests/runtime/test_task24_policy_gates.py tests/runtime/test_task25_market_data_proxy_no_config_to_dict.py` → 41 passed

---

## Example Debug Snippet (shape)

Expected compute result shape (V2 internal):

```text
MacroSyncResult(phi=0.83, ready=True, why=None, bins_used=60, drops_out_of_order=0, gaps=0)
```

Fail-closed example:

```text
MacroSyncResult(phi=0.5, ready=False, why="no_fresh_anchor_data", bins_used=12, drops_out_of_order=0, gaps=4)
```

