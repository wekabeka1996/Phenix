# Active Positions Snapshot (2026-03-09T07:08:54.086193Z)

## Summary Counts
- Active positions: 1
- Pending orders: 2
- Anomalies: 2

## Active Positions Table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | current_regime | unrealized_pnl | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DOGEUSDT:rid-54096416d6fc1df8 | DOGEUSDT | mean_reversion | sell | open_position | 2026-03-09T05:50:02.333000Z | 0.09142 | FLAT_LOW | unknown | 147.5208 | 4731 |  |

## Pending Orders Table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | current_regime | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT:aurora_BTCUSDT_1773027900740 | BTCUSDT | aurora | sell | pending | 2026-03-09T03:45:01.582000Z |  | unknown | LOW_VOLATILITY | 12232 | timeout_risk |
| SOLUSDT:aurora_SOLUSDT_1773009904226 | SOLUSDT | aurora | buy | pending | 2026-03-08T22:45:04.957000Z |  | unknown | HIGH_VOLATILITY | 30229 | timeout_risk |

## Anomaly Table
| type | symbol | lifecycle_id | details | count | age_sec | regime |
|---|---|---|---|---|---|---|
| timeout_risk | BTCUSDT | BTCUSDT:aurora_BTCUSDT_1773027900740 |  |  | 12232 |  |
| timeout_risk | SOLUSDT | SOLUSDT:aurora_SOLUSDT_1773009904226 |  |  | 30229 |  |

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
