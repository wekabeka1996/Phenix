# Active Trade Snapshot (2026-03-08T11:06:48.245102Z)

## Summary counts
- Active positions: **0**
- Pending orders: **0**
- Anomalies: **1**

## Active positions table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | current_regime | unrealized_pnl | age_sec | anomaly_flags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| - | - | - | - | - | - | - | - | - | - | - | - |

## Pending orders table
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | age_sec | last_cancel_supersede_timeout | anomaly_flags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| - | - | - | - | - | - | - | - | - | - | - |

## Anomaly table
| lifecycle_id | symbol | type | severity | evidence |
| --- | --- | --- | --- | --- |
| SOLUSDT:aurora_SOLUSDT_1772964601222 | SOLUSDT | symbol-busy conflict | medium | NRR-SYMBOL-BUSY at 1772964601222 while latest account positions=[] at 1772968004646 |

## Exact evidence files used
- `ops/wal/2026-03-08.jsonl`
- `logs/order_log_v1.jsonl`
- `config/aurora/strategies/aurora.yaml`
- `config/aurora/trading.yaml`
- `config/aurora/regime.yaml`
- `reports/auto/trade_lifecycle_ledger.jsonl`
- `reports/auto/active_positions_snapshot_latest.json`

## Unresolved ambiguities
- No active/pending lifecycles at snapshot time; closure inferred from latest ACCOUNT_UPDATE_RECEIVED positions=[].
- Recent NRR-SYMBOL-BUSY rejects exist despite flat account updates; possible stale symbol-busy cache.
- Explicit fill events are sparse; entry/exit transitions rely on ACCOUNT_UPDATE_RECEIVED continuity.
