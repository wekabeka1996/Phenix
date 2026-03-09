# Active Positions Snapshot (2026-03-08T03:05:00.801000+00:00)

## Summary Counts
- Active positions: 1
- Pending orders: 3
- Anomalies: 2

## Active Positions
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | entry_regime | current_regime | unrealized_pnl | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SOLUSDT:aurora_SOLUSDT_1772935803130 | SOLUSDT | aurora | sell | open_position | 2026-03-08T02:15:42.059000+00:00 | 82.84 | HIGH_VOLATILITY | HIGH_VOLATILITY | 56.52754326 | 2958 | symbol_busy_conflict,opposite_side_overlap |

## Pending Orders
| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | age_sec | anomaly_flags |
|---|---|---|---|---|---|---|---|---|
| SOLUSDT:aurora_SOLUSDT_1772916600018 | SOLUSDT | aurora | buy | pending | 2026-03-07T20:50:01.225000+00:00 | 82.91 | 22499 | opposite_side_overlap |
| DOGEUSDT:rid-9657bd20a43ca82c | DOGEUSDT |  | buy | pending | 2026-03-08T02:50:04.448000+00:00 | 0.0 | 896 |  |
| ETHUSDT:aurora_ETHUSDT_1772939103463 | ETHUSDT | aurora | buy | pending | 2026-03-08T03:05:04.210000+00:00 | 1943.55 | -3 |  |

## Anomalies
| lifecycle_id | symbol | type | severity | evidence |
|---|---|---|---|---|
| SOLUSDT:aurora_SOLUSDT_1772935803130 | SOLUSDT | symbol-busy conflict | medium | WAL line 4956 TRADE_INTENT_REJECTED NRR-SYMBOL-BUSY |
| * | SOLUSDT | opposite-side overlap | high | Both buy and sell active/pending for same symbol in current snapshot |

## Exact Evidence Files Used
- `ops/wal/2026-03-08.jsonl`
- `logs/order_log_v1.jsonl`
- `config/aurora/strategies/aurora.yaml`
- `config/aurora/trading.yaml`
- `config/aurora/regime.yaml`
- `reports/auto/trade_lifecycle_ledger.jsonl`

## Unresolved Ambiguities
- Lifecycle IDs are partially missing in runtime events; fallback IDs used where absent.
- Entry fill events are inferred from PENDING_BRACKETS_CLEARED(reason=filled) and account updates.
- Strategy ownership checks are best-effort; explicit owner tags not present on all events.
