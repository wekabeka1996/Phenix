# Active Positions Snapshot (2026-03-09T03:04:58.485340Z)

## Summary Counts
- Active positions: 1
- Pending orders: 21
- Anomalies: 24

## Active Positions Table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | current_regime | unrealized_pnl | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|---|---|
| DOGEUSDT:rid-3abda79d7725aff1 | DOGEUSDT | mean_reversion | buy | open_position | 2026-03-08T22:05:04.544000Z | 0.08801 | unknown | 249.08277102 | 17993 |  |

## Pending Orders Table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|
| SOLUSDT:aurora_SOLUSDT_1772916600018 | SOLUSDT | aurora | buy | pending | 2026-03-07T20:50:01.225000Z | 82.91 | 108897 |  |
| SOLUSDT:aurora_SOLUSDT_1772922601536 | SOLUSDT | aurora | sell | pending | 2026-03-07T22:30:02.307000Z | 83.01 | 102896 |  |
| BTCUSDT:aurora_BTCUSDT_1772923801727 | BTCUSDT | aurora | buy | pending | 2026-03-07T22:50:02.478000Z | 67228.7 | 101696 |  |
| SOLUSDT:aurora_SOLUSDT_1772935803130 | SOLUSDT | aurora | sell | pending | 2026-03-08T02:10:04.728000Z | 82.84 | 89693 |  |
| DOGEUSDT:rid-9657bd20a43ca82c | DOGEUSDT | unknown | buy | pending | 2026-03-08T02:50:04.448000Z | 0.0 | 87294 |  |
| BTCUSDT:aurora_BTCUSDT_1772940003717 | BTCUSDT | aurora | buy | pending | 2026-03-08T03:20:04.462000Z | 66972.2 | 85494 |  |
| BTCUSDT:aurora_BTCUSDT_1772948404463 | BTCUSDT | aurora | buy | pending | 2026-03-08T05:40:05.263000Z | 67133.1 | 77093 |  |
| SOLUSDT:aurora_SOLUSDT_1772951404614 | SOLUSDT | aurora | sell | pending | 2026-03-08T06:30:05.499000Z | 82.35 | 74092 |  |
| ETHUSDT:aurora_ETHUSDT_1772970302246 | ETHUSDT | aurora | sell | pending | 2026-03-08T11:45:03.325000Z | 1948.5 | 55195 |  |
| BTCUSDT:aurora_BTCUSDT_1772970302472 | BTCUSDT | aurora | sell | pending | 2026-03-08T11:45:03.388000Z | 67478.0 | 55195 |  |
| ETHUSDT:aurora_ETHUSDT_1772972102224 | ETHUSDT | aurora | sell | pending | 2026-03-08T12:15:02.960000Z | 1935.59 | 53395 |  |
| SOLUSDT:aurora_SOLUSDT_1772973302070 | SOLUSDT | aurora | sell | pending | 2026-03-08T12:35:02.865000Z | 82.48 | 52195 |  |
| XRPUSDT:mdamr-82d2a8c71e1ca08a | XRPUSDT | unknown | buy | pending | 2026-03-08T13:30:04.119000Z | 1.3475 | 48894 |  |
| BNBUSDT:mdamr-3fcf6abde2cf1d04 | BNBUSDT | unknown | buy | pending | 2026-03-08T13:30:04.198000Z | 615.47 | 48894 |  |
| BTCUSDT:aurora_BTCUSDT_1772986203168 | BTCUSDT | aurora | sell | pending | 2026-03-08T16:10:03.993000Z | 67164.4 | 39294 |  |
| SOLUSDT:aurora_SOLUSDT_1772993403777 | SOLUSDT | aurora | sell | pending | 2026-03-08T18:10:05.387000Z | 81.47 | 32093 |  |
| BTCUSDT:aurora_BTCUSDT_1772995504484 | BTCUSDT | aurora | sell | pending | 2026-03-08T18:45:06.191000Z | 66793.1 | 29992 |  |
| DOGEUSDT:rid-c51a492affa9688c | DOGEUSDT | unknown | sell | pending | 2026-03-08T19:20:05.269000Z | 0.0 | 27893 |  |
| ETHUSDT:aurora_ETHUSDT_1772998804767 | ETHUSDT | aurora | sell | pending | 2026-03-08T19:40:05.528000Z | 1964.19 | 26692 |  |
| BTCUSDT:aurora_BTCUSDT_1773002702976 | BTCUSDT | aurora | sell | pending | 2026-03-08T20:45:03.785000Z | 67327.8 | 22794 |  |
| BTCUSDT:aurora_BTCUSDT_1773006604012 | BTCUSDT | aurora | sell | pending | 2026-03-08T21:50:04.807000Z | 66982.1 | 18893 |  |

