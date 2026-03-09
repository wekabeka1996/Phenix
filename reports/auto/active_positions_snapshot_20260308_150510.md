# Active Trade Snapshot (2026-03-08T15:05:10.230486Z)

## Summary counts
- Active positions: **3**
- Pending orders: **4**
- Anomalies: **2**

## Active positions table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | current_regime | unrealized_pnl | age_sec | anomaly_flags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETHUSDT:aurora_ETHUSDT_1772972102224 | ETHUSDT | aurora | sell | open_position | 2026-03-08T12:20:39.853000Z | 1935.59 | HIGH_VOLATILITY | MEAN_REVERSION | -37.66014 | 9866 | forbidden_regime_exposure |
| BNBUSDT:mdamr-3fcf6abde2cf1d04 | BNBUSDT | md_amr | buy | open_position | 2026-03-08T13:30:08.387000Z | 615.47 | MEAN_REVERSION | MEAN_REVERSION | 17.45121052 | 5698 | - |
| XRPUSDT:mdamr-82d2a8c71e1ca08a | XRPUSDT | md_amr | buy | open_position | 2026-03-08T13:31:06.866000Z | 1.3475 | MEAN_REVERSION | MEAN_REVERSION | -1.21758191 | 5639 | strategy_ownership_violation |

## Pending orders table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | age_sec | last_cancel_supersede_timeout | anomaly_flags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BNBUSDT:mdamr-3fcf6abde2cf1d04 | BNBUSDT | md_amr | sell | pending | 2026-03-08T13:30:08.424000Z | 608.12 | MEAN_REVERSION | 5698 | - | - |
| BNBUSDT:mdamr-3fcf6abde2cf1d04 | BNBUSDT | md_amr | sell | pending | 2026-03-08T13:30:08.424000Z | 619.08 | MEAN_REVERSION | 5698 | - | - |
| XRPUSDT:mdamr-82d2a8c71e1ca08a | XRPUSDT | md_amr | sell | pending | 2026-03-08T13:31:06.903000Z | 1.3314 | MEAN_REVERSION | 5639 | - | - |
| XRPUSDT:mdamr-82d2a8c71e1ca08a | XRPUSDT | md_amr | sell | pending | 2026-03-08T13:31:06.903000Z | 1.3554 | MEAN_REVERSION | 5639 | - | - |

## Anomaly table
| lifecycle_id | symbol | type | severity | evidence |
| --- | --- | --- | --- | --- |
| ETHUSDT:aurora_ETHUSDT_1772972102224 | ETHUSDT | forbidden regime exposure | medium | REGIME_NOT_ALLOWLISTED at 1772982302882 while position remains open in latest account update. |
| XRPUSDT:mdamr-82d2a8c71e1ca08a | XRPUSDT | strategy ownership violation | medium | mean_reversion.yaml sets assets.XRPUSDT.enabled=false while active md_amr position exists. |

## Exact evidence files used
- `ops/wal/2026-03-08.jsonl`
- `logs/order_log_v1.jsonl`
- `config/aurora/strategies/aurora.yaml`
- `config/aurora/strategies/mean_reversion.yaml`
- `config/aurora/trading.yaml`
- `config/aurora/regime.yaml`
- `reports/auto/trade_lifecycle_ledger.jsonl`
- `reports/auto/active_positions_snapshot_latest.json`

## Unresolved ambiguities
- No explicit ORDER_FILLED telemetry for open entries; fill time inferred from PENDING_BRACKETS_CLEARED(reason=filled).
- Aurora ETH protective bracket order IDs are not explicitly emitted in current-day WAL, so pending protective status is inferred only for mdamr brackets.
- Strategy ownership checks use live YAML and may diverge from runtime-effective config snapshots.
