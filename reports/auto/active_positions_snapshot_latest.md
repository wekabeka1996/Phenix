# Active Positions Snapshot (2026-03-09T07:10:37.023843Z)

## Summary Counts
- Active positions: 1
- Pending orders: 0
- Anomalies: 0

## Active Positions Table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | current_regime | unrealized_pnl | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DOGEUSDT:rid-54096416d6fc1df8 | DOGEUSDT | mean_reversion | sell | open_position | 2026-03-09T05:50:02.333000Z | 0.09142 | FLAT_LOW | unknown | 142.53275295 | 4829 |  |

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
- reports/auto/active_positions_snapshot_latest.json

## Unresolved Ambiguities
- Market entries still lack a guaranteed explicit ORDER_FILLED verb in WAL; open-state inference uses ORDER_PLACED + ACCOUNT_UPDATE continuity and PENDING_BRACKETS_CLEARED(reason=filled).
- Current regime for active DOGEUSDT lifecycle is unknown in latest reject telemetry; entry regime is FLAT_LOW from intent context.
