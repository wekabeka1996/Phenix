# RATE-FORENSIC-DIFF-001 — What changed (865bf5c..HEAD)

Date: 2026-01-09

Scope (as requested):
- `apps/reference/domains/account_balance/**`
- `apps/reference/adapters/binance_adapter.py`
- `apps/reference/main.py`
- `apps/reference/domains/market_data/**`
- `config/**`
- `apps/reference/config_loader.py`, `apps/reference/config_models.py`

Artifacts:
- Raw diff: `reports/RATE-FORENSIC-001_raw_diff.patch`
- Log: `reports/RATE-FORENSIC-001_log.txt`
- Extra diff (flip-related): `reports/RATE-FORENSIC-001_execpos_services_diff.patch`

## Hypothesis matrix

| Hypothesis | Evidence in diff | How to prove quickly |
|---|---|---|
| poll_interval decreased | **NOT CONFIRMED**: `config/aurora/system.yaml` still has `account_observer.poll_interval: 5` in 865bf5c and HEAD. | Print effective `config.account_observer.poll_interval` at startup; verify it’s >= 5. |
| poller duplicated | **POSSIBLE**: new startup guard creates a temporary `BinanceAdapter` in `apps/reference/main.py` (extra REST client instance). | Count `rest_requests_total{endpoint="/fapi/v1/time"}` right after startup; if it spikes (2+ adapters), confirm by logging adapter creation sites once. |
| retry storm | **LIKELY**: existing fast retry patterns + new cancel fallback scans can create bursts; once -1003 ban triggers, any polling amplifies. | Watch `rest_request_errors_total{code="-1003"}` plus `rest_requests_total` growth during ban window; ensure backoff waits until `banned until`. |
| extra REST endpoints introduced | **LIKELY**: adapter gained an open-orders scan fallback (`/fapi/v1/openOrders`) to resolve symbol in cancel/retry paths. Under flip/cancel churn this adds REST load. | Compare `rest_requests_total{endpoint="/fapi/v1/openOrders"}` before/after flip workload. |

## Root cause (most likely)

**Root cause = additional REST request amplification during flip/cancel churn**, caused by a new fallback path in the Binance adapter that **scans open orders via REST** when cancel/retry cannot rely on `symbol`.

In `apps/reference/adapters/binance_adapter.py`, a new helper `_find_symbol_by_order_id()` was added. It performs:
- `GET /fapi/v1/openOrders` scan when `symbol` is empty (or when -2011 unknown order triggers a “verify symbol and retry” flow).

Evidence pointers (HEAD):
- `apps/reference/adapters/binance_adapter.py`:
  - `_find_symbol_by_order_id` starts at ~line 233
  - `cancel_order` fallback scan starts at ~line 554

When flip-related logic increases cancel/repair activity (and/or when symbol is missing in some cancel calls), this fallback creates extra REST calls, which can push Binance Testnet over rate limits. Once the IP is banned (`-1003`), the existing account poller (`/fapi/v2/balance` + `/fapi/v2/positionRisk`) keeps hitting REST and “observes” the ban on those endpoints.

## Supporting causes (1–2)

### A) Startup burst via extra adapter instance

`apps/reference/main.py` added a Startup Guard that creates a temporary `BinanceAdapter` and runs exchange-filter validation on startup.
Even if it is “batch mode”, it still adds extra REST calls early in process lifetime (separate adapter instance → separate time-sync calls).

Evidence pointers (HEAD):
- `apps/reference/main.py` Startup Guard block starts at ~line 1433

### B) Background REST polling always on

Account polling still does REST balance+positions each cycle. Even with `poll_interval=5s`, this is a steady baseline load.
If any other component adds REST load (openOrders scans, watchdog polling, etc.), the total can cross testnet limits.

Evidence pointers (HEAD):
- `apps/reference/domains/account_balance/account_connector.py`:
  - poll interval read/clamp at ~line 52–57
  - `time.sleep(self.update_interval)` at ~line 127

## What changed between 865bf5c and HEAD (high-signal)

1) `apps/reference/main.py`
- AccountObserver is removed/disabled.
- Startup Guard is added and constructs a `BinanceAdapter` to validate exchange filters.

2) `apps/reference/adapters/binance_adapter.py`
- Added `_find_symbol_by_order_id()` which can call `GET /fapi/v1/openOrders`.
- Cancel path now scans open orders when `symbol` missing and also for -2011 retry.

3) `apps/reference/domains/execution_position/**` (extra diff for flip correlation)
- ExposureGuard flip changes increase the surface area where cancels/retries can occur.

## How to prove in 2 minutes (practical)

1) Run and watch metrics:
- `rest_requests_total{endpoint="/fapi/v1/openOrders"}`
- `rest_requests_total{endpoint="/fapi/v2/positionRisk"}`
- `rest_request_errors_total{code="-1003"}`

2) Trigger a flip-heavy scenario (or run the normal bot if it flips often) and compare:
- If `/fapi/v1/openOrders` grows fast, the cancel fallback scan is contributing.

3) Confirm no accidental zero-sleep polling:
- Run `pytest -q tests/runtime/test_rate_forensic_account_poller.py`.

## Mitigations / instrumentation (in working tree)

- Added Prometheus counters:
  - `rest_requests_total{adapter,method,endpoint}`
  - `rest_request_errors_total{adapter,method,endpoint,code}`
  - `account_poll_cycles_total`
  - `account_poll_errors_total{stage,code}`

- Added a deterministic runtime test:
  - `tests/runtime/test_rate_forensic_account_poller.py`

(If you want a hard block for dangerous fallback scans, next step is to rate-limit or disable openOrders scans under live/testnet strictness.)
