# Active Positions Snapshot (2026-03-09T07:07:10.471742Z)

## Summary Counts
- Active positions: 1
- Pending orders: 22
- Anomalies: 0

## Active Positions Table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | current_regime | unrealized_pnl | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DOGEUSDT:rid-54096416d6fc1df8 | DOGEUSDT | mean_reversion | sell | open_position | 2026-03-09T05:50:02.333000Z | 0.09142 | FLAT_LOW | unknown | 147.5208 | 4625 |  |

## Pending Orders Table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | current_regime | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|---|---|
| BNBUSDT:mdamr-3fcf6abde2cf1d04 | BNBUSDT | md_amr | buy | pending | 2026-03-08T13:30:04.198000Z |  | unknown | LOW_VOLATILITY |  |  |
| BTCUSDT:aurora_BTCUSDT_1772923801727 | BTCUSDT | aurora | buy | pending | 2026-03-07T22:50:02.478000Z |  | unknown | LOW_VOLATILITY |  |  |
| BTCUSDT:aurora_BTCUSDT_1772940003717 | BTCUSDT | aurora | buy | pending | 2026-03-08T03:20:04.462000Z |  | unknown | LOW_VOLATILITY |  |  |
| BTCUSDT:aurora_BTCUSDT_1772948404463 | BTCUSDT | aurora | buy | pending | 2026-03-08T05:40:05.263000Z |  | unknown | LOW_VOLATILITY |  |  |
| BTCUSDT:aurora_BTCUSDT_1772970302472 | BTCUSDT | aurora | sell | pending | 2026-03-08T11:45:03.388000Z |  | unknown | LOW_VOLATILITY |  |  |
| BTCUSDT:aurora_BTCUSDT_1772986203168 | BTCUSDT | aurora | sell | pending | 2026-03-08T16:10:03.993000Z |  | unknown | LOW_VOLATILITY |  |  |
| BTCUSDT:aurora_BTCUSDT_1772995504484 | BTCUSDT | aurora | sell | pending | 2026-03-08T18:45:06.191000Z |  | unknown | LOW_VOLATILITY |  |  |
| BTCUSDT:aurora_BTCUSDT_1773002702976 | BTCUSDT | aurora | sell | pending | 2026-03-08T20:45:03.785000Z |  | unknown | LOW_VOLATILITY |  |  |
| BTCUSDT:aurora_BTCUSDT_1773006604012 | BTCUSDT | aurora | sell | pending | 2026-03-08T21:50:04.807000Z |  | unknown | LOW_VOLATILITY |  |  |
| DOGEUSDT:rid-3abda79d7725aff1 | DOGEUSDT | mean_reversion | buy | pending | 2026-03-08T22:05:04.544000Z |  | unknown | unknown |  |  |
| DOGEUSDT:rid-9657bd20a43ca82c | DOGEUSDT | mean_reversion | buy | pending | 2026-03-08T02:50:04.448000Z |  | unknown | unknown |  |  |
| DOGEUSDT:rid-c51a492affa9688c | DOGEUSDT | mean_reversion | sell | pending | 2026-03-08T19:20:05.269000Z |  | unknown | unknown |  |  |
| ETHUSDT:aurora_ETHUSDT_1772970302246 | ETHUSDT | aurora | sell | pending | 2026-03-08T11:45:03.325000Z |  | unknown | HIGH_VOLATILITY |  |  |
| ETHUSDT:aurora_ETHUSDT_1772972102224 | ETHUSDT | aurora | sell | pending | 2026-03-08T12:15:02.960000Z |  | unknown | HIGH_VOLATILITY |  |  |
| ETHUSDT:aurora_ETHUSDT_1772998804767 | ETHUSDT | aurora | sell | pending | 2026-03-08T19:40:05.528000Z |  | unknown | HIGH_VOLATILITY |  |  |
| SOLUSDT:aurora_SOLUSDT_1772916600018 | SOLUSDT | aurora | buy | pending | 2026-03-07T20:50:01.225000Z |  | unknown | HIGH_VOLATILITY |  |  |
| SOLUSDT:aurora_SOLUSDT_1772922601536 | SOLUSDT | aurora | sell | pending | 2026-03-07T22:30:02.307000Z |  | unknown | HIGH_VOLATILITY |  |  |
| SOLUSDT:aurora_SOLUSDT_1772935803130 | SOLUSDT | aurora | sell | pending | 2026-03-08T02:10:04.728000Z |  | unknown | HIGH_VOLATILITY |  |  |
| SOLUSDT:aurora_SOLUSDT_1772951404614 | SOLUSDT | aurora | sell | pending | 2026-03-08T06:30:05.499000Z |  | unknown | HIGH_VOLATILITY |  |  |
| SOLUSDT:aurora_SOLUSDT_1772973302070 | SOLUSDT | aurora | sell | pending | 2026-03-08T12:35:02.865000Z |  | unknown | HIGH_VOLATILITY |  |  |
| SOLUSDT:aurora_SOLUSDT_1772993403777 | SOLUSDT | aurora | sell | pending | 2026-03-08T18:10:05.387000Z |  | unknown | HIGH_VOLATILITY |  |  |
| XRPUSDT:mdamr-82d2a8c71e1ca08a | XRPUSDT | md_amr | buy | pending | 2026-03-08T13:30:04.119000Z |  | unknown | HIGH_VOLATILITY |  |  |

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
- Market entries still lack a guaranteed explicit ORDER_FILLED verb in WAL; open-state inference uses ORDER_PLACED + ACCOUNT_UPDATE_RECEIVED continuity and PENDING_BRACKETS_CLEARED(reason=filled).
- Current regime for active DOGEUSDT lifecycle is unknown in latest symbol-level reject telemetry; entry regime is FLAT_LOW from intent context.
