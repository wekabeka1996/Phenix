# Active Positions Snapshot (2026-03-08T23:05:04.778158Z)

## Summary Counts

- Active positions: 2
- Pending orders: 1
- Anomalies: 2

## Active Positions

| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | current_regime | unrealized_pnl | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|---|---|
| ETHUSDT:aurora_ETHUSDT_1773008403767 | ETHUSDT | aurora | sell | open_position | 2026-03-08T22:20:03.772000Z | 1926.11 | HIGH_VOLATILITY | -123.5458 | 2697 | forbidden_regime_exposure,symbol_busy_conflict |
| DOGEUSDT:rid-3abda79d7725aff1 | DOGEUSDT | mean_reversion | buy | open_position | 2026-03-08T22:05:03.830000Z | 0.08801 | unknown | 184.21996952 | 3597 |  |

## Pending Orders

| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|
| SOLUSDT:aurora_SOLUSDT_1773009904226 | SOLUSDT | aurora | buy | pending | 2026-03-08T22:45:04.235000Z | 81.60872142857143 | 1197 |  |

## Anomalies

| lifecycle_id | symbol | type | severity | evidence |
|---|---|---|---|---|
| ETHUSDT:aurora_ETHUSDT_1773008403767 | ETHUSDT | forbidden regime exposure | medium | ETHUSDT active lifecycle flagged: forbidden_regime_exposure. |
| ETHUSDT:aurora_ETHUSDT_1773008403767 | ETHUSDT | symbol busy conflict | medium | ETHUSDT active lifecycle flagged: symbol_busy_conflict. |

## Exact Evidence Files Used

- `ops/wal/2026-03-09.jsonl`
- `logs/order_log_v1.jsonl`
- `logs/*.jsonl`
- `reports/trade_lifecycle_failure_vectors_20260308_rca.md`
- `reports/testnet_last_50_trades.csv`
- `config/aurora/strategies/aurora.yaml`
- `config/aurora/strategies/mean_reversion.yaml`
- `config/aurora/trading.yaml`
- `config/aurora/regime.yaml`
- `reports/auto/trade_lifecycle_ledger.jsonl`
- `reports/auto/active_positions_snapshot_latest.json`

## Unresolved Ambiguities

- DOGEUSDT fill transition has no explicit ORDER_FILLED event in WAL; open state inferred from market ORDER_PLACED + persistent ACCOUNT_UPDATE_RECEIVED position continuity.
- Pending status is inferred from absence of ORDER_CANCELLED/ORDER_TIMEOUT/PENDING_BRACKETS_CLEARED(reason=filled) for the same order_id in current-day WAL.
