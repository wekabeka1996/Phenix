# Active Positions Snapshot (2026-03-08T07:08:12.0882787Z)

## Summary Counts

- Active positions: 2
- Pending orders: 0
- Anomalies: 2

## Active Positions Table

| lifecycle_id | symbol | side | status | entry_ts | entry_price | current_regime | unrealized_pnl | age_sec | anomaly_flags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SOLUSDT:aurora_SOLUSDT_1772951404614 | SOLUSDT | sell | open_position | 2026-03-08T06:30:05.4990000+00:00 | 82.35 | MEAN_REVERSION | -45.74266455 | 2274 | symbol_busy_conflict |
| BTCUSDT:aurora_BTCUSDT_1772948404463 | BTCUSDT | buy | open_position | 2026-03-08T05:40:05.2630000+00:00 | 67133.1 | MEAN_REVERSION | 26.37678713 | 5274 | symbol_busy_conflict |

## Pending Orders Table

(none)

## Anomaly Table

| lifecycle_id | symbol | type | severity | evidence |
| --- | --- | --- | --- | --- |
| SOLUSDT:aurora_SOLUSDT_1772951404614 | SOLUSDT | symbol-busy conflict | medium | ops/wal/2026-03-08.jsonl rid=aurora_SOLUSDT_1772953499732 reason_code=NRR-SYMBOL-BUSY |
| BTCUSDT:aurora_BTCUSDT_1772948404463 | BTCUSDT | symbol-busy conflict | medium | ops/wal/2026-03-08.jsonl rid=aurora_BTCUSDT_1772953499986 reason_code=NRR-SYMBOL-BUSY |

## Exact Evidence Files Used

- ops/wal/2026-03-08.jsonl
- logs/order_log_v1.jsonl
- config/aurora/strategies/aurora.yaml
- config/aurora/trading.yaml
- config/aurora/regime.yaml
- reports/aurora_forensic_2026-03-06_2026-03-07_conflicts.csv
- reports/auto/trade_lifecycle_ledger.jsonl
- reports/auto/active_positions_snapshot_20260308_030655.json

## Unresolved Ambiguities

- Fill/open transitions are inferred from ACCOUNT_UPDATE_RECEIVED because explicit fill events are sparse in WAL.
- No explicit strategy-ownership tag exists on every lifecycle event; ownership checks remain best-effort.
- TP/SL absolute bracket prices are not consistently emitted; tpsl context strings are used when available.
