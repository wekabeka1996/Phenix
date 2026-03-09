# Active Positions Snapshot (2026-03-08T03:06:55.959000+00:00)

## Summary Counts
- Active positions: 1
- Pending orders: 0
- Anomalies: 1

## Active Positions
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | current_regime | unrealized_pnl | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SOLUSDT:aurora_SOLUSDT_1772935803130 | SOLUSDT | aurora | sell | open_position | 2026-03-08T02:15:42.059000+00:00 | 82.84 | HIGH_VOLATILITY | HIGH_VOLATILITY | 52.86493692 | 3073 | symbol_busy_conflict |

## Pending Orders
_None_

## Anomalies
| lifecycle_id | symbol | type | severity | evidence |
|---|---|---|---|---|
| SOLUSDT:aurora_SOLUSDT_1772935803130 | SOLUSDT | symbol-busy conflict | medium | WAL line 4956 NRR-SYMBOL-BUSY |

## Exact Evidence Files Used
- `ops/wal/2026-03-08.jsonl`
- `logs/order_log_v1.jsonl`
- `config/aurora/strategies/aurora.yaml`
- `config/aurora/trading.yaml`
- `config/aurora/regime.yaml`
- `reports/auto/trade_lifecycle_ledger.jsonl`

## Unresolved Ambiguities
- Some lifecycle_id values are absent in runtime events; stable fallback IDs are used.
- Entry fill is inferred from PENDING_BRACKETS_CLEARED(reason=filled) plus account updates.
- No explicit strategy-owner tag exists on all events; ownership checks are best-effort.
