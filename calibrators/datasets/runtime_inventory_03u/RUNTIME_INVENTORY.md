# RUNTIME_INVENTORY

## Runtime Window
- first_timestamp_utc: 2026-05-09T22:15:03.634000+00:00
- last_timestamp_utc: 2026-05-13T19:04:06.723000+00:00
- duration: 3d 20h 49m 3s
- boot_rows_order_log: 3
- restart_count_proxy: 3
- trading_modes_observed: hybrid_live_data_testnet_exec
- symbols_observed: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT

## Sources
| Source | Rows | Time Range | Symbols | Key Notes |
| --- | ---: | --- | --- | --- |
| order_log | 761 | 2026-05-11T15:10:03.413000+00:00 -> 2026-05-13T17:55:01.595000+00:00 | BNBUSDT, BTCUSDT, ETHUSDT, XRPUSDT | parse_errors=0 |
| decision_ledger | 334 | 2026-05-09T22:15:03.634000+00:00 -> 2026-05-13T14:20:01.047000+00:00 | BNBUSDT, BTCUSDT, ETHUSDT, XRPUSDT | parse_errors=0 |
| trade_lifecycle | 232021 | 2026-05-11T14:54:11.586000+00:00 -> 2026-05-13T19:04:06.723000+00:00 | 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT | parse_errors=1 |

## Order Log
- POSITION_CLOSED rows: 27
- ORDER_TIMEOUT rows: 7
- ORDER_CANCELLED rows: 41
- DECISION_INTENT_REJECTED rows: 234

## Decision Ledger
- accepted rows: 0
- rejected rows: 0
- null accepted_or_rejected rows: 334

## Trade Lifecycle
- total rows: 232021
- terminal-close-like rows: 61
- sidecar rows: 231305
- peak giveback field rows: 231271