## Anomaly Table
| lifecycle_id | symbol | type | severity | evidence |
|---|---|---|---|---|
| DOGEUSDT:multi | DOGEUSDT | opposite-side overlap | high | Both buy and sell lifecycles present simultaneously. |
| SOLUSDT:multi | SOLUSDT | opposite-side overlap | high | Both buy and sell lifecycles present simultaneously. |
| BTCUSDT:multi | BTCUSDT | opposite-side overlap | high | Both buy and sell lifecycles present simultaneously. |
| SOLUSDT:aurora_SOLUSDT_1772916600018 | SOLUSDT | timeout risk | medium | Pending order age 108897s exceeds 900s. |
| SOLUSDT:aurora_SOLUSDT_1772922601536 | SOLUSDT | timeout risk | medium | Pending order age 102896s exceeds 900s. |
| BTCUSDT:aurora_BTCUSDT_1772923801727 | BTCUSDT | timeout risk | medium | Pending order age 101696s exceeds 900s. |
| SOLUSDT:aurora_SOLUSDT_1772935803130 | SOLUSDT | timeout risk | medium | Pending order age 89693s exceeds 900s. |
| DOGEUSDT:rid-9657bd20a43ca82c | DOGEUSDT | timeout risk | medium | Pending order age 87294s exceeds 900s. |
| BTCUSDT:aurora_BTCUSDT_1772940003717 | BTCUSDT | timeout risk | medium | Pending order age 85494s exceeds 900s. |
| BTCUSDT:aurora_BTCUSDT_1772948404463 | BTCUSDT | timeout risk | medium | Pending order age 77093s exceeds 900s. |
| SOLUSDT:aurora_SOLUSDT_1772951404614 | SOLUSDT | timeout risk | medium | Pending order age 74092s exceeds 900s. |
| ETHUSDT:aurora_ETHUSDT_1772970302246 | ETHUSDT | timeout risk | medium | Pending order age 55195s exceeds 900s. |
| BTCUSDT:aurora_BTCUSDT_1772970302472 | BTCUSDT | timeout risk | medium | Pending order age 55195s exceeds 900s. |
| ETHUSDT:aurora_ETHUSDT_1772972102224 | ETHUSDT | timeout risk | medium | Pending order age 53395s exceeds 900s. |
| SOLUSDT:aurora_SOLUSDT_1772973302070 | SOLUSDT | timeout risk | medium | Pending order age 52195s exceeds 900s. |
| XRPUSDT:mdamr-82d2a8c71e1ca08a | XRPUSDT | timeout risk | medium | Pending order age 48894s exceeds 900s. |
| BNBUSDT:mdamr-3fcf6abde2cf1d04 | BNBUSDT | timeout risk | medium | Pending order age 48894s exceeds 900s. |
| BTCUSDT:aurora_BTCUSDT_1772986203168 | BTCUSDT | timeout risk | medium | Pending order age 39294s exceeds 900s. |
| SOLUSDT:aurora_SOLUSDT_1772993403777 | SOLUSDT | timeout risk | medium | Pending order age 32093s exceeds 900s. |
| BTCUSDT:aurora_BTCUSDT_1772995504484 | BTCUSDT | timeout risk | medium | Pending order age 29992s exceeds 900s. |
| DOGEUSDT:rid-c51a492affa9688c | DOGEUSDT | timeout risk | medium | Pending order age 27893s exceeds 900s. |
| ETHUSDT:aurora_ETHUSDT_1772998804767 | ETHUSDT | timeout risk | medium | Pending order age 26692s exceeds 900s. |
| BTCUSDT:aurora_BTCUSDT_1773002702976 | BTCUSDT | timeout risk | medium | Pending order age 22794s exceeds 900s. |
| BTCUSDT:aurora_BTCUSDT_1773006604012 | BTCUSDT | timeout risk | medium | Pending order age 18893s exceeds 900s. |

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
- DOGEUSDT lifecycle has no explicit ORDER_FILLED verb; open state is inferred from persistent ACCOUNT_UPDATE_RECEIVED position continuity after ORDER_PLACED.
