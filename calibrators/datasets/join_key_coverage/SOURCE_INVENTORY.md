# SOURCE_INVENTORY

| Source | Exists | Rows | Time Range | Key Fields | Outcome Fields | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| data/authority_request_journal_v1.jsonl | True | 28 | 2026-05-07T03:15:03.456000+00:00 -> 2026-05-07T12:35:05.541000+00:00 | decision_id, rid, symbol, decision_basis_ts_ms | none |  |
| data/authority_response_journal_v1.jsonl | True | 28 | n/a | decision_id | none |  |
| data/order_ledger.db::orders | True | 1781 | 2026-03-13T08:35:02.984000+00:00 -> 2026-05-07T12:35:06.554000+00:00 | order_id, client_order_id, entry_client_id, symbol, created_at, updated_at | none | sqlite_table=orders; sqlite_table=orders |
| data/recorder/2026-02-08/BTCUSDT_180.csv | True | 103 | 2026-02-08T13:59:59.999000+00:00 -> 2026-02-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/BTCUSDT_300.csv | True | 65 | 2026-02-08T13:54:59.999000+00:00 -> 2026-02-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/BTCUSDT_900.csv | True | 23 | 2026-02-08T13:59:59.999000+00:00 -> 2026-02-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/DOGEUSDT_180.csv | True | 103 | 2026-02-08T13:59:59.999000+00:00 -> 2026-02-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/DOGEUSDT_300.csv | True | 65 | 2026-02-08T13:54:59.999000+00:00 -> 2026-02-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/DOGEUSDT_900.csv | True | 23 | 2026-02-08T13:59:59.999000+00:00 -> 2026-02-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/ETHUSDT_180.csv | True | 103 | 2026-02-08T13:59:59.999000+00:00 -> 2026-02-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/ETHUSDT_300.csv | True | 65 | 2026-02-08T13:54:59.999000+00:00 -> 2026-02-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/ETHUSDT_900.csv | True | 23 | 2026-02-08T13:59:59.999000+00:00 -> 2026-02-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/SOLUSDT_180.csv | True | 103 | 2026-02-08T13:59:59.999000+00:00 -> 2026-02-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/SOLUSDT_300.csv | True | 65 | 2026-02-08T13:54:59.999000+00:00 -> 2026-02-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/SOLUSDT_900.csv | True | 23 | 2026-02-08T13:59:59.999000+00:00 -> 2026-02-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/XRPUSDT_180.csv | True | 103 | 2026-02-08T13:59:59.999000+00:00 -> 2026-02-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/XRPUSDT_300.csv | True | 65 | 2026-02-08T13:54:59.999000+00:00 -> 2026-02-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-08/XRPUSDT_900.csv | True | 23 | 2026-02-08T13:59:59.999000+00:00 -> 2026-02-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/BTCUSDT_180.csv | True | 255 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/BTCUSDT_300.csv | True | 156 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/BTCUSDT_900.csv | True | 56 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/DOGEUSDT_180.csv | True | 255 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/DOGEUSDT_300.csv | True | 156 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/DOGEUSDT_900.csv | True | 56 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/ETHUSDT_180.csv | True | 255 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/ETHUSDT_300.csv | True | 156 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/ETHUSDT_900.csv | True | 56 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/SOLUSDT_180.csv | True | 255 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/SOLUSDT_300.csv | True | 156 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/SOLUSDT_900.csv | True | 56 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/XRPUSDT_180.csv | True | 255 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/XRPUSDT_300.csv | True | 156 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-09/XRPUSDT_900.csv | True | 56 | 2026-02-08T23:59:59.999000+00:00 -> 2026-02-09T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/BTCUSDT_180.csv | True | 474 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/BTCUSDT_300.csv | True | 284 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/BTCUSDT_900.csv | True | 95 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/DOGEUSDT_180.csv | True | 474 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/DOGEUSDT_300.csv | True | 284 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/DOGEUSDT_900.csv | True | 95 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/ETHUSDT_180.csv | True | 474 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/ETHUSDT_300.csv | True | 284 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/ETHUSDT_900.csv | True | 95 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/SOLUSDT_180.csv | True | 474 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/SOLUSDT_300.csv | True | 284 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/SOLUSDT_900.csv | True | 95 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/XRPUSDT_180.csv | True | 474 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/XRPUSDT_300.csv | True | 283 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-10/XRPUSDT_900.csv | True | 95 | 2026-02-09T23:59:59.999000+00:00 -> 2026-02-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/BTCUSDT_180.csv | True | 385 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/BTCUSDT_300.csv | True | 231 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/BTCUSDT_900.csv | True | 77 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/DOGEUSDT_180.csv | True | 385 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/DOGEUSDT_300.csv | True | 231 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/DOGEUSDT_900.csv | True | 77 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/ETHUSDT_180.csv | True | 385 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/ETHUSDT_300.csv | True | 231 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/ETHUSDT_900.csv | True | 77 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/SOLUSDT_180.csv | True | 385 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/SOLUSDT_300.csv | True | 231 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/SOLUSDT_900.csv | True | 77 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/XRPUSDT_180.csv | True | 385 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/XRPUSDT_300.csv | True | 231 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-11/XRPUSDT_900.csv | True | 77 | 2026-02-10T23:59:59.999000+00:00 -> 2026-02-11T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/BTCUSDT_180.csv | True | 476 | 2026-02-12T00:05:59.999000+00:00 -> 2026-02-12T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/BTCUSDT_300.csv | True | 286 | 2026-02-12T00:09:59.999000+00:00 -> 2026-02-12T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/BTCUSDT_900.csv | True | 95 | 2026-02-12T00:14:59.999000+00:00 -> 2026-02-12T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/DOGEUSDT_180.csv | True | 476 | 2026-02-12T00:05:59.999000+00:00 -> 2026-02-12T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/DOGEUSDT_300.csv | True | 286 | 2026-02-12T00:09:59.999000+00:00 -> 2026-02-12T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/DOGEUSDT_900.csv | True | 95 | 2026-02-12T00:14:59.999000+00:00 -> 2026-02-12T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/ETHUSDT_180.csv | True | 476 | 2026-02-12T00:05:59.999000+00:00 -> 2026-02-12T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/ETHUSDT_300.csv | True | 286 | 2026-02-12T00:09:59.999000+00:00 -> 2026-02-12T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/ETHUSDT_900.csv | True | 95 | 2026-02-12T00:14:59.999000+00:00 -> 2026-02-12T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/SOLUSDT_180.csv | True | 476 | 2026-02-12T00:05:59.999000+00:00 -> 2026-02-12T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/SOLUSDT_300.csv | True | 286 | 2026-02-12T00:09:59.999000+00:00 -> 2026-02-12T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/SOLUSDT_900.csv | True | 95 | 2026-02-12T00:14:59.999000+00:00 -> 2026-02-12T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/XRPUSDT_180.csv | True | 476 | 2026-02-12T00:05:59.999000+00:00 -> 2026-02-12T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/XRPUSDT_300.csv | True | 286 | 2026-02-12T00:09:59.999000+00:00 -> 2026-02-12T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-12/XRPUSDT_900.csv | True | 95 | 2026-02-12T00:14:59.999000+00:00 -> 2026-02-12T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/BTCUSDT_180.csv | True | 450 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/BTCUSDT_300.csv | True | 270 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/BTCUSDT_900.csv | True | 90 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/DOGEUSDT_180.csv | True | 450 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/DOGEUSDT_300.csv | True | 270 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/DOGEUSDT_900.csv | True | 90 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/ETHUSDT_180.csv | True | 450 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/ETHUSDT_300.csv | True | 270 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/ETHUSDT_900.csv | True | 90 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/SOLUSDT_180.csv | True | 450 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/SOLUSDT_300.csv | True | 270 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/SOLUSDT_900.csv | True | 90 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/XRPUSDT_180.csv | True | 450 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/XRPUSDT_300.csv | True | 270 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-13/XRPUSDT_900.csv | True | 90 | 2026-02-12T23:59:59.999000+00:00 -> 2026-02-13T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/BTCUSDT_180.csv | True | 474 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:47:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/BTCUSDT_300.csv | True | 285 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/BTCUSDT_900.csv | True | 96 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/DOGEUSDT_180.csv | True | 474 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:47:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/DOGEUSDT_300.csv | True | 285 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/DOGEUSDT_900.csv | True | 96 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/ETHUSDT_180.csv | True | 474 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:47:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/ETHUSDT_300.csv | True | 285 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/ETHUSDT_900.csv | True | 96 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/SOLUSDT_180.csv | True | 474 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:47:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/SOLUSDT_300.csv | True | 285 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/SOLUSDT_900.csv | True | 96 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/XRPUSDT_180.csv | True | 474 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:47:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/XRPUSDT_300.csv | True | 285 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-14/XRPUSDT_900.csv | True | 96 | 2026-02-13T23:59:59.999000+00:00 -> 2026-02-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/BTCUSDT_180.csv | True | 476 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/BTCUSDT_300.csv | True | 284 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/BTCUSDT_900.csv | True | 95 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/DOGEUSDT_180.csv | True | 476 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/DOGEUSDT_300.csv | True | 284 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/DOGEUSDT_900.csv | True | 95 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/ETHUSDT_180.csv | True | 476 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/ETHUSDT_300.csv | True | 284 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/ETHUSDT_900.csv | True | 95 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/SOLUSDT_180.csv | True | 476 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/SOLUSDT_300.csv | True | 284 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/SOLUSDT_900.csv | True | 95 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/XRPUSDT_180.csv | True | 476 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/XRPUSDT_300.csv | True | 284 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-15/XRPUSDT_900.csv | True | 95 | 2026-02-14T23:59:59.999000+00:00 -> 2026-02-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/BTCUSDT_180.csv | True | 461 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/BTCUSDT_300.csv | True | 280 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/BTCUSDT_900.csv | True | 95 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/DOGEUSDT_180.csv | True | 461 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/DOGEUSDT_300.csv | True | 280 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/DOGEUSDT_900.csv | True | 95 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/ETHUSDT_180.csv | True | 461 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/ETHUSDT_300.csv | True | 280 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/ETHUSDT_900.csv | True | 95 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/SOLUSDT_180.csv | True | 461 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/SOLUSDT_300.csv | True | 280 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/SOLUSDT_900.csv | True | 95 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/XRPUSDT_180.csv | True | 461 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/XRPUSDT_300.csv | True | 280 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-16/XRPUSDT_900.csv | True | 95 | 2026-02-15T23:59:59.999000+00:00 -> 2026-02-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/BTCUSDT_180.csv | True | 475 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/BTCUSDT_300.csv | True | 284 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/BTCUSDT_900.csv | True | 95 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/DOGEUSDT_180.csv | True | 475 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/DOGEUSDT_300.csv | True | 284 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/DOGEUSDT_900.csv | True | 95 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/ETHUSDT_180.csv | True | 475 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/ETHUSDT_300.csv | True | 284 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/ETHUSDT_900.csv | True | 95 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/SOLUSDT_180.csv | True | 475 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/SOLUSDT_300.csv | True | 284 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/SOLUSDT_900.csv | True | 95 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/XRPUSDT_180.csv | True | 475 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/XRPUSDT_300.csv | True | 284 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-17/XRPUSDT_900.csv | True | 95 | 2026-02-16T23:59:59.999000+00:00 -> 2026-02-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/BTCUSDT_180.csv | True | 480 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/BTCUSDT_300.csv | True | 288 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/BTCUSDT_900.csv | True | 96 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/DOGEUSDT_180.csv | True | 480 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/DOGEUSDT_300.csv | True | 288 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/DOGEUSDT_900.csv | True | 96 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/ETHUSDT_180.csv | True | 480 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/ETHUSDT_300.csv | True | 288 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/ETHUSDT_900.csv | True | 96 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/SOLUSDT_180.csv | True | 480 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/SOLUSDT_300.csv | True | 288 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/SOLUSDT_900.csv | True | 96 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/XRPUSDT_180.csv | True | 480 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/XRPUSDT_300.csv | True | 288 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-18/XRPUSDT_900.csv | True | 96 | 2026-02-17T23:59:59.999000+00:00 -> 2026-02-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/BTCUSDT_180.csv | True | 385 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/BTCUSDT_300.csv | True | 230 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/BTCUSDT_900.csv | True | 76 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/DOGEUSDT_180.csv | True | 385 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/DOGEUSDT_300.csv | True | 230 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/DOGEUSDT_900.csv | True | 76 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/ETHUSDT_180.csv | True | 385 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/ETHUSDT_300.csv | True | 230 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/ETHUSDT_900.csv | True | 76 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/SOLUSDT_180.csv | True | 385 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/SOLUSDT_300.csv | True | 230 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/SOLUSDT_900.csv | True | 76 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/XRPUSDT_180.csv | True | 385 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/XRPUSDT_300.csv | True | 230 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-19/XRPUSDT_900.csv | True | 76 | 2026-02-18T23:59:59.999000+00:00 -> 2026-02-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/BTCUSDT_180.csv | True | 480 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/BTCUSDT_300.csv | True | 288 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/BTCUSDT_900.csv | True | 96 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/DOGEUSDT_180.csv | True | 480 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/DOGEUSDT_300.csv | True | 288 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/DOGEUSDT_900.csv | True | 96 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/ETHUSDT_180.csv | True | 480 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/ETHUSDT_300.csv | True | 288 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/ETHUSDT_900.csv | True | 96 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/SOLUSDT_180.csv | True | 480 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/SOLUSDT_300.csv | True | 288 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/SOLUSDT_900.csv | True | 96 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/XRPUSDT_180.csv | True | 480 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/XRPUSDT_300.csv | True | 288 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-20/XRPUSDT_900.csv | True | 96 | 2026-02-19T23:59:59.999000+00:00 -> 2026-02-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/BTCUSDT_180.csv | True | 480 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/BTCUSDT_300.csv | True | 288 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/BTCUSDT_900.csv | True | 96 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/DOGEUSDT_180.csv | True | 480 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/DOGEUSDT_300.csv | True | 288 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/DOGEUSDT_900.csv | True | 96 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/ETHUSDT_180.csv | True | 480 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/ETHUSDT_300.csv | True | 288 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/ETHUSDT_900.csv | True | 96 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/SOLUSDT_180.csv | True | 480 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/SOLUSDT_300.csv | True | 288 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/SOLUSDT_900.csv | True | 96 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/XRPUSDT_180.csv | True | 480 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/XRPUSDT_300.csv | True | 288 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-21/XRPUSDT_900.csv | True | 96 | 2026-02-20T23:59:59.999000+00:00 -> 2026-02-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/BTCUSDT_180.csv | True | 480 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/BTCUSDT_300.csv | True | 288 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/BTCUSDT_900.csv | True | 96 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/DOGEUSDT_180.csv | True | 480 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/DOGEUSDT_300.csv | True | 288 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/DOGEUSDT_900.csv | True | 96 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/ETHUSDT_180.csv | True | 480 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/ETHUSDT_300.csv | True | 288 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/ETHUSDT_900.csv | True | 96 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/SOLUSDT_180.csv | True | 480 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/SOLUSDT_300.csv | True | 288 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/SOLUSDT_900.csv | True | 96 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/XRPUSDT_180.csv | True | 480 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/XRPUSDT_300.csv | True | 288 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-22/XRPUSDT_900.csv | True | 96 | 2026-02-21T23:59:59.999000+00:00 -> 2026-02-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/BTCUSDT_180.csv | True | 461 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/BTCUSDT_300.csv | True | 276 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/BTCUSDT_900.csv | True | 92 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/DOGEUSDT_180.csv | True | 461 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/DOGEUSDT_300.csv | True | 276 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/DOGEUSDT_900.csv | True | 92 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/ETHUSDT_180.csv | True | 461 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/ETHUSDT_300.csv | True | 276 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/ETHUSDT_900.csv | True | 92 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/SOLUSDT_180.csv | True | 461 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/SOLUSDT_300.csv | True | 276 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/SOLUSDT_900.csv | True | 92 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/XRPUSDT_180.csv | True | 461 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/XRPUSDT_300.csv | True | 276 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-23/XRPUSDT_900.csv | True | 92 | 2026-02-22T23:59:59.999000+00:00 -> 2026-02-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/BTCUSDT_180.csv | True | 310 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/BTCUSDT_300.csv | True | 186 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/BTCUSDT_900.csv | True | 62 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/DOGEUSDT_180.csv | True | 310 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/DOGEUSDT_300.csv | True | 186 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/DOGEUSDT_900.csv | True | 62 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/ETHUSDT_180.csv | True | 310 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/ETHUSDT_300.csv | True | 186 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/ETHUSDT_900.csv | True | 62 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/SOLUSDT_180.csv | True | 310 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/SOLUSDT_300.csv | True | 186 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/SOLUSDT_900.csv | True | 62 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/XRPUSDT_180.csv | True | 310 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/XRPUSDT_300.csv | True | 186 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-24/XRPUSDT_900.csv | True | 62 | 2026-02-23T23:59:59.999000+00:00 -> 2026-02-24T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/BTCUSDT_180.csv | True | 423 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/BTCUSDT_300.csv | True | 255 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/BTCUSDT_900.csv | True | 86 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/DOGEUSDT_180.csv | True | 423 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/DOGEUSDT_300.csv | True | 255 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/DOGEUSDT_900.csv | True | 86 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/ETHUSDT_180.csv | True | 423 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/ETHUSDT_300.csv | True | 255 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/ETHUSDT_900.csv | True | 86 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/SOLUSDT_180.csv | True | 423 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/SOLUSDT_300.csv | True | 255 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/SOLUSDT_900.csv | True | 86 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/XRPUSDT_180.csv | True | 423 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/XRPUSDT_300.csv | True | 255 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-25/XRPUSDT_900.csv | True | 86 | 2026-02-24T23:59:59.999000+00:00 -> 2026-02-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/BTCUSDT_180.csv | True | 465 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/BTCUSDT_300.csv | True | 279 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/BTCUSDT_900.csv | True | 94 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/DOGEUSDT_180.csv | True | 465 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/DOGEUSDT_300.csv | True | 279 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/DOGEUSDT_900.csv | True | 94 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/ETHUSDT_180.csv | True | 465 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/ETHUSDT_300.csv | True | 279 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/ETHUSDT_900.csv | True | 94 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/SOLUSDT_180.csv | True | 465 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/SOLUSDT_300.csv | True | 279 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/SOLUSDT_900.csv | True | 94 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/XRPUSDT_180.csv | True | 465 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/XRPUSDT_300.csv | True | 279 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-26/XRPUSDT_900.csv | True | 94 | 2026-02-25T23:59:59.999000+00:00 -> 2026-02-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/BTCUSDT_180.csv | True | 480 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/BTCUSDT_300.csv | True | 288 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/BTCUSDT_900.csv | True | 96 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/DOGEUSDT_180.csv | True | 480 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/DOGEUSDT_300.csv | True | 288 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/DOGEUSDT_900.csv | True | 96 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/ETHUSDT_180.csv | True | 480 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/ETHUSDT_300.csv | True | 288 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/ETHUSDT_900.csv | True | 96 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/SOLUSDT_180.csv | True | 480 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/SOLUSDT_300.csv | True | 288 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/SOLUSDT_900.csv | True | 96 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/XRPUSDT_180.csv | True | 480 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/XRPUSDT_300.csv | True | 288 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-27/XRPUSDT_900.csv | True | 96 | 2026-02-26T23:59:59.999000+00:00 -> 2026-02-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/BTCUSDT_180.csv | True | 442 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/BTCUSDT_300.csv | True | 266 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/BTCUSDT_900.csv | True | 89 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/DOGEUSDT_180.csv | True | 442 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/DOGEUSDT_300.csv | True | 266 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/DOGEUSDT_900.csv | True | 89 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/ETHUSDT_180.csv | True | 442 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/ETHUSDT_300.csv | True | 266 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/ETHUSDT_900.csv | True | 89 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/SOLUSDT_180.csv | True | 442 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/SOLUSDT_300.csv | True | 266 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/SOLUSDT_900.csv | True | 89 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/XRPUSDT_180.csv | True | 442 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/XRPUSDT_300.csv | True | 266 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-02-28/XRPUSDT_900.csv | True | 89 | 2026-02-27T23:59:59.999000+00:00 -> 2026-02-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/BTCUSDT_180.csv | True | 352 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/BTCUSDT_300.csv | True | 213 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/BTCUSDT_900.csv | True | 71 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/DOGEUSDT_180.csv | True | 352 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/DOGEUSDT_300.csv | True | 213 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/DOGEUSDT_900.csv | True | 71 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/ETHUSDT_180.csv | True | 352 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/ETHUSDT_300.csv | True | 213 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/ETHUSDT_900.csv | True | 71 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/SOLUSDT_180.csv | True | 352 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/SOLUSDT_300.csv | True | 213 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/SOLUSDT_900.csv | True | 71 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/XRPUSDT_180.csv | True | 352 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/XRPUSDT_300.csv | True | 213 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-01/XRPUSDT_900.csv | True | 71 | 2026-02-28T23:59:59.999000+00:00 -> 2026-03-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/BTCUSDT_180.csv | True | 380 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/BTCUSDT_300.csv | True | 228 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/BTCUSDT_900.csv | True | 76 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/DOGEUSDT_180.csv | True | 380 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/DOGEUSDT_300.csv | True | 228 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/DOGEUSDT_900.csv | True | 76 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/ETHUSDT_180.csv | True | 380 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/ETHUSDT_300.csv | True | 228 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/ETHUSDT_900.csv | True | 76 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/SOLUSDT_180.csv | True | 380 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/SOLUSDT_300.csv | True | 228 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/SOLUSDT_900.csv | True | 76 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/XRPUSDT_180.csv | True | 380 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/XRPUSDT_300.csv | True | 228 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-02/XRPUSDT_900.csv | True | 76 | 2026-03-01T23:59:59.999000+00:00 -> 2026-03-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-03/BTCUSDT_180.csv | True | 2 | 2026-03-02T23:59:59.999000+00:00 -> 2026-03-02T23:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/BTCUSDT_300.csv | True | 17 | 1970-01-01T00:05:00+00:00 -> 2026-03-03T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/BTCUSDT_900.csv | True | 27 | 2026-03-02T23:59:59.999000+00:00 -> 2026-03-03T06:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/DOGEUSDT_180.csv | True | 2 | 2026-03-02T23:59:59.999000+00:00 -> 2026-03-02T23:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/DOGEUSDT_300.csv | True | 17 | 1970-01-01T00:05:00+00:00 -> 2026-03-03T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/DOGEUSDT_900.csv | True | 27 | 2026-03-02T23:59:59.999000+00:00 -> 2026-03-03T06:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/ETHUSDT_180.csv | True | 2 | 2026-03-02T23:59:59.999000+00:00 -> 2026-03-02T23:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/ETHUSDT_300.csv | True | 17 | 1970-01-01T00:05:00+00:00 -> 2026-03-03T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/ETHUSDT_900.csv | True | 27 | 2026-03-02T23:59:59.999000+00:00 -> 2026-03-03T06:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/SOLUSDT_180.csv | True | 2 | 2026-03-02T23:59:59.999000+00:00 -> 2026-03-02T23:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/SOLUSDT_300.csv | True | 17 | 1970-01-01T00:05:00+00:00 -> 2026-03-03T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/SOLUSDT_900.csv | True | 27 | 2026-03-02T23:59:59.999000+00:00 -> 2026-03-03T06:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/XRPUSDT_180.csv | True | 2 | 2026-03-02T23:59:59.999000+00:00 -> 2026-03-02T23:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/XRPUSDT_300.csv | True | 17 | 1970-01-01T00:05:00+00:00 -> 2026-03-03T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-03/XRPUSDT_900.csv | True | 27 | 2026-03-02T23:59:59.999000+00:00 -> 2026-03-03T06:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/BTCUSDT_180.csv | True | 3 | 1970-01-01T00:03:00+00:00 -> 2026-03-04T00:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/BTCUSDT_300.csv | True | 4 | 1970-01-01T00:05:00+00:00 -> 2026-03-04T00:09:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/BTCUSDT_900.csv | True | 12 | 2026-03-03T23:59:59.999000+00:00 -> 2026-03-04T02:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/DOGEUSDT_180.csv | True | 3 | 1970-01-01T00:03:00+00:00 -> 2026-03-04T00:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/DOGEUSDT_300.csv | True | 4 | 1970-01-01T00:05:00+00:00 -> 2026-03-04T00:09:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/DOGEUSDT_900.csv | True | 12 | 2026-03-03T23:59:59.999000+00:00 -> 2026-03-04T02:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/ETHUSDT_180.csv | True | 3 | 1970-01-01T00:03:00+00:00 -> 2026-03-04T00:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/ETHUSDT_300.csv | True | 4 | 1970-01-01T00:05:00+00:00 -> 2026-03-04T00:09:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/ETHUSDT_900.csv | True | 12 | 2026-03-03T23:59:59.999000+00:00 -> 2026-03-04T02:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/SOLUSDT_180.csv | True | 3 | 1970-01-01T00:03:00+00:00 -> 2026-03-04T00:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/SOLUSDT_300.csv | True | 4 | 1970-01-01T00:05:00+00:00 -> 2026-03-04T00:09:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/SOLUSDT_900.csv | True | 12 | 2026-03-03T23:59:59.999000+00:00 -> 2026-03-04T02:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/XRPUSDT_180.csv | True | 3 | 1970-01-01T00:03:00+00:00 -> 2026-03-04T00:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/XRPUSDT_300.csv | True | 4 | 1970-01-01T00:05:00+00:00 -> 2026-03-04T00:09:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-04/XRPUSDT_900.csv | True | 12 | 2026-03-03T23:59:59.999000+00:00 -> 2026-03-04T02:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/BNBUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-05T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/BNBUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-05T01:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/BNBUSDT_900.csv | True | 15 | 2026-03-05T00:44:59.999000+00:00 -> 2026-03-05T03:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/BTCUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-05T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/BTCUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-05T01:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/BTCUSDT_900.csv | True | 15 | 2026-03-05T00:44:59.999000+00:00 -> 2026-03-05T03:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/DOGEUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-05T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/DOGEUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-05T01:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/DOGEUSDT_900.csv | True | 15 | 2026-03-05T00:44:59.999000+00:00 -> 2026-03-05T03:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/ETHUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-05T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/ETHUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-05T01:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/ETHUSDT_900.csv | True | 15 | 2026-03-05T00:44:59.999000+00:00 -> 2026-03-05T03:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/SOLUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-05T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/SOLUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-05T01:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/SOLUSDT_900.csv | True | 15 | 2026-03-05T00:44:59.999000+00:00 -> 2026-03-05T03:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/XRPUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-05T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/XRPUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-05T01:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-05/XRPUSDT_900.csv | True | 15 | 2026-03-05T00:44:59.999000+00:00 -> 2026-03-05T03:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/BNBUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-06T07:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/BNBUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-06T07:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/BNBUSDT_900.csv | True | 15 | 2026-03-06T06:29:59.999000+00:00 -> 2026-03-06T09:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/BTCUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-06T07:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/BTCUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-06T07:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/BTCUSDT_900.csv | True | 15 | 2026-03-06T06:29:59.999000+00:00 -> 2026-03-06T09:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/DOGEUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-06T07:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/DOGEUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-06T07:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/DOGEUSDT_900.csv | True | 15 | 2026-03-06T06:29:59.999000+00:00 -> 2026-03-06T09:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/ETHUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-06T07:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/ETHUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-06T07:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/ETHUSDT_900.csv | True | 15 | 2026-03-06T06:29:59.999000+00:00 -> 2026-03-06T09:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/SOLUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-06T07:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/SOLUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-06T07:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/SOLUSDT_900.csv | True | 15 | 2026-03-06T06:29:59.999000+00:00 -> 2026-03-06T09:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/XRPUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-06T07:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/XRPUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-06T07:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-06/XRPUSDT_900.csv | True | 15 | 2026-03-06T06:29:59.999000+00:00 -> 2026-03-06T09:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-07/1000PEPEUSDT_180.csv | True | 15 | 1970-01-01T00:03:00+00:00 -> 2026-03-07T17:41:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-07/1000PEPEUSDT_300.csv | True | 15 | 1970-01-01T00:05:00+00:00 -> 2026-03-07T18:09:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-07/1000PEPEUSDT_900.csv | True | 15 | 2026-03-07T17:14:59.999000+00:00 -> 2026-03-07T20:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-07/BNBUSDT_180.csv | True | 469 | 1970-01-01T00:00:36+00:00 -> 2026-03-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/BNBUSDT_300.csv | True | 281 | 2026-03-06T23:59:59.999000+00:00 -> 2026-03-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/BNBUSDT_900.csv | True | 93 | 2026-03-06T23:59:59.999000+00:00 -> 2026-03-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/BTCUSDT_180.csv | True | 469 | 1970-01-01T00:00:36+00:00 -> 2026-03-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/BTCUSDT_300.csv | True | 281 | 2026-03-06T23:59:59.999000+00:00 -> 2026-03-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/BTCUSDT_900.csv | True | 93 | 2026-03-06T23:59:59.999000+00:00 -> 2026-03-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/DOGEUSDT_180.csv | True | 469 | 1970-01-01T00:00:36+00:00 -> 2026-03-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/DOGEUSDT_300.csv | True | 281 | 2026-03-06T23:59:59.999000+00:00 -> 2026-03-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/DOGEUSDT_900.csv | True | 93 | 2026-03-06T23:59:59.999000+00:00 -> 2026-03-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/ETHUSDT_180.csv | True | 469 | 1970-01-01T00:00:36+00:00 -> 2026-03-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/ETHUSDT_300.csv | True | 281 | 2026-03-06T23:59:59.999000+00:00 -> 2026-03-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/ETHUSDT_900.csv | True | 93 | 2026-03-06T23:59:59.999000+00:00 -> 2026-03-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/SOLUSDT_180.csv | True | 469 | 1970-01-01T00:00:36+00:00 -> 2026-03-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/SOLUSDT_300.csv | True | 281 | 2026-03-06T23:59:59.999000+00:00 -> 2026-03-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/SOLUSDT_900.csv | True | 93 | 2026-03-06T23:59:59.999000+00:00 -> 2026-03-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/XRPUSDT_180.csv | True | 469 | 1970-01-01T00:00:36+00:00 -> 2026-03-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/XRPUSDT_300.csv | True | 281 | 2026-03-06T23:59:59.999000+00:00 -> 2026-03-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-07/XRPUSDT_900.csv | True | 93 | 2026-03-06T23:59:59.999000+00:00 -> 2026-03-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/1000PEPEUSDT_180.csv | True | 478 | 1970-01-01T00:00:36+00:00 -> 2026-03-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/1000PEPEUSDT_300.csv | True | 288 | 1970-01-01T00:01:00+00:00 -> 2026-03-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/1000PEPEUSDT_900.csv | True | 96 | 2026-03-07T23:59:59.999000+00:00 -> 2026-03-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/BNBUSDT_180.csv | True | 478 | 1970-01-01T00:00:36+00:00 -> 2026-03-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/BNBUSDT_300.csv | True | 288 | 1970-01-01T00:01:00+00:00 -> 2026-03-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/BNBUSDT_900.csv | True | 96 | 2026-03-07T23:59:59.999000+00:00 -> 2026-03-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/BTCUSDT_180.csv | True | 478 | 1970-01-01T00:00:36+00:00 -> 2026-03-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/BTCUSDT_300.csv | True | 288 | 1970-01-01T00:01:00+00:00 -> 2026-03-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/BTCUSDT_900.csv | True | 96 | 2026-03-07T23:59:59.999000+00:00 -> 2026-03-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/DOGEUSDT_180.csv | True | 479 | 1970-01-01T00:00:36+00:00 -> 2026-03-08T23:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/DOGEUSDT_300.csv | True | 288 | 1970-01-01T00:01:00+00:00 -> 2026-03-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/DOGEUSDT_900.csv | True | 96 | 2026-03-07T23:59:59.999000+00:00 -> 2026-03-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/ETHUSDT_180.csv | True | 478 | 1970-01-01T00:00:36+00:00 -> 2026-03-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/ETHUSDT_300.csv | True | 288 | 1970-01-01T00:01:00+00:00 -> 2026-03-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/ETHUSDT_900.csv | True | 96 | 2026-03-07T23:59:59.999000+00:00 -> 2026-03-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/SOLUSDT_180.csv | True | 478 | 1970-01-01T00:00:36+00:00 -> 2026-03-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/SOLUSDT_300.csv | True | 288 | 1970-01-01T00:01:00+00:00 -> 2026-03-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/SOLUSDT_900.csv | True | 96 | 2026-03-07T23:59:59.999000+00:00 -> 2026-03-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/XRPUSDT_180.csv | True | 478 | 1970-01-01T00:00:36+00:00 -> 2026-03-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/XRPUSDT_300.csv | True | 288 | 1970-01-01T00:01:00+00:00 -> 2026-03-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-08/XRPUSDT_900.csv | True | 96 | 2026-03-07T23:59:59.999000+00:00 -> 2026-03-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/1000PEPEUSDT_180.csv | True | 213 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/1000PEPEUSDT_300.csv | True | 128 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/1000PEPEUSDT_900.csv | True | 43 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/BNBUSDT_180.csv | True | 213 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/BNBUSDT_300.csv | True | 128 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/BNBUSDT_900.csv | True | 43 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/BTCUSDT_180.csv | True | 213 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/BTCUSDT_300.csv | True | 128 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/BTCUSDT_900.csv | True | 43 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/DOGEUSDT_180.csv | True | 212 | 2026-03-09T00:02:59.999000+00:00 -> 2026-03-09T10:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/DOGEUSDT_300.csv | True | 128 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/DOGEUSDT_900.csv | True | 43 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/ETHUSDT_180.csv | True | 213 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/ETHUSDT_300.csv | True | 128 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/ETHUSDT_900.csv | True | 43 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/SOLUSDT_180.csv | True | 213 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/SOLUSDT_300.csv | True | 128 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/SOLUSDT_900.csv | True | 43 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/XRPUSDT_180.csv | True | 213 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/XRPUSDT_300.csv | True | 128 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-09/XRPUSDT_900.csv | True | 43 | 2026-03-08T23:59:59.999000+00:00 -> 2026-03-09T10:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/1000PEPEUSDT_180.csv | True | 13 | 2026-03-10T23:20:59.999000+00:00 -> 2026-03-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/1000PEPEUSDT_300.csv | True | 7 | 2026-03-10T23:24:59.999000+00:00 -> 2026-03-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/1000PEPEUSDT_900.csv | True | 2 | 2026-03-10T23:29:59.999000+00:00 -> 2026-03-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/BNBUSDT_180.csv | True | 13 | 2026-03-10T23:20:59.999000+00:00 -> 2026-03-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/BNBUSDT_300.csv | True | 7 | 2026-03-10T23:24:59.999000+00:00 -> 2026-03-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/BNBUSDT_900.csv | True | 2 | 2026-03-10T23:29:59.999000+00:00 -> 2026-03-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/BTCUSDT_180.csv | True | 13 | 2026-03-10T23:20:59.999000+00:00 -> 2026-03-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/BTCUSDT_300.csv | True | 7 | 2026-03-10T23:24:59.999000+00:00 -> 2026-03-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/BTCUSDT_900.csv | True | 2 | 2026-03-10T23:29:59.999000+00:00 -> 2026-03-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/DOGEUSDT_180.csv | True | 13 | 2026-03-10T23:20:59.999000+00:00 -> 2026-03-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/DOGEUSDT_300.csv | True | 7 | 2026-03-10T23:24:59.999000+00:00 -> 2026-03-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/DOGEUSDT_900.csv | True | 2 | 2026-03-10T23:29:59.999000+00:00 -> 2026-03-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/ETHUSDT_180.csv | True | 13 | 2026-03-10T23:20:59.999000+00:00 -> 2026-03-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/ETHUSDT_300.csv | True | 7 | 2026-03-10T23:24:59.999000+00:00 -> 2026-03-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/ETHUSDT_900.csv | True | 2 | 2026-03-10T23:29:59.999000+00:00 -> 2026-03-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/SOLUSDT_180.csv | True | 13 | 2026-03-10T23:20:59.999000+00:00 -> 2026-03-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/SOLUSDT_300.csv | True | 3 | 1970-01-01T00:00:00+00:00 -> 2026-03-10T23:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-10/SOLUSDT_900.csv | True | 2 | 2026-03-10T23:29:59.999000+00:00 -> 2026-03-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/XRPUSDT_180.csv | True | 13 | 2026-03-10T23:20:59.999000+00:00 -> 2026-03-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/XRPUSDT_300.csv | True | 7 | 2026-03-10T23:24:59.999000+00:00 -> 2026-03-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-10/XRPUSDT_900.csv | True | 2 | 2026-03-10T23:29:59.999000+00:00 -> 2026-03-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/1000PEPEUSDT_180.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:02:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/1000PEPEUSDT_300.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/1000PEPEUSDT_900.csv | True | 1 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-10T23:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/BNBUSDT_180.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:02:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/BNBUSDT_300.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/BNBUSDT_900.csv | True | 1 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-10T23:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/BTCUSDT_180.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:02:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/BTCUSDT_300.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/BTCUSDT_900.csv | True | 1 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-10T23:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/DOGEUSDT_180.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:02:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/DOGEUSDT_300.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/DOGEUSDT_900.csv | True | 1 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-10T23:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/ETHUSDT_180.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:02:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/ETHUSDT_300.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/ETHUSDT_900.csv | True | 1 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-10T23:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/SOLUSDT_180.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:02:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/SOLUSDT_300.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/SOLUSDT_900.csv | True | 1 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-10T23:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/XRPUSDT_180.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:02:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/XRPUSDT_300.csv | True | 2 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-11T00:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-11/XRPUSDT_900.csv | True | 1 | 2026-03-10T23:59:59.999000+00:00 -> 2026-03-10T23:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-12/1000PEPEUSDT_180.csv | True | 151 | 2026-03-12T01:11:59.999000+00:00 -> 2026-03-12T10:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/1000PEPEUSDT_300.csv | True | 91 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/1000PEPEUSDT_900.csv | True | 32 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/BNBUSDT_180.csv | True | 151 | 2026-03-12T01:11:59.999000+00:00 -> 2026-03-12T10:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/BNBUSDT_300.csv | True | 91 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/BNBUSDT_900.csv | True | 32 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/BTCUSDT_180.csv | True | 151 | 2026-03-12T01:11:59.999000+00:00 -> 2026-03-12T10:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/BTCUSDT_300.csv | True | 91 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/BTCUSDT_900.csv | True | 32 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/DOGEUSDT_180.csv | True | 151 | 2026-03-12T01:11:59.999000+00:00 -> 2026-03-12T10:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/DOGEUSDT_300.csv | True | 91 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/DOGEUSDT_900.csv | True | 32 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/ETHUSDT_180.csv | True | 151 | 2026-03-12T01:11:59.999000+00:00 -> 2026-03-12T10:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/ETHUSDT_300.csv | True | 91 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/ETHUSDT_900.csv | True | 32 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/SOLUSDT_180.csv | True | 151 | 2026-03-12T01:11:59.999000+00:00 -> 2026-03-12T10:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/SOLUSDT_300.csv | True | 91 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/SOLUSDT_900.csv | True | 32 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/XRPUSDT_180.csv | True | 151 | 2026-03-12T01:11:59.999000+00:00 -> 2026-03-12T10:02:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/XRPUSDT_300.csv | True | 91 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-12/XRPUSDT_900.csv | True | 32 | 2026-03-12T01:14:59.999000+00:00 -> 2026-03-12T09:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-13/1000PEPEUSDT_180.csv | True | 228 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/1000PEPEUSDT_300.csv | True | 138 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/1000PEPEUSDT_900.csv | True | 46 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:14:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/BNBUSDT_180.csv | True | 228 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/BNBUSDT_300.csv | True | 138 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/BNBUSDT_900.csv | True | 46 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:14:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/BTCUSDT_180.csv | True | 228 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/BTCUSDT_300.csv | True | 138 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/BTCUSDT_900.csv | True | 46 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:14:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/DOGEUSDT_180.csv | True | 228 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/DOGEUSDT_300.csv | True | 138 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/DOGEUSDT_900.csv | True | 46 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:14:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/ETHUSDT_180.csv | True | 228 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/ETHUSDT_300.csv | True | 138 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/ETHUSDT_900.csv | True | 46 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:14:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/SOLUSDT_180.csv | True | 228 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/SOLUSDT_300.csv | True | 138 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/SOLUSDT_900.csv | True | 46 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:14:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/XRPUSDT_180.csv | True | 228 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/XRPUSDT_300.csv | True | 138 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-13/XRPUSDT_900.csv | True | 46 | 2026-03-12T23:59:59.999000+00:00 -> 2026-03-13T12:14:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/1000PEPEUSDT_180.csv | True | 286 | 2026-03-14T00:56:59.999000+00:00 -> 2026-03-14T15:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/1000PEPEUSDT_300.csv | True | 170 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T15:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/1000PEPEUSDT_900.csv | True | 57 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T14:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/BNBUSDT_180.csv | True | 286 | 2026-03-14T00:56:59.999000+00:00 -> 2026-03-14T15:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/BNBUSDT_300.csv | True | 170 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T15:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/BNBUSDT_900.csv | True | 57 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T14:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/BTCUSDT_180.csv | True | 286 | 2026-03-14T00:56:59.999000+00:00 -> 2026-03-14T15:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/BTCUSDT_300.csv | True | 170 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T15:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/BTCUSDT_900.csv | True | 57 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T14:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/DOGEUSDT_180.csv | True | 286 | 2026-03-14T00:56:59.999000+00:00 -> 2026-03-14T15:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/DOGEUSDT_300.csv | True | 170 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T15:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/DOGEUSDT_900.csv | True | 57 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T14:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/ETHUSDT_180.csv | True | 286 | 2026-03-14T00:56:59.999000+00:00 -> 2026-03-14T15:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/ETHUSDT_300.csv | True | 170 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T15:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/ETHUSDT_900.csv | True | 57 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T14:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/SOLUSDT_180.csv | True | 286 | 2026-03-14T00:56:59.999000+00:00 -> 2026-03-14T15:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/SOLUSDT_300.csv | True | 170 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T15:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/SOLUSDT_900.csv | True | 57 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T14:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/XRPUSDT_180.csv | True | 286 | 2026-03-14T00:56:59.999000+00:00 -> 2026-03-14T15:17:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/XRPUSDT_300.csv | True | 170 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T15:04:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-14/XRPUSDT_900.csv | True | 57 | 2026-03-14T00:59:59.999000+00:00 -> 2026-03-14T14:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/1000PEPEUSDT_180.csv | True | 419 | 2026-03-15T00:23:59.999000+00:00 -> 2026-03-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/1000PEPEUSDT_300.csv | True | 251 | 2026-03-15T00:24:59.999000+00:00 -> 2026-03-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/1000PEPEUSDT_900.csv | True | 83 | 2026-03-15T00:29:59.999000+00:00 -> 2026-03-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/BNBUSDT_180.csv | True | 419 | 2026-03-15T00:23:59.999000+00:00 -> 2026-03-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/BNBUSDT_300.csv | True | 251 | 2026-03-15T00:24:59.999000+00:00 -> 2026-03-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/BNBUSDT_900.csv | True | 83 | 2026-03-15T00:29:59.999000+00:00 -> 2026-03-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/BTCUSDT_180.csv | True | 419 | 2026-03-15T00:23:59.999000+00:00 -> 2026-03-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/BTCUSDT_300.csv | True | 251 | 2026-03-15T00:24:59.999000+00:00 -> 2026-03-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/BTCUSDT_900.csv | True | 83 | 2026-03-15T00:29:59.999000+00:00 -> 2026-03-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/DOGEUSDT_180.csv | True | 419 | 2026-03-15T00:23:59.999000+00:00 -> 2026-03-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/DOGEUSDT_300.csv | True | 251 | 2026-03-15T00:24:59.999000+00:00 -> 2026-03-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/DOGEUSDT_900.csv | True | 83 | 2026-03-15T00:29:59.999000+00:00 -> 2026-03-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/ETHUSDT_180.csv | True | 419 | 2026-03-15T00:23:59.999000+00:00 -> 2026-03-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/ETHUSDT_300.csv | True | 251 | 2026-03-15T00:24:59.999000+00:00 -> 2026-03-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/ETHUSDT_900.csv | True | 83 | 2026-03-15T00:29:59.999000+00:00 -> 2026-03-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/SOLUSDT_180.csv | True | 419 | 2026-03-15T00:23:59.999000+00:00 -> 2026-03-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/SOLUSDT_300.csv | True | 251 | 2026-03-15T00:24:59.999000+00:00 -> 2026-03-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/SOLUSDT_900.csv | True | 83 | 2026-03-15T00:29:59.999000+00:00 -> 2026-03-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/XRPUSDT_180.csv | True | 419 | 2026-03-15T00:23:59.999000+00:00 -> 2026-03-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/XRPUSDT_300.csv | True | 251 | 2026-03-15T00:24:59.999000+00:00 -> 2026-03-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-15/XRPUSDT_900.csv | True | 83 | 2026-03-15T00:29:59.999000+00:00 -> 2026-03-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/1000PEPEUSDT_180.csv | True | 348 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/1000PEPEUSDT_300.csv | True | 207 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/1000PEPEUSDT_900.csv | True | 69 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/BNBUSDT_180.csv | True | 348 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/BNBUSDT_300.csv | True | 208 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/BNBUSDT_900.csv | True | 197 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/BTCUSDT_180.csv | True | 348 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/BTCUSDT_300.csv | True | 765 | 1970-01-01T00:00:00+00:00 -> 2026-03-16T20:04:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-16/BTCUSDT_900.csv | True | 69 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/DOGEUSDT_180.csv | True | 348 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/DOGEUSDT_300.csv | True | 810 | 2026-03-15T15:24:59.999000+00:00 -> 2026-03-16T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/DOGEUSDT_900.csv | True | 69 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/ETHUSDT_180.csv | True | 348 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/ETHUSDT_300.csv | True | 765 | 1970-01-01T00:00:00+00:00 -> 2026-03-16T20:04:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-16/ETHUSDT_900.csv | True | 69 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/SOLUSDT_180.csv | True | 348 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/SOLUSDT_300.csv | True | 765 | 1970-01-01T00:00:00+00:00 -> 2026-03-16T20:04:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-16/SOLUSDT_900.csv | True | 69 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/XRPUSDT_180.csv | True | 347 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/XRPUSDT_300.csv | True | 208 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-16/XRPUSDT_900.csv | True | 197 | 2026-03-15T23:59:59.999000+00:00 -> 2026-03-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/1000PEPEUSDT_180.csv | True | 250 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/1000PEPEUSDT_300.csv | True | 150 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/1000PEPEUSDT_900.csv | True | 50 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/BNBUSDT_180.csv | True | 250 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/BNBUSDT_300.csv | True | 150 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/BNBUSDT_900.csv | True | 210 | 2026-03-16T11:14:59.999000+00:00 -> 2026-03-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/BTCUSDT_180.csv | True | 250 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/BTCUSDT_300.csv | True | 752 | 1970-01-01T00:00:00+00:00 -> 2026-03-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/BTCUSDT_900.csv | True | 50 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/DOGEUSDT_180.csv | True | 250 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/DOGEUSDT_300.csv | True | 752 | 2026-03-16T01:59:59.999000+00:00 -> 2026-03-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/DOGEUSDT_900.csv | True | 50 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/ETHUSDT_180.csv | True | 250 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/ETHUSDT_300.csv | True | 752 | 1970-01-01T00:00:00.500000+00:00 -> 2026-03-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/ETHUSDT_900.csv | True | 50 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/SOLUSDT_180.csv | True | 250 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/SOLUSDT_300.csv | True | 752 | 1970-01-01T00:00:00+00:00 -> 2026-03-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/SOLUSDT_900.csv | True | 50 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/XRPUSDT_180.csv | True | 250 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/XRPUSDT_300.csv | True | 150 | 2026-03-16T23:59:59.999000+00:00 -> 2026-03-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-17/XRPUSDT_900.csv | True | 210 | 2026-03-16T11:14:59.999000+00:00 -> 2026-03-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/1000PEPEUSDT_180.csv | True | 432 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/1000PEPEUSDT_300.csv | True | 259 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/1000PEPEUSDT_900.csv | True | 86 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/BNBUSDT_180.csv | True | 432 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/BNBUSDT_300.csv | True | 259 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/BNBUSDT_900.csv | True | 133 | 1970-01-01T00:15:00+00:00 -> 2026-03-18T10:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-18/BTCUSDT_180.csv | True | 432 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/BTCUSDT_300.csv | True | 1162 | 1970-01-01T00:00:00+00:00 -> 2026-03-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/BTCUSDT_900.csv | True | 86 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/DOGEUSDT_180.csv | True | 432 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/DOGEUSDT_300.csv | True | 1162 | 2026-03-17T07:29:59.999000+00:00 -> 2026-03-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/DOGEUSDT_900.csv | True | 86 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/ETHUSDT_180.csv | True | 432 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/ETHUSDT_300.csv | True | 1162 | 1970-01-01T00:00:00+00:00 -> 2026-03-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/ETHUSDT_900.csv | True | 86 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/SOLUSDT_180.csv | True | 432 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/SOLUSDT_300.csv | True | 1162 | 1970-01-01T00:00:00+00:00 -> 2026-03-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/SOLUSDT_900.csv | True | 86 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/XRPUSDT_180.csv | True | 432 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/XRPUSDT_300.csv | True | 259 | 2026-03-17T23:59:59.999000+00:00 -> 2026-03-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-18/XRPUSDT_900.csv | True | 134 | 1970-01-01T00:15:00+00:00 -> 2026-03-18T10:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-19/1000PEPEUSDT_180.csv | True | 371 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/1000PEPEUSDT_300.csv | True | 223 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/1000PEPEUSDT_900.csv | True | 75 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/BNBUSDT_180.csv | True | 371 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/BNBUSDT_300.csv | True | 223 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/BNBUSDT_900.csv | True | 18 | 1970-01-01T00:15:00+00:00 -> 2026-03-19T03:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-19/BTCUSDT_180.csv | True | 371 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/BTCUSDT_300.csv | True | 1125 | 1970-01-01T00:00:00+00:00 -> 2026-03-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/BTCUSDT_900.csv | True | 75 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/DOGEUSDT_180.csv | True | 371 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/DOGEUSDT_300.csv | True | 1126 | 2026-03-18T15:54:59.999000+00:00 -> 2026-03-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/DOGEUSDT_900.csv | True | 75 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/ETHUSDT_180.csv | True | 371 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/ETHUSDT_300.csv | True | 1126 | 1970-01-01T00:00:00+00:00 -> 2026-03-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/ETHUSDT_900.csv | True | 75 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/SOLUSDT_180.csv | True | 371 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/SOLUSDT_300.csv | True | 1126 | 1970-01-01T00:00:00+00:00 -> 2026-03-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/SOLUSDT_900.csv | True | 75 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/XRPUSDT_180.csv | True | 371 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/XRPUSDT_300.csv | True | 223 | 2026-03-18T23:59:59.999000+00:00 -> 2026-03-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-19/XRPUSDT_900.csv | True | 8 | 1970-01-01T00:15:00+00:00 -> 2026-03-19T01:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-20/1000PEPEUSDT_180.csv | True | 477 | 2026-03-20T00:02:59.999000+00:00 -> 2026-03-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/1000PEPEUSDT_300.csv | True | 286 | 2026-03-20T00:04:59.999000+00:00 -> 2026-03-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/1000PEPEUSDT_900.csv | True | 94 | 2026-03-20T00:14:59.999000+00:00 -> 2026-03-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/BNBUSDT_180.csv | True | 477 | 2026-03-20T00:02:59.999000+00:00 -> 2026-03-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/BNBUSDT_300.csv | True | 286 | 2026-03-20T00:04:59.999000+00:00 -> 2026-03-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/BNBUSDT_900.csv | True | 110 | 1970-01-01T00:15:00+00:00 -> 2026-03-20T03:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-20/BTCUSDT_180.csv | True | 477 | 2026-03-20T00:02:59.999000+00:00 -> 2026-03-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/BTCUSDT_300.csv | True | 302 | 1970-01-01T00:00:00+00:00 -> 2026-03-19T23:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-20/BTCUSDT_900.csv | True | 94 | 2026-03-20T00:14:59.999000+00:00 -> 2026-03-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/DOGEUSDT_180.csv | True | 477 | 2026-03-20T00:02:59.999000+00:00 -> 2026-03-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/DOGEUSDT_300.csv | True | 888 | 2026-03-18T22:59:59.999000+00:00 -> 2026-03-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/DOGEUSDT_900.csv | True | 94 | 2026-03-20T00:14:59.999000+00:00 -> 2026-03-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/ETHUSDT_180.csv | True | 477 | 2026-03-20T00:02:59.999000+00:00 -> 2026-03-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/ETHUSDT_300.csv | True | 302 | 1970-01-01T00:00:00+00:00 -> 2026-03-19T23:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-20/ETHUSDT_900.csv | True | 94 | 2026-03-20T00:14:59.999000+00:00 -> 2026-03-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/SOLUSDT_180.csv | True | 477 | 2026-03-20T00:02:59.999000+00:00 -> 2026-03-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/SOLUSDT_300.csv | True | 302 | 1970-01-01T00:00:00+00:00 -> 2026-03-19T23:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-20/SOLUSDT_900.csv | True | 94 | 2026-03-20T00:14:59.999000+00:00 -> 2026-03-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/XRPUSDT_180.csv | True | 477 | 2026-03-20T00:02:59.999000+00:00 -> 2026-03-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/XRPUSDT_300.csv | True | 286 | 2026-03-20T00:04:59.999000+00:00 -> 2026-03-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-20/XRPUSDT_900.csv | True | 104 | 1970-01-01T00:15:00+00:00 -> 2026-03-20T01:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-21/1000PEPEUSDT_180.csv | True | 466 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/1000PEPEUSDT_300.csv | True | 281 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/1000PEPEUSDT_900.csv | True | 93 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/BNBUSDT_180.csv | True | 466 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/BNBUSDT_300.csv | True | 281 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/BNBUSDT_900.csv | True | 7 | 1970-01-01T00:15:00+00:00 -> 2026-03-21T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-21/BTCUSDT_180.csv | True | 466 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/BTCUSDT_300.csv | True | 883 | 1970-01-01T00:00:00+00:00 -> 2026-03-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/BTCUSDT_900.csv | True | 93 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/DOGEUSDT_180.csv | True | 466 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/DOGEUSDT_300.csv | True | 883 | 2026-03-20T18:29:59.999000+00:00 -> 2026-03-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/DOGEUSDT_900.csv | True | 93 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/ETHUSDT_180.csv | True | 466 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/ETHUSDT_300.csv | True | 883 | 1970-01-01T00:00:00.500000+00:00 -> 2026-03-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/ETHUSDT_900.csv | True | 93 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/SOLUSDT_180.csv | True | 466 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/SOLUSDT_300.csv | True | 883 | 1970-01-01T00:00:00+00:00 -> 2026-03-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/SOLUSDT_900.csv | True | 93 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/XRPUSDT_180.csv | True | 466 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/XRPUSDT_300.csv | True | 281 | 2026-03-20T23:59:59.999000+00:00 -> 2026-03-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-21/XRPUSDT_900.csv | True | 24 | 1970-01-01T00:15:00+00:00 -> 2026-03-21T05:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-22/1000PEPEUSDT_180.csv | True | 480 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/1000PEPEUSDT_300.csv | True | 288 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/1000PEPEUSDT_900.csv | True | 96 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/BNBUSDT_180.csv | True | 480 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/BNBUSDT_300.csv | True | 288 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/BNBUSDT_900.csv | True | 26 | 1970-01-01T00:15:00+00:00 -> 2026-03-22T05:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-22/BTCUSDT_180.csv | True | 480 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/BTCUSDT_300.csv | True | 288 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/BTCUSDT_900.csv | True | 96 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/DOGEUSDT_180.csv | True | 480 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/DOGEUSDT_300.csv | True | 288 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/DOGEUSDT_900.csv | True | 96 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/ETHUSDT_180.csv | True | 480 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/ETHUSDT_300.csv | True | 288 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/ETHUSDT_900.csv | True | 96 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/SOLUSDT_180.csv | True | 480 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/SOLUSDT_300.csv | True | 288 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/SOLUSDT_900.csv | True | 96 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/XRPUSDT_180.csv | True | 480 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/XRPUSDT_300.csv | True | 288 | 2026-03-21T23:59:59.999000+00:00 -> 2026-03-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-22/XRPUSDT_900.csv | True | 24 | 1970-01-01T00:15:00+00:00 -> 2026-03-22T05:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-23/1000PEPEUSDT_180.csv | True | 480 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/1000PEPEUSDT_300.csv | True | 288 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/1000PEPEUSDT_900.csv | True | 96 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/BNBUSDT_180.csv | True | 480 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/BNBUSDT_300.csv | True | 288 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/BNBUSDT_900.csv | True | 4 | 1970-01-01T00:15:00+00:00 -> 2026-03-23T00:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-23/BTCUSDT_180.csv | True | 480 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/BTCUSDT_300.csv | True | 288 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/BTCUSDT_900.csv | True | 96 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/DOGEUSDT_180.csv | True | 480 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/DOGEUSDT_300.csv | True | 288 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/DOGEUSDT_900.csv | True | 96 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/ETHUSDT_180.csv | True | 480 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/ETHUSDT_300.csv | True | 288 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/ETHUSDT_900.csv | True | 96 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/SOLUSDT_180.csv | True | 480 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/SOLUSDT_300.csv | True | 288 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/SOLUSDT_900.csv | True | 96 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/XRPUSDT_180.csv | True | 480 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/XRPUSDT_300.csv | True | 288 | 2026-03-22T23:59:59.999000+00:00 -> 2026-03-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-23/XRPUSDT_900.csv | True | 5 | 1970-01-01T00:15:00+00:00 -> 2026-03-23T00:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-24/1000PEPEUSDT_180.csv | True | 428 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:20:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/1000PEPEUSDT_300.csv | True | 257 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/1000PEPEUSDT_900.csv | True | 86 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:14:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/BNBUSDT_180.csv | True | 428 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:20:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/BNBUSDT_300.csv | True | 257 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/BNBUSDT_900.csv | True | 4 | 1970-01-01T00:15:00+00:00 -> 2026-03-24T00:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-24/BTCUSDT_180.csv | True | 428 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:20:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/BTCUSDT_300.csv | True | 257 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/BTCUSDT_900.csv | True | 86 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:14:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/DOGEUSDT_180.csv | True | 428 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:20:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/DOGEUSDT_300.csv | True | 257 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/DOGEUSDT_900.csv | True | 86 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:14:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/ETHUSDT_180.csv | True | 428 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:20:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/ETHUSDT_300.csv | True | 257 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/ETHUSDT_900.csv | True | 86 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:14:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/SOLUSDT_180.csv | True | 428 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:20:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/SOLUSDT_300.csv | True | 257 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/SOLUSDT_900.csv | True | 86 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:14:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/XRPUSDT_180.csv | True | 428 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:20:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/XRPUSDT_300.csv | True | 257 | 2026-03-23T23:59:59.999000+00:00 -> 2026-03-24T21:19:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-24/XRPUSDT_900.csv | True | 3 | 1970-01-01T00:15:00+00:00 -> 2026-03-24T00:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-25/1000PEPEUSDT_180.csv | True | 349 | 2026-03-25T06:32:59.999000+00:00 -> 2026-03-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/1000PEPEUSDT_300.csv | True | 209 | 2026-03-25T06:34:59.999000+00:00 -> 2026-03-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/1000PEPEUSDT_900.csv | True | 69 | 2026-03-25T06:44:59.999000+00:00 -> 2026-03-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/BNBUSDT_180.csv | True | 349 | 2026-03-25T06:32:59.999000+00:00 -> 2026-03-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/BNBUSDT_300.csv | True | 209 | 2026-03-25T06:34:59.999000+00:00 -> 2026-03-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/BNBUSDT_900.csv | True | 105 | 1970-01-01T00:15:00+00:00 -> 2026-03-25T08:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-25/BTCUSDT_180.csv | True | 349 | 2026-03-25T06:32:59.999000+00:00 -> 2026-03-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/BTCUSDT_300.csv | True | 302 | 1970-01-01T00:00:00+00:00 -> 2026-03-25T06:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-25/BTCUSDT_900.csv | True | 69 | 2026-03-25T06:44:59.999000+00:00 -> 2026-03-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/DOGEUSDT_180.csv | True | 349 | 2026-03-25T06:32:59.999000+00:00 -> 2026-03-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/DOGEUSDT_300.csv | True | 510 | 2026-03-24T05:29:59.999000+00:00 -> 2026-03-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/DOGEUSDT_900.csv | True | 69 | 2026-03-25T06:44:59.999000+00:00 -> 2026-03-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/ETHUSDT_180.csv | True | 349 | 2026-03-25T06:32:59.999000+00:00 -> 2026-03-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/ETHUSDT_300.csv | True | 302 | 1970-01-01T00:00:00+00:00 -> 2026-03-25T06:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-25/ETHUSDT_900.csv | True | 69 | 2026-03-25T06:44:59.999000+00:00 -> 2026-03-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/SOLUSDT_180.csv | True | 349 | 2026-03-25T06:32:59.999000+00:00 -> 2026-03-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/SOLUSDT_300.csv | True | 302 | 1970-01-01T00:00:00+00:00 -> 2026-03-25T06:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-25/SOLUSDT_900.csv | True | 69 | 2026-03-25T06:44:59.999000+00:00 -> 2026-03-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/XRPUSDT_180.csv | True | 349 | 2026-03-25T06:32:59.999000+00:00 -> 2026-03-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/XRPUSDT_300.csv | True | 209 | 2026-03-25T06:34:59.999000+00:00 -> 2026-03-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-25/XRPUSDT_900.csv | True | 115 | 1970-01-01T00:15:00+00:00 -> 2026-03-25T10:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-26/1000PEPEUSDT_180.csv | True | 480 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/1000PEPEUSDT_300.csv | True | 288 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/1000PEPEUSDT_900.csv | True | 96 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/BNBUSDT_180.csv | True | 480 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/BNBUSDT_300.csv | True | 288 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/BNBUSDT_900.csv | True | 10 | 1970-01-01T00:15:00+00:00 -> 2026-03-26T01:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-26/BTCUSDT_180.csv | True | 480 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/BTCUSDT_300.csv | True | 288 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/BTCUSDT_900.csv | True | 96 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/DOGEUSDT_180.csv | True | 480 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/DOGEUSDT_300.csv | True | 288 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/DOGEUSDT_900.csv | True | 96 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/ETHUSDT_180.csv | True | 480 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/ETHUSDT_300.csv | True | 288 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/ETHUSDT_900.csv | True | 96 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/SOLUSDT_180.csv | True | 480 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/SOLUSDT_300.csv | True | 288 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/SOLUSDT_900.csv | True | 96 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/XRPUSDT_180.csv | True | 480 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/XRPUSDT_300.csv | True | 288 | 2026-03-25T23:59:59.999000+00:00 -> 2026-03-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-26/XRPUSDT_900.csv | True | 8 | 1970-01-01T00:15:00+00:00 -> 2026-03-26T01:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-27/1000PEPEUSDT_180.csv | True | 440 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/1000PEPEUSDT_300.csv | True | 263 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/1000PEPEUSDT_900.csv | True | 88 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/BNBUSDT_180.csv | True | 440 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/BNBUSDT_300.csv | True | 263 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/BNBUSDT_900.csv | True | 7 | 1970-01-01T00:15:00+00:00 -> 2026-03-27T01:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-27/BTCUSDT_180.csv | True | 440 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/BTCUSDT_300.csv | True | 564 | 1970-01-01T00:00:00.500000+00:00 -> 2026-03-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/BTCUSDT_900.csv | True | 88 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/DOGEUSDT_180.csv | True | 440 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/DOGEUSDT_300.csv | True | 564 | 2026-03-26T04:59:59.999000+00:00 -> 2026-03-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/DOGEUSDT_900.csv | True | 88 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/ETHUSDT_180.csv | True | 440 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/ETHUSDT_300.csv | True | 565 | 1970-01-01T00:00:00+00:00 -> 2026-03-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/ETHUSDT_900.csv | True | 88 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/SOLUSDT_180.csv | True | 440 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/SOLUSDT_300.csv | True | 565 | 1970-01-01T00:00:00.500000+00:00 -> 2026-03-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/SOLUSDT_900.csv | True | 88 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/XRPUSDT_180.csv | True | 440 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/XRPUSDT_300.csv | True | 263 | 2026-03-26T23:59:59.999000+00:00 -> 2026-03-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-27/XRPUSDT_900.csv | True | 6 | 1970-01-01T00:15:00+00:00 -> 2026-03-27T00:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-28/1000PEPEUSDT_180.csv | True | 480 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/1000PEPEUSDT_300.csv | True | 288 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/1000PEPEUSDT_900.csv | True | 96 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/BNBUSDT_180.csv | True | 480 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/BNBUSDT_300.csv | True | 288 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/BNBUSDT_900.csv | True | 96 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/BTCUSDT_180.csv | True | 480 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/BTCUSDT_300.csv | True | 288 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/BTCUSDT_900.csv | True | 96 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/DOGEUSDT_180.csv | True | 480 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/DOGEUSDT_300.csv | True | 288 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/DOGEUSDT_900.csv | True | 96 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/ETHUSDT_180.csv | True | 480 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/ETHUSDT_300.csv | True | 288 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/ETHUSDT_900.csv | True | 96 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/SOLUSDT_180.csv | True | 480 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/SOLUSDT_300.csv | True | 288 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/SOLUSDT_900.csv | True | 96 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/XRPUSDT_180.csv | True | 480 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/XRPUSDT_300.csv | True | 288 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-28/XRPUSDT_900.csv | True | 96 | 2026-03-27T23:59:59.999000+00:00 -> 2026-03-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/1000PEPEUSDT_180.csv | True | 178 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/1000PEPEUSDT_300.csv | True | 107 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/1000PEPEUSDT_900.csv | True | 36 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/BNBUSDT_180.csv | True | 178 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/BNBUSDT_300.csv | True | 107 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/BNBUSDT_900.csv | True | 324 | 2026-03-28T09:44:59.999000+00:00 -> 2026-03-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/BTCUSDT_180.csv | True | 178 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/BTCUSDT_300.csv | True | 2495 | 1970-01-01T00:00:00+00:00 -> 2026-03-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/BTCUSDT_900.csv | True | 36 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/DOGEUSDT_180.csv | True | 178 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/DOGEUSDT_300.csv | True | 961 | 2026-03-28T08:19:59.999000+00:00 -> 2026-03-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/DOGEUSDT_900.csv | True | 36 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/ETHUSDT_180.csv | True | 178 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/ETHUSDT_300.csv | True | 2096 | 1970-01-01T00:00:00+00:00 -> 2026-03-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/ETHUSDT_900.csv | True | 36 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/SOLUSDT_180.csv | True | 178 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/SOLUSDT_300.csv | True | 1913 | 1970-01-01T00:00:00+00:00 -> 2026-03-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/SOLUSDT_900.csv | True | 36 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/XRPUSDT_180.csv | True | 178 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/XRPUSDT_300.csv | True | 107 | 2026-03-28T23:59:59.999000+00:00 -> 2026-03-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-29/XRPUSDT_900.csv | True | 228 | 2026-03-28T09:44:59.999000+00:00 -> 2026-03-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/1000PEPEUSDT_180.csv | True | 479 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/1000PEPEUSDT_300.csv | True | 288 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/1000PEPEUSDT_900.csv | True | 96 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/BNBUSDT_180.csv | True | 479 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/BNBUSDT_300.csv | True | 288 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/BNBUSDT_900.csv | True | 96 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/BTCUSDT_180.csv | True | 479 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/BTCUSDT_300.csv | True | 589 | 1970-01-01T00:00:00+00:00 -> 2026-03-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/BTCUSDT_900.csv | True | 96 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/DOGEUSDT_180.csv | True | 479 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/DOGEUSDT_300.csv | True | 589 | 2026-03-29T15:34:59.999000+00:00 -> 2026-03-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/DOGEUSDT_900.csv | True | 96 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/ETHUSDT_180.csv | True | 479 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/ETHUSDT_300.csv | True | 589 | 1970-01-01T00:00:00.500000+00:00 -> 2026-03-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/ETHUSDT_900.csv | True | 96 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/SOLUSDT_180.csv | True | 479 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/SOLUSDT_300.csv | True | 589 | 1970-01-01T00:00:00+00:00 -> 2026-03-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/SOLUSDT_900.csv | True | 96 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/XRPUSDT_180.csv | True | 479 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/XRPUSDT_300.csv | True | 288 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-30/XRPUSDT_900.csv | True | 96 | 2026-03-29T23:59:59.999000+00:00 -> 2026-03-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/1000PEPEUSDT_180.csv | True | 480 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/1000PEPEUSDT_300.csv | True | 288 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/1000PEPEUSDT_900.csv | True | 96 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/BNBUSDT_180.csv | True | 480 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/BNBUSDT_300.csv | True | 214 | 1970-01-01T00:00:00+00:00 -> 2026-03-31T17:39:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-31/BNBUSDT_900.csv | True | 96 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/BTCUSDT_180.csv | True | 480 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/BTCUSDT_300.csv | True | 288 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/BTCUSDT_900.csv | True | 96 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/DOGEUSDT_180.csv | True | 480 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/DOGEUSDT_300.csv | True | 288 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/DOGEUSDT_900.csv | True | 96 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/ETHUSDT_180.csv | True | 480 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/ETHUSDT_300.csv | True | 288 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/ETHUSDT_900.csv | True | 96 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/SOLUSDT_180.csv | True | 480 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/SOLUSDT_300.csv | True | 288 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/SOLUSDT_900.csv | True | 96 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/XRPUSDT_180.csv | True | 480 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-03-31/XRPUSDT_300.csv | True | 214 | 1970-01-01T00:00:00+00:00 -> 2026-03-31T17:39:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-03-31/XRPUSDT_900.csv | True | 96 | 2026-03-30T23:59:59.999000+00:00 -> 2026-03-31T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/1000PEPEUSDT_180.csv | True | 174 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/1000PEPEUSDT_300.csv | True | 104 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/1000PEPEUSDT_900.csv | True | 35 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/BNBUSDT_180.csv | True | 174 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/BNBUSDT_300.csv | True | 104 | 1970-01-01T00:00:00.111000+00:00 -> 2026-04-01T07:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/BNBUSDT_900.csv | True | 35 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/BTCUSDT_180.csv | True | 174 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/BTCUSDT_300.csv | True | 405 | 1970-01-01T00:00:00+00:00 -> 2026-04-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/BTCUSDT_900.csv | True | 35 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/DOGEUSDT_180.csv | True | 174 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/DOGEUSDT_300.csv | True | 405 | 2026-03-31T21:54:59.999000+00:00 -> 2026-04-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/DOGEUSDT_900.csv | True | 35 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/ETHUSDT_180.csv | True | 174 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/ETHUSDT_300.csv | True | 405 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/ETHUSDT_900.csv | True | 35 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/SOLUSDT_180.csv | True | 174 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/SOLUSDT_300.csv | True | 405 | 1970-01-01T00:00:00+00:00 -> 2026-04-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/SOLUSDT_900.csv | True | 35 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/XRPUSDT_180.csv | True | 174 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/XRPUSDT_300.csv | True | 104 | 1970-01-01T00:00:00.166000+00:00 -> 2026-04-01T07:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-01/XRPUSDT_900.csv | True | 35 | 2026-03-31T23:59:59.999000+00:00 -> 2026-04-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/1000PEPEUSDT_180.csv | True | 480 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/1000PEPEUSDT_300.csv | True | 288 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/1000PEPEUSDT_900.csv | True | 96 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/BNBUSDT_180.csv | True | 480 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/BNBUSDT_300.csv | True | 288 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/BNBUSDT_900.csv | True | 96 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/BTCUSDT_180.csv | True | 480 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/BTCUSDT_300.csv | True | 288 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/BTCUSDT_900.csv | True | 96 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/DOGEUSDT_180.csv | True | 480 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/DOGEUSDT_300.csv | True | 288 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/DOGEUSDT_900.csv | True | 96 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/ETHUSDT_180.csv | True | 480 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/ETHUSDT_300.csv | True | 288 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/ETHUSDT_900.csv | True | 96 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/SOLUSDT_180.csv | True | 480 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/SOLUSDT_300.csv | True | 288 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/SOLUSDT_900.csv | True | 96 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/XRPUSDT_180.csv | True | 480 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/XRPUSDT_300.csv | True | 288 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-02/XRPUSDT_900.csv | True | 96 | 2026-04-01T23:59:59.999000+00:00 -> 2026-04-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-03/1000PEPEUSDT_180.csv | True | 263 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:35:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/1000PEPEUSDT_300.csv | True | 158 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:34:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/1000PEPEUSDT_900.csv | True | 53 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/BNBUSDT_180.csv | True | 263 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:35:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/BNBUSDT_300.csv | True | 158 | 1970-01-01T00:00:00.033000+00:00 -> 2026-04-03T09:09:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/BNBUSDT_900.csv | True | 53 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/BTCUSDT_180.csv | True | 263 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:35:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/BTCUSDT_300.csv | True | 459 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-03T14:34:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/BTCUSDT_900.csv | True | 53 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/DOGEUSDT_180.csv | True | 263 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:35:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/DOGEUSDT_300.csv | True | 459 | 2026-04-02T09:49:59.999000+00:00 -> 2026-04-03T14:34:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/DOGEUSDT_900.csv | True | 53 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/ETHUSDT_180.csv | True | 263 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:35:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/ETHUSDT_300.csv | True | 459 | 1970-01-01T00:00:00+00:00 -> 2026-04-03T14:34:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/ETHUSDT_900.csv | True | 53 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/SOLUSDT_180.csv | True | 263 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:35:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/SOLUSDT_300.csv | True | 459 | 1970-01-01T00:00:00+00:00 -> 2026-04-03T14:34:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/SOLUSDT_900.csv | True | 53 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/XRPUSDT_180.csv | True | 263 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:35:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/XRPUSDT_300.csv | True | 158 | 1970-01-01T00:00:00.066000+00:00 -> 2026-04-03T09:09:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-03/XRPUSDT_900.csv | True | 53 | 2026-04-02T23:59:59.999000+00:00 -> 2026-04-03T14:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-04/1000PEPEUSDT_180.csv | True | 465 | 2026-04-04T00:41:59.999000+00:00 -> 2026-04-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/1000PEPEUSDT_300.csv | True | 279 | 2026-04-04T00:39:59.999000+00:00 -> 2026-04-04T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/1000PEPEUSDT_900.csv | True | 92 | 2026-04-04T00:44:59.999000+00:00 -> 2026-04-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/BNBUSDT_180.csv | True | 465 | 2026-04-04T00:41:59.999000+00:00 -> 2026-04-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/BNBUSDT_300.csv | True | 279 | 2026-04-04T00:39:59.999000+00:00 -> 2026-04-04T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/BNBUSDT_900.csv | True | 92 | 2026-04-04T00:44:59.999000+00:00 -> 2026-04-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/BTCUSDT_180.csv | True | 465 | 2026-04-04T00:41:59.999000+00:00 -> 2026-04-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/BTCUSDT_300.csv | True | 302 | 2026-04-02T23:39:59.999000+00:00 -> 2026-04-04T00:39:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-04/BTCUSDT_900.csv | True | 92 | 2026-04-04T00:44:59.999000+00:00 -> 2026-04-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/DOGEUSDT_180.csv | True | 465 | 2026-04-04T00:41:59.999000+00:00 -> 2026-04-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/DOGEUSDT_300.csv | True | 881 | 2026-04-02T23:39:59.999000+00:00 -> 2026-04-04T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/DOGEUSDT_900.csv | True | 92 | 2026-04-04T00:44:59.999000+00:00 -> 2026-04-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/ETHUSDT_180.csv | True | 465 | 2026-04-04T00:41:59.999000+00:00 -> 2026-04-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/ETHUSDT_300.csv | True | 303 | 2026-04-02T23:39:59.999000+00:00 -> 2026-04-04T00:39:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-04/ETHUSDT_900.csv | True | 92 | 2026-04-04T00:44:59.999000+00:00 -> 2026-04-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/SOLUSDT_180.csv | True | 465 | 2026-04-04T00:41:59.999000+00:00 -> 2026-04-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/SOLUSDT_300.csv | True | 302 | 2026-04-02T23:39:59.999000+00:00 -> 2026-04-04T00:39:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-04/SOLUSDT_900.csv | True | 92 | 2026-04-04T00:44:59.999000+00:00 -> 2026-04-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/XRPUSDT_180.csv | True | 465 | 2026-04-04T00:41:59.999000+00:00 -> 2026-04-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/XRPUSDT_300.csv | True | 279 | 2026-04-04T00:39:59.999000+00:00 -> 2026-04-04T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-04/XRPUSDT_900.csv | True | 92 | 2026-04-04T00:44:59.999000+00:00 -> 2026-04-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/1000PEPEUSDT_180.csv | True | 212 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/1000PEPEUSDT_300.csv | True | 128 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/1000PEPEUSDT_900.csv | True | 42 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/BNBUSDT_180.csv | True | 212 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/BNBUSDT_300.csv | True | 128 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/BNBUSDT_900.csv | True | 42 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/BTCUSDT_180.csv | True | 212 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/BTCUSDT_300.csv | True | 730 | 1970-01-01T00:00:00+00:00 -> 2026-04-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/BTCUSDT_900.csv | True | 42 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/DOGEUSDT_180.csv | True | 212 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/DOGEUSDT_300.csv | True | 730 | 2026-04-04T13:49:59.999000+00:00 -> 2026-04-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/DOGEUSDT_900.csv | True | 42 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/ETHUSDT_180.csv | True | 212 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/ETHUSDT_300.csv | True | 730 | 1970-01-01T00:00:00+00:00 -> 2026-04-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/ETHUSDT_900.csv | True | 42 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/SOLUSDT_180.csv | True | 212 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/SOLUSDT_300.csv | True | 730 | 1970-01-01T00:00:00+00:00 -> 2026-04-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/SOLUSDT_900.csv | True | 42 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/XRPUSDT_180.csv | True | 212 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/XRPUSDT_300.csv | True | 128 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-05/XRPUSDT_900.csv | True | 42 | 2026-04-04T23:59:59.999000+00:00 -> 2026-04-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/1000PEPEUSDT_180.csv | True | 458 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/1000PEPEUSDT_300.csv | True | 275 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/1000PEPEUSDT_900.csv | True | 92 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/BNBUSDT_180.csv | True | 458 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/BNBUSDT_300.csv | True | 275 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/BNBUSDT_900.csv | True | 92 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/BTCUSDT_180.csv | True | 458 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/BTCUSDT_300.csv | True | 877 | 1970-01-01T00:00:00+00:00 -> 2026-04-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/BTCUSDT_900.csv | True | 92 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/DOGEUSDT_180.csv | True | 458 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/DOGEUSDT_300.csv | True | 877 | 2026-04-05T07:54:59.999000+00:00 -> 2026-04-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/DOGEUSDT_900.csv | True | 92 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/ETHUSDT_180.csv | True | 458 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/ETHUSDT_300.csv | True | 877 | 1970-01-01T00:00:00+00:00 -> 2026-04-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/ETHUSDT_900.csv | True | 92 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/SOLUSDT_180.csv | True | 458 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/SOLUSDT_300.csv | True | 877 | 1970-01-01T00:00:00+00:00 -> 2026-04-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/SOLUSDT_900.csv | True | 92 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/XRPUSDT_180.csv | True | 458 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/XRPUSDT_300.csv | True | 275 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-06/XRPUSDT_900.csv | True | 92 | 2026-04-05T23:59:59.999000+00:00 -> 2026-04-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/1000PEPEUSDT_180.csv | True | 470 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/1000PEPEUSDT_300.csv | True | 282 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/1000PEPEUSDT_900.csv | True | 94 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/BNBUSDT_180.csv | True | 470 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/BNBUSDT_300.csv | True | 282 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/BNBUSDT_900.csv | True | 94 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/BTCUSDT_180.csv | True | 470 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/BTCUSDT_300.csv | True | 583 | 1970-01-01T00:00:00+00:00 -> 2026-04-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/BTCUSDT_900.csv | True | 94 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/DOGEUSDT_180.csv | True | 470 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/DOGEUSDT_300.csv | True | 583 | 2026-04-06T06:24:59.999000+00:00 -> 2026-04-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/DOGEUSDT_900.csv | True | 94 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/ETHUSDT_180.csv | True | 470 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/ETHUSDT_300.csv | True | 583 | 1970-01-01T00:00:00+00:00 -> 2026-04-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/ETHUSDT_900.csv | True | 94 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/SOLUSDT_180.csv | True | 470 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/SOLUSDT_300.csv | True | 583 | 1970-01-01T00:00:00.111000+00:00 -> 2026-04-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/SOLUSDT_900.csv | True | 94 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/XRPUSDT_180.csv | True | 470 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/XRPUSDT_300.csv | True | 282 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-07/XRPUSDT_900.csv | True | 94 | 2026-04-06T23:59:59.999000+00:00 -> 2026-04-07T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/1000PEPEUSDT_180.csv | True | 365 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/1000PEPEUSDT_300.csv | True | 219 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/1000PEPEUSDT_900.csv | True | 73 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/BNBUSDT_180.csv | True | 365 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/BNBUSDT_300.csv | True | 219 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/BNBUSDT_900.csv | True | 73 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/BTCUSDT_180.csv | True | 365 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/BTCUSDT_300.csv | True | 821 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/BTCUSDT_900.csv | True | 73 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/DOGEUSDT_180.csv | True | 365 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/DOGEUSDT_300.csv | True | 821 | 2026-04-07T09:44:59.999000+00:00 -> 2026-04-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/DOGEUSDT_900.csv | True | 73 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/ETHUSDT_180.csv | True | 365 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/ETHUSDT_300.csv | True | 821 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/ETHUSDT_900.csv | True | 73 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/SOLUSDT_180.csv | True | 365 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/SOLUSDT_300.csv | True | 821 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/SOLUSDT_900.csv | True | 73 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/XRPUSDT_180.csv | True | 365 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/XRPUSDT_300.csv | True | 219 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-08/XRPUSDT_900.csv | True | 73 | 2026-04-07T23:59:59.999000+00:00 -> 2026-04-08T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/1000PEPEUSDT_180.csv | True | 456 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/1000PEPEUSDT_300.csv | True | 274 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/1000PEPEUSDT_900.csv | True | 91 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/BNBUSDT_180.csv | True | 456 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/BNBUSDT_300.csv | True | 274 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/BNBUSDT_900.csv | True | 91 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/BTCUSDT_180.csv | True | 456 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/BTCUSDT_300.csv | True | 575 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-09T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/BTCUSDT_900.csv | True | 91 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/DOGEUSDT_180.csv | True | 456 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/DOGEUSDT_300.csv | True | 575 | 2026-04-08T08:54:59.999000+00:00 -> 2026-04-09T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/DOGEUSDT_900.csv | True | 91 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/ETHUSDT_180.csv | True | 456 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/ETHUSDT_300.csv | True | 575 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-09T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/ETHUSDT_900.csv | True | 91 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/SOLUSDT_180.csv | True | 456 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/SOLUSDT_300.csv | True | 575 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-09T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/SOLUSDT_900.csv | True | 91 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/XRPUSDT_180.csv | True | 456 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/XRPUSDT_300.csv | True | 274 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-09/XRPUSDT_900.csv | True | 91 | 2026-04-08T23:59:59.999000+00:00 -> 2026-04-09T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/1000PEPEUSDT_180.csv | True | 397 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/1000PEPEUSDT_300.csv | True | 238 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/1000PEPEUSDT_900.csv | True | 80 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/BNBUSDT_180.csv | True | 397 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/BNBUSDT_300.csv | True | 133 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T10:54:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-10/BNBUSDT_900.csv | True | 268 | 1970-01-01T00:15:00+00:00 -> 2026-04-10T22:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-10/BTCUSDT_180.csv | True | 397 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/BTCUSDT_300.csv | True | 1140 | 1970-01-01T00:00:00+00:00 -> 2026-04-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/BTCUSDT_900.csv | True | 80 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/DOGEUSDT_180.csv | True | 397 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/DOGEUSDT_300.csv | True | 840 | 2026-04-09T16:59:59.999000+00:00 -> 2026-04-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/DOGEUSDT_900.csv | True | 80 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/ETHUSDT_180.csv | True | 397 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/ETHUSDT_300.csv | True | 840 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/ETHUSDT_900.csv | True | 80 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/SOLUSDT_180.csv | True | 397 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/SOLUSDT_300.csv | True | 840 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-10T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/SOLUSDT_900.csv | True | 80 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/XRPUSDT_180.csv | True | 397 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-10/XRPUSDT_300.csv | True | 133 | 2026-04-09T23:59:59.999000+00:00 -> 2026-04-10T10:54:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-10/XRPUSDT_900.csv | True | 267 | 1970-01-01T00:15:00+00:00 -> 2026-04-10T22:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-11/1000PEPEUSDT_180.csv | True | 386 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/1000PEPEUSDT_300.csv | True | 235 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/1000PEPEUSDT_900.csv | True | 81 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/BNBUSDT_180.csv | True | 386 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/BNBUSDT_300.csv | True | 235 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/BNBUSDT_900.csv | True | 81 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/BTCUSDT_180.csv | True | 386 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/BTCUSDT_300.csv | True | 235 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/BTCUSDT_900.csv | True | 81 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/DOGEUSDT_180.csv | True | 386 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/DOGEUSDT_300.csv | True | 235 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/DOGEUSDT_900.csv | True | 81 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/ETHUSDT_180.csv | True | 386 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/ETHUSDT_300.csv | True | 235 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/ETHUSDT_900.csv | True | 81 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/SOLUSDT_180.csv | True | 386 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/SOLUSDT_300.csv | True | 235 | 1970-01-01T00:00:00.010000+00:00 -> 2026-04-11T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/SOLUSDT_900.csv | True | 81 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/XRPUSDT_180.csv | True | 386 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/XRPUSDT_300.csv | True | 235 | 2026-04-10T23:59:59.999000+00:00 -> 2026-04-11T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-11/XRPUSDT_900.csv | True | 40 | 1970-01-01T00:15:00+00:00 -> 2026-04-11T09:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-12/1000PEPEUSDT_180.csv | True | 464 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/1000PEPEUSDT_300.csv | True | 278 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/1000PEPEUSDT_900.csv | True | 93 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/BNBUSDT_180.csv | True | 464 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/BNBUSDT_300.csv | True | 278 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/BNBUSDT_900.csv | True | 180 | 1970-01-01T00:15:00+00:00 -> 2026-04-12T21:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-12/BTCUSDT_180.csv | True | 464 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/BTCUSDT_300.csv | True | 579 | 1970-01-01T00:00:00+00:00 -> 2026-04-12T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/BTCUSDT_900.csv | True | 93 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/DOGEUSDT_180.csv | True | 464 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/DOGEUSDT_300.csv | True | 579 | 2026-04-11T17:59:59.999000+00:00 -> 2026-04-12T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/DOGEUSDT_900.csv | True | 93 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/ETHUSDT_180.csv | True | 464 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/ETHUSDT_300.csv | True | 579 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-12T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/ETHUSDT_900.csv | True | 93 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/SOLUSDT_180.csv | True | 464 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/SOLUSDT_300.csv | True | 579 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-12T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/SOLUSDT_900.csv | True | 93 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/XRPUSDT_180.csv | True | 464 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/XRPUSDT_300.csv | True | 278 | 2026-04-11T23:59:59.999000+00:00 -> 2026-04-12T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-12/XRPUSDT_900.csv | True | 178 | 1970-01-01T00:15:00+00:00 -> 2026-04-12T20:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-13/1000PEPEUSDT_180.csv | True | 480 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/1000PEPEUSDT_300.csv | True | 288 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/1000PEPEUSDT_900.csv | True | 96 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/BNBUSDT_180.csv | True | 480 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/BNBUSDT_300.csv | True | 288 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/BNBUSDT_900.csv | True | 4 | 1970-01-01T00:15:00+00:00 -> 2026-04-13T00:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-13/BTCUSDT_180.csv | True | 480 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/BTCUSDT_300.csv | True | 288 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/BTCUSDT_900.csv | True | 96 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/DOGEUSDT_180.csv | True | 480 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/DOGEUSDT_300.csv | True | 288 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/DOGEUSDT_900.csv | True | 96 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/ETHUSDT_180.csv | True | 480 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/ETHUSDT_300.csv | True | 288 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/ETHUSDT_900.csv | True | 96 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/SOLUSDT_180.csv | True | 480 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/SOLUSDT_300.csv | True | 288 | 1970-01-01T00:00:00.273000+00:00 -> 2026-04-13T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/SOLUSDT_900.csv | True | 96 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/XRPUSDT_180.csv | True | 480 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/XRPUSDT_300.csv | True | 288 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-13/XRPUSDT_900.csv | True | 96 | 2026-04-12T23:59:59.999000+00:00 -> 2026-04-13T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/1000PEPEUSDT_180.csv | True | 265 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/1000PEPEUSDT_300.csv | True | 159 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/1000PEPEUSDT_900.csv | True | 53 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/BNBUSDT_180.csv | True | 264 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/BNBUSDT_300.csv | True | 386 | 2026-04-13T16:44:59.999000+00:00 -> 2026-04-14T17:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-14/BNBUSDT_900.csv | True | 142 | 1970-01-01T00:15:00+00:00 -> 2026-04-14T21:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-14/BTCUSDT_180.csv | True | 265 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/BTCUSDT_300.csv | True | 460 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-14T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/BTCUSDT_900.csv | True | 53 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/DOGEUSDT_180.csv | True | 265 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/DOGEUSDT_300.csv | True | 387 | 2026-04-13T16:44:59.999000+00:00 -> 2026-04-14T17:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-14/DOGEUSDT_900.csv | True | 53 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/ETHUSDT_180.csv | True | 265 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/ETHUSDT_300.csv | True | 460 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-14T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/ETHUSDT_900.csv | True | 53 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/SOLUSDT_180.csv | True | 265 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/SOLUSDT_300.csv | True | 460 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-14T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/SOLUSDT_900.csv | True | 53 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/XRPUSDT_180.csv | True | 265 | 2026-04-13T23:59:59.999000+00:00 -> 2026-04-14T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-14/XRPUSDT_300.csv | True | 387 | 2026-04-13T16:44:59.999000+00:00 -> 2026-04-14T17:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-14/XRPUSDT_900.csv | True | 133 | 1970-01-01T00:15:00+00:00 -> 2026-04-14T19:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-15/1000PEPEUSDT_180.csv | True | 463 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/1000PEPEUSDT_300.csv | True | 278 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/1000PEPEUSDT_900.csv | True | 93 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/BNBUSDT_180.csv | True | 463 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/BNBUSDT_300.csv | True | 579 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/BNBUSDT_900.csv | True | 3 | 1970-01-01T00:15:00+00:00 -> 2026-04-15T00:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-15/BTCUSDT_180.csv | True | 463 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/BTCUSDT_300.csv | True | 579 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/BTCUSDT_900.csv | True | 93 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/DOGEUSDT_180.csv | True | 463 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/DOGEUSDT_300.csv | True | 579 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/DOGEUSDT_900.csv | True | 93 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/ETHUSDT_180.csv | True | 463 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/ETHUSDT_300.csv | True | 579 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/ETHUSDT_900.csv | True | 93 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/SOLUSDT_180.csv | True | 463 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/SOLUSDT_300.csv | True | 579 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/SOLUSDT_900.csv | True | 93 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/XRPUSDT_180.csv | True | 463 | 2026-04-14T23:59:59.999000+00:00 -> 2026-04-15T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/XRPUSDT_300.csv | True | 579 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-15T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-15/XRPUSDT_900.csv | True | 12 | 1970-01-01T00:15:00+00:00 -> 2026-04-15T02:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-16/1000PEPEUSDT_180.csv | True | 376 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/1000PEPEUSDT_300.csv | True | 225 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/1000PEPEUSDT_900.csv | True | 74 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/BNBUSDT_180.csv | True | 376 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/BNBUSDT_300.csv | True | 1068 | 1970-01-01T00:00:00+00:00 -> 2026-04-16T18:54:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-16/BNBUSDT_900.csv | True | 74 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/BTCUSDT_180.csv | True | 376 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/BTCUSDT_300.csv | True | 1068 | 1970-01-01T00:00:00.129000+00:00 -> 2026-04-16T18:54:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-16/BTCUSDT_900.csv | True | 74 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/DOGEUSDT_180.csv | True | 376 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/DOGEUSDT_300.csv | True | 1068 | 1970-01-01T00:00:00.005000+00:00 -> 2026-04-16T18:54:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-16/DOGEUSDT_900.csv | True | 74 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/ETHUSDT_180.csv | True | 376 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/ETHUSDT_300.csv | True | 1068 | 1970-01-01T00:00:00.500000+00:00 -> 2026-04-16T18:54:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-16/ETHUSDT_900.csv | True | 74 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/SOLUSDT_180.csv | True | 376 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/SOLUSDT_300.csv | True | 1068 | 1970-01-01T00:00:00.042000+00:00 -> 2026-04-16T18:54:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-16/SOLUSDT_900.csv | True | 74 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/XRPUSDT_180.csv | True | 376 | 2026-04-15T23:59:59.999000+00:00 -> 2026-04-16T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-16/XRPUSDT_300.csv | True | 1067 | 1970-01-01T00:00:00.017000+00:00 -> 2026-04-16T18:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-16/XRPUSDT_900.csv | True | 362 | 2026-04-15T07:14:59.999000+00:00 -> 2026-04-16T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/1000PEPEUSDT_180.csv | True | 475 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/1000PEPEUSDT_300.csv | True | 285 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/1000PEPEUSDT_900.csv | True | 95 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/BNBUSDT_180.csv | True | 475 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/BNBUSDT_300.csv | True | 1188 | 1970-01-01T00:10:15.790000+00:00 -> 2026-04-17T05:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/BNBUSDT_900.csv | True | 95 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/BTCUSDT_180.csv | True | 475 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/BTCUSDT_300.csv | True | 1188 | 1970-01-01T20:26:10.700000+00:00 -> 2026-04-17T05:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/BTCUSDT_900.csv | True | 95 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/DOGEUSDT_180.csv | True | 475 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/DOGEUSDT_300.csv | True | 1188 | 1970-01-01T00:00:00.094000+00:00 -> 2026-04-17T05:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/DOGEUSDT_900.csv | True | 95 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/ETHUSDT_180.csv | True | 475 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/ETHUSDT_300.csv | True | 1188 | 1970-01-01T00:38:06.840000+00:00 -> 2026-04-17T05:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/ETHUSDT_900.csv | True | 95 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/SOLUSDT_180.csv | True | 475 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/SOLUSDT_300.csv | True | 1187 | 1970-01-01T00:01:20+00:00 -> 2026-04-17T05:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/SOLUSDT_900.csv | True | 95 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/XRPUSDT_180.csv | True | 475 | 2026-04-16T23:59:59.999000+00:00 -> 2026-04-17T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/XRPUSDT_300.csv | True | 1188 | 1970-01-01T00:00:01.394000+00:00 -> 2026-04-17T05:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-17/XRPUSDT_900.csv | True | 383 | 2026-04-16T06:29:59.999000+00:00 -> 2026-04-17T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/1000PEPEUSDT_180.csv | True | 421 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/1000PEPEUSDT_300.csv | True | 252 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/1000PEPEUSDT_900.csv | True | 84 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/BNBUSDT_180.csv | True | 421 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/BNBUSDT_300.csv | True | 853 | 2026-04-17T11:54:59.999000+00:00 -> 2026-04-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/BNBUSDT_900.csv | True | 84 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/BTCUSDT_180.csv | True | 421 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/BTCUSDT_300.csv | True | 853 | 2026-04-17T11:54:59.999000+00:00 -> 2026-04-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/BTCUSDT_900.csv | True | 84 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/DOGEUSDT_180.csv | True | 421 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/DOGEUSDT_300.csv | True | 853 | 2026-04-17T11:54:59.999000+00:00 -> 2026-04-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/DOGEUSDT_900.csv | True | 84 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/ETHUSDT_180.csv | True | 421 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/ETHUSDT_300.csv | True | 853 | 2026-04-17T11:54:59.999000+00:00 -> 2026-04-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/ETHUSDT_900.csv | True | 84 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/SOLUSDT_180.csv | True | 421 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/SOLUSDT_300.csv | True | 854 | 2026-04-17T11:54:59.999000+00:00 -> 2026-04-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/SOLUSDT_900.csv | True | 84 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/XRPUSDT_180.csv | True | 421 | 2026-04-17T23:59:59.999000+00:00 -> 2026-04-18T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/XRPUSDT_300.csv | True | 854 | 2026-04-17T11:54:59.999000+00:00 -> 2026-04-18T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-18/XRPUSDT_900.csv | True | 276 | 2026-04-17T13:14:59.999000+00:00 -> 2026-04-18T23:59:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/1000PEPEUSDT_180.csv | True | 480 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/1000PEPEUSDT_300.csv | True | 288 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/1000PEPEUSDT_900.csv | True | 96 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/BNBUSDT_180.csv | True | 480 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/BNBUSDT_300.csv | True | 288 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/BNBUSDT_900.csv | True | 96 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/BTCUSDT_180.csv | True | 480 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/BTCUSDT_300.csv | True | 288 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/BTCUSDT_900.csv | True | 96 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/DOGEUSDT_180.csv | True | 480 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/DOGEUSDT_300.csv | True | 288 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/DOGEUSDT_900.csv | True | 96 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/ETHUSDT_180.csv | True | 480 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/ETHUSDT_300.csv | True | 288 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/ETHUSDT_900.csv | True | 96 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/SOLUSDT_180.csv | True | 480 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/SOLUSDT_300.csv | True | 288 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/SOLUSDT_900.csv | True | 96 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/XRPUSDT_180.csv | True | 480 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/XRPUSDT_300.csv | True | 288 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-19/XRPUSDT_900.csv | True | 96 | 2026-04-18T23:59:59.999000+00:00 -> 2026-04-19T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/1000PEPEUSDT_180.csv | True | 480 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/1000PEPEUSDT_300.csv | True | 288 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/1000PEPEUSDT_900.csv | True | 96 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/BNBUSDT_180.csv | True | 480 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/BNBUSDT_300.csv | True | 288 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/BNBUSDT_900.csv | True | 96 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/BTCUSDT_180.csv | True | 480 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/BTCUSDT_300.csv | True | 288 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/BTCUSDT_900.csv | True | 96 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/DOGEUSDT_180.csv | True | 480 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/DOGEUSDT_300.csv | True | 288 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/DOGEUSDT_900.csv | True | 96 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/ETHUSDT_180.csv | True | 480 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/ETHUSDT_300.csv | True | 288 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/ETHUSDT_900.csv | True | 96 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/SOLUSDT_180.csv | True | 480 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/SOLUSDT_300.csv | True | 288 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/SOLUSDT_900.csv | True | 96 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/XRPUSDT_180.csv | True | 480 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/XRPUSDT_300.csv | True | 288 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-20/XRPUSDT_900.csv | True | 96 | 2026-04-19T23:59:59.999000+00:00 -> 2026-04-20T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/1000PEPEUSDT_180.csv | True | 429 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/1000PEPEUSDT_300.csv | True | 258 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/1000PEPEUSDT_900.csv | True | 86 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/BNBUSDT_180.csv | True | 427 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/BNBUSDT_300.csv | True | 559 | 2026-04-20T11:34:59.999000+00:00 -> 2026-04-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/BNBUSDT_900.csv | True | 86 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/BTCUSDT_180.csv | True | 429 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/BTCUSDT_300.csv | True | 559 | 2026-04-20T11:34:59.999000+00:00 -> 2026-04-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/BTCUSDT_900.csv | True | 86 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/DOGEUSDT_180.csv | True | 429 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/DOGEUSDT_300.csv | True | 559 | 2026-04-20T11:34:59.999000+00:00 -> 2026-04-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/DOGEUSDT_900.csv | True | 86 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/ETHUSDT_180.csv | True | 428 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/ETHUSDT_300.csv | True | 559 | 2026-04-20T11:34:59.999000+00:00 -> 2026-04-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/ETHUSDT_900.csv | True | 86 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/SOLUSDT_180.csv | True | 428 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/SOLUSDT_300.csv | True | 559 | 2026-04-20T11:34:59.999000+00:00 -> 2026-04-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/SOLUSDT_900.csv | True | 86 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/XRPUSDT_180.csv | True | 427 | 2026-04-20T23:59:59.999000+00:00 -> 2026-04-21T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/XRPUSDT_300.csv | True | 559 | 2026-04-20T11:34:59.999000+00:00 -> 2026-04-21T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-21/XRPUSDT_900.csv | True | 182 | 2026-04-20T12:59:59.999000+00:00 -> 2026-04-21T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/1000PEPEUSDT_180.csv | True | 460 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/1000PEPEUSDT_300.csv | True | 276 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/1000PEPEUSDT_900.csv | True | 92 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/BNBUSDT_180.csv | True | 460 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/BNBUSDT_300.csv | True | 577 | 2026-04-21T17:44:59.999000+00:00 -> 2026-04-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/BNBUSDT_900.csv | True | 92 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/BTCUSDT_180.csv | True | 460 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/BTCUSDT_300.csv | True | 577 | 2026-04-21T17:44:59.999000+00:00 -> 2026-04-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/BTCUSDT_900.csv | True | 92 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/DOGEUSDT_180.csv | True | 460 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/DOGEUSDT_300.csv | True | 276 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/DOGEUSDT_900.csv | True | 92 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/ETHUSDT_180.csv | True | 460 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/ETHUSDT_300.csv | True | 276 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/ETHUSDT_900.csv | True | 92 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/SOLUSDT_180.csv | True | 460 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/SOLUSDT_300.csv | True | 577 | 2026-04-21T17:44:59.999000+00:00 -> 2026-04-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/SOLUSDT_900.csv | True | 92 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/XRPUSDT_180.csv | True | 460 | 2026-04-21T23:59:59.999000+00:00 -> 2026-04-22T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/XRPUSDT_300.csv | True | 577 | 2026-04-21T17:44:59.999000+00:00 -> 2026-04-22T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-22/XRPUSDT_900.csv | True | 188 | 2026-04-21T18:59:59.999000+00:00 -> 2026-04-22T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/1000PEPEUSDT_180.csv | True | 472 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/1000PEPEUSDT_300.csv | True | 283 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/1000PEPEUSDT_900.csv | True | 95 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/BNBUSDT_180.csv | True | 421 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/BNBUSDT_300.csv | True | 554 | 2026-04-22T18:29:59.999000+00:00 -> 2026-04-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/BNBUSDT_900.csv | True | 85 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/BTCUSDT_180.csv | True | 421 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/BTCUSDT_300.csv | True | 554 | 2026-04-22T18:29:59.999000+00:00 -> 2026-04-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/BTCUSDT_900.csv | True | 85 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/DOGEUSDT_180.csv | True | 472 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/DOGEUSDT_300.csv | True | 283 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/DOGEUSDT_900.csv | True | 95 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/ETHUSDT_180.csv | True | 421 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/ETHUSDT_300.csv | True | 554 | 2026-04-22T18:29:59.999000+00:00 -> 2026-04-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/ETHUSDT_900.csv | True | 85 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/SOLUSDT_180.csv | True | 421 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/SOLUSDT_300.csv | True | 554 | 2026-04-22T18:29:59.999000+00:00 -> 2026-04-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/SOLUSDT_900.csv | True | 85 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/XRPUSDT_180.csv | True | 421 | 2026-04-22T23:59:59.999000+00:00 -> 2026-04-23T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/XRPUSDT_300.csv | True | 554 | 2026-04-22T18:29:59.999000+00:00 -> 2026-04-23T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-23/XRPUSDT_900.csv | True | 181 | 2026-04-22T19:44:59.999000+00:00 -> 2026-04-23T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/1000PEPEUSDT_180.csv | True | 247 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/1000PEPEUSDT_300.csv | True | 148 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/1000PEPEUSDT_900.csv | True | 49 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/BNBUSDT_180.csv | True | 247 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/BNBUSDT_300.csv | True | 750 | 2026-04-23T10:39:59.999000+00:00 -> 2026-04-24T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/BNBUSDT_900.csv | True | 49 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/BTCUSDT_180.csv | True | 247 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/BTCUSDT_300.csv | True | 750 | 2026-04-23T10:39:59.999000+00:00 -> 2026-04-24T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/BTCUSDT_900.csv | True | 49 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/DOGEUSDT_180.csv | True | 247 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/DOGEUSDT_300.csv | True | 148 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/DOGEUSDT_900.csv | True | 49 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/ETHUSDT_180.csv | True | 247 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/ETHUSDT_300.csv | True | 750 | 2026-04-23T10:39:59.999000+00:00 -> 2026-04-24T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/ETHUSDT_900.csv | True | 49 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/SOLUSDT_180.csv | True | 247 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/SOLUSDT_300.csv | True | 750 | 2026-04-23T10:39:59.999000+00:00 -> 2026-04-24T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/SOLUSDT_900.csv | True | 49 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/XRPUSDT_180.csv | True | 247 | 2026-04-23T23:59:59.999000+00:00 -> 2026-04-24T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/XRPUSDT_300.csv | True | 750 | 2026-04-23T10:39:59.999000+00:00 -> 2026-04-24T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-24/XRPUSDT_900.csv | True | 241 | 2026-04-23T11:59:59.999000+00:00 -> 2026-04-24T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/1000PEPEUSDT_180.csv | True | 449 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/1000PEPEUSDT_300.csv | True | 270 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/1000PEPEUSDT_900.csv | True | 90 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/BNBUSDT_180.csv | True | 449 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/BNBUSDT_300.csv | True | 872 | 2026-04-23T23:49:59.999000+00:00 -> 2026-04-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/BNBUSDT_900.csv | True | 90 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/BTCUSDT_180.csv | True | 449 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/BTCUSDT_300.csv | True | 872 | 2026-04-23T23:49:59.999000+00:00 -> 2026-04-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/BTCUSDT_900.csv | True | 90 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/DOGEUSDT_180.csv | True | 449 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/DOGEUSDT_300.csv | True | 270 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/DOGEUSDT_900.csv | True | 90 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/ETHUSDT_180.csv | True | 449 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/ETHUSDT_300.csv | True | 872 | 2026-04-23T23:49:59.999000+00:00 -> 2026-04-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/ETHUSDT_900.csv | True | 90 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/SOLUSDT_180.csv | True | 449 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/SOLUSDT_300.csv | True | 872 | 2026-04-23T23:49:59.999000+00:00 -> 2026-04-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/SOLUSDT_900.csv | True | 90 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/XRPUSDT_180.csv | True | 449 | 2026-04-24T23:59:59.999000+00:00 -> 2026-04-25T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/XRPUSDT_300.csv | True | 872 | 2026-04-23T23:49:59.999000+00:00 -> 2026-04-25T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-25/XRPUSDT_900.csv | True | 282 | 2026-04-24T01:14:59.999000+00:00 -> 2026-04-25T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/1000PEPEUSDT_180.csv | True | 478 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/1000PEPEUSDT_300.csv | True | 287 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/1000PEPEUSDT_900.csv | True | 95 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/BNBUSDT_180.csv | True | 478 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/BNBUSDT_300.csv | True | 588 | 2026-04-25T14:04:59.999000+00:00 -> 2026-04-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/BNBUSDT_900.csv | True | 95 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/BTCUSDT_180.csv | True | 478 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/BTCUSDT_300.csv | True | 588 | 2026-04-25T14:04:59.999000+00:00 -> 2026-04-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/BTCUSDT_900.csv | True | 95 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/DOGEUSDT_180.csv | True | 478 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/DOGEUSDT_300.csv | True | 287 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/DOGEUSDT_900.csv | True | 95 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/ETHUSDT_180.csv | True | 478 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/ETHUSDT_300.csv | True | 588 | 2026-04-25T14:04:59.999000+00:00 -> 2026-04-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/ETHUSDT_900.csv | True | 95 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/SOLUSDT_180.csv | True | 478 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/SOLUSDT_300.csv | True | 588 | 2026-04-25T14:04:59.999000+00:00 -> 2026-04-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/SOLUSDT_900.csv | True | 95 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/XRPUSDT_180.csv | True | 478 | 2026-04-25T23:59:59.999000+00:00 -> 2026-04-26T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/XRPUSDT_300.csv | True | 588 | 2026-04-25T14:04:59.999000+00:00 -> 2026-04-26T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-26/XRPUSDT_900.csv | True | 16 | 1970-01-01T00:15:00+00:00 -> 2026-04-26T03:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-27/1000PEPEUSDT_180.csv | True | 299 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/1000PEPEUSDT_300.csv | True | 179 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/1000PEPEUSDT_900.csv | True | 60 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/BNBUSDT_180.csv | True | 299 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/BNBUSDT_300.csv | True | 480 | 2026-04-26T17:14:59.999000+00:00 -> 2026-04-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/BNBUSDT_900.csv | True | 60 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/BTCUSDT_180.csv | True | 299 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/BTCUSDT_300.csv | True | 480 | 2026-04-26T17:14:59.999000+00:00 -> 2026-04-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/BTCUSDT_900.csv | True | 60 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/DOGEUSDT_180.csv | True | 299 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/DOGEUSDT_300.csv | True | 179 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/DOGEUSDT_900.csv | True | 60 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/ETHUSDT_180.csv | True | 299 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/ETHUSDT_300.csv | True | 480 | 2026-04-26T17:14:59.999000+00:00 -> 2026-04-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/ETHUSDT_900.csv | True | 60 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/SOLUSDT_180.csv | True | 299 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/SOLUSDT_300.csv | True | 480 | 2026-04-26T17:14:59.999000+00:00 -> 2026-04-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/SOLUSDT_900.csv | True | 60 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/XRPUSDT_180.csv | True | 299 | 2026-04-26T23:59:59.999000+00:00 -> 2026-04-27T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/XRPUSDT_300.csv | True | 480 | 2026-04-26T17:14:59.999000+00:00 -> 2026-04-27T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-27/XRPUSDT_900.csv | True | 156 | 2026-04-26T18:29:59.999000+00:00 -> 2026-04-27T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/1000PEPEUSDT_180.csv | True | 471 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/1000PEPEUSDT_300.csv | True | 282 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/1000PEPEUSDT_900.csv | True | 94 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/BNBUSDT_180.csv | True | 471 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/BNBUSDT_300.csv | True | 884 | 2026-04-27T11:39:59.999000+00:00 -> 2026-04-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/BNBUSDT_900.csv | True | 94 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/BTCUSDT_180.csv | True | 471 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/BTCUSDT_300.csv | True | 884 | 2026-04-27T11:39:59.999000+00:00 -> 2026-04-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/BTCUSDT_900.csv | True | 94 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/DOGEUSDT_180.csv | True | 471 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/DOGEUSDT_300.csv | True | 282 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/DOGEUSDT_900.csv | True | 94 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/ETHUSDT_180.csv | True | 471 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/ETHUSDT_300.csv | True | 884 | 2026-04-27T11:39:59.999000+00:00 -> 2026-04-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/ETHUSDT_900.csv | True | 94 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/SOLUSDT_180.csv | True | 471 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/SOLUSDT_300.csv | True | 884 | 2026-04-27T11:39:59.999000+00:00 -> 2026-04-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/SOLUSDT_900.csv | True | 94 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/XRPUSDT_180.csv | True | 471 | 2026-04-27T23:59:59.999000+00:00 -> 2026-04-28T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/XRPUSDT_300.csv | True | 884 | 2026-04-27T11:39:59.999000+00:00 -> 2026-04-28T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-28/XRPUSDT_900.csv | True | 156 | 1970-01-01T00:15:00+00:00 -> 2026-04-28T14:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-29/1000PEPEUSDT_180.csv | True | 439 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/1000PEPEUSDT_300.csv | True | 265 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/1000PEPEUSDT_900.csv | True | 87 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/BNBUSDT_180.csv | True | 439 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/BNBUSDT_300.csv | True | 2071 | 2026-04-28T00:24:59.999000+00:00 -> 2026-04-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/BNBUSDT_900.csv | True | 87 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/BTCUSDT_180.csv | True | 439 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/BTCUSDT_300.csv | True | 2071 | 2026-04-28T00:24:59.999000+00:00 -> 2026-04-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/BTCUSDT_900.csv | True | 87 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/DOGEUSDT_180.csv | True | 439 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/DOGEUSDT_300.csv | True | 265 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/DOGEUSDT_900.csv | True | 87 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/ETHUSDT_180.csv | True | 439 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/ETHUSDT_300.csv | True | 2071 | 2026-04-28T00:24:59.999000+00:00 -> 2026-04-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/ETHUSDT_900.csv | True | 87 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/SOLUSDT_180.csv | True | 439 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/SOLUSDT_300.csv | True | 2071 | 2026-04-28T00:24:59.999000+00:00 -> 2026-04-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/SOLUSDT_900.csv | True | 87 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/XRPUSDT_180.csv | True | 439 | 2026-04-28T23:59:59.999000+00:00 -> 2026-04-29T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/XRPUSDT_300.csv | True | 2071 | 2026-04-28T00:24:59.999000+00:00 -> 2026-04-29T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-29/XRPUSDT_900.csv | True | 532 | 1970-01-01T00:15:00+00:00 -> 2026-04-29T14:14:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-04-30/1000PEPEUSDT_180.csv | True | 433 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/1000PEPEUSDT_300.csv | True | 260 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/1000PEPEUSDT_900.csv | True | 86 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/BNBUSDT_180.csv | True | 433 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/BNBUSDT_300.csv | True | 561 | 2026-04-29T12:19:59.999000+00:00 -> 2026-04-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/BNBUSDT_900.csv | True | 86 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/BTCUSDT_180.csv | True | 433 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/BTCUSDT_300.csv | True | 561 | 2026-04-29T12:19:59.999000+00:00 -> 2026-04-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/BTCUSDT_900.csv | True | 86 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/DOGEUSDT_180.csv | True | 433 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/DOGEUSDT_300.csv | True | 260 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/DOGEUSDT_900.csv | True | 86 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/ETHUSDT_180.csv | True | 433 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/ETHUSDT_300.csv | True | 561 | 2026-04-29T12:19:59.999000+00:00 -> 2026-04-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/ETHUSDT_900.csv | True | 86 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/SOLUSDT_180.csv | True | 433 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/SOLUSDT_300.csv | True | 561 | 2026-04-29T12:19:59.999000+00:00 -> 2026-04-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/SOLUSDT_900.csv | True | 86 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/XRPUSDT_180.csv | True | 433 | 2026-04-29T23:59:59.999000+00:00 -> 2026-04-30T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/XRPUSDT_300.csv | True | 561 | 2026-04-29T12:19:59.999000+00:00 -> 2026-04-30T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-04-30/XRPUSDT_900.csv | True | 5 | 1970-01-01T00:15:00+00:00 -> 2026-04-30T00:44:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-05-01/1000PEPEUSDT_180.csv | True | 480 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/1000PEPEUSDT_300.csv | True | 288 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/1000PEPEUSDT_900.csv | True | 96 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/BNBUSDT_180.csv | True | 480 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/BNBUSDT_300.csv | True | 288 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/BNBUSDT_900.csv | True | 96 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/BTCUSDT_180.csv | True | 480 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/BTCUSDT_300.csv | True | 288 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/BTCUSDT_900.csv | True | 96 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/DOGEUSDT_180.csv | True | 480 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/DOGEUSDT_300.csv | True | 288 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/DOGEUSDT_900.csv | True | 96 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/ETHUSDT_180.csv | True | 480 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/ETHUSDT_300.csv | True | 288 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/ETHUSDT_900.csv | True | 96 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/SOLUSDT_180.csv | True | 480 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/SOLUSDT_300.csv | True | 288 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/SOLUSDT_900.csv | True | 96 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/XRPUSDT_180.csv | True | 480 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/XRPUSDT_300.csv | True | 288 | 2026-04-30T23:59:59.999000+00:00 -> 2026-05-01T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-01/XRPUSDT_900.csv | True | 6 | 1970-01-01T00:15:00+00:00 -> 2026-05-01T00:59:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-05-02/1000PEPEUSDT_180.csv | True | 343 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/1000PEPEUSDT_300.csv | True | 206 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/1000PEPEUSDT_900.csv | True | 69 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/BNBUSDT_180.csv | True | 343 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/BNBUSDT_300.csv | True | 808 | 2026-05-01T17:04:59.999000+00:00 -> 2026-05-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/BNBUSDT_900.csv | True | 69 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/BTCUSDT_180.csv | True | 343 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/BTCUSDT_300.csv | True | 808 | 2026-05-01T17:04:59.999000+00:00 -> 2026-05-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/BTCUSDT_900.csv | True | 69 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/DOGEUSDT_180.csv | True | 343 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/DOGEUSDT_300.csv | True | 206 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/DOGEUSDT_900.csv | True | 69 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/ETHUSDT_180.csv | True | 343 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/ETHUSDT_300.csv | True | 808 | 2026-05-01T17:09:59.999000+00:00 -> 2026-05-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/ETHUSDT_900.csv | True | 69 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/SOLUSDT_180.csv | True | 343 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/SOLUSDT_300.csv | True | 808 | 2026-05-01T17:14:59.999000+00:00 -> 2026-05-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/SOLUSDT_900.csv | True | 69 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/XRPUSDT_180.csv | True | 343 | 2026-05-01T23:59:59.999000+00:00 -> 2026-05-02T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/XRPUSDT_300.csv | True | 808 | 2026-05-01T17:19:59.999000+00:00 -> 2026-05-02T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-02/XRPUSDT_900.csv | True | 261 | 2026-05-01T18:44:59.999000+00:00 -> 2026-05-02T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/1000PEPEUSDT_180.csv | True | 403 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/1000PEPEUSDT_300.csv | True | 243 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/1000PEPEUSDT_900.csv | True | 80 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/BNBUSDT_180.csv | True | 403 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/BNBUSDT_300.csv | True | 2350 | 2026-05-02T09:14:59.999000+00:00 -> 2026-05-03T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/BNBUSDT_900.csv | True | 80 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/BTCUSDT_180.csv | True | 403 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/BTCUSDT_300.csv | True | 2349 | 2026-05-02T09:14:59.999000+00:00 -> 2026-05-03T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/BTCUSDT_900.csv | True | 80 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/DOGEUSDT_180.csv | True | 403 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/DOGEUSDT_300.csv | True | 243 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/DOGEUSDT_900.csv | True | 80 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/ETHUSDT_180.csv | True | 403 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/ETHUSDT_300.csv | True | 2350 | 2026-05-02T09:14:59.999000+00:00 -> 2026-05-03T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/ETHUSDT_900.csv | True | 80 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/SOLUSDT_180.csv | True | 403 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/SOLUSDT_300.csv | True | 2350 | 2026-05-01T18:29:59.999000+00:00 -> 2026-05-03T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/SOLUSDT_900.csv | True | 80 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/XRPUSDT_180.csv | True | 403 | 2026-05-02T23:59:59.999000+00:00 -> 2026-05-03T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/XRPUSDT_300.csv | True | 2349 | 2026-05-01T18:29:59.999000+00:00 -> 2026-05-03T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-03/XRPUSDT_900.csv | True | 4 | 1970-01-01T00:15:00+00:00 -> 2026-05-03T00:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-05-04/1000PEPEUSDT_180.csv | True | 474 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/1000PEPEUSDT_300.csv | True | 284 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/1000PEPEUSDT_900.csv | True | 95 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/BNBUSDT_180.csv | True | 474 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/BNBUSDT_300.csv | True | 1789 | 2026-05-03T03:04:59.999000+00:00 -> 2026-05-04T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/BNBUSDT_900.csv | True | 95 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/BTCUSDT_180.csv | True | 474 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/BTCUSDT_300.csv | True | 1788 | 2026-05-03T03:04:59.999000+00:00 -> 2026-05-04T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/BTCUSDT_900.csv | True | 95 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/DOGEUSDT_180.csv | True | 474 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/DOGEUSDT_300.csv | True | 284 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/DOGEUSDT_900.csv | True | 95 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/ETHUSDT_180.csv | True | 474 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/ETHUSDT_300.csv | True | 1488 | 2026-05-03T03:04:59.999000+00:00 -> 2026-05-04T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/ETHUSDT_900.csv | True | 95 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/SOLUSDT_180.csv | True | 474 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/SOLUSDT_300.csv | True | 1789 | 2026-05-03T03:09:59.999000+00:00 -> 2026-05-04T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/SOLUSDT_900.csv | True | 95 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/XRPUSDT_180.csv | True | 474 | 2026-05-03T23:59:59.999000+00:00 -> 2026-05-04T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/XRPUSDT_300.csv | True | 1789 | 2026-05-03T03:09:59.999000+00:00 -> 2026-05-04T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-04/XRPUSDT_900.csv | True | 4 | 1970-01-01T00:15:00+00:00 -> 2026-05-04T00:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-05-05/1000PEPEUSDT_180.csv | True | 434 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/1000PEPEUSDT_300.csv | True | 262 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/1000PEPEUSDT_900.csv | True | 88 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/BNBUSDT_180.csv | True | 434 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/BNBUSDT_300.csv | True | 1165 | 2026-05-04T15:04:59.999000+00:00 -> 2026-05-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/BNBUSDT_900.csv | True | 88 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/BTCUSDT_180.csv | True | 434 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/BTCUSDT_300.csv | True | 1165 | 2026-05-04T15:04:59.999000+00:00 -> 2026-05-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/BTCUSDT_900.csv | True | 88 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/DOGEUSDT_180.csv | True | 434 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/DOGEUSDT_300.csv | True | 262 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/DOGEUSDT_900.csv | True | 88 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/ETHUSDT_180.csv | True | 434 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/ETHUSDT_300.csv | True | 1165 | 2026-05-04T15:04:59.999000+00:00 -> 2026-05-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/ETHUSDT_900.csv | True | 88 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/SOLUSDT_180.csv | True | 434 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/SOLUSDT_300.csv | True | 1165 | 2026-05-04T15:04:59.999000+00:00 -> 2026-05-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/SOLUSDT_900.csv | True | 88 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/XRPUSDT_180.csv | True | 434 | 2026-05-04T23:59:59.999000+00:00 -> 2026-05-05T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/XRPUSDT_300.csv | True | 1165 | 2026-05-04T15:04:59.999000+00:00 -> 2026-05-05T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-05/XRPUSDT_900.csv | True | 60 | 1970-01-01T00:15:00+00:00 -> 2026-05-05T14:29:59.999000+00:00 | symbol, regime, tf_sec | none | scan_error=AttributeError:'NoneType' object has no attribute 'endswith' |
| data/recorder/2026-05-06/1000PEPEUSDT_180.csv | True | 480 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/1000PEPEUSDT_300.csv | True | 288 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/1000PEPEUSDT_900.csv | True | 96 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/BNBUSDT_180.csv | True | 480 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/BNBUSDT_300.csv | True | 288 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/BNBUSDT_900.csv | True | 96 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/BTCUSDT_180.csv | True | 480 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/BTCUSDT_300.csv | True | 288 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/BTCUSDT_900.csv | True | 96 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/DOGEUSDT_180.csv | True | 480 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/DOGEUSDT_300.csv | True | 288 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/DOGEUSDT_900.csv | True | 96 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/ETHUSDT_180.csv | True | 480 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/ETHUSDT_300.csv | True | 288 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/ETHUSDT_900.csv | True | 96 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/SOLUSDT_180.csv | True | 480 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/SOLUSDT_300.csv | True | 288 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/SOLUSDT_900.csv | True | 96 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/XRPUSDT_180.csv | True | 480 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:56:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/XRPUSDT_300.csv | True | 288 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:54:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-06/XRPUSDT_900.csv | True | 96 | 2026-05-05T23:59:59.999000+00:00 -> 2026-05-06T23:44:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/1000PEPEUSDT_180.csv | True | 254 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/1000PEPEUSDT_300.csv | True | 153 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/1000PEPEUSDT_900.csv | True | 52 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/BNBUSDT_180.csv | True | 254 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/BNBUSDT_300.csv | True | 454 | 2026-05-06T00:59:59.999000+00:00 -> 2026-05-07T12:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/BNBUSDT_900.csv | True | 52 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/BTCUSDT_180.csv | True | 254 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/BTCUSDT_300.csv | True | 454 | 2026-05-06T00:59:59.999000+00:00 -> 2026-05-07T12:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/BTCUSDT_900.csv | True | 52 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/DOGEUSDT_180.csv | True | 254 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/DOGEUSDT_300.csv | True | 153 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/DOGEUSDT_900.csv | True | 52 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/ETHUSDT_180.csv | True | 254 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/ETHUSDT_300.csv | True | 424 | 2026-05-05T08:19:59.999000+00:00 -> 2026-05-07T12:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/ETHUSDT_900.csv | True | 52 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/SOLUSDT_180.csv | True | 254 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/SOLUSDT_300.csv | True | 424 | 2026-05-05T08:19:59.999000+00:00 -> 2026-05-07T12:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/SOLUSDT_900.csv | True | 52 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/XRPUSDT_180.csv | True | 254 | 2026-05-06T23:59:59.999000+00:00 -> 2026-05-07T12:35:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/XRPUSDT_300.csv | True | 424 | 2026-05-05T08:19:59.999000+00:00 -> 2026-05-07T12:34:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| data/recorder/2026-05-07/XRPUSDT_900.csv | True | 148 | 2026-05-03T13:29:59.999000+00:00 -> 2026-05-07T12:29:59.999000+00:00 | symbol, regime, tf_sec | none |  |
| logs/order_log_v1.jsonl | True | 1495 | 2026-05-05T22:59:58.605000+00:00 -> 2026-05-07T12:35:06.568000+00:00 | rid, order_id, client_order_id, lifecycle_id, trade_id, symbol, strategy_id, side | realized_pnl_net, fees |  |
| logs/regime_confidence_audit_v1.jsonl | True | 3488 | 2023-11-14T22:13:20+00:00 -> 2026-05-07T12:35:05.533000+00:00 | rid, lifecycle_id, symbol, strategy_id, regime, ts_ms | outcome |  |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | True | 31 | 2026-05-07T01:25:00.706000+00:00 -> 2026-05-07T10:55:01.482000+00:00 | decision_id, rid, lifecycle_id, trade_id, symbol | realized_pnl_net, fees, terminal_status |  |
| logs/trade_lifecycle.jsonl | True | 193488 | 2026-05-05T22:42:12.890000+00:00 -> 2026-05-07T12:37:48.779000+00:00 | request_id, rid, trace_id, order_id, client_order_id, exchange_order_id, entry_order_id, symbol | none | json_decode_errors=3 |
| ops/wal/2026-04-30.jsonl | True | 11155 | 2026-04-30T13:15:49.668000+00:00 -> 2026-04-30T20:59:58.756000+00:00 | rid | none | json_decode_errors=18 |
| ops/wal/2026-05-01.jsonl | True | 31078 | 2026-04-30T21:00:04.664000+00:00 -> 2026-05-01T20:59:58.203000+00:00 | rid, event_ts_ms | none | json_decode_errors=29 |
| ops/wal/2026-05-02.jsonl | True | 22413 | 2026-05-01T21:00:04.139000+00:00 -> 2026-05-02T20:46:31.863000+00:00 | rid, event_ts_ms | none | json_decode_errors=24 |
| ops/wal/2026-05-03.jsonl | True | 28445 | 2026-05-02T21:13:43.687000+00:00 -> 2026-05-03T20:59:59.841000+00:00 | rid, event_ts_ms | none | json_decode_errors=21 |
| ops/wal/2026-05-04.jsonl | True | 31283 | 2026-05-03T21:00:06.022000+00:00 -> 2026-05-04T20:59:58.837000+00:00 | rid | none | json_decode_errors=32 |
| ops/wal/2026-05-05.jsonl | True | 28141 | 2026-05-04T21:00:04.925000+00:00 -> 2026-05-05T20:59:55.360000+00:00 | rid | none | json_decode_errors=39 |
| ops/wal/2026-05-06.jsonl | True | 21888 | 2026-05-05T21:00:01.353000+00:00 -> 2026-05-06T20:59:54.994000+00:00 | rid, event_ts_ms | none |  |
| ops/wal/2026-05-07.jsonl | True | 14963 | 2026-05-06T21:00:00.863000+00:00 -> 2026-05-07T12:37:54.868000+00:00 | rid, event_ts_ms | none |  |
| ops/wal/execution_position_pending_brackets_v1.jsonl | True | 137 | n/a | rid | none |  |
| reports/AURORA_TREND_DOWN_BD1_ETH_STATEFUL_TRADES_2026_05_04.csv | True | 19805 | n/a | symbol | exit_price |  |
| reports/AURORA_TREND_DOWN_SEGMENT_LEVEL_BEST_TRADES_2026_05_04.csv | True | 1326 | 2025-05-02T07:09:59.999000+00:00 -> 2026-04-30T04:39:59.999000+00:00 | symbol, exit_ts | exit_price |  |
| reports/AURORA_TREND_UP_BEST_CANDIDATE_TRADES_2026_05_04.csv | True | 25 | n/a | symbol | none |  |
| reports/BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_smoke_trades.csv | True | 6 | n/a | symbol, side | exit_price |  |
| reports/BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_trades.csv | True | 9407 | n/a | symbol, side | exit_price |  |
| reports/executed_trades_master.csv | True | 0 | n/a | none | none | rows=0 |
| reports/md_amr_integrated_validation_trades.csv | True | 346 | 2026-04-02T02:15:00+00:00 -> 2026-04-08T23:15:00+00:00 | trade_id, symbol, side, entry_ts_ms, exit_ts_ms | exit_price |  |
| reports/order_attempts_master.csv | True | 4 | 2026-04-26T20:20:04.606000+00:00 -> 2026-04-26T22:10:00.538000+00:00 | attempt_id, synthetic_id, symbol, side, intent_ts | outcome, realized_pnl, commission, exact_roundtrip, exit_price |  |
| reports/rejected_attempts_master.csv | True | 4 | 2026-04-26T20:20:04.606000+00:00 -> 2026-04-26T22:10:00.538000+00:00 | attempt_id, synthetic_id, symbol, side, intent_ts | outcome, realized_pnl, commission, exact_roundtrip, exit_price |  |