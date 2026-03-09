# Active Positions Snapshot (2026-03-09T03:08:10.897271Z)

## Summary Counts
- Active positions: 1
- Pending orders: 0
- Anomalies: 0

## Active Positions Table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | current_regime | unrealized_pnl | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|---|---|
| DOGEUSDT:rid-3abda79d7725aff1 | DOGEUSDT | mean_reversion | buy | open_position | 2026-03-08T22:05:04.544000Z | 0.08801 | unknown | 236.05894 | 18186 |  |

## Pending Orders Table
| none |
|---|
| none |

## Anomaly Table
| none |
|---|
| none |

## Exact Evidence Files Used
- ops/wal/2026-03-09.jsonl
- logs/order_log_v1.jsonl
- logs/*.jsonl
- reports/trade_lifecycle_failure_vectors_20260308_rca.md
- reports/testnet_last_50_trades.csv
- config/aurora/strategies/aurora.yaml
- config/aurora/strategies/mean_reversion.yaml
- config/aurora/trading.yaml
- config/aurora/regime.yaml
- reports/auto/trade_lifecycle_ledger.jsonl
- reports/auto/active_positions_snapshot_20260308_230504.json

## Unresolved Ambiguities
- DOGEUSDT fill transition has no explicit ORDER_FILLED verb in WAL; active state is inferred from ACCOUNT_UPDATE_RECEIVED continuity after market ORDER_PLACED.
- No pending orders remain after applying current-day ORDER_TIMEOUT/ORDER_CANCELLED/PENDING_BRACKETS_CLEARED terminal signals to prior pending continuity.
