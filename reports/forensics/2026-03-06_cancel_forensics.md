# Cancel Forensics Report (2026-03-06)

## Scope

- Requested window: last `72h` ending `2026-03-05T21:55:03.456000+00:00`.
- Available pending-entry lifecycle window: `2026-03-05T04:25:04.729000+00:00` -> `2026-03-05T21:55:03.456000+00:00` (17.50h).
- Time normalization: JSONL timestamps are UTC epoch-ms; text logs are parsed as Europe/Kiev and converted to UTC.
- Limitation: `order_log_v1.jsonl` retention is shorter than the requested window, so the audit covers the full available lifecycle window instead of a full 24-72h sample.

## Log Sources

- `.env` `TRADING_MODE`: `testnet`
- `config/aurora/trading.yaml` `trading.mode`: `hybrid_live_data_testnet_exec`
- Effective runtime mode from execution logs: `hybrid_live_data_testnet_exec`

| Path | Format | Events | UTC start | UTC end |
| --- | --- | --- | --- | --- |
| C:/Users/user/Music/Phenix/logs/domain_execution_position.log | text | 5879 | 2026-03-05T18:36:31.321000+00:00 | 2026-03-05T22:14:08.501000+00:00 |
| C:/Users/user/Music/Phenix/logs/domain_execution_position.log.1 | text | 26523 | 2026-03-05T00:35:46.330000+00:00 | 2026-03-05T18:36:25.967000+00:00 |
| C:/Users/user/Music/Phenix/logs/domain_feature_engineering.log | text | 13678 | 2026-03-05T19:21:19.122000+00:00 | 2026-03-05T22:14:04.926000+00:00 |
| C:/Users/user/Music/Phenix/logs/domain_feature_engineering.log.1 | text | 15314 | 2026-03-05T16:11:51.478000+00:00 | 2026-03-05T19:21:19.089000+00:00 |
| C:/Users/user/Music/Phenix/logs/domain_feature_engineering.log.2 | text | 15493 | 2026-03-05T13:04:16.200000+00:00 | 2026-03-05T16:11:46.517000+00:00 |
| C:/Users/user/Music/Phenix/logs/domain_feature_engineering.log.3 | text | 15864 | 2026-03-05T09:57:33.857000+00:00 | 2026-03-05T13:04:16.171000+00:00 |
| C:/Users/user/Music/Phenix/logs/domain_feature_engineering.log.4 | text | 14888 | 2026-03-05T06:49:38.140000+00:00 | 2026-03-05T09:57:33.848000+00:00 |
| C:/Users/user/Music/Phenix/logs/domain_feature_engineering.log.5 | text | 15329 | 2026-03-05T03:42:33.617000+00:00 | 2026-03-05T06:49:38.130000+00:00 |
| C:/Users/user/Music/Phenix/logs/domain_feature_engineering.log.6 | text | 15337 | 2026-03-05T00:35:46.322000+00:00 | 2026-03-05T03:42:33.610000+00:00 |
| C:/Users/user/Music/Phenix/logs/domain_regime_detector.log | text | 1577 | 2026-03-05T00:35:51.443000+00:00 | 2026-03-05T22:10:00.079000+00:00 |
| C:/Users/user/Music/Phenix/logs/mean_reversion/bars_180s.jsonl | jsonl | 1660 | 2026-03-03T01:29:59.999000+00:00 | 2026-03-05T22:11:59.999000+00:00 |
| C:/Users/user/Music/Phenix/logs/order_guardian.log | text | 37062 | 2026-03-05T00:35:46.808000+00:00 | 2026-03-05T22:14:05.828000+00:00 |
| C:/Users/user/Music/Phenix/logs/order_log_v1.jsonl | jsonl | 477 | 2026-03-05T01:15:32.804000+00:00 | 2026-03-05T22:09:59.972000+00:00 |

## Matching Policy

