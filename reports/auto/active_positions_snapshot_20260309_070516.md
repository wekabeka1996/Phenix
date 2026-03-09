# Active Positions Snapshot (2026-03-09T07:05:16.231080Z)

## Summary Counts
- Active positions: 1
- Pending orders: 4
- Anomalies: 4

## Active Positions Table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | current_regime | unrealized_pnl | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DOGEUSDT:rid-54096416d6fc1df8 | DOGEUSDT | mean_reversion | sell | open_position | 2026-03-09T05:50:02.333000Z | 0.09142 | FLAT_LOW | unknown | 148.4550984 | 4509 |  |

## Pending Orders Table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | current_regime | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT:aurora_BTCUSDT_1773018900049 | BTCUSDT | aurora | buy | pending | 2026-03-09T01:15:00.826000Z |  | unknown | LOW_VOLATILITY | 21015 | timeout_risk |
| BTCUSDT:aurora_BTCUSDT_1773023099984 | BTCUSDT | aurora | buy | pending | 2026-03-09T02:25:00.792000Z |  | unknown | LOW_VOLATILITY | 16815 | timeout_risk |
| BTCUSDT:aurora_BTCUSDT_1773028200440 | BTCUSDT | aurora | buy | pending | 2026-03-09T03:50:02.209000Z |  | unknown | LOW_VOLATILITY | 11714 | timeout_risk |
| ETHUSDT:aurora_ETHUSDT_1773028500415 | ETHUSDT | aurora | sell | pending | 2026-03-09T03:55:01.196000Z |  | unknown | HIGH_VOLATILITY | 11415 | timeout_risk |

## Anomaly Table
| type | symbol | lifecycle_id | details | count | age_sec | regime |
|---|---|---|---|---|---|---|
| timeout_risk | BTCUSDT | BTCUSDT:aurora_BTCUSDT_1773018900049 |  |  | 21015 |  |
| timeout_risk | BTCUSDT | BTCUSDT:aurora_BTCUSDT_1773023099984 |  |  | 16815 |  |
| timeout_risk | BTCUSDT | BTCUSDT:aurora_BTCUSDT_1773028200440 |  |  | 11714 |  |
| timeout_risk | ETHUSDT | ETHUSDT:aurora_ETHUSDT_1773028500415 |  |  | 11415 |  |

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
- Market entries still lack a guaranteed explicit ORDER_FILLED verb in WAL; open-state inference uses ORDER_PLACED + persistent ACCOUNT_UPDATE_RECEIVED positions.
- Current regime for active DOGEUSDT lifecycle is inferred from latest reject telemetry per symbol and may lag bar-close regime transitions.
