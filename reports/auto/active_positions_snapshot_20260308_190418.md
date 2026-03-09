# Active Positions Snapshot (2026-03-08T19:04:18.247000Z)

## Summary Counts

- Active positions: **5**
- Pending orders: **0**
- Anomalies: **4**

## Active Positions

| lifecycle_id | symbol | strategy_id | side | status | entry_ts | entry_price | current_regime | unrealized_pnl | age_sec | anomaly_flags |
| --- | --- | --- | --- | --- | --- | ---: | --- | ---: | ---: | --- |
| BNBUSDT:mdamr-3fcf6abde2cf1d04 | BNBUSDT | md_amr | buy | open_position | 2026-03-08T13:30:08.387000Z | 615.47 | LOW_VOLATILITY | -13.27646226 | 20049 |  |
| BTCUSDT:aurora_BTCUSDT_1772995504484 | BTCUSDT | aurora | sell | open_position | 2026-03-08T18:45:06.191000Z | 66793.1 | MEAN_REVERSION | -10.6684 | 1152 | forbidden_regime_exposure |
| ETHUSDT:aurora_ETHUSDT_1772972102224 | ETHUSDT | aurora | sell | open_position | 2026-03-08T12:20:39.853000Z | 1935.59 | MEAN_REVERSION | 9.19548 | 24218 | forbidden_regime_exposure |
| SOLUSDT:aurora_SOLUSDT_1772993403777 | SOLUSDT | aurora | sell | open_position | 2026-03-08T18:10:05.387000Z | 81.47 | MEAN_REVERSION | -28.06 | 3252 | forbidden_regime_exposure |
| XRPUSDT:mdamr-82d2a8c71e1ca08a | XRPUSDT | md_amr | buy | open_position | 2026-03-08T13:31:06.866000Z | 1.3475 | LOW_VOLATILITY | -13.70014 | 19991 | strategy_ownership_violation |

## Pending Orders

| lifecycle_id | symbol | strategy_id | side | client_order_id | order_type | entry_price | reduce_only | age_sec |
| --- | --- | --- | --- | --- | --- | ---: | --- | ---: |

## Anomalies

| lifecycle_id | symbol | type | severity | evidence |
| --- | --- | --- | --- | --- |
| BTCUSDT:aurora_BTCUSDT_1772995504484 | BTCUSDT | forbidden regime exposure | medium | Recent TRADE_INTENT_REJECTED reason_code=REGIME_NOT_ALLOWLISTED while lifecycle remains open. |
| ETHUSDT:aurora_ETHUSDT_1772972102224 | ETHUSDT | forbidden regime exposure | medium | Recent TRADE_INTENT_REJECTED reason_code=REGIME_NOT_ALLOWLISTED while lifecycle remains open. |
| SOLUSDT:aurora_SOLUSDT_1772993403777 | SOLUSDT | forbidden regime exposure | medium | Recent TRADE_INTENT_REJECTED reason_code=REGIME_NOT_ALLOWLISTED while lifecycle remains open. |
| XRPUSDT:mdamr-82d2a8c71e1ca08a | XRPUSDT | strategy ownership violation | medium | mean_reversion.yaml asset enabled=false while md_amr lifecycle remains active. |

## Exact Evidence Files Used

- `ops/wal/2026-03-08.jsonl`
- `logs/order_log_v1.jsonl`
- `config/aurora/strategies/aurora.yaml`
- `config/aurora/strategies/mean_reversion.yaml`
- `config/aurora/trading.yaml`
- `config/aurora/regime.yaml`
- `reports/auto/trade_lifecycle_ledger.jsonl`
- `reports/auto/active_positions_snapshot_latest.json`

## Unresolved Ambiguities

- No explicit ORDER_FILLED telemetry in order_log_v1 for every active entry; filled state inferred from account update continuity and WAL bracket-clear events.
- Protective bracket visibility for aurora limit entries is partial in order_log_v1; WAL bracket events used where available.
- Strategy ownership checks rely on current YAML and may diverge from runtime-effective config at execution time.