- Primary lifecycle key: `order_id` from `logs/order_log_v1.jsonl` `ORDER_PLACED`.
- Fallback key: `client_order_id` only when timeout lines carry it but `order_id` is missing.
- Text logs are written in `Europe/Kiev` and normalized to UTC before matching against JSONL epoch timestamps.
- Pending-entry scope = `client_order_id` starts with `ENTRY-` and `adapter_response.type == LIMIT`; market entries and bracket cancels are excluded.
- Feature snapshots carry `price`, not `mid_price`; the report uses `price` as the runtime price proxy.
- ATR at cancel and post-cancel horizons use `FEATURES_CALCULATED` when available; bar-based fallback comes from `logs/mean_reversion/bars_180s.jsonl`.
- Observed limitation: `bars_180s.jsonl` contains only `DOGEUSDT/XRPUSDT` in this runtime snapshot, so `BTCUSDT/ETHUSDT/SOLUSDT` drift samples come from `FEATURES_CALCULATED`.

## Funnel

| Metric | Value |
| --- | --- |
| ORDER_PLACED | 52 |
| FILLED | 37 |
| CANCELED | 14 |
| OPEN_AT_WINDOW_END | 1 |
| fill_rate_pct | 71.15 |
| cancel_rate_pct | 26.92 |
| median_time_to_fill_sec | 123.6 |
| median_time_to_cancel_sec | 300.1 |

## Cancel Reasons Breakdown

| reason | count | share % | median age s | symbols top-10 | strategies top-10 | regime change +/-2 bars |
| --- | --- | --- | --- | --- | --- | --- |
| CANCEL_SUPERSEDED | 11 | 78.57 | 300.0 | ETHUSDT:10; SOLUSDT:1 | aurora:11 | 0 (0.00%) |
| CANCEL_TTL_EXPIRED | 3 | 21.43 | 1201.5 | BTCUSDT:2; ETHUSDT:1 | aurora:3 | 0 (0.00%) |

## Per-Symbol Scoreboard

| symbol | placed | filled | canceled | open | top cancel reasons | median cancel s | median fill s | cancel heaviness |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTCUSDT | 8 | 6 | 2 | 0 | CANCEL_TTL_EXPIRED:2 | 1201.73 | 94.0 | 0.33 |
| ETHUSDT | 36 | 24 | 11 | 1 | CANCEL_SUPERSEDED:10; CANCEL_TTL_EXPIRED:1 | 300.03 | 109.03 | 0.46 |
| SOLUSDT | 8 | 7 | 1 | 0 | CANCEL_SUPERSEDED:1 | 299.9 | 154.31 | 0.14 |

## Killer Checks

### Advanced stale cancel

- `CANCEL_STALE_REGIME_ADVANCED` count: `0`.
- No runtime examples in the available window, so effectiveness/prematurity cannot be validated from observed cancels.

### Watchdog / TTL / orphan / exchange reject mechanisms

- `trading.execution.watchdog.ack_ttl_ms`: `8000`
- `trading.execution.watchdog.fill_ttl_ms`: `300000`
- `domains.execution_position.pending_entry_ttl.ttl_by_tf_sec`: `{180: 600, 300: 1200, 900: 1800}`
- `orphan_monitor.periodic_interval_sec`: `300`; `min_order_age_sec`: `0`
- Timeout cancel count (`CANCEL_TTL_EXPIRED`): `3`; median age `1201.5` s; dominant age cluster `1200s:3`.
- Orphan cleanup runs: `379`; total brackets canceled `0`; non-zero cleanup runs `0`.
- Maker-only rejects (`MAKER_ONLY_REJECT`): `17`; by symbol `SOLUSDT:8; ETHUSDT:5; BTCUSDT:4`; by side `SELL:11; BUY:6`; error codes `-5022:17`.
- Inference: timeout ages line up with configured per-TF TTL buckets, so the actual killer is the pending-entry TTL override path, not the global 300s watchdog default.
- Orphan monitor is noisy in logs but did not cancel anything in this window, so it is not the #1 killer for pending entries here.
- Maker rejects are pre-placement failures and should be tracked separately from the pending-entry cancel funnel.

