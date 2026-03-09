# Active Positions Snapshot (2026-03-08T07:04:17.1552659Z)

## Summary Counts

- Active positions: 0
- Pending orders: 0
- Anomalies: 0

## Active Positions Table


## Pending Orders Table


## Anomaly Table


## Exact Evidence Files Used

- ops/wal/2026-03-08.jsonl
- logs/order_log_v1.jsonl
- config/aurora/strategies/aurora.yaml
- config/aurora/trading.yaml
- config/aurora/regime.yaml
- reports/auto/trade_lifecycle_ledger.jsonl
- reports/auto/active_positions_snapshot_20260308_030655.json

## Unresolved Ambiguities

- Fill/open transitions are inferred from ACCOUNT_UPDATE_RECEIVED because explicit fill events are sparse in WAL.
- No explicit strategy-ownership tag exists for every lifecycle event; ownership checks remain best-effort.
- TP/SL are preserved as tpsl context hints when absolute bracket prices are not emitted.