## Premature Cancels By Reason

| reason | horizon | samples | win % | avg potential bps | avg potential ATR |
| --- | --- | --- | --- | --- | --- |
| CANCEL_SUPERSEDED | T+5m | 11 | 81.82 | 14.23 | 0.5219 |
| CANCEL_SUPERSEDED | T+10m | 11 | 63.64 | 14.05 | 0.4664 |
| CANCEL_SUPERSEDED | T+15m | 11 | 63.64 | 22.73 | 0.7803 |
| CANCEL_SUPERSEDED | T+20m | 11 | 72.73 | 25.76 | 0.7993 |
| CANCEL_SUPERSEDED | T+30m | 10 | 70.00 | 19.64 | 0.5428 |
| CANCEL_TTL_EXPIRED | T+5m | 3 | 100.00 | 56.05 | 2.0026 |
| CANCEL_TTL_EXPIRED | T+10m | 3 | 100.00 | 57.36 | 1.7994 |
| CANCEL_TTL_EXPIRED | T+15m | 3 | 100.00 | 58.93 | 2.6678 |
| CANCEL_TTL_EXPIRED | T+20m | 2 | 100.00 | 70.90 | 2.4882 |
| CANCEL_TTL_EXPIRED | T+30m | 2 | 100.00 | 51.80 | 2.4213 |

## Root-Cause Ranking

| reason | count | share % | median age s | premature win @15m % | avg potential @15m bps |
| --- | --- | --- | --- | --- | --- |
| CANCEL_SUPERSEDED | 11 | 78.57 | 300.0 | 63.64 | 22.73 |
| CANCEL_TTL_EXPIRED | 3 | 21.43 | 1201.5 | 100.00 | 58.93 |
| MAKER_ONLY_REJECT | 17 |  |  |  |  |

## Recommendations

- Priority 1: timeouts are real cancels. Tune `domains.execution_position.pending_entry_ttl.ttl_by_tf_sec` before touching the global watchdog if the age cluster matches per-order TTL overrides.
- Inference: timeout cancels cluster around `1200s`; this is consistent with `ttl_by_tf_sec` rather than `trading.execution.watchdog.fill_ttl_ms=300000`.
- Priority 2: `CANCEL_SUPERSEDED` is churn-driven. Add a supersede guard that skips cancel/repost when the new limit is within a small bps/ATR band of the resting order, then verify with the same drift report.
- Priority 3: maker rejects are frequent but sit outside the cancel funnel. Reprice GTX entries one tick deeper or add a bounded retry-on-maker-reject path, then track `MAKER_ONLY_REJECT` count separately from cancels.
- No observed `CANCEL_STALE_REGIME_ADVANCED` in the available window. Keep current thresholds unchanged until logs contain real examples or add explicit gate telemetry for age/drift/regime on every advanced-cancel decision.

## Config Snapshot

- `advanced_stale_cancel.min_age_before_cancel_sec`: `300`
- `advanced_stale_cancel.drift_away.atr_mult`: `0.5`
- `advanced_stale_cancel.may_cancel_regimes`: `{'BUY': ['TREND_DOWN'], 'SELL': ['TREND_UP']}`
- `advanced_stale_cancel.never_cancel_regimes`: `['UNCERTAIN', 'MEAN_REVERSION', 'LOW_VOLATILITY']`

## Artifacts

- `C:/Users/user/Music/Phenix/reports/forensics/2026-03-06_cancel_forensics.md`
- `C:/Users/user/Music/Phenix/reports/forensics/2026-03-06_cancel_reasons.csv`
- `C:/Users/user/Music/Phenix/reports/forensics/2026-03-06_symbol_scoreboard.csv`
- `C:/Users/user/Music/Phenix/reports/forensics/2026-03-06_post_cancel_drift.csv`
