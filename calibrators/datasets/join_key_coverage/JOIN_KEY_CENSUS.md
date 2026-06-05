# JOIN_KEY_CENSUS

| Source | Field | Non-null Count | Example Values | Notes |
| --- | --- | --- | --- | --- |
| data/authority_request_journal_v1.jsonl | decision_id | 28 | b6a190af-786b-4efa-aa5f-3f017cd07652, 4ebe9a57-dbcd-41c0-b676-57bf4c5badc1, 38728134-9dd7-4fee-bbf5-d1f8b59dc23a, 17c5aaa1-9f25-4da3-899a-982ac1f8e468, 036ebb69-30bd-461e-9eda-325bef3fb97c | canonical |
| data/authority_request_journal_v1.jsonl | rid | 28 | aurora_XRPUSDT_1778123703440, aurora_XRPUSDT_1778124303469, aurora_XRPUSDT_1778128505414, aurora_BTCUSDT_1778130003092, aurora_ETHUSDT_1778132702038 | canonical |
| data/authority_request_journal_v1.jsonl | symbol | 28 | XRPUSDT, BTCUSDT, ETHUSDT, BNBUSDT | context |
| data/authority_request_journal_v1.jsonl | decision_basis_ts_ms | 28 | 1778123703456, 1778124303490, 1778128505429, 1778130003108, 1778132702057 | context |
| data/authority_response_journal_v1.jsonl | decision_id | 28 | b6a190af-786b-4efa-aa5f-3f017cd07652, 4ebe9a57-dbcd-41c0-b676-57bf4c5badc1, 38728134-9dd7-4fee-bbf5-d1f8b59dc23a, 17c5aaa1-9f25-4da3-899a-982ac1f8e468, 036ebb69-30bd-461e-9eda-325bef3fb97c | canonical |
| data/order_ledger.db::orders | order_id | 1781 | 736300548, 1000000024381566, 1000000024381563, 736322119, 1000000024389988 | canonical |
| data/order_ledger.db::orders | client_order_id | 1781 | 736300548, SL-073874443397, TP-17252a906c2c, 736322119, SL-bb75a490b6f4 | canonical |
| data/order_ledger.db::orders | entry_client_id | 829 | 736300548, 736322119, 736400063, 737980445, 747130527 | canonical |
| data/order_ledger.db::orders | symbol | 1781 | DOGEUSDT, BNBUSDT, BTCUSDT, XRPUSDT, 1000PEPEUSDT | context |
| data/order_ledger.db::orders | created_at | 1781 | 1773390902.9842906, 1773390904.4422932, 1773390904.4516382, 1773391803.765617, 1773391805.6680138 | context |
| data/order_ledger.db::orders | updated_at | 1781 | 1773390902.9842908, 1773390904.4422936, 1773390904.4516385, 1773391803.7656178, 1773391805.668015 | context |
| data/recorder/2026-02-08/BTCUSDT_180.csv | symbol | 103 | BTCUSDT | context |
| data/recorder/2026-02-08/BTCUSDT_180.csv | regime | 103 | UNCERTAIN, PENDING, MEAN_REVERSION | context |
| data/recorder/2026-02-08/BTCUSDT_180.csv | tf_sec | 103 | 180 | context |
| data/recorder/2026-02-08/BTCUSDT_300.csv | symbol | 65 | BTCUSDT | context |
| data/recorder/2026-02-08/BTCUSDT_300.csv | regime | 65 | PENDING | context |
| data/recorder/2026-02-08/BTCUSDT_300.csv | tf_sec | 65 | 300 | context |
| data/recorder/2026-02-08/BTCUSDT_900.csv | symbol | 23 | BTCUSDT | context |
| data/recorder/2026-02-08/BTCUSDT_900.csv | regime | 23 | PENDING | context |
| data/recorder/2026-02-08/BTCUSDT_900.csv | tf_sec | 23 | 900 | context |
| data/recorder/2026-02-08/DOGEUSDT_180.csv | symbol | 103 | DOGEUSDT | context |
| data/recorder/2026-02-08/DOGEUSDT_180.csv | regime | 103 | UNCERTAIN, PENDING, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-08/DOGEUSDT_180.csv | tf_sec | 103 | 180 | context |
| data/recorder/2026-02-08/DOGEUSDT_300.csv | symbol | 65 | DOGEUSDT | context |
| data/recorder/2026-02-08/DOGEUSDT_300.csv | regime | 65 | PENDING | context |
| data/recorder/2026-02-08/DOGEUSDT_300.csv | tf_sec | 65 | 300 | context |
| data/recorder/2026-02-08/DOGEUSDT_900.csv | symbol | 23 | DOGEUSDT | context |
| data/recorder/2026-02-08/DOGEUSDT_900.csv | regime | 23 | PENDING | context |
| data/recorder/2026-02-08/DOGEUSDT_900.csv | tf_sec | 23 | 900 | context |
| data/recorder/2026-02-08/ETHUSDT_180.csv | symbol | 103 | ETHUSDT | context |
| data/recorder/2026-02-08/ETHUSDT_180.csv | regime | 103 | UNCERTAIN, PENDING, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-08/ETHUSDT_180.csv | tf_sec | 103 | 180 | context |
| data/recorder/2026-02-08/ETHUSDT_300.csv | symbol | 65 | ETHUSDT | context |
| data/recorder/2026-02-08/ETHUSDT_300.csv | regime | 65 | PENDING | context |
| data/recorder/2026-02-08/ETHUSDT_300.csv | tf_sec | 65 | 300 | context |
| data/recorder/2026-02-08/ETHUSDT_900.csv | symbol | 23 | ETHUSDT | context |
| data/recorder/2026-02-08/ETHUSDT_900.csv | regime | 23 | PENDING | context |
| data/recorder/2026-02-08/ETHUSDT_900.csv | tf_sec | 23 | 900 | context |
| data/recorder/2026-02-08/SOLUSDT_180.csv | symbol | 103 | SOLUSDT | context |
| data/recorder/2026-02-08/SOLUSDT_180.csv | regime | 103 | UNCERTAIN, PENDING, MEAN_REVERSION | context |
| data/recorder/2026-02-08/SOLUSDT_180.csv | tf_sec | 103 | 180 | context |
| data/recorder/2026-02-08/SOLUSDT_300.csv | symbol | 65 | SOLUSDT | context |
| data/recorder/2026-02-08/SOLUSDT_300.csv | regime | 65 | PENDING | context |
| data/recorder/2026-02-08/SOLUSDT_300.csv | tf_sec | 65 | 300 | context |
| data/recorder/2026-02-08/SOLUSDT_900.csv | symbol | 23 | SOLUSDT | context |
| data/recorder/2026-02-08/SOLUSDT_900.csv | regime | 23 | PENDING | context |
| data/recorder/2026-02-08/SOLUSDT_900.csv | tf_sec | 23 | 900 | context |
| data/recorder/2026-02-08/XRPUSDT_180.csv | symbol | 103 | XRPUSDT | context |
| data/recorder/2026-02-08/XRPUSDT_180.csv | regime | 103 | UNCERTAIN, PENDING, MEAN_REVERSION | context |
| data/recorder/2026-02-08/XRPUSDT_180.csv | tf_sec | 103 | 180 | context |
| data/recorder/2026-02-08/XRPUSDT_300.csv | symbol | 65 | XRPUSDT | context |
| data/recorder/2026-02-08/XRPUSDT_300.csv | regime | 65 | PENDING | context |
| data/recorder/2026-02-08/XRPUSDT_300.csv | tf_sec | 65 | 300 | context |
| data/recorder/2026-02-08/XRPUSDT_900.csv | symbol | 23 | XRPUSDT | context |
| data/recorder/2026-02-08/XRPUSDT_900.csv | regime | 23 | PENDING | context |
| data/recorder/2026-02-08/XRPUSDT_900.csv | tf_sec | 23 | 900 | context |
| data/recorder/2026-02-09/BTCUSDT_180.csv | symbol | 255 | BTCUSDT | context |
| data/recorder/2026-02-09/BTCUSDT_180.csv | regime | 255 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-02-09/BTCUSDT_180.csv | tf_sec | 255 | 180 | context |
| data/recorder/2026-02-09/BTCUSDT_300.csv | symbol | 156 | BTCUSDT | context |
| data/recorder/2026-02-09/BTCUSDT_300.csv | regime | 156 | PENDING | context |
| data/recorder/2026-02-09/BTCUSDT_300.csv | tf_sec | 156 | 300 | context |
| data/recorder/2026-02-09/BTCUSDT_900.csv | symbol | 56 | BTCUSDT | context |
| data/recorder/2026-02-09/BTCUSDT_900.csv | regime | 56 | PENDING | context |
| data/recorder/2026-02-09/BTCUSDT_900.csv | tf_sec | 56 | 900 | context |
| data/recorder/2026-02-09/DOGEUSDT_180.csv | symbol | 255 | DOGEUSDT | context |
| data/recorder/2026-02-09/DOGEUSDT_180.csv | regime | 255 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-02-09/DOGEUSDT_180.csv | tf_sec | 255 | 180 | context |
| data/recorder/2026-02-09/DOGEUSDT_300.csv | symbol | 156 | DOGEUSDT | context |
| data/recorder/2026-02-09/DOGEUSDT_300.csv | regime | 156 | PENDING | context |
| data/recorder/2026-02-09/DOGEUSDT_300.csv | tf_sec | 156 | 300 | context |
| data/recorder/2026-02-09/DOGEUSDT_900.csv | symbol | 56 | DOGEUSDT | context |
| data/recorder/2026-02-09/DOGEUSDT_900.csv | regime | 56 | PENDING | context |
| data/recorder/2026-02-09/DOGEUSDT_900.csv | tf_sec | 56 | 900 | context |
| data/recorder/2026-02-09/ETHUSDT_180.csv | symbol | 255 | ETHUSDT | context |
| data/recorder/2026-02-09/ETHUSDT_180.csv | regime | 255 | UNCERTAIN, PENDING, LOW_VOLATILITY | context |
| data/recorder/2026-02-09/ETHUSDT_180.csv | tf_sec | 255 | 180 | context |
| data/recorder/2026-02-09/ETHUSDT_300.csv | symbol | 156 | ETHUSDT | context |
| data/recorder/2026-02-09/ETHUSDT_300.csv | regime | 156 | PENDING | context |
| data/recorder/2026-02-09/ETHUSDT_300.csv | tf_sec | 156 | 300 | context |
| data/recorder/2026-02-09/ETHUSDT_900.csv | symbol | 56 | ETHUSDT | context |
| data/recorder/2026-02-09/ETHUSDT_900.csv | regime | 56 | PENDING | context |
| data/recorder/2026-02-09/ETHUSDT_900.csv | tf_sec | 56 | 900 | context |
| data/recorder/2026-02-09/SOLUSDT_180.csv | symbol | 255 | SOLUSDT | context |
| data/recorder/2026-02-09/SOLUSDT_180.csv | regime | 255 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-02-09/SOLUSDT_180.csv | tf_sec | 255 | 180 | context |
| data/recorder/2026-02-09/SOLUSDT_300.csv | symbol | 156 | SOLUSDT | context |
| data/recorder/2026-02-09/SOLUSDT_300.csv | regime | 156 | PENDING | context |
| data/recorder/2026-02-09/SOLUSDT_300.csv | tf_sec | 156 | 300 | context |
| data/recorder/2026-02-09/SOLUSDT_900.csv | symbol | 56 | SOLUSDT | context |
| data/recorder/2026-02-09/SOLUSDT_900.csv | regime | 56 | PENDING | context |
| data/recorder/2026-02-09/SOLUSDT_900.csv | tf_sec | 56 | 900 | context |
| data/recorder/2026-02-09/XRPUSDT_180.csv | symbol | 255 | XRPUSDT | context |
| data/recorder/2026-02-09/XRPUSDT_180.csv | regime | 255 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-02-09/XRPUSDT_180.csv | tf_sec | 255 | 180 | context |
| data/recorder/2026-02-09/XRPUSDT_300.csv | symbol | 156 | XRPUSDT | context |
| data/recorder/2026-02-09/XRPUSDT_300.csv | regime | 156 | PENDING | context |
| data/recorder/2026-02-09/XRPUSDT_300.csv | tf_sec | 156 | 300 | context |
| data/recorder/2026-02-09/XRPUSDT_900.csv | symbol | 56 | XRPUSDT | context |
| data/recorder/2026-02-09/XRPUSDT_900.csv | regime | 56 | PENDING | context |
| data/recorder/2026-02-09/XRPUSDT_900.csv | tf_sec | 56 | 900 | context |
| data/recorder/2026-02-10/BTCUSDT_180.csv | symbol | 474 | BTCUSDT | context |
| data/recorder/2026-02-10/BTCUSDT_180.csv | regime | 474 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-10/BTCUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-02-10/BTCUSDT_300.csv | symbol | 284 | BTCUSDT | context |
| data/recorder/2026-02-10/BTCUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-10/BTCUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-10/BTCUSDT_900.csv | symbol | 95 | BTCUSDT | context |
| data/recorder/2026-02-10/BTCUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-10/BTCUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-10/DOGEUSDT_180.csv | symbol | 474 | DOGEUSDT | context |
| data/recorder/2026-02-10/DOGEUSDT_180.csv | regime | 474 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-10/DOGEUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-02-10/DOGEUSDT_300.csv | symbol | 284 | DOGEUSDT | context |
| data/recorder/2026-02-10/DOGEUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-10/DOGEUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-10/DOGEUSDT_900.csv | symbol | 95 | DOGEUSDT | context |
| data/recorder/2026-02-10/DOGEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-10/DOGEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-10/ETHUSDT_180.csv | symbol | 474 | ETHUSDT | context |
| data/recorder/2026-02-10/ETHUSDT_180.csv | regime | 474 | LOW_VOLATILITY, PENDING, HIGH_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-02-10/ETHUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-02-10/ETHUSDT_300.csv | symbol | 284 | ETHUSDT | context |
| data/recorder/2026-02-10/ETHUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-10/ETHUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-10/ETHUSDT_900.csv | symbol | 95 | ETHUSDT | context |
| data/recorder/2026-02-10/ETHUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-10/ETHUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-10/SOLUSDT_180.csv | symbol | 474 | SOLUSDT | context |
| data/recorder/2026-02-10/SOLUSDT_180.csv | regime | 474 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-10/SOLUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-02-10/SOLUSDT_300.csv | symbol | 284 | SOLUSDT | context |
| data/recorder/2026-02-10/SOLUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-10/SOLUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-10/SOLUSDT_900.csv | symbol | 95 | SOLUSDT | context |
| data/recorder/2026-02-10/SOLUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-10/SOLUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-10/XRPUSDT_180.csv | symbol | 474 | XRPUSDT | context |
| data/recorder/2026-02-10/XRPUSDT_180.csv | regime | 474 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-10/XRPUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-02-10/XRPUSDT_300.csv | symbol | 283 | XRPUSDT | context |
| data/recorder/2026-02-10/XRPUSDT_300.csv | regime | 283 | PENDING | context |
| data/recorder/2026-02-10/XRPUSDT_300.csv | tf_sec | 283 | 300 | context |
| data/recorder/2026-02-10/XRPUSDT_900.csv | symbol | 95 | XRPUSDT | context |
| data/recorder/2026-02-10/XRPUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-10/XRPUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-11/BTCUSDT_180.csv | symbol | 385 | BTCUSDT | context |
| data/recorder/2026-02-11/BTCUSDT_180.csv | regime | 385 | MEAN_REVERSION, PENDING, UNCERTAIN, HIGH_VOLATILITY, LOW_VOLATILITY | context |
| data/recorder/2026-02-11/BTCUSDT_180.csv | tf_sec | 385 | 180 | context |
| data/recorder/2026-02-11/BTCUSDT_300.csv | symbol | 231 | BTCUSDT | context |
| data/recorder/2026-02-11/BTCUSDT_300.csv | regime | 231 | PENDING | context |
| data/recorder/2026-02-11/BTCUSDT_300.csv | tf_sec | 231 | 300 | context |
| data/recorder/2026-02-11/BTCUSDT_900.csv | symbol | 77 | BTCUSDT | context |
| data/recorder/2026-02-11/BTCUSDT_900.csv | regime | 77 | PENDING | context |
| data/recorder/2026-02-11/BTCUSDT_900.csv | tf_sec | 77 | 900 | context |
| data/recorder/2026-02-11/DOGEUSDT_180.csv | symbol | 385 | DOGEUSDT | context |
| data/recorder/2026-02-11/DOGEUSDT_180.csv | regime | 385 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-11/DOGEUSDT_180.csv | tf_sec | 385 | 180 | context |
| data/recorder/2026-02-11/DOGEUSDT_300.csv | symbol | 231 | DOGEUSDT | context |
| data/recorder/2026-02-11/DOGEUSDT_300.csv | regime | 231 | PENDING | context |
| data/recorder/2026-02-11/DOGEUSDT_300.csv | tf_sec | 231 | 300 | context |
| data/recorder/2026-02-11/DOGEUSDT_900.csv | symbol | 77 | DOGEUSDT | context |
| data/recorder/2026-02-11/DOGEUSDT_900.csv | regime | 77 | PENDING | context |
| data/recorder/2026-02-11/DOGEUSDT_900.csv | tf_sec | 77 | 900 | context |
| data/recorder/2026-02-11/ETHUSDT_180.csv | symbol | 385 | ETHUSDT | context |
| data/recorder/2026-02-11/ETHUSDT_180.csv | regime | 385 | PENDING, MEAN_REVERSION, UNCERTAIN, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-11/ETHUSDT_180.csv | tf_sec | 385 | 180 | context |
| data/recorder/2026-02-11/ETHUSDT_300.csv | symbol | 231 | ETHUSDT | context |
| data/recorder/2026-02-11/ETHUSDT_300.csv | regime | 231 | PENDING | context |
| data/recorder/2026-02-11/ETHUSDT_300.csv | tf_sec | 231 | 300 | context |
| data/recorder/2026-02-11/ETHUSDT_900.csv | symbol | 77 | ETHUSDT | context |
| data/recorder/2026-02-11/ETHUSDT_900.csv | regime | 77 | PENDING | context |
| data/recorder/2026-02-11/ETHUSDT_900.csv | tf_sec | 77 | 900 | context |
| data/recorder/2026-02-11/SOLUSDT_180.csv | symbol | 385 | SOLUSDT | context |
| data/recorder/2026-02-11/SOLUSDT_180.csv | regime | 385 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-11/SOLUSDT_180.csv | tf_sec | 385 | 180 | context |
| data/recorder/2026-02-11/SOLUSDT_300.csv | symbol | 231 | SOLUSDT | context |
| data/recorder/2026-02-11/SOLUSDT_300.csv | regime | 231 | PENDING | context |
| data/recorder/2026-02-11/SOLUSDT_300.csv | tf_sec | 231 | 300 | context |
| data/recorder/2026-02-11/SOLUSDT_900.csv | symbol | 77 | SOLUSDT | context |
| data/recorder/2026-02-11/SOLUSDT_900.csv | regime | 77 | PENDING | context |
| data/recorder/2026-02-11/SOLUSDT_900.csv | tf_sec | 77 | 900 | context |
| data/recorder/2026-02-11/XRPUSDT_180.csv | symbol | 385 | XRPUSDT | context |
| data/recorder/2026-02-11/XRPUSDT_180.csv | regime | 385 | MEAN_REVERSION, PENDING, UNCERTAIN, HIGH_VOLATILITY, LOW_VOLATILITY | context |
| data/recorder/2026-02-11/XRPUSDT_180.csv | tf_sec | 385 | 180 | context |
| data/recorder/2026-02-11/XRPUSDT_300.csv | symbol | 231 | XRPUSDT | context |
| data/recorder/2026-02-11/XRPUSDT_300.csv | regime | 231 | PENDING | context |
| data/recorder/2026-02-11/XRPUSDT_300.csv | tf_sec | 231 | 300 | context |
| data/recorder/2026-02-11/XRPUSDT_900.csv | symbol | 77 | XRPUSDT | context |
| data/recorder/2026-02-11/XRPUSDT_900.csv | regime | 77 | PENDING | context |
| data/recorder/2026-02-11/XRPUSDT_900.csv | tf_sec | 77 | 900 | context |
| data/recorder/2026-02-12/BTCUSDT_180.csv | symbol | 476 | BTCUSDT | context |
| data/recorder/2026-02-12/BTCUSDT_180.csv | regime | 476 | PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-12/BTCUSDT_180.csv | tf_sec | 476 | 180 | context |
| data/recorder/2026-02-12/BTCUSDT_300.csv | symbol | 286 | BTCUSDT | context |
| data/recorder/2026-02-12/BTCUSDT_300.csv | regime | 286 | PENDING | context |
| data/recorder/2026-02-12/BTCUSDT_300.csv | tf_sec | 286 | 300 | context |
| data/recorder/2026-02-12/BTCUSDT_900.csv | symbol | 95 | BTCUSDT | context |
| data/recorder/2026-02-12/BTCUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-12/BTCUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-12/DOGEUSDT_180.csv | symbol | 476 | DOGEUSDT | context |
| data/recorder/2026-02-12/DOGEUSDT_180.csv | regime | 476 | PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-12/DOGEUSDT_180.csv | tf_sec | 476 | 180 | context |
| data/recorder/2026-02-12/DOGEUSDT_300.csv | symbol | 286 | DOGEUSDT | context |
| data/recorder/2026-02-12/DOGEUSDT_300.csv | regime | 286 | PENDING | context |
| data/recorder/2026-02-12/DOGEUSDT_300.csv | tf_sec | 286 | 300 | context |
| data/recorder/2026-02-12/DOGEUSDT_900.csv | symbol | 95 | DOGEUSDT | context |
| data/recorder/2026-02-12/DOGEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-12/DOGEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-12/ETHUSDT_180.csv | symbol | 476 | ETHUSDT | context |
| data/recorder/2026-02-12/ETHUSDT_180.csv | regime | 476 | PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-12/ETHUSDT_180.csv | tf_sec | 476 | 180 | context |
| data/recorder/2026-02-12/ETHUSDT_300.csv | symbol | 286 | ETHUSDT | context |
| data/recorder/2026-02-12/ETHUSDT_300.csv | regime | 286 | PENDING | context |
| data/recorder/2026-02-12/ETHUSDT_300.csv | tf_sec | 286 | 300 | context |
| data/recorder/2026-02-12/ETHUSDT_900.csv | symbol | 95 | ETHUSDT | context |
| data/recorder/2026-02-12/ETHUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-12/ETHUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-12/SOLUSDT_180.csv | symbol | 476 | SOLUSDT | context |
| data/recorder/2026-02-12/SOLUSDT_180.csv | regime | 476 | PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY, LOW_VOLATILITY | context |
| data/recorder/2026-02-12/SOLUSDT_180.csv | tf_sec | 476 | 180 | context |
| data/recorder/2026-02-12/SOLUSDT_300.csv | symbol | 286 | SOLUSDT | context |
| data/recorder/2026-02-12/SOLUSDT_300.csv | regime | 286 | PENDING | context |
| data/recorder/2026-02-12/SOLUSDT_300.csv | tf_sec | 286 | 300 | context |
| data/recorder/2026-02-12/SOLUSDT_900.csv | symbol | 95 | SOLUSDT | context |
| data/recorder/2026-02-12/SOLUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-12/SOLUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-12/XRPUSDT_180.csv | symbol | 476 | XRPUSDT | context |
| data/recorder/2026-02-12/XRPUSDT_180.csv | regime | 476 | PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY, LOW_VOLATILITY | context |
| data/recorder/2026-02-12/XRPUSDT_180.csv | tf_sec | 476 | 180 | context |
| data/recorder/2026-02-12/XRPUSDT_300.csv | symbol | 286 | XRPUSDT | context |
| data/recorder/2026-02-12/XRPUSDT_300.csv | regime | 286 | PENDING | context |
| data/recorder/2026-02-12/XRPUSDT_300.csv | tf_sec | 286 | 300 | context |
| data/recorder/2026-02-12/XRPUSDT_900.csv | symbol | 95 | XRPUSDT | context |
| data/recorder/2026-02-12/XRPUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-12/XRPUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-13/BTCUSDT_180.csv | symbol | 450 | BTCUSDT | context |
| data/recorder/2026-02-13/BTCUSDT_180.csv | regime | 450 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-13/BTCUSDT_180.csv | tf_sec | 450 | 180 | context |
| data/recorder/2026-02-13/BTCUSDT_300.csv | symbol | 270 | BTCUSDT | context |
| data/recorder/2026-02-13/BTCUSDT_300.csv | regime | 270 | PENDING | context |
| data/recorder/2026-02-13/BTCUSDT_300.csv | tf_sec | 270 | 300 | context |
| data/recorder/2026-02-13/BTCUSDT_900.csv | symbol | 90 | BTCUSDT | context |
| data/recorder/2026-02-13/BTCUSDT_900.csv | regime | 90 | PENDING | context |
| data/recorder/2026-02-13/BTCUSDT_900.csv | tf_sec | 90 | 900 | context |
| data/recorder/2026-02-13/DOGEUSDT_180.csv | symbol | 450 | DOGEUSDT | context |
| data/recorder/2026-02-13/DOGEUSDT_180.csv | regime | 450 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-13/DOGEUSDT_180.csv | tf_sec | 450 | 180 | context |
| data/recorder/2026-02-13/DOGEUSDT_300.csv | symbol | 270 | DOGEUSDT | context |
| data/recorder/2026-02-13/DOGEUSDT_300.csv | regime | 270 | PENDING | context |
| data/recorder/2026-02-13/DOGEUSDT_300.csv | tf_sec | 270 | 300 | context |
| data/recorder/2026-02-13/DOGEUSDT_900.csv | symbol | 90 | DOGEUSDT | context |
| data/recorder/2026-02-13/DOGEUSDT_900.csv | regime | 90 | PENDING | context |
| data/recorder/2026-02-13/DOGEUSDT_900.csv | tf_sec | 90 | 900 | context |
| data/recorder/2026-02-13/ETHUSDT_180.csv | symbol | 450 | ETHUSDT | context |
| data/recorder/2026-02-13/ETHUSDT_180.csv | regime | 450 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-02-13/ETHUSDT_180.csv | tf_sec | 450 | 180 | context |
| data/recorder/2026-02-13/ETHUSDT_300.csv | symbol | 270 | ETHUSDT | context |
| data/recorder/2026-02-13/ETHUSDT_300.csv | regime | 270 | PENDING | context |
| data/recorder/2026-02-13/ETHUSDT_300.csv | tf_sec | 270 | 300 | context |
| data/recorder/2026-02-13/ETHUSDT_900.csv | symbol | 90 | ETHUSDT | context |
| data/recorder/2026-02-13/ETHUSDT_900.csv | regime | 90 | PENDING | context |
| data/recorder/2026-02-13/ETHUSDT_900.csv | tf_sec | 90 | 900 | context |
| data/recorder/2026-02-13/SOLUSDT_180.csv | symbol | 450 | SOLUSDT | context |
| data/recorder/2026-02-13/SOLUSDT_180.csv | regime | 450 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-13/SOLUSDT_180.csv | tf_sec | 450 | 180 | context |
| data/recorder/2026-02-13/SOLUSDT_300.csv | symbol | 270 | SOLUSDT | context |
| data/recorder/2026-02-13/SOLUSDT_300.csv | regime | 270 | PENDING | context |
| data/recorder/2026-02-13/SOLUSDT_300.csv | tf_sec | 270 | 300 | context |
| data/recorder/2026-02-13/SOLUSDT_900.csv | symbol | 90 | SOLUSDT | context |
| data/recorder/2026-02-13/SOLUSDT_900.csv | regime | 90 | PENDING | context |
| data/recorder/2026-02-13/SOLUSDT_900.csv | tf_sec | 90 | 900 | context |
| data/recorder/2026-02-13/XRPUSDT_180.csv | symbol | 450 | XRPUSDT | context |
| data/recorder/2026-02-13/XRPUSDT_180.csv | regime | 450 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-13/XRPUSDT_180.csv | tf_sec | 450 | 180 | context |
| data/recorder/2026-02-13/XRPUSDT_300.csv | symbol | 270 | XRPUSDT | context |
| data/recorder/2026-02-13/XRPUSDT_300.csv | regime | 270 | PENDING | context |
| data/recorder/2026-02-13/XRPUSDT_300.csv | tf_sec | 270 | 300 | context |
| data/recorder/2026-02-13/XRPUSDT_900.csv | symbol | 90 | XRPUSDT | context |
| data/recorder/2026-02-13/XRPUSDT_900.csv | regime | 90 | PENDING | context |
| data/recorder/2026-02-13/XRPUSDT_900.csv | tf_sec | 90 | 900 | context |
| data/recorder/2026-02-14/BTCUSDT_180.csv | symbol | 474 | BTCUSDT | context |
| data/recorder/2026-02-14/BTCUSDT_180.csv | regime | 474 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-14/BTCUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-02-14/BTCUSDT_300.csv | symbol | 285 | BTCUSDT | context |
| data/recorder/2026-02-14/BTCUSDT_300.csv | regime | 285 | PENDING | context |
| data/recorder/2026-02-14/BTCUSDT_300.csv | tf_sec | 285 | 300 | context |
| data/recorder/2026-02-14/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-02-14/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-14/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-14/DOGEUSDT_180.csv | symbol | 474 | DOGEUSDT | context |
| data/recorder/2026-02-14/DOGEUSDT_180.csv | regime | 474 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-14/DOGEUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-02-14/DOGEUSDT_300.csv | symbol | 285 | DOGEUSDT | context |
| data/recorder/2026-02-14/DOGEUSDT_300.csv | regime | 285 | PENDING | context |
| data/recorder/2026-02-14/DOGEUSDT_300.csv | tf_sec | 285 | 300 | context |
| data/recorder/2026-02-14/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-02-14/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-14/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-14/ETHUSDT_180.csv | symbol | 474 | ETHUSDT | context |
| data/recorder/2026-02-14/ETHUSDT_180.csv | regime | 474 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-14/ETHUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-02-14/ETHUSDT_300.csv | symbol | 285 | ETHUSDT | context |
| data/recorder/2026-02-14/ETHUSDT_300.csv | regime | 285 | PENDING | context |
| data/recorder/2026-02-14/ETHUSDT_300.csv | tf_sec | 285 | 300 | context |
| data/recorder/2026-02-14/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-02-14/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-14/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-14/SOLUSDT_180.csv | symbol | 474 | SOLUSDT | context |
| data/recorder/2026-02-14/SOLUSDT_180.csv | regime | 474 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-02-14/SOLUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-02-14/SOLUSDT_300.csv | symbol | 285 | SOLUSDT | context |
| data/recorder/2026-02-14/SOLUSDT_300.csv | regime | 285 | PENDING | context |
| data/recorder/2026-02-14/SOLUSDT_300.csv | tf_sec | 285 | 300 | context |
| data/recorder/2026-02-14/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-02-14/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-14/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-14/XRPUSDT_180.csv | symbol | 474 | XRPUSDT | context |
| data/recorder/2026-02-14/XRPUSDT_180.csv | regime | 474 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-14/XRPUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-02-14/XRPUSDT_300.csv | symbol | 285 | XRPUSDT | context |
| data/recorder/2026-02-14/XRPUSDT_300.csv | regime | 285 | PENDING | context |
| data/recorder/2026-02-14/XRPUSDT_300.csv | tf_sec | 285 | 300 | context |
| data/recorder/2026-02-14/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-02-14/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-14/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-15/BTCUSDT_180.csv | symbol | 476 | BTCUSDT | context |
| data/recorder/2026-02-15/BTCUSDT_180.csv | regime | 476 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-15/BTCUSDT_180.csv | tf_sec | 476 | 180 | context |
| data/recorder/2026-02-15/BTCUSDT_300.csv | symbol | 284 | BTCUSDT | context |
| data/recorder/2026-02-15/BTCUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-15/BTCUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-15/BTCUSDT_900.csv | symbol | 95 | BTCUSDT | context |
| data/recorder/2026-02-15/BTCUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-15/BTCUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-15/DOGEUSDT_180.csv | symbol | 476 | DOGEUSDT | context |
| data/recorder/2026-02-15/DOGEUSDT_180.csv | regime | 476 | UNCERTAIN, PENDING, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-15/DOGEUSDT_180.csv | tf_sec | 476 | 180 | context |
| data/recorder/2026-02-15/DOGEUSDT_300.csv | symbol | 284 | DOGEUSDT | context |
| data/recorder/2026-02-15/DOGEUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-15/DOGEUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-15/DOGEUSDT_900.csv | symbol | 95 | DOGEUSDT | context |
| data/recorder/2026-02-15/DOGEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-15/DOGEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-15/ETHUSDT_180.csv | symbol | 476 | ETHUSDT | context |
| data/recorder/2026-02-15/ETHUSDT_180.csv | regime | 476 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-15/ETHUSDT_180.csv | tf_sec | 476 | 180 | context |
| data/recorder/2026-02-15/ETHUSDT_300.csv | symbol | 284 | ETHUSDT | context |
| data/recorder/2026-02-15/ETHUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-15/ETHUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-15/ETHUSDT_900.csv | symbol | 95 | ETHUSDT | context |
| data/recorder/2026-02-15/ETHUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-15/ETHUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-15/SOLUSDT_180.csv | symbol | 476 | SOLUSDT | context |
| data/recorder/2026-02-15/SOLUSDT_180.csv | regime | 476 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-15/SOLUSDT_180.csv | tf_sec | 476 | 180 | context |
| data/recorder/2026-02-15/SOLUSDT_300.csv | symbol | 284 | SOLUSDT | context |
| data/recorder/2026-02-15/SOLUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-15/SOLUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-15/SOLUSDT_900.csv | symbol | 95 | SOLUSDT | context |
| data/recorder/2026-02-15/SOLUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-15/SOLUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-15/XRPUSDT_180.csv | symbol | 476 | XRPUSDT | context |
| data/recorder/2026-02-15/XRPUSDT_180.csv | regime | 476 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-15/XRPUSDT_180.csv | tf_sec | 476 | 180 | context |
| data/recorder/2026-02-15/XRPUSDT_300.csv | symbol | 284 | XRPUSDT | context |
| data/recorder/2026-02-15/XRPUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-15/XRPUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-15/XRPUSDT_900.csv | symbol | 95 | XRPUSDT | context |
| data/recorder/2026-02-15/XRPUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-15/XRPUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-16/BTCUSDT_180.csv | symbol | 461 | BTCUSDT | context |
| data/recorder/2026-02-16/BTCUSDT_180.csv | regime | 461 | MEAN_REVERSION, PENDING, UNCERTAIN, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-16/BTCUSDT_180.csv | tf_sec | 461 | 180 | context |
| data/recorder/2026-02-16/BTCUSDT_300.csv | symbol | 280 | BTCUSDT | context |
| data/recorder/2026-02-16/BTCUSDT_300.csv | regime | 280 | PENDING | context |
| data/recorder/2026-02-16/BTCUSDT_300.csv | tf_sec | 280 | 300 | context |
| data/recorder/2026-02-16/BTCUSDT_900.csv | symbol | 95 | BTCUSDT | context |
| data/recorder/2026-02-16/BTCUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-16/BTCUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-16/DOGEUSDT_180.csv | symbol | 461 | DOGEUSDT | context |
| data/recorder/2026-02-16/DOGEUSDT_180.csv | regime | 461 | MEAN_REVERSION, PENDING, UNCERTAIN, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-16/DOGEUSDT_180.csv | tf_sec | 461 | 180 | context |
| data/recorder/2026-02-16/DOGEUSDT_300.csv | symbol | 280 | DOGEUSDT | context |
| data/recorder/2026-02-16/DOGEUSDT_300.csv | regime | 280 | PENDING | context |
| data/recorder/2026-02-16/DOGEUSDT_300.csv | tf_sec | 280 | 300 | context |
| data/recorder/2026-02-16/DOGEUSDT_900.csv | symbol | 95 | DOGEUSDT | context |
| data/recorder/2026-02-16/DOGEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-16/DOGEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-16/ETHUSDT_180.csv | symbol | 461 | ETHUSDT | context |
| data/recorder/2026-02-16/ETHUSDT_180.csv | regime | 461 | PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-16/ETHUSDT_180.csv | tf_sec | 461 | 180 | context |
| data/recorder/2026-02-16/ETHUSDT_300.csv | symbol | 280 | ETHUSDT | context |
| data/recorder/2026-02-16/ETHUSDT_300.csv | regime | 280 | PENDING | context |
| data/recorder/2026-02-16/ETHUSDT_300.csv | tf_sec | 280 | 300 | context |
| data/recorder/2026-02-16/ETHUSDT_900.csv | symbol | 95 | ETHUSDT | context |
| data/recorder/2026-02-16/ETHUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-16/ETHUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-16/SOLUSDT_180.csv | symbol | 461 | SOLUSDT | context |
| data/recorder/2026-02-16/SOLUSDT_180.csv | regime | 461 | UNCERTAIN, PENDING, HIGH_VOLATILITY, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-02-16/SOLUSDT_180.csv | tf_sec | 461 | 180 | context |
| data/recorder/2026-02-16/SOLUSDT_300.csv | symbol | 280 | SOLUSDT | context |
| data/recorder/2026-02-16/SOLUSDT_300.csv | regime | 280 | PENDING | context |
| data/recorder/2026-02-16/SOLUSDT_300.csv | tf_sec | 280 | 300 | context |
| data/recorder/2026-02-16/SOLUSDT_900.csv | symbol | 95 | SOLUSDT | context |
| data/recorder/2026-02-16/SOLUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-16/SOLUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-16/XRPUSDT_180.csv | symbol | 461 | XRPUSDT | context |
| data/recorder/2026-02-16/XRPUSDT_180.csv | regime | 461 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-16/XRPUSDT_180.csv | tf_sec | 461 | 180 | context |
| data/recorder/2026-02-16/XRPUSDT_300.csv | symbol | 280 | XRPUSDT | context |
| data/recorder/2026-02-16/XRPUSDT_300.csv | regime | 280 | PENDING | context |
| data/recorder/2026-02-16/XRPUSDT_300.csv | tf_sec | 280 | 300 | context |
| data/recorder/2026-02-16/XRPUSDT_900.csv | symbol | 95 | XRPUSDT | context |
| data/recorder/2026-02-16/XRPUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-16/XRPUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-17/BTCUSDT_180.csv | symbol | 475 | BTCUSDT | context |
| data/recorder/2026-02-17/BTCUSDT_180.csv | regime | 475 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-17/BTCUSDT_180.csv | tf_sec | 475 | 180 | context |
| data/recorder/2026-02-17/BTCUSDT_300.csv | symbol | 284 | BTCUSDT | context |
| data/recorder/2026-02-17/BTCUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-17/BTCUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-17/BTCUSDT_900.csv | symbol | 95 | BTCUSDT | context |
| data/recorder/2026-02-17/BTCUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-17/BTCUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-17/DOGEUSDT_180.csv | symbol | 475 | DOGEUSDT | context |
| data/recorder/2026-02-17/DOGEUSDT_180.csv | regime | 475 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-17/DOGEUSDT_180.csv | tf_sec | 475 | 180 | context |
| data/recorder/2026-02-17/DOGEUSDT_300.csv | symbol | 284 | DOGEUSDT | context |
| data/recorder/2026-02-17/DOGEUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-17/DOGEUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-17/DOGEUSDT_900.csv | symbol | 95 | DOGEUSDT | context |
| data/recorder/2026-02-17/DOGEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-17/DOGEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-17/ETHUSDT_180.csv | symbol | 475 | ETHUSDT | context |
| data/recorder/2026-02-17/ETHUSDT_180.csv | regime | 475 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-17/ETHUSDT_180.csv | tf_sec | 475 | 180 | context |
| data/recorder/2026-02-17/ETHUSDT_300.csv | symbol | 284 | ETHUSDT | context |
| data/recorder/2026-02-17/ETHUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-17/ETHUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-17/ETHUSDT_900.csv | symbol | 95 | ETHUSDT | context |
| data/recorder/2026-02-17/ETHUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-17/ETHUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-17/SOLUSDT_180.csv | symbol | 475 | SOLUSDT | context |
| data/recorder/2026-02-17/SOLUSDT_180.csv | regime | 475 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-17/SOLUSDT_180.csv | tf_sec | 475 | 180 | context |
| data/recorder/2026-02-17/SOLUSDT_300.csv | symbol | 284 | SOLUSDT | context |
| data/recorder/2026-02-17/SOLUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-17/SOLUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-17/SOLUSDT_900.csv | symbol | 95 | SOLUSDT | context |
| data/recorder/2026-02-17/SOLUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-17/SOLUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-17/XRPUSDT_180.csv | symbol | 475 | XRPUSDT | context |
| data/recorder/2026-02-17/XRPUSDT_180.csv | regime | 475 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-02-17/XRPUSDT_180.csv | tf_sec | 475 | 180 | context |
| data/recorder/2026-02-17/XRPUSDT_300.csv | symbol | 284 | XRPUSDT | context |
| data/recorder/2026-02-17/XRPUSDT_300.csv | regime | 284 | PENDING | context |
| data/recorder/2026-02-17/XRPUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-02-17/XRPUSDT_900.csv | symbol | 95 | XRPUSDT | context |
| data/recorder/2026-02-17/XRPUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-02-17/XRPUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-02-18/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-02-18/BTCUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-18/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-18/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-02-18/BTCUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-18/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-18/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-02-18/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-18/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-18/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-02-18/DOGEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-18/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-18/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-02-18/DOGEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-18/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-18/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-02-18/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-18/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-18/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-02-18/ETHUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-18/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-18/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-02-18/ETHUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-18/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-18/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-02-18/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-18/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-18/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-02-18/SOLUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-18/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-18/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-02-18/SOLUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-18/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-18/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-02-18/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-18/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-18/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-02-18/XRPUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-18/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-18/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-02-18/XRPUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-18/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-18/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-02-18/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-18/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-19/BTCUSDT_180.csv | symbol | 385 | BTCUSDT | context |
| data/recorder/2026-02-19/BTCUSDT_180.csv | regime | 385 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-19/BTCUSDT_180.csv | tf_sec | 385 | 180 | context |
| data/recorder/2026-02-19/BTCUSDT_300.csv | symbol | 230 | BTCUSDT | context |
| data/recorder/2026-02-19/BTCUSDT_300.csv | regime | 230 | PENDING | context |
| data/recorder/2026-02-19/BTCUSDT_300.csv | tf_sec | 230 | 300 | context |
| data/recorder/2026-02-19/BTCUSDT_900.csv | symbol | 76 | BTCUSDT | context |
| data/recorder/2026-02-19/BTCUSDT_900.csv | regime | 76 | PENDING | context |
| data/recorder/2026-02-19/BTCUSDT_900.csv | tf_sec | 76 | 900 | context |
| data/recorder/2026-02-19/DOGEUSDT_180.csv | symbol | 385 | DOGEUSDT | context |
| data/recorder/2026-02-19/DOGEUSDT_180.csv | regime | 385 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-19/DOGEUSDT_180.csv | tf_sec | 385 | 180 | context |
| data/recorder/2026-02-19/DOGEUSDT_300.csv | symbol | 230 | DOGEUSDT | context |
| data/recorder/2026-02-19/DOGEUSDT_300.csv | regime | 230 | PENDING | context |
| data/recorder/2026-02-19/DOGEUSDT_300.csv | tf_sec | 230 | 300 | context |
| data/recorder/2026-02-19/DOGEUSDT_900.csv | symbol | 76 | DOGEUSDT | context |
| data/recorder/2026-02-19/DOGEUSDT_900.csv | regime | 76 | PENDING | context |
| data/recorder/2026-02-19/DOGEUSDT_900.csv | tf_sec | 76 | 900 | context |
| data/recorder/2026-02-19/ETHUSDT_180.csv | symbol | 385 | ETHUSDT | context |
| data/recorder/2026-02-19/ETHUSDT_180.csv | regime | 385 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-19/ETHUSDT_180.csv | tf_sec | 385 | 180 | context |
| data/recorder/2026-02-19/ETHUSDT_300.csv | symbol | 230 | ETHUSDT | context |
| data/recorder/2026-02-19/ETHUSDT_300.csv | regime | 230 | PENDING | context |
| data/recorder/2026-02-19/ETHUSDT_300.csv | tf_sec | 230 | 300 | context |
| data/recorder/2026-02-19/ETHUSDT_900.csv | symbol | 76 | ETHUSDT | context |
| data/recorder/2026-02-19/ETHUSDT_900.csv | regime | 76 | PENDING | context |
| data/recorder/2026-02-19/ETHUSDT_900.csv | tf_sec | 76 | 900 | context |
| data/recorder/2026-02-19/SOLUSDT_180.csv | symbol | 385 | SOLUSDT | context |
| data/recorder/2026-02-19/SOLUSDT_180.csv | regime | 385 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-19/SOLUSDT_180.csv | tf_sec | 385 | 180 | context |
| data/recorder/2026-02-19/SOLUSDT_300.csv | symbol | 230 | SOLUSDT | context |
| data/recorder/2026-02-19/SOLUSDT_300.csv | regime | 230 | PENDING | context |
| data/recorder/2026-02-19/SOLUSDT_300.csv | tf_sec | 230 | 300 | context |
| data/recorder/2026-02-19/SOLUSDT_900.csv | symbol | 76 | SOLUSDT | context |
| data/recorder/2026-02-19/SOLUSDT_900.csv | regime | 76 | PENDING | context |
| data/recorder/2026-02-19/SOLUSDT_900.csv | tf_sec | 76 | 900 | context |
| data/recorder/2026-02-19/XRPUSDT_180.csv | symbol | 385 | XRPUSDT | context |
| data/recorder/2026-02-19/XRPUSDT_180.csv | regime | 385 | MEAN_REVERSION, PENDING, UNCERTAIN, HIGH_VOLATILITY, LOW_VOLATILITY | context |
| data/recorder/2026-02-19/XRPUSDT_180.csv | tf_sec | 385 | 180 | context |
| data/recorder/2026-02-19/XRPUSDT_300.csv | symbol | 230 | XRPUSDT | context |
| data/recorder/2026-02-19/XRPUSDT_300.csv | regime | 230 | PENDING | context |
| data/recorder/2026-02-19/XRPUSDT_300.csv | tf_sec | 230 | 300 | context |
| data/recorder/2026-02-19/XRPUSDT_900.csv | symbol | 76 | XRPUSDT | context |
| data/recorder/2026-02-19/XRPUSDT_900.csv | regime | 76 | PENDING | context |
| data/recorder/2026-02-19/XRPUSDT_900.csv | tf_sec | 76 | 900 | context |
| data/recorder/2026-02-20/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-02-20/BTCUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-20/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-20/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-02-20/BTCUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-20/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-20/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-02-20/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-20/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-20/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-02-20/DOGEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-20/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-20/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-02-20/DOGEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-20/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-20/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-02-20/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-20/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-20/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-02-20/ETHUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-20/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-20/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-02-20/ETHUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-20/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-20/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-02-20/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-20/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-20/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-02-20/SOLUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, HIGH_VOLATILITY, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-02-20/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-20/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-02-20/SOLUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-20/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-20/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-02-20/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-20/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-20/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-02-20/XRPUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-02-20/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-20/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-02-20/XRPUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-20/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-20/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-02-20/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-20/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-21/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-02-21/BTCUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-21/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-21/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-02-21/BTCUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-21/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-21/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-02-21/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-21/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-21/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-02-21/DOGEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-21/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-21/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-02-21/DOGEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-21/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-21/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-02-21/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-21/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-21/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-02-21/ETHUSDT_180.csv | regime | 480 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-21/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-21/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-02-21/ETHUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-21/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-21/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-02-21/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-21/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-21/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-02-21/SOLUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-21/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-21/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-02-21/SOLUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-21/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-21/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-02-21/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-21/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-21/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-02-21/XRPUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-21/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-21/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-02-21/XRPUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-21/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-21/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-02-21/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-21/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-22/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-02-22/BTCUSDT_180.csv | regime | 480 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, HIGH_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-02-22/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-22/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-02-22/BTCUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-22/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-22/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-02-22/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-22/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-22/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-02-22/DOGEUSDT_180.csv | regime | 480 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-22/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-22/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-02-22/DOGEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-22/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-22/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-02-22/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-22/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-22/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-02-22/ETHUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-02-22/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-22/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-02-22/ETHUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-22/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-22/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-02-22/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-22/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-22/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-02-22/SOLUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-02-22/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-22/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-02-22/SOLUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-22/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-22/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-02-22/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-22/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-22/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-02-22/XRPUSDT_180.csv | regime | 480 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-22/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-22/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-02-22/XRPUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-22/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-22/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-02-22/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-22/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-23/BTCUSDT_180.csv | symbol | 461 | BTCUSDT | context |
| data/recorder/2026-02-23/BTCUSDT_180.csv | regime | 461 | MEAN_REVERSION, PENDING, HIGH_VOLATILITY, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-02-23/BTCUSDT_180.csv | tf_sec | 461 | 180 | context |
| data/recorder/2026-02-23/BTCUSDT_300.csv | symbol | 276 | BTCUSDT | context |
| data/recorder/2026-02-23/BTCUSDT_300.csv | regime | 276 | PENDING | context |
| data/recorder/2026-02-23/BTCUSDT_300.csv | tf_sec | 276 | 300 | context |
| data/recorder/2026-02-23/BTCUSDT_900.csv | symbol | 92 | BTCUSDT | context |
| data/recorder/2026-02-23/BTCUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-02-23/BTCUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-02-23/DOGEUSDT_180.csv | symbol | 461 | DOGEUSDT | context |
| data/recorder/2026-02-23/DOGEUSDT_180.csv | regime | 461 | MEAN_REVERSION, PENDING, HIGH_VOLATILITY, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-02-23/DOGEUSDT_180.csv | tf_sec | 461 | 180 | context |
| data/recorder/2026-02-23/DOGEUSDT_300.csv | symbol | 276 | DOGEUSDT | context |
| data/recorder/2026-02-23/DOGEUSDT_300.csv | regime | 276 | PENDING | context |
| data/recorder/2026-02-23/DOGEUSDT_300.csv | tf_sec | 276 | 300 | context |
| data/recorder/2026-02-23/DOGEUSDT_900.csv | symbol | 92 | DOGEUSDT | context |
| data/recorder/2026-02-23/DOGEUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-02-23/DOGEUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-02-23/ETHUSDT_180.csv | symbol | 461 | ETHUSDT | context |
| data/recorder/2026-02-23/ETHUSDT_180.csv | regime | 461 | MEAN_REVERSION, PENDING, UNCERTAIN, HIGH_VOLATILITY, LOW_VOLATILITY | context |
| data/recorder/2026-02-23/ETHUSDT_180.csv | tf_sec | 461 | 180 | context |
| data/recorder/2026-02-23/ETHUSDT_300.csv | symbol | 276 | ETHUSDT | context |
| data/recorder/2026-02-23/ETHUSDT_300.csv | regime | 276 | PENDING | context |
| data/recorder/2026-02-23/ETHUSDT_300.csv | tf_sec | 276 | 300 | context |
| data/recorder/2026-02-23/ETHUSDT_900.csv | symbol | 92 | ETHUSDT | context |
| data/recorder/2026-02-23/ETHUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-02-23/ETHUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-02-23/SOLUSDT_180.csv | symbol | 461 | SOLUSDT | context |
| data/recorder/2026-02-23/SOLUSDT_180.csv | regime | 461 | UNCERTAIN, PENDING, HIGH_VOLATILITY, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-02-23/SOLUSDT_180.csv | tf_sec | 461 | 180 | context |
| data/recorder/2026-02-23/SOLUSDT_300.csv | symbol | 276 | SOLUSDT | context |
| data/recorder/2026-02-23/SOLUSDT_300.csv | regime | 276 | PENDING | context |
| data/recorder/2026-02-23/SOLUSDT_300.csv | tf_sec | 276 | 300 | context |
| data/recorder/2026-02-23/SOLUSDT_900.csv | symbol | 92 | SOLUSDT | context |
| data/recorder/2026-02-23/SOLUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-02-23/SOLUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-02-23/XRPUSDT_180.csv | symbol | 461 | XRPUSDT | context |
| data/recorder/2026-02-23/XRPUSDT_180.csv | regime | 461 | MEAN_REVERSION, PENDING, HIGH_VOLATILITY, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-02-23/XRPUSDT_180.csv | tf_sec | 461 | 180 | context |
| data/recorder/2026-02-23/XRPUSDT_300.csv | symbol | 276 | XRPUSDT | context |
| data/recorder/2026-02-23/XRPUSDT_300.csv | regime | 276 | PENDING | context |
| data/recorder/2026-02-23/XRPUSDT_300.csv | tf_sec | 276 | 300 | context |
| data/recorder/2026-02-23/XRPUSDT_900.csv | symbol | 92 | XRPUSDT | context |
| data/recorder/2026-02-23/XRPUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-02-23/XRPUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-02-24/BTCUSDT_180.csv | symbol | 310 | BTCUSDT | context |
| data/recorder/2026-02-24/BTCUSDT_180.csv | regime | 310 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-02-24/BTCUSDT_180.csv | tf_sec | 310 | 180 | context |
| data/recorder/2026-02-24/BTCUSDT_300.csv | symbol | 186 | BTCUSDT | context |
| data/recorder/2026-02-24/BTCUSDT_300.csv | regime | 186 | PENDING | context |
| data/recorder/2026-02-24/BTCUSDT_300.csv | tf_sec | 186 | 300 | context |
| data/recorder/2026-02-24/BTCUSDT_900.csv | symbol | 62 | BTCUSDT | context |
| data/recorder/2026-02-24/BTCUSDT_900.csv | regime | 62 | PENDING | context |
| data/recorder/2026-02-24/BTCUSDT_900.csv | tf_sec | 62 | 900 | context |
| data/recorder/2026-02-24/DOGEUSDT_180.csv | symbol | 310 | DOGEUSDT | context |
| data/recorder/2026-02-24/DOGEUSDT_180.csv | regime | 310 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-02-24/DOGEUSDT_180.csv | tf_sec | 310 | 180 | context |
| data/recorder/2026-02-24/DOGEUSDT_300.csv | symbol | 186 | DOGEUSDT | context |
| data/recorder/2026-02-24/DOGEUSDT_300.csv | regime | 186 | PENDING | context |
| data/recorder/2026-02-24/DOGEUSDT_300.csv | tf_sec | 186 | 300 | context |
| data/recorder/2026-02-24/DOGEUSDT_900.csv | symbol | 62 | DOGEUSDT | context |
| data/recorder/2026-02-24/DOGEUSDT_900.csv | regime | 62 | PENDING | context |
| data/recorder/2026-02-24/DOGEUSDT_900.csv | tf_sec | 62 | 900 | context |
| data/recorder/2026-02-24/ETHUSDT_180.csv | symbol | 310 | ETHUSDT | context |
| data/recorder/2026-02-24/ETHUSDT_180.csv | regime | 310 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-02-24/ETHUSDT_180.csv | tf_sec | 310 | 180 | context |
| data/recorder/2026-02-24/ETHUSDT_300.csv | symbol | 186 | ETHUSDT | context |
| data/recorder/2026-02-24/ETHUSDT_300.csv | regime | 186 | PENDING | context |
| data/recorder/2026-02-24/ETHUSDT_300.csv | tf_sec | 186 | 300 | context |
| data/recorder/2026-02-24/ETHUSDT_900.csv | symbol | 62 | ETHUSDT | context |
| data/recorder/2026-02-24/ETHUSDT_900.csv | regime | 62 | PENDING | context |
| data/recorder/2026-02-24/ETHUSDT_900.csv | tf_sec | 62 | 900 | context |
| data/recorder/2026-02-24/SOLUSDT_180.csv | symbol | 310 | SOLUSDT | context |
| data/recorder/2026-02-24/SOLUSDT_180.csv | regime | 310 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-02-24/SOLUSDT_180.csv | tf_sec | 310 | 180 | context |
| data/recorder/2026-02-24/SOLUSDT_300.csv | symbol | 186 | SOLUSDT | context |
| data/recorder/2026-02-24/SOLUSDT_300.csv | regime | 186 | PENDING | context |
| data/recorder/2026-02-24/SOLUSDT_300.csv | tf_sec | 186 | 300 | context |
| data/recorder/2026-02-24/SOLUSDT_900.csv | symbol | 62 | SOLUSDT | context |
| data/recorder/2026-02-24/SOLUSDT_900.csv | regime | 62 | PENDING | context |
| data/recorder/2026-02-24/SOLUSDT_900.csv | tf_sec | 62 | 900 | context |
| data/recorder/2026-02-24/XRPUSDT_180.csv | symbol | 310 | XRPUSDT | context |
| data/recorder/2026-02-24/XRPUSDT_180.csv | regime | 310 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-02-24/XRPUSDT_180.csv | tf_sec | 310 | 180 | context |
| data/recorder/2026-02-24/XRPUSDT_300.csv | symbol | 186 | XRPUSDT | context |
| data/recorder/2026-02-24/XRPUSDT_300.csv | regime | 186 | PENDING | context |
| data/recorder/2026-02-24/XRPUSDT_300.csv | tf_sec | 186 | 300 | context |
| data/recorder/2026-02-24/XRPUSDT_900.csv | symbol | 62 | XRPUSDT | context |
| data/recorder/2026-02-24/XRPUSDT_900.csv | regime | 62 | PENDING | context |
| data/recorder/2026-02-24/XRPUSDT_900.csv | tf_sec | 62 | 900 | context |
| data/recorder/2026-02-25/BTCUSDT_180.csv | symbol | 423 | BTCUSDT | context |
| data/recorder/2026-02-25/BTCUSDT_180.csv | regime | 423 | MEAN_REVERSION, PENDING, HIGH_VOLATILITY, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-02-25/BTCUSDT_180.csv | tf_sec | 423 | 180 | context |
| data/recorder/2026-02-25/BTCUSDT_300.csv | symbol | 255 | BTCUSDT | context |
| data/recorder/2026-02-25/BTCUSDT_300.csv | regime | 255 | PENDING | context |
| data/recorder/2026-02-25/BTCUSDT_300.csv | tf_sec | 255 | 300 | context |
| data/recorder/2026-02-25/BTCUSDT_900.csv | symbol | 86 | BTCUSDT | context |
| data/recorder/2026-02-25/BTCUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-02-25/BTCUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-02-25/DOGEUSDT_180.csv | symbol | 423 | DOGEUSDT | context |
| data/recorder/2026-02-25/DOGEUSDT_180.csv | regime | 423 | MEAN_REVERSION, PENDING, HIGH_VOLATILITY, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-02-25/DOGEUSDT_180.csv | tf_sec | 423 | 180 | context |
| data/recorder/2026-02-25/DOGEUSDT_300.csv | symbol | 255 | DOGEUSDT | context |
| data/recorder/2026-02-25/DOGEUSDT_300.csv | regime | 255 | PENDING | context |
| data/recorder/2026-02-25/DOGEUSDT_300.csv | tf_sec | 255 | 300 | context |
| data/recorder/2026-02-25/DOGEUSDT_900.csv | symbol | 86 | DOGEUSDT | context |
| data/recorder/2026-02-25/DOGEUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-02-25/DOGEUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-02-25/ETHUSDT_180.csv | symbol | 423 | ETHUSDT | context |
| data/recorder/2026-02-25/ETHUSDT_180.csv | regime | 423 | MEAN_REVERSION, PENDING, HIGH_VOLATILITY, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-02-25/ETHUSDT_180.csv | tf_sec | 423 | 180 | context |
| data/recorder/2026-02-25/ETHUSDT_300.csv | symbol | 255 | ETHUSDT | context |
| data/recorder/2026-02-25/ETHUSDT_300.csv | regime | 255 | PENDING | context |
| data/recorder/2026-02-25/ETHUSDT_300.csv | tf_sec | 255 | 300 | context |
| data/recorder/2026-02-25/ETHUSDT_900.csv | symbol | 86 | ETHUSDT | context |
| data/recorder/2026-02-25/ETHUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-02-25/ETHUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-02-25/SOLUSDT_180.csv | symbol | 423 | SOLUSDT | context |
| data/recorder/2026-02-25/SOLUSDT_180.csv | regime | 423 | UNCERTAIN, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, LOW_VOLATILITY | context |
| data/recorder/2026-02-25/SOLUSDT_180.csv | tf_sec | 423 | 180 | context |
| data/recorder/2026-02-25/SOLUSDT_300.csv | symbol | 255 | SOLUSDT | context |
| data/recorder/2026-02-25/SOLUSDT_300.csv | regime | 255 | PENDING | context |
| data/recorder/2026-02-25/SOLUSDT_300.csv | tf_sec | 255 | 300 | context |
| data/recorder/2026-02-25/SOLUSDT_900.csv | symbol | 86 | SOLUSDT | context |
| data/recorder/2026-02-25/SOLUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-02-25/SOLUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-02-25/XRPUSDT_180.csv | symbol | 423 | XRPUSDT | context |
| data/recorder/2026-02-25/XRPUSDT_180.csv | regime | 423 | MEAN_REVERSION, PENDING, HIGH_VOLATILITY, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-02-25/XRPUSDT_180.csv | tf_sec | 423 | 180 | context |
| data/recorder/2026-02-25/XRPUSDT_300.csv | symbol | 255 | XRPUSDT | context |
| data/recorder/2026-02-25/XRPUSDT_300.csv | regime | 255 | PENDING | context |
| data/recorder/2026-02-25/XRPUSDT_300.csv | tf_sec | 255 | 300 | context |
| data/recorder/2026-02-25/XRPUSDT_900.csv | symbol | 86 | XRPUSDT | context |
| data/recorder/2026-02-25/XRPUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-02-25/XRPUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-02-26/BTCUSDT_180.csv | symbol | 465 | BTCUSDT | context |
| data/recorder/2026-02-26/BTCUSDT_180.csv | regime | 465 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-26/BTCUSDT_180.csv | tf_sec | 465 | 180 | context |
| data/recorder/2026-02-26/BTCUSDT_300.csv | symbol | 279 | BTCUSDT | context |
| data/recorder/2026-02-26/BTCUSDT_300.csv | regime | 279 | PENDING | context |
| data/recorder/2026-02-26/BTCUSDT_300.csv | tf_sec | 279 | 300 | context |
| data/recorder/2026-02-26/BTCUSDT_900.csv | symbol | 94 | BTCUSDT | context |
| data/recorder/2026-02-26/BTCUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-02-26/BTCUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-02-26/DOGEUSDT_180.csv | symbol | 465 | DOGEUSDT | context |
| data/recorder/2026-02-26/DOGEUSDT_180.csv | regime | 465 | HIGH_VOLATILITY, PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-02-26/DOGEUSDT_180.csv | tf_sec | 465 | 180 | context |
| data/recorder/2026-02-26/DOGEUSDT_300.csv | symbol | 279 | DOGEUSDT | context |
| data/recorder/2026-02-26/DOGEUSDT_300.csv | regime | 279 | PENDING | context |
| data/recorder/2026-02-26/DOGEUSDT_300.csv | tf_sec | 279 | 300 | context |
| data/recorder/2026-02-26/DOGEUSDT_900.csv | symbol | 94 | DOGEUSDT | context |
| data/recorder/2026-02-26/DOGEUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-02-26/DOGEUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-02-26/ETHUSDT_180.csv | symbol | 465 | ETHUSDT | context |
| data/recorder/2026-02-26/ETHUSDT_180.csv | regime | 465 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-26/ETHUSDT_180.csv | tf_sec | 465 | 180 | context |
| data/recorder/2026-02-26/ETHUSDT_300.csv | symbol | 279 | ETHUSDT | context |
| data/recorder/2026-02-26/ETHUSDT_300.csv | regime | 279 | PENDING | context |
| data/recorder/2026-02-26/ETHUSDT_300.csv | tf_sec | 279 | 300 | context |
| data/recorder/2026-02-26/ETHUSDT_900.csv | symbol | 94 | ETHUSDT | context |
| data/recorder/2026-02-26/ETHUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-02-26/ETHUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-02-26/SOLUSDT_180.csv | symbol | 465 | SOLUSDT | context |
| data/recorder/2026-02-26/SOLUSDT_180.csv | regime | 465 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-26/SOLUSDT_180.csv | tf_sec | 465 | 180 | context |
| data/recorder/2026-02-26/SOLUSDT_300.csv | symbol | 279 | SOLUSDT | context |
| data/recorder/2026-02-26/SOLUSDT_300.csv | regime | 279 | PENDING | context |
| data/recorder/2026-02-26/SOLUSDT_300.csv | tf_sec | 279 | 300 | context |
| data/recorder/2026-02-26/SOLUSDT_900.csv | symbol | 94 | SOLUSDT | context |
| data/recorder/2026-02-26/SOLUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-02-26/SOLUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-02-26/XRPUSDT_180.csv | symbol | 465 | XRPUSDT | context |
| data/recorder/2026-02-26/XRPUSDT_180.csv | regime | 465 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-26/XRPUSDT_180.csv | tf_sec | 465 | 180 | context |
| data/recorder/2026-02-26/XRPUSDT_300.csv | symbol | 279 | XRPUSDT | context |
| data/recorder/2026-02-26/XRPUSDT_300.csv | regime | 279 | PENDING | context |
| data/recorder/2026-02-26/XRPUSDT_300.csv | tf_sec | 279 | 300 | context |
| data/recorder/2026-02-26/XRPUSDT_900.csv | symbol | 94 | XRPUSDT | context |
| data/recorder/2026-02-26/XRPUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-02-26/XRPUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-02-27/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-02-27/BTCUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-27/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-27/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-02-27/BTCUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-27/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-27/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-02-27/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-27/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-27/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-02-27/DOGEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-27/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-27/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-02-27/DOGEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-27/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-27/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-02-27/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-27/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-27/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-02-27/ETHUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-27/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-27/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-02-27/ETHUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-27/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-27/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-02-27/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-27/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-27/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-02-27/SOLUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-02-27/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-27/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-02-27/SOLUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-27/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-27/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-02-27/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-27/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-27/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-02-27/XRPUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-02-27/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-02-27/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-02-27/XRPUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-02-27/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-02-27/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-02-27/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-02-27/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-02-28/BTCUSDT_180.csv | symbol | 442 | BTCUSDT | context |
| data/recorder/2026-02-28/BTCUSDT_180.csv | regime | 442 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-28/BTCUSDT_180.csv | tf_sec | 442 | 180 | context |
| data/recorder/2026-02-28/BTCUSDT_300.csv | symbol | 266 | BTCUSDT | context |
| data/recorder/2026-02-28/BTCUSDT_300.csv | regime | 266 | PENDING | context |
| data/recorder/2026-02-28/BTCUSDT_300.csv | tf_sec | 266 | 300 | context |
| data/recorder/2026-02-28/BTCUSDT_900.csv | symbol | 89 | BTCUSDT | context |
| data/recorder/2026-02-28/BTCUSDT_900.csv | regime | 89 | PENDING | context |
| data/recorder/2026-02-28/BTCUSDT_900.csv | tf_sec | 89 | 900 | context |
| data/recorder/2026-02-28/DOGEUSDT_180.csv | symbol | 442 | DOGEUSDT | context |
| data/recorder/2026-02-28/DOGEUSDT_180.csv | regime | 442 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-28/DOGEUSDT_180.csv | tf_sec | 442 | 180 | context |
| data/recorder/2026-02-28/DOGEUSDT_300.csv | symbol | 266 | DOGEUSDT | context |
| data/recorder/2026-02-28/DOGEUSDT_300.csv | regime | 266 | PENDING | context |
| data/recorder/2026-02-28/DOGEUSDT_300.csv | tf_sec | 266 | 300 | context |
| data/recorder/2026-02-28/DOGEUSDT_900.csv | symbol | 89 | DOGEUSDT | context |
| data/recorder/2026-02-28/DOGEUSDT_900.csv | regime | 89 | PENDING | context |
| data/recorder/2026-02-28/DOGEUSDT_900.csv | tf_sec | 89 | 900 | context |
| data/recorder/2026-02-28/ETHUSDT_180.csv | symbol | 442 | ETHUSDT | context |
| data/recorder/2026-02-28/ETHUSDT_180.csv | regime | 442 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-28/ETHUSDT_180.csv | tf_sec | 442 | 180 | context |
| data/recorder/2026-02-28/ETHUSDT_300.csv | symbol | 266 | ETHUSDT | context |
| data/recorder/2026-02-28/ETHUSDT_300.csv | regime | 266 | PENDING | context |
| data/recorder/2026-02-28/ETHUSDT_300.csv | tf_sec | 266 | 300 | context |
| data/recorder/2026-02-28/ETHUSDT_900.csv | symbol | 89 | ETHUSDT | context |
| data/recorder/2026-02-28/ETHUSDT_900.csv | regime | 89 | PENDING | context |
| data/recorder/2026-02-28/ETHUSDT_900.csv | tf_sec | 89 | 900 | context |
| data/recorder/2026-02-28/SOLUSDT_180.csv | symbol | 442 | SOLUSDT | context |
| data/recorder/2026-02-28/SOLUSDT_180.csv | regime | 442 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-28/SOLUSDT_180.csv | tf_sec | 442 | 180 | context |
| data/recorder/2026-02-28/SOLUSDT_300.csv | symbol | 266 | SOLUSDT | context |
| data/recorder/2026-02-28/SOLUSDT_300.csv | regime | 266 | PENDING | context |
| data/recorder/2026-02-28/SOLUSDT_300.csv | tf_sec | 266 | 300 | context |
| data/recorder/2026-02-28/SOLUSDT_900.csv | symbol | 89 | SOLUSDT | context |
| data/recorder/2026-02-28/SOLUSDT_900.csv | regime | 89 | PENDING | context |
| data/recorder/2026-02-28/SOLUSDT_900.csv | tf_sec | 89 | 900 | context |
| data/recorder/2026-02-28/XRPUSDT_180.csv | symbol | 442 | XRPUSDT | context |
| data/recorder/2026-02-28/XRPUSDT_180.csv | regime | 442 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-02-28/XRPUSDT_180.csv | tf_sec | 442 | 180 | context |
| data/recorder/2026-02-28/XRPUSDT_300.csv | symbol | 266 | XRPUSDT | context |
| data/recorder/2026-02-28/XRPUSDT_300.csv | regime | 266 | PENDING | context |
| data/recorder/2026-02-28/XRPUSDT_300.csv | tf_sec | 266 | 300 | context |
| data/recorder/2026-02-28/XRPUSDT_900.csv | symbol | 89 | XRPUSDT | context |
| data/recorder/2026-02-28/XRPUSDT_900.csv | regime | 89 | PENDING | context |
| data/recorder/2026-02-28/XRPUSDT_900.csv | tf_sec | 89 | 900 | context |
| data/recorder/2026-03-01/BTCUSDT_180.csv | symbol | 352 | BTCUSDT | context |
| data/recorder/2026-03-01/BTCUSDT_180.csv | regime | 352 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-03-01/BTCUSDT_180.csv | tf_sec | 352 | 180 | context |
| data/recorder/2026-03-01/BTCUSDT_300.csv | symbol | 213 | BTCUSDT | context |
| data/recorder/2026-03-01/BTCUSDT_300.csv | regime | 213 | PENDING | context |
| data/recorder/2026-03-01/BTCUSDT_300.csv | tf_sec | 213 | 300 | context |
| data/recorder/2026-03-01/BTCUSDT_900.csv | symbol | 71 | BTCUSDT | context |
| data/recorder/2026-03-01/BTCUSDT_900.csv | regime | 71 | PENDING | context |
| data/recorder/2026-03-01/BTCUSDT_900.csv | tf_sec | 71 | 900 | context |
| data/recorder/2026-03-01/DOGEUSDT_180.csv | symbol | 352 | DOGEUSDT | context |
| data/recorder/2026-03-01/DOGEUSDT_180.csv | regime | 352 | UNCERTAIN, PENDING, TREND_UP, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-03-01/DOGEUSDT_180.csv | tf_sec | 352 | 180 | context |
| data/recorder/2026-03-01/DOGEUSDT_300.csv | symbol | 213 | DOGEUSDT | context |
| data/recorder/2026-03-01/DOGEUSDT_300.csv | regime | 213 | PENDING | context |
| data/recorder/2026-03-01/DOGEUSDT_300.csv | tf_sec | 213 | 300 | context |
| data/recorder/2026-03-01/DOGEUSDT_900.csv | symbol | 71 | DOGEUSDT | context |
| data/recorder/2026-03-01/DOGEUSDT_900.csv | regime | 71 | PENDING | context |
| data/recorder/2026-03-01/DOGEUSDT_900.csv | tf_sec | 71 | 900 | context |
| data/recorder/2026-03-01/ETHUSDT_180.csv | symbol | 352 | ETHUSDT | context |
| data/recorder/2026-03-01/ETHUSDT_180.csv | regime | 352 | UNCERTAIN, PENDING, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-01/ETHUSDT_180.csv | tf_sec | 352 | 180 | context |
| data/recorder/2026-03-01/ETHUSDT_300.csv | symbol | 213 | ETHUSDT | context |
| data/recorder/2026-03-01/ETHUSDT_300.csv | regime | 213 | PENDING | context |
| data/recorder/2026-03-01/ETHUSDT_300.csv | tf_sec | 213 | 300 | context |
| data/recorder/2026-03-01/ETHUSDT_900.csv | symbol | 71 | ETHUSDT | context |
| data/recorder/2026-03-01/ETHUSDT_900.csv | regime | 71 | PENDING | context |
| data/recorder/2026-03-01/ETHUSDT_900.csv | tf_sec | 71 | 900 | context |
| data/recorder/2026-03-01/SOLUSDT_180.csv | symbol | 352 | SOLUSDT | context |
| data/recorder/2026-03-01/SOLUSDT_180.csv | regime | 352 | UNCERTAIN, PENDING, TREND_UP, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-03-01/SOLUSDT_180.csv | tf_sec | 352 | 180 | context |
| data/recorder/2026-03-01/SOLUSDT_300.csv | symbol | 213 | SOLUSDT | context |
| data/recorder/2026-03-01/SOLUSDT_300.csv | regime | 213 | PENDING | context |
| data/recorder/2026-03-01/SOLUSDT_300.csv | tf_sec | 213 | 300 | context |
| data/recorder/2026-03-01/SOLUSDT_900.csv | symbol | 71 | SOLUSDT | context |
| data/recorder/2026-03-01/SOLUSDT_900.csv | regime | 71 | PENDING | context |
| data/recorder/2026-03-01/SOLUSDT_900.csv | tf_sec | 71 | 900 | context |
| data/recorder/2026-03-01/XRPUSDT_180.csv | symbol | 352 | XRPUSDT | context |
| data/recorder/2026-03-01/XRPUSDT_180.csv | regime | 352 | UNCERTAIN, PENDING, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-01/XRPUSDT_180.csv | tf_sec | 352 | 180 | context |
| data/recorder/2026-03-01/XRPUSDT_300.csv | symbol | 213 | XRPUSDT | context |
| data/recorder/2026-03-01/XRPUSDT_300.csv | regime | 213 | PENDING | context |
| data/recorder/2026-03-01/XRPUSDT_300.csv | tf_sec | 213 | 300 | context |
| data/recorder/2026-03-01/XRPUSDT_900.csv | symbol | 71 | XRPUSDT | context |
| data/recorder/2026-03-01/XRPUSDT_900.csv | regime | 71 | PENDING | context |
| data/recorder/2026-03-01/XRPUSDT_900.csv | tf_sec | 71 | 900 | context |
| data/recorder/2026-03-02/BTCUSDT_180.csv | symbol | 380 | BTCUSDT | context |
| data/recorder/2026-03-02/BTCUSDT_180.csv | regime | 380 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-03-02/BTCUSDT_180.csv | tf_sec | 380 | 180 | context |
| data/recorder/2026-03-02/BTCUSDT_300.csv | symbol | 228 | BTCUSDT | context |
| data/recorder/2026-03-02/BTCUSDT_300.csv | regime | 228 | PENDING | context |
| data/recorder/2026-03-02/BTCUSDT_300.csv | tf_sec | 228 | 300 | context |
| data/recorder/2026-03-02/BTCUSDT_900.csv | symbol | 76 | BTCUSDT | context |
| data/recorder/2026-03-02/BTCUSDT_900.csv | regime | 76 | PENDING | context |
| data/recorder/2026-03-02/BTCUSDT_900.csv | tf_sec | 76 | 900 | context |
| data/recorder/2026-03-02/DOGEUSDT_180.csv | symbol | 380 | DOGEUSDT | context |
| data/recorder/2026-03-02/DOGEUSDT_180.csv | regime | 380 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-03-02/DOGEUSDT_180.csv | tf_sec | 380 | 180 | context |
| data/recorder/2026-03-02/DOGEUSDT_300.csv | symbol | 228 | DOGEUSDT | context |
| data/recorder/2026-03-02/DOGEUSDT_300.csv | regime | 228 | PENDING | context |
| data/recorder/2026-03-02/DOGEUSDT_300.csv | tf_sec | 228 | 300 | context |
| data/recorder/2026-03-02/DOGEUSDT_900.csv | symbol | 76 | DOGEUSDT | context |
| data/recorder/2026-03-02/DOGEUSDT_900.csv | regime | 76 | PENDING | context |
| data/recorder/2026-03-02/DOGEUSDT_900.csv | tf_sec | 76 | 900 | context |
| data/recorder/2026-03-02/ETHUSDT_180.csv | symbol | 380 | ETHUSDT | context |
| data/recorder/2026-03-02/ETHUSDT_180.csv | regime | 380 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-03-02/ETHUSDT_180.csv | tf_sec | 380 | 180 | context |
| data/recorder/2026-03-02/ETHUSDT_300.csv | symbol | 228 | ETHUSDT | context |
| data/recorder/2026-03-02/ETHUSDT_300.csv | regime | 228 | PENDING | context |
| data/recorder/2026-03-02/ETHUSDT_300.csv | tf_sec | 228 | 300 | context |
| data/recorder/2026-03-02/ETHUSDT_900.csv | symbol | 76 | ETHUSDT | context |
| data/recorder/2026-03-02/ETHUSDT_900.csv | regime | 76 | PENDING | context |
| data/recorder/2026-03-02/ETHUSDT_900.csv | tf_sec | 76 | 900 | context |
| data/recorder/2026-03-02/SOLUSDT_180.csv | symbol | 380 | SOLUSDT | context |
| data/recorder/2026-03-02/SOLUSDT_180.csv | regime | 380 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-03-02/SOLUSDT_180.csv | tf_sec | 380 | 180 | context |
| data/recorder/2026-03-02/SOLUSDT_300.csv | symbol | 228 | SOLUSDT | context |
| data/recorder/2026-03-02/SOLUSDT_300.csv | regime | 228 | PENDING | context |
| data/recorder/2026-03-02/SOLUSDT_300.csv | tf_sec | 228 | 300 | context |
| data/recorder/2026-03-02/SOLUSDT_900.csv | symbol | 76 | SOLUSDT | context |
| data/recorder/2026-03-02/SOLUSDT_900.csv | regime | 76 | PENDING | context |
| data/recorder/2026-03-02/SOLUSDT_900.csv | tf_sec | 76 | 900 | context |
| data/recorder/2026-03-02/XRPUSDT_180.csv | symbol | 380 | XRPUSDT | context |
| data/recorder/2026-03-02/XRPUSDT_180.csv | regime | 380 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-03-02/XRPUSDT_180.csv | tf_sec | 380 | 180 | context |
| data/recorder/2026-03-02/XRPUSDT_300.csv | symbol | 228 | XRPUSDT | context |
| data/recorder/2026-03-02/XRPUSDT_300.csv | regime | 228 | PENDING | context |
| data/recorder/2026-03-02/XRPUSDT_300.csv | tf_sec | 228 | 300 | context |
| data/recorder/2026-03-02/XRPUSDT_900.csv | symbol | 76 | XRPUSDT | context |
| data/recorder/2026-03-02/XRPUSDT_900.csv | regime | 76 | PENDING | context |
| data/recorder/2026-03-02/XRPUSDT_900.csv | tf_sec | 76 | 900 | context |
| data/recorder/2026-03-03/BTCUSDT_180.csv | symbol | 2 | BTCUSDT, PENDING | context |
| data/recorder/2026-03-03/BTCUSDT_180.csv | regime | 2 | UNCERTAIN, None | context |
| data/recorder/2026-03-03/BTCUSDT_180.csv | tf_sec | 2 | 180, 0.0 | context |
| data/recorder/2026-03-03/BTCUSDT_300.csv | symbol | 17 | BTCUSDT, 0.0 | context |
| data/recorder/2026-03-03/BTCUSDT_300.csv | regime | 17 | PENDING, True | context |
| data/recorder/2026-03-03/BTCUSDT_300.csv | tf_sec | 17 | 300, BTCUSDT | context |
| data/recorder/2026-03-03/BTCUSDT_900.csv | symbol | 27 | BTCUSDT, PENDING | context |
| data/recorder/2026-03-03/BTCUSDT_900.csv | regime | 27 | PENDING, None | context |
| data/recorder/2026-03-03/BTCUSDT_900.csv | tf_sec | 27 | 900, 0.0 | context |
| data/recorder/2026-03-03/DOGEUSDT_180.csv | symbol | 2 | DOGEUSDT, PENDING | context |
| data/recorder/2026-03-03/DOGEUSDT_180.csv | regime | 2 | UNCERTAIN, None | context |
| data/recorder/2026-03-03/DOGEUSDT_180.csv | tf_sec | 2 | 180, 0.0 | context |
| data/recorder/2026-03-03/DOGEUSDT_300.csv | symbol | 17 | DOGEUSDT, 0.0 | context |
| data/recorder/2026-03-03/DOGEUSDT_300.csv | regime | 17 | PENDING, True | context |
| data/recorder/2026-03-03/DOGEUSDT_300.csv | tf_sec | 17 | 300, DOGEUSDT | context |
| data/recorder/2026-03-03/DOGEUSDT_900.csv | symbol | 27 | DOGEUSDT, PENDING | context |
| data/recorder/2026-03-03/DOGEUSDT_900.csv | regime | 27 | PENDING, None | context |
| data/recorder/2026-03-03/DOGEUSDT_900.csv | tf_sec | 27 | 900, 0.0 | context |
| data/recorder/2026-03-03/ETHUSDT_180.csv | symbol | 2 | ETHUSDT, PENDING | context |
| data/recorder/2026-03-03/ETHUSDT_180.csv | regime | 2 | UNCERTAIN, None | context |
| data/recorder/2026-03-03/ETHUSDT_180.csv | tf_sec | 2 | 180, 0.0 | context |
| data/recorder/2026-03-03/ETHUSDT_300.csv | symbol | 17 | ETHUSDT, 0.0 | context |
| data/recorder/2026-03-03/ETHUSDT_300.csv | regime | 17 | PENDING, True | context |
| data/recorder/2026-03-03/ETHUSDT_300.csv | tf_sec | 17 | 300, ETHUSDT | context |
| data/recorder/2026-03-03/ETHUSDT_900.csv | symbol | 27 | ETHUSDT, PENDING | context |
| data/recorder/2026-03-03/ETHUSDT_900.csv | regime | 27 | PENDING, None | context |
| data/recorder/2026-03-03/ETHUSDT_900.csv | tf_sec | 27 | 900, 0.0 | context |
| data/recorder/2026-03-03/SOLUSDT_180.csv | symbol | 2 | SOLUSDT, PENDING | context |
| data/recorder/2026-03-03/SOLUSDT_180.csv | regime | 2 | UNCERTAIN, None | context |
| data/recorder/2026-03-03/SOLUSDT_180.csv | tf_sec | 2 | 180, 0.0 | context |
| data/recorder/2026-03-03/SOLUSDT_300.csv | symbol | 17 | SOLUSDT, 0.0 | context |
| data/recorder/2026-03-03/SOLUSDT_300.csv | regime | 17 | PENDING, True | context |
| data/recorder/2026-03-03/SOLUSDT_300.csv | tf_sec | 17 | 300, SOLUSDT | context |
| data/recorder/2026-03-03/SOLUSDT_900.csv | symbol | 27 | SOLUSDT, PENDING | context |
| data/recorder/2026-03-03/SOLUSDT_900.csv | regime | 27 | PENDING, None | context |
| data/recorder/2026-03-03/SOLUSDT_900.csv | tf_sec | 27 | 900, 0.0 | context |
| data/recorder/2026-03-03/XRPUSDT_180.csv | symbol | 2 | XRPUSDT, PENDING | context |
| data/recorder/2026-03-03/XRPUSDT_180.csv | regime | 2 | UNCERTAIN, None | context |
| data/recorder/2026-03-03/XRPUSDT_180.csv | tf_sec | 2 | 180, 0.0 | context |
| data/recorder/2026-03-03/XRPUSDT_300.csv | symbol | 17 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-03/XRPUSDT_300.csv | regime | 17 | PENDING, True | context |
| data/recorder/2026-03-03/XRPUSDT_300.csv | tf_sec | 17 | 300, XRPUSDT | context |
| data/recorder/2026-03-03/XRPUSDT_900.csv | symbol | 27 | XRPUSDT, PENDING | context |
| data/recorder/2026-03-03/XRPUSDT_900.csv | regime | 27 | PENDING, None | context |
| data/recorder/2026-03-03/XRPUSDT_900.csv | tf_sec | 27 | 900, 0.0 | context |
| data/recorder/2026-03-04/BTCUSDT_180.csv | symbol | 3 | BTCUSDT, 0.0 | context |
| data/recorder/2026-03-04/BTCUSDT_180.csv | regime | 3 | UNCERTAIN, PENDING, True | context |
| data/recorder/2026-03-04/BTCUSDT_180.csv | tf_sec | 3 | 180, BTCUSDT | context |
| data/recorder/2026-03-04/BTCUSDT_300.csv | symbol | 4 | BTCUSDT, 0.0 | context |
| data/recorder/2026-03-04/BTCUSDT_300.csv | regime | 4 | PENDING, True | context |
| data/recorder/2026-03-04/BTCUSDT_300.csv | tf_sec | 4 | 300, BTCUSDT | context |
| data/recorder/2026-03-04/BTCUSDT_900.csv | symbol | 12 | BTCUSDT, PENDING | context |
| data/recorder/2026-03-04/BTCUSDT_900.csv | regime | 12 | PENDING, None | context |
| data/recorder/2026-03-04/BTCUSDT_900.csv | tf_sec | 12 | 900, 0.0 | context |
| data/recorder/2026-03-04/DOGEUSDT_180.csv | symbol | 3 | DOGEUSDT, 0.0 | context |
| data/recorder/2026-03-04/DOGEUSDT_180.csv | regime | 3 | UNCERTAIN, PENDING, True | context |
| data/recorder/2026-03-04/DOGEUSDT_180.csv | tf_sec | 3 | 180, DOGEUSDT | context |
| data/recorder/2026-03-04/DOGEUSDT_300.csv | symbol | 4 | DOGEUSDT, 0.0 | context |
| data/recorder/2026-03-04/DOGEUSDT_300.csv | regime | 4 | PENDING, True | context |
| data/recorder/2026-03-04/DOGEUSDT_300.csv | tf_sec | 4 | 300, DOGEUSDT | context |
| data/recorder/2026-03-04/DOGEUSDT_900.csv | symbol | 12 | DOGEUSDT, PENDING | context |
| data/recorder/2026-03-04/DOGEUSDT_900.csv | regime | 12 | PENDING, None | context |
| data/recorder/2026-03-04/DOGEUSDT_900.csv | tf_sec | 12 | 900, 0.0 | context |
| data/recorder/2026-03-04/ETHUSDT_180.csv | symbol | 3 | ETHUSDT, 0.0 | context |
| data/recorder/2026-03-04/ETHUSDT_180.csv | regime | 3 | UNCERTAIN, PENDING, True | context |
| data/recorder/2026-03-04/ETHUSDT_180.csv | tf_sec | 3 | 180, ETHUSDT | context |
| data/recorder/2026-03-04/ETHUSDT_300.csv | symbol | 4 | ETHUSDT, 0.0 | context |
| data/recorder/2026-03-04/ETHUSDT_300.csv | regime | 4 | PENDING, True | context |
| data/recorder/2026-03-04/ETHUSDT_300.csv | tf_sec | 4 | 300, ETHUSDT | context |
| data/recorder/2026-03-04/ETHUSDT_900.csv | symbol | 12 | ETHUSDT, PENDING | context |
| data/recorder/2026-03-04/ETHUSDT_900.csv | regime | 12 | PENDING, None | context |
| data/recorder/2026-03-04/ETHUSDT_900.csv | tf_sec | 12 | 900, 0.0 | context |
| data/recorder/2026-03-04/SOLUSDT_180.csv | symbol | 3 | SOLUSDT, 0.0 | context |
| data/recorder/2026-03-04/SOLUSDT_180.csv | regime | 3 | UNCERTAIN, PENDING, True | context |
| data/recorder/2026-03-04/SOLUSDT_180.csv | tf_sec | 3 | 180, SOLUSDT | context |
| data/recorder/2026-03-04/SOLUSDT_300.csv | symbol | 4 | SOLUSDT, 0.0 | context |
| data/recorder/2026-03-04/SOLUSDT_300.csv | regime | 4 | PENDING, True | context |
| data/recorder/2026-03-04/SOLUSDT_300.csv | tf_sec | 4 | 300, SOLUSDT | context |
| data/recorder/2026-03-04/SOLUSDT_900.csv | symbol | 12 | SOLUSDT, PENDING | context |
| data/recorder/2026-03-04/SOLUSDT_900.csv | regime | 12 | PENDING, None | context |
| data/recorder/2026-03-04/SOLUSDT_900.csv | tf_sec | 12 | 900, 0.0 | context |
| data/recorder/2026-03-04/XRPUSDT_180.csv | symbol | 3 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-04/XRPUSDT_180.csv | regime | 3 | UNCERTAIN, PENDING, True | context |
| data/recorder/2026-03-04/XRPUSDT_180.csv | tf_sec | 3 | 180, XRPUSDT | context |
| data/recorder/2026-03-04/XRPUSDT_300.csv | symbol | 4 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-04/XRPUSDT_300.csv | regime | 4 | PENDING, True | context |
| data/recorder/2026-03-04/XRPUSDT_300.csv | tf_sec | 4 | 300, XRPUSDT | context |
| data/recorder/2026-03-04/XRPUSDT_900.csv | symbol | 12 | XRPUSDT, PENDING | context |
| data/recorder/2026-03-04/XRPUSDT_900.csv | regime | 12 | PENDING, None | context |
| data/recorder/2026-03-04/XRPUSDT_900.csv | tf_sec | 12 | 900, 0.0 | context |
| data/recorder/2026-03-05/BNBUSDT_180.csv | symbol | 15 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-05/BNBUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-05/BNBUSDT_180.csv | tf_sec | 15 | 180, BNBUSDT | context |
| data/recorder/2026-03-05/BNBUSDT_300.csv | symbol | 15 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-05/BNBUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-05/BNBUSDT_300.csv | tf_sec | 15 | 300, BNBUSDT | context |
| data/recorder/2026-03-05/BNBUSDT_900.csv | symbol | 15 | BNBUSDT, PENDING | context |
| data/recorder/2026-03-05/BNBUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-05/BNBUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-05/BTCUSDT_180.csv | symbol | 15 | BTCUSDT, 0.0 | context |
| data/recorder/2026-03-05/BTCUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-05/BTCUSDT_180.csv | tf_sec | 15 | 180, BTCUSDT | context |
| data/recorder/2026-03-05/BTCUSDT_300.csv | symbol | 15 | BTCUSDT, 0.0 | context |
| data/recorder/2026-03-05/BTCUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-05/BTCUSDT_300.csv | tf_sec | 15 | 300, BTCUSDT | context |
| data/recorder/2026-03-05/BTCUSDT_900.csv | symbol | 15 | BTCUSDT, PENDING | context |
| data/recorder/2026-03-05/BTCUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-05/BTCUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-05/DOGEUSDT_180.csv | symbol | 15 | DOGEUSDT, 0.0 | context |
| data/recorder/2026-03-05/DOGEUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-05/DOGEUSDT_180.csv | tf_sec | 15 | 180, DOGEUSDT | context |
| data/recorder/2026-03-05/DOGEUSDT_300.csv | symbol | 15 | DOGEUSDT, 0.0 | context |
| data/recorder/2026-03-05/DOGEUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-05/DOGEUSDT_300.csv | tf_sec | 15 | 300, DOGEUSDT | context |
| data/recorder/2026-03-05/DOGEUSDT_900.csv | symbol | 15 | DOGEUSDT, PENDING | context |
| data/recorder/2026-03-05/DOGEUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-05/DOGEUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-05/ETHUSDT_180.csv | symbol | 15 | ETHUSDT, 0.0 | context |
| data/recorder/2026-03-05/ETHUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-05/ETHUSDT_180.csv | tf_sec | 15 | 180, ETHUSDT | context |
| data/recorder/2026-03-05/ETHUSDT_300.csv | symbol | 15 | ETHUSDT, 0.0 | context |
| data/recorder/2026-03-05/ETHUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-05/ETHUSDT_300.csv | tf_sec | 15 | 300, ETHUSDT | context |
| data/recorder/2026-03-05/ETHUSDT_900.csv | symbol | 15 | ETHUSDT, PENDING | context |
| data/recorder/2026-03-05/ETHUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-05/ETHUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-05/SOLUSDT_180.csv | symbol | 15 | SOLUSDT, 0.0 | context |
| data/recorder/2026-03-05/SOLUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-05/SOLUSDT_180.csv | tf_sec | 15 | 180, SOLUSDT | context |
| data/recorder/2026-03-05/SOLUSDT_300.csv | symbol | 15 | SOLUSDT, 0.0 | context |
| data/recorder/2026-03-05/SOLUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-05/SOLUSDT_300.csv | tf_sec | 15 | 300, SOLUSDT | context |
| data/recorder/2026-03-05/SOLUSDT_900.csv | symbol | 15 | SOLUSDT, PENDING | context |
| data/recorder/2026-03-05/SOLUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-05/SOLUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-05/XRPUSDT_180.csv | symbol | 15 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-05/XRPUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-05/XRPUSDT_180.csv | tf_sec | 15 | 180, XRPUSDT | context |
| data/recorder/2026-03-05/XRPUSDT_300.csv | symbol | 15 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-05/XRPUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-05/XRPUSDT_300.csv | tf_sec | 15 | 300, XRPUSDT | context |
| data/recorder/2026-03-05/XRPUSDT_900.csv | symbol | 15 | XRPUSDT, PENDING | context |
| data/recorder/2026-03-05/XRPUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-05/XRPUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-06/BNBUSDT_180.csv | symbol | 15 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-06/BNBUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-06/BNBUSDT_180.csv | tf_sec | 15 | 180, BNBUSDT | context |
| data/recorder/2026-03-06/BNBUSDT_300.csv | symbol | 15 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-06/BNBUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-06/BNBUSDT_300.csv | tf_sec | 15 | 300, BNBUSDT | context |
| data/recorder/2026-03-06/BNBUSDT_900.csv | symbol | 15 | BNBUSDT, PENDING | context |
| data/recorder/2026-03-06/BNBUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-06/BNBUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-06/BTCUSDT_180.csv | symbol | 15 | BTCUSDT, 0.0 | context |
| data/recorder/2026-03-06/BTCUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-06/BTCUSDT_180.csv | tf_sec | 15 | 180, BTCUSDT | context |
| data/recorder/2026-03-06/BTCUSDT_300.csv | symbol | 15 | BTCUSDT, 0.0 | context |
| data/recorder/2026-03-06/BTCUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-06/BTCUSDT_300.csv | tf_sec | 15 | 300, BTCUSDT | context |
| data/recorder/2026-03-06/BTCUSDT_900.csv | symbol | 15 | BTCUSDT, PENDING | context |
| data/recorder/2026-03-06/BTCUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-06/BTCUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-06/DOGEUSDT_180.csv | symbol | 15 | DOGEUSDT, 0.0 | context |
| data/recorder/2026-03-06/DOGEUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-06/DOGEUSDT_180.csv | tf_sec | 15 | 180, DOGEUSDT | context |
| data/recorder/2026-03-06/DOGEUSDT_300.csv | symbol | 15 | DOGEUSDT, 0.0 | context |
| data/recorder/2026-03-06/DOGEUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-06/DOGEUSDT_300.csv | tf_sec | 15 | 300, DOGEUSDT | context |
| data/recorder/2026-03-06/DOGEUSDT_900.csv | symbol | 15 | DOGEUSDT, PENDING | context |
| data/recorder/2026-03-06/DOGEUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-06/DOGEUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-06/ETHUSDT_180.csv | symbol | 15 | ETHUSDT, 0.0 | context |
| data/recorder/2026-03-06/ETHUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-06/ETHUSDT_180.csv | tf_sec | 15 | 180, ETHUSDT | context |
| data/recorder/2026-03-06/ETHUSDT_300.csv | symbol | 15 | ETHUSDT, 0.0 | context |
| data/recorder/2026-03-06/ETHUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-06/ETHUSDT_300.csv | tf_sec | 15 | 300, ETHUSDT | context |
| data/recorder/2026-03-06/ETHUSDT_900.csv | symbol | 15 | ETHUSDT, PENDING | context |
| data/recorder/2026-03-06/ETHUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-06/ETHUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-06/SOLUSDT_180.csv | symbol | 15 | SOLUSDT, 0.0 | context |
| data/recorder/2026-03-06/SOLUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-06/SOLUSDT_180.csv | tf_sec | 15 | 180, SOLUSDT | context |
| data/recorder/2026-03-06/SOLUSDT_300.csv | symbol | 15 | SOLUSDT, 0.0 | context |
| data/recorder/2026-03-06/SOLUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-06/SOLUSDT_300.csv | tf_sec | 15 | 300, SOLUSDT | context |
| data/recorder/2026-03-06/SOLUSDT_900.csv | symbol | 15 | SOLUSDT, PENDING | context |
| data/recorder/2026-03-06/SOLUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-06/SOLUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-06/XRPUSDT_180.csv | symbol | 15 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-06/XRPUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-06/XRPUSDT_180.csv | tf_sec | 15 | 180, XRPUSDT | context |
| data/recorder/2026-03-06/XRPUSDT_300.csv | symbol | 15 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-06/XRPUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-06/XRPUSDT_300.csv | tf_sec | 15 | 300, XRPUSDT | context |
| data/recorder/2026-03-06/XRPUSDT_900.csv | symbol | 15 | XRPUSDT, PENDING | context |
| data/recorder/2026-03-06/XRPUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-06/XRPUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-07/1000PEPEUSDT_180.csv | symbol | 15 | 1000PEPEUSDT, 0.42 | context |
| data/recorder/2026-03-07/1000PEPEUSDT_180.csv | regime | 15 | PENDING, UNCERTAIN, True | context |
| data/recorder/2026-03-07/1000PEPEUSDT_180.csv | tf_sec | 15 | 180, 1000PEPEUSDT | context |
| data/recorder/2026-03-07/1000PEPEUSDT_300.csv | symbol | 15 | 1000PEPEUSDT, 0.0 | context |
| data/recorder/2026-03-07/1000PEPEUSDT_300.csv | regime | 15 | PENDING, True | context |
| data/recorder/2026-03-07/1000PEPEUSDT_300.csv | tf_sec | 15 | 300, 1000PEPEUSDT | context |
| data/recorder/2026-03-07/1000PEPEUSDT_900.csv | symbol | 15 | 1000PEPEUSDT, PENDING | context |
| data/recorder/2026-03-07/1000PEPEUSDT_900.csv | regime | 15 | PENDING, None | context |
| data/recorder/2026-03-07/1000PEPEUSDT_900.csv | tf_sec | 15 | 900, 0.0 | context |
| data/recorder/2026-03-07/BNBUSDT_180.csv | symbol | 453 | BNBUSDT, 0, 180 | context |
| data/recorder/2026-03-07/BNBUSDT_180.csv | regime | 454 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, 36 | context |
| data/recorder/2026-03-07/BNBUSDT_180.csv | tf_sec | 450 | 180, 1772906399999 | context |
| data/recorder/2026-03-07/BNBUSDT_300.csv | symbol | 266 | BNBUSDT, 0 | context |
| data/recorder/2026-03-07/BNBUSDT_300.csv | regime | 266 | PENDING, 1772907599999, 1772907899999, 1772908199999, 1772908499999 | context |
| data/recorder/2026-03-07/BNBUSDT_300.csv | tf_sec | 262 | 300 | context |
| data/recorder/2026-03-07/BNBUSDT_900.csv | symbol | 78 | BNBUSDT, 0, 180 | context |
| data/recorder/2026-03-07/BNBUSDT_900.csv | regime | 79 | PENDING, 0, 1772917199999, 1772918099999, 1772918999999 | context |
| data/recorder/2026-03-07/BNBUSDT_900.csv | tf_sec | 75 | 900, 0 | context |
| data/recorder/2026-03-07/BTCUSDT_180.csv | symbol | 453 | BTCUSDT, 0, 180 | context |
| data/recorder/2026-03-07/BTCUSDT_180.csv | regime | 454 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, 36, 1772905859999 | context |
| data/recorder/2026-03-07/BTCUSDT_180.csv | tf_sec | 450 | 180, 1772906399999 | context |
| data/recorder/2026-03-07/BTCUSDT_300.csv | symbol | 266 | BTCUSDT, 0 | context |
| data/recorder/2026-03-07/BTCUSDT_300.csv | regime | 266 | PENDING, 1772907599999, 1772907899999, 1772908199999, 1772908499999 | context |
| data/recorder/2026-03-07/BTCUSDT_300.csv | tf_sec | 262 | 300 | context |
| data/recorder/2026-03-07/BTCUSDT_900.csv | symbol | 78 | BTCUSDT, 0, 180 | context |
| data/recorder/2026-03-07/BTCUSDT_900.csv | regime | 79 | PENDING, 0, 1772917199999, 1772918099999, 1772918999999 | context |
| data/recorder/2026-03-07/BTCUSDT_900.csv | tf_sec | 75 | 900, 0 | context |
| data/recorder/2026-03-07/DOGEUSDT_180.csv | symbol | 453 | DOGEUSDT, 0, 180 | context |
| data/recorder/2026-03-07/DOGEUSDT_180.csv | regime | 454 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-03-07/DOGEUSDT_180.csv | tf_sec | 450 | 180, 1772906399999 | context |
| data/recorder/2026-03-07/DOGEUSDT_300.csv | symbol | 266 | DOGEUSDT, 0 | context |
| data/recorder/2026-03-07/DOGEUSDT_300.csv | regime | 266 | PENDING, 1772907599999, 1772907899999, 1772908199999, 1772908499999 | context |
| data/recorder/2026-03-07/DOGEUSDT_300.csv | tf_sec | 262 | 300 | context |
| data/recorder/2026-03-07/DOGEUSDT_900.csv | symbol | 78 | DOGEUSDT, 0, 180 | context |
| data/recorder/2026-03-07/DOGEUSDT_900.csv | regime | 79 | PENDING, 0, 1772917199999, 1772918099999, 1772918999999 | context |
| data/recorder/2026-03-07/DOGEUSDT_900.csv | tf_sec | 75 | 900, 0 | context |
| data/recorder/2026-03-07/ETHUSDT_180.csv | symbol | 453 | ETHUSDT, 0, 180 | context |
| data/recorder/2026-03-07/ETHUSDT_180.csv | regime | 454 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-03-07/ETHUSDT_180.csv | tf_sec | 450 | 180, 1772906399999 | context |
| data/recorder/2026-03-07/ETHUSDT_300.csv | symbol | 266 | ETHUSDT, 0 | context |
| data/recorder/2026-03-07/ETHUSDT_300.csv | regime | 266 | PENDING, 1772907599999, 1772907899999, 1772908199999, 1772908499999 | context |
| data/recorder/2026-03-07/ETHUSDT_300.csv | tf_sec | 262 | 300 | context |
| data/recorder/2026-03-07/ETHUSDT_900.csv | symbol | 78 | ETHUSDT, 0, 180 | context |
| data/recorder/2026-03-07/ETHUSDT_900.csv | regime | 79 | PENDING, 0, 1772917199999, 1772918099999, 1772918999999 | context |
| data/recorder/2026-03-07/ETHUSDT_900.csv | tf_sec | 75 | 900, 0 | context |
| data/recorder/2026-03-07/SOLUSDT_180.csv | symbol | 453 | SOLUSDT, 0, 180 | context |
| data/recorder/2026-03-07/SOLUSDT_180.csv | regime | 454 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-03-07/SOLUSDT_180.csv | tf_sec | 450 | 180, 1772906399999 | context |
| data/recorder/2026-03-07/SOLUSDT_300.csv | symbol | 266 | SOLUSDT, 0 | context |
| data/recorder/2026-03-07/SOLUSDT_300.csv | regime | 266 | PENDING, 1772907599999, 1772907899999, 1772908199999, 1772908499999 | context |
| data/recorder/2026-03-07/SOLUSDT_300.csv | tf_sec | 262 | 300 | context |
| data/recorder/2026-03-07/SOLUSDT_900.csv | symbol | 78 | SOLUSDT, 0, 180 | context |
| data/recorder/2026-03-07/SOLUSDT_900.csv | regime | 79 | PENDING, 0, 1772917199999, 1772918099999, 1772918999999 | context |
| data/recorder/2026-03-07/SOLUSDT_900.csv | tf_sec | 75 | 900, 0 | context |
| data/recorder/2026-03-07/XRPUSDT_180.csv | symbol | 453 | XRPUSDT, 0, 180 | context |
| data/recorder/2026-03-07/XRPUSDT_180.csv | regime | 454 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, 36, 1772905859999 | context |
| data/recorder/2026-03-07/XRPUSDT_180.csv | tf_sec | 450 | 180, 1772906399999 | context |
| data/recorder/2026-03-07/XRPUSDT_300.csv | symbol | 266 | XRPUSDT, 0 | context |
| data/recorder/2026-03-07/XRPUSDT_300.csv | regime | 266 | PENDING, 1772907599999, 1772907899999, 1772908199999, 1772908499999 | context |
| data/recorder/2026-03-07/XRPUSDT_300.csv | tf_sec | 262 | 300 | context |
| data/recorder/2026-03-07/XRPUSDT_900.csv | symbol | 78 | XRPUSDT, 0, 180 | context |
| data/recorder/2026-03-07/XRPUSDT_900.csv | regime | 79 | PENDING, 0, 1772917199999, 1772918099999, 1772918999999 | context |
| data/recorder/2026-03-07/XRPUSDT_900.csv | tf_sec | 75 | 900, 0 | context |
| data/recorder/2026-03-08/1000PEPEUSDT_180.csv | symbol | 462 | 1000PEPEUSDT, 0, 180 | context |
| data/recorder/2026-03-08/1000PEPEUSDT_180.csv | regime | 463 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, HIGH_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-03-08/1000PEPEUSDT_180.csv | tf_sec | 459 | 180, 1772960039999 | context |
| data/recorder/2026-03-08/1000PEPEUSDT_300.csv | symbol | 272 | 1000PEPEUSDT, 0, 300 | context |
| data/recorder/2026-03-08/1000PEPEUSDT_300.csv | regime | 273 | PENDING, 59, 1772961299999, 1772961599999, 1772961899999 | context |
| data/recorder/2026-03-08/1000PEPEUSDT_300.csv | tf_sec | 269 | 300, 1772962199999 | context |
| data/recorder/2026-03-08/1000PEPEUSDT_900.csv | symbol | 81 | 1000PEPEUSDT, 0 | context |
| data/recorder/2026-03-08/1000PEPEUSDT_900.csv | regime | 81 | PENDING, 1772970299999, 1772971199999, 1772972099999, 1772972999999 | context |
| data/recorder/2026-03-08/1000PEPEUSDT_900.csv | tf_sec | 77 | 900 | context |
| data/recorder/2026-03-08/BNBUSDT_180.csv | symbol | 462 | BNBUSDT, 0, 180 | context |
| data/recorder/2026-03-08/BNBUSDT_180.csv | regime | 463 | MEAN_REVERSION, PENDING, HIGH_VOLATILITY, LOW_VOLATILITY, 36 | context |
| data/recorder/2026-03-08/BNBUSDT_180.csv | tf_sec | 459 | 180, 1772960039999 | context |
| data/recorder/2026-03-08/BNBUSDT_300.csv | symbol | 272 | BNBUSDT, 0, 300 | context |
| data/recorder/2026-03-08/BNBUSDT_300.csv | regime | 273 | PENDING, 60, 1772961299999, 1772961599999, 1772961899999 | context |
| data/recorder/2026-03-08/BNBUSDT_300.csv | tf_sec | 269 | 300, 1772962199999 | context |
| data/recorder/2026-03-08/BNBUSDT_900.csv | symbol | 81 | BNBUSDT, 0 | context |
| data/recorder/2026-03-08/BNBUSDT_900.csv | regime | 81 | PENDING, 1772970299999, 1772971199999, 1772972099999, 1772972999999 | context |
| data/recorder/2026-03-08/BNBUSDT_900.csv | tf_sec | 77 | 900 | context |
| data/recorder/2026-03-08/BTCUSDT_180.csv | symbol | 462 | BTCUSDT, 0, 180 | context |
| data/recorder/2026-03-08/BTCUSDT_180.csv | regime | 463 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, 36 | context |
| data/recorder/2026-03-08/BTCUSDT_180.csv | tf_sec | 459 | 180, 1772960039999 | context |
| data/recorder/2026-03-08/BTCUSDT_300.csv | symbol | 272 | BTCUSDT, 0, 300 | context |
| data/recorder/2026-03-08/BTCUSDT_300.csv | regime | 273 | PENDING, 60, 1772961299999, 1772961599999, 1772961899999 | context |
| data/recorder/2026-03-08/BTCUSDT_300.csv | tf_sec | 269 | 300, 1772962199999 | context |
| data/recorder/2026-03-08/BTCUSDT_900.csv | symbol | 81 | BTCUSDT, 0 | context |
| data/recorder/2026-03-08/BTCUSDT_900.csv | regime | 81 | PENDING, 1772970299999, 1772971199999, 1772972099999, 1772972999999 | context |
| data/recorder/2026-03-08/BTCUSDT_900.csv | tf_sec | 77 | 900 | context |
| data/recorder/2026-03-08/DOGEUSDT_180.csv | symbol | 463 | DOGEUSDT, 0, 180 | context |
| data/recorder/2026-03-08/DOGEUSDT_180.csv | regime | 464 | MEAN_REVERSION, PENDING, HIGH_VOLATILITY, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-08/DOGEUSDT_180.csv | tf_sec | 460 | 180, 1772960039999 | context |
| data/recorder/2026-03-08/DOGEUSDT_300.csv | symbol | 272 | DOGEUSDT, 0, 300 | context |
| data/recorder/2026-03-08/DOGEUSDT_300.csv | regime | 273 | PENDING, 60, 1772961299999, 1772961599999, 1772961899999 | context |
| data/recorder/2026-03-08/DOGEUSDT_300.csv | tf_sec | 269 | 300, 1772962199999 | context |
| data/recorder/2026-03-08/DOGEUSDT_900.csv | symbol | 81 | DOGEUSDT, 0 | context |
| data/recorder/2026-03-08/DOGEUSDT_900.csv | regime | 81 | PENDING, 1772970299999, 1772971199999, 1772972099999, 1772972999999 | context |
| data/recorder/2026-03-08/DOGEUSDT_900.csv | tf_sec | 77 | 900 | context |
| data/recorder/2026-03-08/ETHUSDT_180.csv | symbol | 462 | ETHUSDT, 0, 180 | context |
| data/recorder/2026-03-08/ETHUSDT_180.csv | regime | 463 | MEAN_REVERSION, PENDING, HIGH_VOLATILITY, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-08/ETHUSDT_180.csv | tf_sec | 459 | 180, 1772960039999 | context |
| data/recorder/2026-03-08/ETHUSDT_300.csv | symbol | 272 | ETHUSDT, 0, 300 | context |
| data/recorder/2026-03-08/ETHUSDT_300.csv | regime | 273 | PENDING, 60, 1772961299999, 1772961599999, 1772961899999 | context |
| data/recorder/2026-03-08/ETHUSDT_300.csv | tf_sec | 269 | 300, 1772962199999 | context |
| data/recorder/2026-03-08/ETHUSDT_900.csv | symbol | 81 | ETHUSDT, 0 | context |
| data/recorder/2026-03-08/ETHUSDT_900.csv | regime | 81 | PENDING, 1772970299999, 1772971199999, 1772972099999, 1772972999999 | context |
| data/recorder/2026-03-08/ETHUSDT_900.csv | tf_sec | 77 | 900 | context |
| data/recorder/2026-03-08/SOLUSDT_180.csv | symbol | 462 | SOLUSDT, 0, 180 | context |
| data/recorder/2026-03-08/SOLUSDT_180.csv | regime | 463 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, 36 | context |
| data/recorder/2026-03-08/SOLUSDT_180.csv | tf_sec | 459 | 180, 1772960039999 | context |
| data/recorder/2026-03-08/SOLUSDT_300.csv | symbol | 272 | SOLUSDT, 0, 300 | context |
| data/recorder/2026-03-08/SOLUSDT_300.csv | regime | 273 | PENDING, 60, 1772961299999, 1772961599999, 1772961899999 | context |
| data/recorder/2026-03-08/SOLUSDT_300.csv | tf_sec | 269 | 300, 1772962199999 | context |
| data/recorder/2026-03-08/SOLUSDT_900.csv | symbol | 81 | SOLUSDT, 0 | context |
| data/recorder/2026-03-08/SOLUSDT_900.csv | regime | 81 | PENDING, 1772970299999, 1772971199999, 1772972099999, 1772972999999 | context |
| data/recorder/2026-03-08/SOLUSDT_900.csv | tf_sec | 77 | 900 | context |
| data/recorder/2026-03-08/XRPUSDT_180.csv | symbol | 462 | XRPUSDT, 0, 180 | context |
| data/recorder/2026-03-08/XRPUSDT_180.csv | regime | 463 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-03-08/XRPUSDT_180.csv | tf_sec | 459 | 180, 1772960039999 | context |
| data/recorder/2026-03-08/XRPUSDT_300.csv | symbol | 272 | XRPUSDT, 0, 300 | context |
| data/recorder/2026-03-08/XRPUSDT_300.csv | regime | 273 | PENDING, 59, 1772961299999, 1772961599999, 1772961899999 | context |
| data/recorder/2026-03-08/XRPUSDT_300.csv | tf_sec | 269 | 300, 1772962199999 | context |
| data/recorder/2026-03-08/XRPUSDT_900.csv | symbol | 81 | XRPUSDT, 0 | context |
| data/recorder/2026-03-08/XRPUSDT_900.csv | regime | 81 | PENDING, 1772970299999, 1772971199999, 1772972099999, 1772972999999 | context |
| data/recorder/2026-03-08/XRPUSDT_900.csv | tf_sec | 77 | 900 | context |
| data/recorder/2026-03-09/1000PEPEUSDT_180.csv | symbol | 213 | 1000PEPEUSDT | context |
| data/recorder/2026-03-09/1000PEPEUSDT_180.csv | regime | 213 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-09/1000PEPEUSDT_180.csv | tf_sec | 213 | 180 | context |
| data/recorder/2026-03-09/1000PEPEUSDT_300.csv | symbol | 128 | 1000PEPEUSDT | context |
| data/recorder/2026-03-09/1000PEPEUSDT_300.csv | regime | 128 | PENDING | context |
| data/recorder/2026-03-09/1000PEPEUSDT_300.csv | tf_sec | 128 | 300 | context |
| data/recorder/2026-03-09/1000PEPEUSDT_900.csv | symbol | 43 | 1000PEPEUSDT | context |
| data/recorder/2026-03-09/1000PEPEUSDT_900.csv | regime | 43 | PENDING | context |
| data/recorder/2026-03-09/1000PEPEUSDT_900.csv | tf_sec | 43 | 900 | context |
| data/recorder/2026-03-09/BNBUSDT_180.csv | symbol | 213 | BNBUSDT | context |
| data/recorder/2026-03-09/BNBUSDT_180.csv | regime | 213 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-03-09/BNBUSDT_180.csv | tf_sec | 213 | 180 | context |
| data/recorder/2026-03-09/BNBUSDT_300.csv | symbol | 128 | BNBUSDT | context |
| data/recorder/2026-03-09/BNBUSDT_300.csv | regime | 128 | PENDING | context |
| data/recorder/2026-03-09/BNBUSDT_300.csv | tf_sec | 128 | 300 | context |
| data/recorder/2026-03-09/BNBUSDT_900.csv | symbol | 43 | BNBUSDT | context |
| data/recorder/2026-03-09/BNBUSDT_900.csv | regime | 43 | PENDING | context |
| data/recorder/2026-03-09/BNBUSDT_900.csv | tf_sec | 43 | 900 | context |
| data/recorder/2026-03-09/BTCUSDT_180.csv | symbol | 213 | BTCUSDT | context |
| data/recorder/2026-03-09/BTCUSDT_180.csv | regime | 213 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-03-09/BTCUSDT_180.csv | tf_sec | 213 | 180 | context |
| data/recorder/2026-03-09/BTCUSDT_300.csv | symbol | 128 | BTCUSDT | context |
| data/recorder/2026-03-09/BTCUSDT_300.csv | regime | 128 | PENDING | context |
| data/recorder/2026-03-09/BTCUSDT_300.csv | tf_sec | 128 | 300 | context |
| data/recorder/2026-03-09/BTCUSDT_900.csv | symbol | 43 | BTCUSDT | context |
| data/recorder/2026-03-09/BTCUSDT_900.csv | regime | 43 | PENDING | context |
| data/recorder/2026-03-09/BTCUSDT_900.csv | tf_sec | 43 | 900 | context |
| data/recorder/2026-03-09/DOGEUSDT_180.csv | symbol | 212 | DOGEUSDT | context |
| data/recorder/2026-03-09/DOGEUSDT_180.csv | regime | 212 | PENDING, LOW_VOLATILITY, UNCERTAIN, HIGH_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-09/DOGEUSDT_180.csv | tf_sec | 212 | 180 | context |
| data/recorder/2026-03-09/DOGEUSDT_300.csv | symbol | 128 | DOGEUSDT | context |
| data/recorder/2026-03-09/DOGEUSDT_300.csv | regime | 128 | PENDING | context |
| data/recorder/2026-03-09/DOGEUSDT_300.csv | tf_sec | 128 | 300 | context |
| data/recorder/2026-03-09/DOGEUSDT_900.csv | symbol | 43 | DOGEUSDT | context |
| data/recorder/2026-03-09/DOGEUSDT_900.csv | regime | 43 | PENDING | context |
| data/recorder/2026-03-09/DOGEUSDT_900.csv | tf_sec | 43 | 900 | context |
| data/recorder/2026-03-09/ETHUSDT_180.csv | symbol | 213 | ETHUSDT | context |
| data/recorder/2026-03-09/ETHUSDT_180.csv | regime | 213 | MEAN_REVERSION, PENDING, UNCERTAIN, HIGH_VOLATILITY, LOW_VOLATILITY | context |
| data/recorder/2026-03-09/ETHUSDT_180.csv | tf_sec | 213 | 180 | context |
| data/recorder/2026-03-09/ETHUSDT_300.csv | symbol | 128 | ETHUSDT | context |
| data/recorder/2026-03-09/ETHUSDT_300.csv | regime | 128 | PENDING | context |
| data/recorder/2026-03-09/ETHUSDT_300.csv | tf_sec | 128 | 300 | context |
| data/recorder/2026-03-09/ETHUSDT_900.csv | symbol | 43 | ETHUSDT | context |
| data/recorder/2026-03-09/ETHUSDT_900.csv | regime | 43 | PENDING | context |
| data/recorder/2026-03-09/ETHUSDT_900.csv | tf_sec | 43 | 900 | context |
| data/recorder/2026-03-09/SOLUSDT_180.csv | symbol | 213 | SOLUSDT | context |
| data/recorder/2026-03-09/SOLUSDT_180.csv | regime | 213 | UNCERTAIN, PENDING, LOW_VOLATILITY | context |
| data/recorder/2026-03-09/SOLUSDT_180.csv | tf_sec | 213 | 180 | context |
| data/recorder/2026-03-09/SOLUSDT_300.csv | symbol | 128 | SOLUSDT | context |
| data/recorder/2026-03-09/SOLUSDT_300.csv | regime | 128 | PENDING | context |
| data/recorder/2026-03-09/SOLUSDT_300.csv | tf_sec | 128 | 300 | context |
| data/recorder/2026-03-09/SOLUSDT_900.csv | symbol | 43 | SOLUSDT | context |
| data/recorder/2026-03-09/SOLUSDT_900.csv | regime | 43 | PENDING | context |
| data/recorder/2026-03-09/SOLUSDT_900.csv | tf_sec | 43 | 900 | context |
| data/recorder/2026-03-09/XRPUSDT_180.csv | symbol | 213 | XRPUSDT | context |
| data/recorder/2026-03-09/XRPUSDT_180.csv | regime | 213 | MEAN_REVERSION, PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-09/XRPUSDT_180.csv | tf_sec | 213 | 180 | context |
| data/recorder/2026-03-09/XRPUSDT_300.csv | symbol | 128 | XRPUSDT | context |
| data/recorder/2026-03-09/XRPUSDT_300.csv | regime | 128 | PENDING | context |
| data/recorder/2026-03-09/XRPUSDT_300.csv | tf_sec | 128 | 300 | context |
| data/recorder/2026-03-09/XRPUSDT_900.csv | symbol | 43 | XRPUSDT | context |
| data/recorder/2026-03-09/XRPUSDT_900.csv | regime | 43 | PENDING | context |
| data/recorder/2026-03-09/XRPUSDT_900.csv | tf_sec | 43 | 900 | context |
| data/recorder/2026-03-10/1000PEPEUSDT_180.csv | symbol | 13 | 1000PEPEUSDT | context |
| data/recorder/2026-03-10/1000PEPEUSDT_180.csv | regime | 13 | PENDING, UNCERTAIN | context |
| data/recorder/2026-03-10/1000PEPEUSDT_180.csv | tf_sec | 13 | 180 | context |
| data/recorder/2026-03-10/1000PEPEUSDT_300.csv | symbol | 7 | 1000PEPEUSDT | context |
| data/recorder/2026-03-10/1000PEPEUSDT_300.csv | regime | 7 | PENDING | context |
| data/recorder/2026-03-10/1000PEPEUSDT_300.csv | tf_sec | 7 | 300 | context |
| data/recorder/2026-03-10/1000PEPEUSDT_900.csv | symbol | 2 | 1000PEPEUSDT | context |
| data/recorder/2026-03-10/1000PEPEUSDT_900.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-10/1000PEPEUSDT_900.csv | tf_sec | 2 | 900 | context |
| data/recorder/2026-03-10/BNBUSDT_180.csv | symbol | 13 | BNBUSDT | context |
| data/recorder/2026-03-10/BNBUSDT_180.csv | regime | 13 | PENDING, UNCERTAIN | context |
| data/recorder/2026-03-10/BNBUSDT_180.csv | tf_sec | 13 | 180 | context |
| data/recorder/2026-03-10/BNBUSDT_300.csv | symbol | 7 | BNBUSDT | context |
| data/recorder/2026-03-10/BNBUSDT_300.csv | regime | 7 | PENDING | context |
| data/recorder/2026-03-10/BNBUSDT_300.csv | tf_sec | 7 | 300 | context |
| data/recorder/2026-03-10/BNBUSDT_900.csv | symbol | 2 | BNBUSDT | context |
| data/recorder/2026-03-10/BNBUSDT_900.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-10/BNBUSDT_900.csv | tf_sec | 2 | 900 | context |
| data/recorder/2026-03-10/BTCUSDT_180.csv | symbol | 13 | BTCUSDT | context |
| data/recorder/2026-03-10/BTCUSDT_180.csv | regime | 13 | PENDING, UNCERTAIN | context |
| data/recorder/2026-03-10/BTCUSDT_180.csv | tf_sec | 13 | 180 | context |
| data/recorder/2026-03-10/BTCUSDT_300.csv | symbol | 7 | BTCUSDT | context |
| data/recorder/2026-03-10/BTCUSDT_300.csv | regime | 7 | PENDING | context |
| data/recorder/2026-03-10/BTCUSDT_300.csv | tf_sec | 7 | 300 | context |
| data/recorder/2026-03-10/BTCUSDT_900.csv | symbol | 2 | BTCUSDT | context |
| data/recorder/2026-03-10/BTCUSDT_900.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-10/BTCUSDT_900.csv | tf_sec | 2 | 900 | context |
| data/recorder/2026-03-10/DOGEUSDT_180.csv | symbol | 13 | DOGEUSDT | context |
| data/recorder/2026-03-10/DOGEUSDT_180.csv | regime | 13 | PENDING, UNCERTAIN | context |
| data/recorder/2026-03-10/DOGEUSDT_180.csv | tf_sec | 13 | 180 | context |
| data/recorder/2026-03-10/DOGEUSDT_300.csv | symbol | 7 | DOGEUSDT | context |
| data/recorder/2026-03-10/DOGEUSDT_300.csv | regime | 7 | PENDING | context |
| data/recorder/2026-03-10/DOGEUSDT_300.csv | tf_sec | 7 | 300 | context |
| data/recorder/2026-03-10/DOGEUSDT_900.csv | symbol | 2 | DOGEUSDT | context |
| data/recorder/2026-03-10/DOGEUSDT_900.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-10/DOGEUSDT_900.csv | tf_sec | 2 | 900 | context |
| data/recorder/2026-03-10/ETHUSDT_180.csv | symbol | 13 | ETHUSDT | context |
| data/recorder/2026-03-10/ETHUSDT_180.csv | regime | 13 | PENDING, UNCERTAIN | context |
| data/recorder/2026-03-10/ETHUSDT_180.csv | tf_sec | 13 | 180 | context |
| data/recorder/2026-03-10/ETHUSDT_300.csv | symbol | 7 | ETHUSDT | context |
| data/recorder/2026-03-10/ETHUSDT_300.csv | regime | 7 | PENDING | context |
| data/recorder/2026-03-10/ETHUSDT_300.csv | tf_sec | 7 | 300 | context |
| data/recorder/2026-03-10/ETHUSDT_900.csv | symbol | 2 | ETHUSDT | context |
| data/recorder/2026-03-10/ETHUSDT_900.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-10/ETHUSDT_900.csv | tf_sec | 2 | 900 | context |
| data/recorder/2026-03-10/SOLUSDT_180.csv | symbol | 13 | SOLUSDT | context |
| data/recorder/2026-03-10/SOLUSDT_180.csv | regime | 13 | PENDING, UNCERTAIN | context |
| data/recorder/2026-03-10/SOLUSDT_180.csv | tf_sec | 13 | 180 | context |
| data/recorder/2026-03-10/SOLUSDT_300.csv | symbol | 3 | SOLUSDT, True | context |
| data/recorder/2026-03-10/SOLUSDT_300.csv | regime | 3 | PENDING, None | context |
| data/recorder/2026-03-10/SOLUSDT_300.csv | tf_sec | 3 | 300, PENDING | context |
| data/recorder/2026-03-10/SOLUSDT_900.csv | symbol | 2 | SOLUSDT | context |
| data/recorder/2026-03-10/SOLUSDT_900.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-10/SOLUSDT_900.csv | tf_sec | 2 | 900 | context |
| data/recorder/2026-03-10/XRPUSDT_180.csv | symbol | 13 | XRPUSDT | context |
| data/recorder/2026-03-10/XRPUSDT_180.csv | regime | 13 | PENDING, UNCERTAIN | context |
| data/recorder/2026-03-10/XRPUSDT_180.csv | tf_sec | 13 | 180 | context |
| data/recorder/2026-03-10/XRPUSDT_300.csv | symbol | 7 | XRPUSDT | context |
| data/recorder/2026-03-10/XRPUSDT_300.csv | regime | 7 | PENDING | context |
| data/recorder/2026-03-10/XRPUSDT_300.csv | tf_sec | 7 | 300 | context |
| data/recorder/2026-03-10/XRPUSDT_900.csv | symbol | 2 | XRPUSDT | context |
| data/recorder/2026-03-10/XRPUSDT_900.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-10/XRPUSDT_900.csv | tf_sec | 2 | 900 | context |
| data/recorder/2026-03-11/1000PEPEUSDT_180.csv | symbol | 2 | 1000PEPEUSDT | context |
| data/recorder/2026-03-11/1000PEPEUSDT_180.csv | regime | 2 | UNCERTAIN, PENDING | context |
| data/recorder/2026-03-11/1000PEPEUSDT_180.csv | tf_sec | 2 | 180 | context |
| data/recorder/2026-03-11/1000PEPEUSDT_300.csv | symbol | 2 | 1000PEPEUSDT | context |
| data/recorder/2026-03-11/1000PEPEUSDT_300.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-11/1000PEPEUSDT_300.csv | tf_sec | 2 | 300 | context |
| data/recorder/2026-03-11/1000PEPEUSDT_900.csv | symbol | 1 | 1000PEPEUSDT | context |
| data/recorder/2026-03-11/1000PEPEUSDT_900.csv | regime | 1 | PENDING | context |
| data/recorder/2026-03-11/1000PEPEUSDT_900.csv | tf_sec | 1 | 900 | context |
| data/recorder/2026-03-11/BNBUSDT_180.csv | symbol | 2 | BNBUSDT | context |
| data/recorder/2026-03-11/BNBUSDT_180.csv | regime | 2 | UNCERTAIN, PENDING | context |
| data/recorder/2026-03-11/BNBUSDT_180.csv | tf_sec | 2 | 180 | context |
| data/recorder/2026-03-11/BNBUSDT_300.csv | symbol | 2 | BNBUSDT | context |
| data/recorder/2026-03-11/BNBUSDT_300.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-11/BNBUSDT_300.csv | tf_sec | 2 | 300 | context |
| data/recorder/2026-03-11/BNBUSDT_900.csv | symbol | 1 | BNBUSDT | context |
| data/recorder/2026-03-11/BNBUSDT_900.csv | regime | 1 | PENDING | context |
| data/recorder/2026-03-11/BNBUSDT_900.csv | tf_sec | 1 | 900 | context |
| data/recorder/2026-03-11/BTCUSDT_180.csv | symbol | 2 | BTCUSDT | context |
| data/recorder/2026-03-11/BTCUSDT_180.csv | regime | 2 | UNCERTAIN, PENDING | context |
| data/recorder/2026-03-11/BTCUSDT_180.csv | tf_sec | 2 | 180 | context |
| data/recorder/2026-03-11/BTCUSDT_300.csv | symbol | 2 | BTCUSDT | context |
| data/recorder/2026-03-11/BTCUSDT_300.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-11/BTCUSDT_300.csv | tf_sec | 2 | 300 | context |
| data/recorder/2026-03-11/BTCUSDT_900.csv | symbol | 1 | BTCUSDT | context |
| data/recorder/2026-03-11/BTCUSDT_900.csv | regime | 1 | PENDING | context |
| data/recorder/2026-03-11/BTCUSDT_900.csv | tf_sec | 1 | 900 | context |
| data/recorder/2026-03-11/DOGEUSDT_180.csv | symbol | 2 | DOGEUSDT | context |
| data/recorder/2026-03-11/DOGEUSDT_180.csv | regime | 2 | UNCERTAIN, PENDING | context |
| data/recorder/2026-03-11/DOGEUSDT_180.csv | tf_sec | 2 | 180 | context |
| data/recorder/2026-03-11/DOGEUSDT_300.csv | symbol | 2 | DOGEUSDT | context |
| data/recorder/2026-03-11/DOGEUSDT_300.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-11/DOGEUSDT_300.csv | tf_sec | 2 | 300 | context |
| data/recorder/2026-03-11/DOGEUSDT_900.csv | symbol | 1 | DOGEUSDT | context |
| data/recorder/2026-03-11/DOGEUSDT_900.csv | regime | 1 | PENDING | context |
| data/recorder/2026-03-11/DOGEUSDT_900.csv | tf_sec | 1 | 900 | context |
| data/recorder/2026-03-11/ETHUSDT_180.csv | symbol | 2 | ETHUSDT | context |
| data/recorder/2026-03-11/ETHUSDT_180.csv | regime | 2 | UNCERTAIN, PENDING | context |
| data/recorder/2026-03-11/ETHUSDT_180.csv | tf_sec | 2 | 180 | context |
| data/recorder/2026-03-11/ETHUSDT_300.csv | symbol | 2 | ETHUSDT | context |
| data/recorder/2026-03-11/ETHUSDT_300.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-11/ETHUSDT_300.csv | tf_sec | 2 | 300 | context |
| data/recorder/2026-03-11/ETHUSDT_900.csv | symbol | 1 | ETHUSDT | context |
| data/recorder/2026-03-11/ETHUSDT_900.csv | regime | 1 | PENDING | context |
| data/recorder/2026-03-11/ETHUSDT_900.csv | tf_sec | 1 | 900 | context |
| data/recorder/2026-03-11/SOLUSDT_180.csv | symbol | 2 | SOLUSDT | context |
| data/recorder/2026-03-11/SOLUSDT_180.csv | regime | 2 | UNCERTAIN, PENDING | context |
| data/recorder/2026-03-11/SOLUSDT_180.csv | tf_sec | 2 | 180 | context |
| data/recorder/2026-03-11/SOLUSDT_300.csv | symbol | 2 | SOLUSDT | context |
| data/recorder/2026-03-11/SOLUSDT_300.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-11/SOLUSDT_300.csv | tf_sec | 2 | 300 | context |
| data/recorder/2026-03-11/SOLUSDT_900.csv | symbol | 1 | SOLUSDT | context |
| data/recorder/2026-03-11/SOLUSDT_900.csv | regime | 1 | PENDING | context |
| data/recorder/2026-03-11/SOLUSDT_900.csv | tf_sec | 1 | 900 | context |
| data/recorder/2026-03-11/XRPUSDT_180.csv | symbol | 2 | XRPUSDT | context |
| data/recorder/2026-03-11/XRPUSDT_180.csv | regime | 2 | UNCERTAIN, PENDING | context |
| data/recorder/2026-03-11/XRPUSDT_180.csv | tf_sec | 2 | 180 | context |
| data/recorder/2026-03-11/XRPUSDT_300.csv | symbol | 2 | XRPUSDT | context |
| data/recorder/2026-03-11/XRPUSDT_300.csv | regime | 2 | PENDING | context |
| data/recorder/2026-03-11/XRPUSDT_300.csv | tf_sec | 2 | 300 | context |
| data/recorder/2026-03-11/XRPUSDT_900.csv | symbol | 1 | XRPUSDT | context |
| data/recorder/2026-03-11/XRPUSDT_900.csv | regime | 1 | PENDING | context |
| data/recorder/2026-03-11/XRPUSDT_900.csv | tf_sec | 1 | 900 | context |
| data/recorder/2026-03-12/1000PEPEUSDT_180.csv | symbol | 151 | 1000PEPEUSDT, None | context |
| data/recorder/2026-03-12/1000PEPEUSDT_180.csv | regime | 151 | PENDING, UNCERTAIN, 0.00332505 | context |
| data/recorder/2026-03-12/1000PEPEUSDT_180.csv | tf_sec | 151 | 180, False | context |
| data/recorder/2026-03-12/1000PEPEUSDT_300.csv | symbol | 91 | 1000PEPEUSDT, None | context |
| data/recorder/2026-03-12/1000PEPEUSDT_300.csv | regime | 91 | PENDING, 0.00332505 | context |
| data/recorder/2026-03-12/1000PEPEUSDT_300.csv | tf_sec | 91 | 300, False | context |
| data/recorder/2026-03-12/1000PEPEUSDT_900.csv | symbol | 32 | 1000PEPEUSDT, None | context |
| data/recorder/2026-03-12/1000PEPEUSDT_900.csv | regime | 32 | PENDING, 0.00332505 | context |
| data/recorder/2026-03-12/1000PEPEUSDT_900.csv | tf_sec | 32 | 900, False | context |
| data/recorder/2026-03-12/BNBUSDT_180.csv | symbol | 151 | BNBUSDT, None | context |
| data/recorder/2026-03-12/BNBUSDT_180.csv | regime | 151 | PENDING, UNCERTAIN, 651.555 | context |
| data/recorder/2026-03-12/BNBUSDT_180.csv | tf_sec | 151 | 180, False | context |
| data/recorder/2026-03-12/BNBUSDT_300.csv | symbol | 91 | BNBUSDT, None | context |
| data/recorder/2026-03-12/BNBUSDT_300.csv | regime | 91 | PENDING, 651.555 | context |
| data/recorder/2026-03-12/BNBUSDT_300.csv | tf_sec | 91 | 300, False | context |
| data/recorder/2026-03-12/BNBUSDT_900.csv | symbol | 32 | BNBUSDT, None | context |
| data/recorder/2026-03-12/BNBUSDT_900.csv | regime | 32 | PENDING, 651.555 | context |
| data/recorder/2026-03-12/BNBUSDT_900.csv | tf_sec | 32 | 900, False | context |
| data/recorder/2026-03-12/BTCUSDT_180.csv | symbol | 151 | BTCUSDT, None | context |
| data/recorder/2026-03-12/BTCUSDT_180.csv | regime | 151 | PENDING, UNCERTAIN, 70280.05 | context |
| data/recorder/2026-03-12/BTCUSDT_180.csv | tf_sec | 151 | 180, False | context |
| data/recorder/2026-03-12/BTCUSDT_300.csv | symbol | 91 | BTCUSDT, None | context |
| data/recorder/2026-03-12/BTCUSDT_300.csv | regime | 91 | PENDING, 70280.05 | context |
| data/recorder/2026-03-12/BTCUSDT_300.csv | tf_sec | 91 | 300, False | context |
| data/recorder/2026-03-12/BTCUSDT_900.csv | symbol | 32 | BTCUSDT, None | context |
| data/recorder/2026-03-12/BTCUSDT_900.csv | regime | 32 | PENDING, 70280.05 | context |
| data/recorder/2026-03-12/BTCUSDT_900.csv | tf_sec | 32 | 900, False | context |
| data/recorder/2026-03-12/DOGEUSDT_180.csv | symbol | 151 | DOGEUSDT, None | context |
| data/recorder/2026-03-12/DOGEUSDT_180.csv | regime | 151 | PENDING, UNCERTAIN, 0.094115 | context |
| data/recorder/2026-03-12/DOGEUSDT_180.csv | tf_sec | 151 | 180, False | context |
| data/recorder/2026-03-12/DOGEUSDT_300.csv | symbol | 91 | DOGEUSDT, None | context |
| data/recorder/2026-03-12/DOGEUSDT_300.csv | regime | 91 | PENDING, 0.094115 | context |
| data/recorder/2026-03-12/DOGEUSDT_300.csv | tf_sec | 91 | 300, False | context |
| data/recorder/2026-03-12/DOGEUSDT_900.csv | symbol | 32 | DOGEUSDT, None | context |
| data/recorder/2026-03-12/DOGEUSDT_900.csv | regime | 32 | PENDING, 0.094115 | context |
| data/recorder/2026-03-12/DOGEUSDT_900.csv | tf_sec | 32 | 900, False | context |
| data/recorder/2026-03-12/ETHUSDT_180.csv | symbol | 151 | ETHUSDT, None | context |
| data/recorder/2026-03-12/ETHUSDT_180.csv | regime | 151 | PENDING, UNCERTAIN, 2069.945 | context |
| data/recorder/2026-03-12/ETHUSDT_180.csv | tf_sec | 151 | 180, False | context |
| data/recorder/2026-03-12/ETHUSDT_300.csv | symbol | 91 | ETHUSDT, None | context |
| data/recorder/2026-03-12/ETHUSDT_300.csv | regime | 91 | PENDING, 2069.945 | context |
| data/recorder/2026-03-12/ETHUSDT_300.csv | tf_sec | 91 | 300, False | context |
| data/recorder/2026-03-12/ETHUSDT_900.csv | symbol | 32 | ETHUSDT, None | context |
| data/recorder/2026-03-12/ETHUSDT_900.csv | regime | 32 | PENDING, 2069.945 | context |
| data/recorder/2026-03-12/ETHUSDT_900.csv | tf_sec | 32 | 900, False | context |
| data/recorder/2026-03-12/SOLUSDT_180.csv | symbol | 151 | SOLUSDT, None | context |
| data/recorder/2026-03-12/SOLUSDT_180.csv | regime | 151 | PENDING, UNCERTAIN, 86.6450 | context |
| data/recorder/2026-03-12/SOLUSDT_180.csv | tf_sec | 151 | 180, False | context |
| data/recorder/2026-03-12/SOLUSDT_300.csv | symbol | 91 | SOLUSDT, None | context |
| data/recorder/2026-03-12/SOLUSDT_300.csv | regime | 91 | PENDING, 86.6450 | context |
| data/recorder/2026-03-12/SOLUSDT_300.csv | tf_sec | 91 | 300, False | context |
| data/recorder/2026-03-12/SOLUSDT_900.csv | symbol | 32 | SOLUSDT, None | context |
| data/recorder/2026-03-12/SOLUSDT_900.csv | regime | 32 | PENDING, 86.6450 | context |
| data/recorder/2026-03-12/SOLUSDT_900.csv | tf_sec | 32 | 900, False | context |
| data/recorder/2026-03-12/XRPUSDT_180.csv | symbol | 151 | XRPUSDT, None | context |
| data/recorder/2026-03-12/XRPUSDT_180.csv | regime | 151 | PENDING, UNCERTAIN, 1.38795 | context |
| data/recorder/2026-03-12/XRPUSDT_180.csv | tf_sec | 151 | 180, False | context |
| data/recorder/2026-03-12/XRPUSDT_300.csv | symbol | 91 | XRPUSDT, None | context |
| data/recorder/2026-03-12/XRPUSDT_300.csv | regime | 91 | PENDING, 1.38795 | context |
| data/recorder/2026-03-12/XRPUSDT_300.csv | tf_sec | 91 | 300, False | context |
| data/recorder/2026-03-12/XRPUSDT_900.csv | symbol | 32 | XRPUSDT, None | context |
| data/recorder/2026-03-12/XRPUSDT_900.csv | regime | 32 | PENDING, 1.38795 | context |
| data/recorder/2026-03-12/XRPUSDT_900.csv | tf_sec | 32 | 900, False | context |
| data/recorder/2026-03-13/1000PEPEUSDT_180.csv | symbol | 228 | 1000PEPEUSDT | context |
| data/recorder/2026-03-13/1000PEPEUSDT_180.csv | regime | 228 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-13/1000PEPEUSDT_180.csv | tf_sec | 228 | 180 | context |
| data/recorder/2026-03-13/1000PEPEUSDT_300.csv | symbol | 138 | 1000PEPEUSDT | context |
| data/recorder/2026-03-13/1000PEPEUSDT_300.csv | regime | 138 | PENDING | context |
| data/recorder/2026-03-13/1000PEPEUSDT_300.csv | tf_sec | 138 | 300 | context |
| data/recorder/2026-03-13/1000PEPEUSDT_900.csv | symbol | 46 | 1000PEPEUSDT | context |
| data/recorder/2026-03-13/1000PEPEUSDT_900.csv | regime | 46 | PENDING | context |
| data/recorder/2026-03-13/1000PEPEUSDT_900.csv | tf_sec | 46 | 900 | context |
| data/recorder/2026-03-13/BNBUSDT_180.csv | symbol | 228 | BNBUSDT | context |
| data/recorder/2026-03-13/BNBUSDT_180.csv | regime | 228 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-03-13/BNBUSDT_180.csv | tf_sec | 228 | 180 | context |
| data/recorder/2026-03-13/BNBUSDT_300.csv | symbol | 138 | BNBUSDT | context |
| data/recorder/2026-03-13/BNBUSDT_300.csv | regime | 138 | PENDING | context |
| data/recorder/2026-03-13/BNBUSDT_300.csv | tf_sec | 138 | 300 | context |
| data/recorder/2026-03-13/BNBUSDT_900.csv | symbol | 46 | BNBUSDT | context |
| data/recorder/2026-03-13/BNBUSDT_900.csv | regime | 46 | PENDING | context |
| data/recorder/2026-03-13/BNBUSDT_900.csv | tf_sec | 46 | 900 | context |
| data/recorder/2026-03-13/BTCUSDT_180.csv | symbol | 228 | BTCUSDT | context |
| data/recorder/2026-03-13/BTCUSDT_180.csv | regime | 228 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-03-13/BTCUSDT_180.csv | tf_sec | 228 | 180 | context |
| data/recorder/2026-03-13/BTCUSDT_300.csv | symbol | 138 | BTCUSDT | context |
| data/recorder/2026-03-13/BTCUSDT_300.csv | regime | 138 | PENDING | context |
| data/recorder/2026-03-13/BTCUSDT_300.csv | tf_sec | 138 | 300 | context |
| data/recorder/2026-03-13/BTCUSDT_900.csv | symbol | 46 | BTCUSDT | context |
| data/recorder/2026-03-13/BTCUSDT_900.csv | regime | 46 | PENDING | context |
| data/recorder/2026-03-13/BTCUSDT_900.csv | tf_sec | 46 | 900 | context |
| data/recorder/2026-03-13/DOGEUSDT_180.csv | symbol | 228 | DOGEUSDT | context |
| data/recorder/2026-03-13/DOGEUSDT_180.csv | regime | 228 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-03-13/DOGEUSDT_180.csv | tf_sec | 228 | 180 | context |
| data/recorder/2026-03-13/DOGEUSDT_300.csv | symbol | 138 | DOGEUSDT | context |
| data/recorder/2026-03-13/DOGEUSDT_300.csv | regime | 138 | PENDING | context |
| data/recorder/2026-03-13/DOGEUSDT_300.csv | tf_sec | 138 | 300 | context |
| data/recorder/2026-03-13/DOGEUSDT_900.csv | symbol | 46 | DOGEUSDT | context |
| data/recorder/2026-03-13/DOGEUSDT_900.csv | regime | 46 | PENDING | context |
| data/recorder/2026-03-13/DOGEUSDT_900.csv | tf_sec | 46 | 900 | context |
| data/recorder/2026-03-13/ETHUSDT_180.csv | symbol | 228 | ETHUSDT | context |
| data/recorder/2026-03-13/ETHUSDT_180.csv | regime | 228 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-13/ETHUSDT_180.csv | tf_sec | 228 | 180 | context |
| data/recorder/2026-03-13/ETHUSDT_300.csv | symbol | 138 | ETHUSDT | context |
| data/recorder/2026-03-13/ETHUSDT_300.csv | regime | 138 | PENDING | context |
| data/recorder/2026-03-13/ETHUSDT_300.csv | tf_sec | 138 | 300 | context |
| data/recorder/2026-03-13/ETHUSDT_900.csv | symbol | 46 | ETHUSDT | context |
| data/recorder/2026-03-13/ETHUSDT_900.csv | regime | 46 | PENDING | context |
| data/recorder/2026-03-13/ETHUSDT_900.csv | tf_sec | 46 | 900 | context |
| data/recorder/2026-03-13/SOLUSDT_180.csv | symbol | 228 | SOLUSDT | context |
| data/recorder/2026-03-13/SOLUSDT_180.csv | regime | 228 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-03-13/SOLUSDT_180.csv | tf_sec | 228 | 180 | context |
| data/recorder/2026-03-13/SOLUSDT_300.csv | symbol | 138 | SOLUSDT | context |
| data/recorder/2026-03-13/SOLUSDT_300.csv | regime | 138 | PENDING | context |
| data/recorder/2026-03-13/SOLUSDT_300.csv | tf_sec | 138 | 300 | context |
| data/recorder/2026-03-13/SOLUSDT_900.csv | symbol | 46 | SOLUSDT | context |
| data/recorder/2026-03-13/SOLUSDT_900.csv | regime | 46 | PENDING | context |
| data/recorder/2026-03-13/SOLUSDT_900.csv | tf_sec | 46 | 900 | context |
| data/recorder/2026-03-13/XRPUSDT_180.csv | symbol | 228 | XRPUSDT | context |
| data/recorder/2026-03-13/XRPUSDT_180.csv | regime | 228 | UNCERTAIN, PENDING, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-03-13/XRPUSDT_180.csv | tf_sec | 228 | 180 | context |
| data/recorder/2026-03-13/XRPUSDT_300.csv | symbol | 138 | XRPUSDT | context |
| data/recorder/2026-03-13/XRPUSDT_300.csv | regime | 138 | PENDING | context |
| data/recorder/2026-03-13/XRPUSDT_300.csv | tf_sec | 138 | 300 | context |
| data/recorder/2026-03-13/XRPUSDT_900.csv | symbol | 46 | XRPUSDT | context |
| data/recorder/2026-03-13/XRPUSDT_900.csv | regime | 46 | PENDING | context |
| data/recorder/2026-03-13/XRPUSDT_900.csv | tf_sec | 46 | 900 | context |
| data/recorder/2026-03-14/1000PEPEUSDT_180.csv | symbol | 286 | 1000PEPEUSDT | context |
| data/recorder/2026-03-14/1000PEPEUSDT_180.csv | regime | 286 | PENDING, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-03-14/1000PEPEUSDT_180.csv | tf_sec | 286 | 180 | context |
| data/recorder/2026-03-14/1000PEPEUSDT_300.csv | symbol | 170 | 1000PEPEUSDT | context |
| data/recorder/2026-03-14/1000PEPEUSDT_300.csv | regime | 170 | PENDING | context |
| data/recorder/2026-03-14/1000PEPEUSDT_300.csv | tf_sec | 170 | 300 | context |
| data/recorder/2026-03-14/1000PEPEUSDT_900.csv | symbol | 57 | 1000PEPEUSDT | context |
| data/recorder/2026-03-14/1000PEPEUSDT_900.csv | regime | 57 | PENDING | context |
| data/recorder/2026-03-14/1000PEPEUSDT_900.csv | tf_sec | 57 | 900 | context |
| data/recorder/2026-03-14/BNBUSDT_180.csv | symbol | 286 | BNBUSDT | context |
| data/recorder/2026-03-14/BNBUSDT_180.csv | regime | 286 | PENDING, UNCERTAIN, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-03-14/BNBUSDT_180.csv | tf_sec | 286 | 180 | context |
| data/recorder/2026-03-14/BNBUSDT_300.csv | symbol | 170 | BNBUSDT | context |
| data/recorder/2026-03-14/BNBUSDT_300.csv | regime | 170 | PENDING | context |
| data/recorder/2026-03-14/BNBUSDT_300.csv | tf_sec | 170 | 300 | context |
| data/recorder/2026-03-14/BNBUSDT_900.csv | symbol | 57 | BNBUSDT | context |
| data/recorder/2026-03-14/BNBUSDT_900.csv | regime | 57 | PENDING | context |
| data/recorder/2026-03-14/BNBUSDT_900.csv | tf_sec | 57 | 900 | context |
| data/recorder/2026-03-14/BTCUSDT_180.csv | symbol | 286 | BTCUSDT | context |
| data/recorder/2026-03-14/BTCUSDT_180.csv | regime | 286 | PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-14/BTCUSDT_180.csv | tf_sec | 286 | 180 | context |
| data/recorder/2026-03-14/BTCUSDT_300.csv | symbol | 170 | BTCUSDT | context |
| data/recorder/2026-03-14/BTCUSDT_300.csv | regime | 170 | PENDING | context |
| data/recorder/2026-03-14/BTCUSDT_300.csv | tf_sec | 170 | 300 | context |
| data/recorder/2026-03-14/BTCUSDT_900.csv | symbol | 57 | BTCUSDT | context |
| data/recorder/2026-03-14/BTCUSDT_900.csv | regime | 57 | PENDING | context |
| data/recorder/2026-03-14/BTCUSDT_900.csv | tf_sec | 57 | 900 | context |
| data/recorder/2026-03-14/DOGEUSDT_180.csv | symbol | 286 | DOGEUSDT | context |
| data/recorder/2026-03-14/DOGEUSDT_180.csv | regime | 286 | PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-14/DOGEUSDT_180.csv | tf_sec | 286 | 180 | context |
| data/recorder/2026-03-14/DOGEUSDT_300.csv | symbol | 170 | DOGEUSDT | context |
| data/recorder/2026-03-14/DOGEUSDT_300.csv | regime | 170 | PENDING | context |
| data/recorder/2026-03-14/DOGEUSDT_300.csv | tf_sec | 170 | 300 | context |
| data/recorder/2026-03-14/DOGEUSDT_900.csv | symbol | 57 | DOGEUSDT | context |
| data/recorder/2026-03-14/DOGEUSDT_900.csv | regime | 57 | PENDING | context |
| data/recorder/2026-03-14/DOGEUSDT_900.csv | tf_sec | 57 | 900 | context |
| data/recorder/2026-03-14/ETHUSDT_180.csv | symbol | 286 | ETHUSDT | context |
| data/recorder/2026-03-14/ETHUSDT_180.csv | regime | 286 | PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-14/ETHUSDT_180.csv | tf_sec | 286 | 180 | context |
| data/recorder/2026-03-14/ETHUSDT_300.csv | symbol | 170 | ETHUSDT | context |
| data/recorder/2026-03-14/ETHUSDT_300.csv | regime | 170 | PENDING | context |
| data/recorder/2026-03-14/ETHUSDT_300.csv | tf_sec | 170 | 300 | context |
| data/recorder/2026-03-14/ETHUSDT_900.csv | symbol | 57 | ETHUSDT | context |
| data/recorder/2026-03-14/ETHUSDT_900.csv | regime | 57 | PENDING | context |
| data/recorder/2026-03-14/ETHUSDT_900.csv | tf_sec | 57 | 900 | context |
| data/recorder/2026-03-14/SOLUSDT_180.csv | symbol | 286 | SOLUSDT | context |
| data/recorder/2026-03-14/SOLUSDT_180.csv | regime | 286 | PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-14/SOLUSDT_180.csv | tf_sec | 286 | 180 | context |
| data/recorder/2026-03-14/SOLUSDT_300.csv | symbol | 170 | SOLUSDT | context |
| data/recorder/2026-03-14/SOLUSDT_300.csv | regime | 170 | PENDING | context |
| data/recorder/2026-03-14/SOLUSDT_300.csv | tf_sec | 170 | 300 | context |
| data/recorder/2026-03-14/SOLUSDT_900.csv | symbol | 57 | SOLUSDT | context |
| data/recorder/2026-03-14/SOLUSDT_900.csv | regime | 57 | PENDING | context |
| data/recorder/2026-03-14/SOLUSDT_900.csv | tf_sec | 57 | 900 | context |
| data/recorder/2026-03-14/XRPUSDT_180.csv | symbol | 286 | XRPUSDT | context |
| data/recorder/2026-03-14/XRPUSDT_180.csv | regime | 286 | PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-14/XRPUSDT_180.csv | tf_sec | 286 | 180 | context |
| data/recorder/2026-03-14/XRPUSDT_300.csv | symbol | 170 | XRPUSDT | context |
| data/recorder/2026-03-14/XRPUSDT_300.csv | regime | 170 | PENDING | context |
| data/recorder/2026-03-14/XRPUSDT_300.csv | tf_sec | 170 | 300 | context |
| data/recorder/2026-03-14/XRPUSDT_900.csv | symbol | 57 | XRPUSDT | context |
| data/recorder/2026-03-14/XRPUSDT_900.csv | regime | 57 | PENDING | context |
| data/recorder/2026-03-14/XRPUSDT_900.csv | tf_sec | 57 | 900 | context |
| data/recorder/2026-03-15/1000PEPEUSDT_180.csv | symbol | 419 | 1000PEPEUSDT | context |
| data/recorder/2026-03-15/1000PEPEUSDT_180.csv | regime | 419 | PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-03-15/1000PEPEUSDT_180.csv | tf_sec | 419 | 180 | context |
| data/recorder/2026-03-15/1000PEPEUSDT_300.csv | symbol | 251 | 1000PEPEUSDT | context |
| data/recorder/2026-03-15/1000PEPEUSDT_300.csv | regime | 251 | PENDING | context |
| data/recorder/2026-03-15/1000PEPEUSDT_300.csv | tf_sec | 251 | 300 | context |
| data/recorder/2026-03-15/1000PEPEUSDT_900.csv | symbol | 83 | 1000PEPEUSDT | context |
| data/recorder/2026-03-15/1000PEPEUSDT_900.csv | regime | 83 | PENDING | context |
| data/recorder/2026-03-15/1000PEPEUSDT_900.csv | tf_sec | 83 | 900 | context |
| data/recorder/2026-03-15/BNBUSDT_180.csv | symbol | 419 | BNBUSDT | context |
| data/recorder/2026-03-15/BNBUSDT_180.csv | regime | 419 | PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-03-15/BNBUSDT_180.csv | tf_sec | 419 | 180 | context |
| data/recorder/2026-03-15/BNBUSDT_300.csv | symbol | 251 | BNBUSDT | context |
| data/recorder/2026-03-15/BNBUSDT_300.csv | regime | 251 | PENDING | context |
| data/recorder/2026-03-15/BNBUSDT_300.csv | tf_sec | 251 | 300 | context |
| data/recorder/2026-03-15/BNBUSDT_900.csv | symbol | 83 | BNBUSDT | context |
| data/recorder/2026-03-15/BNBUSDT_900.csv | regime | 83 | PENDING | context |
| data/recorder/2026-03-15/BNBUSDT_900.csv | tf_sec | 83 | 900 | context |
| data/recorder/2026-03-15/BTCUSDT_180.csv | symbol | 419 | BTCUSDT | context |
| data/recorder/2026-03-15/BTCUSDT_180.csv | regime | 419 | PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-03-15/BTCUSDT_180.csv | tf_sec | 419 | 180 | context |
| data/recorder/2026-03-15/BTCUSDT_300.csv | symbol | 251 | BTCUSDT | context |
| data/recorder/2026-03-15/BTCUSDT_300.csv | regime | 251 | PENDING | context |
| data/recorder/2026-03-15/BTCUSDT_300.csv | tf_sec | 251 | 300 | context |
| data/recorder/2026-03-15/BTCUSDT_900.csv | symbol | 83 | BTCUSDT | context |
| data/recorder/2026-03-15/BTCUSDT_900.csv | regime | 83 | PENDING | context |
| data/recorder/2026-03-15/BTCUSDT_900.csv | tf_sec | 83 | 900 | context |
| data/recorder/2026-03-15/DOGEUSDT_180.csv | symbol | 419 | DOGEUSDT | context |
| data/recorder/2026-03-15/DOGEUSDT_180.csv | regime | 419 | PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-03-15/DOGEUSDT_180.csv | tf_sec | 419 | 180 | context |
| data/recorder/2026-03-15/DOGEUSDT_300.csv | symbol | 251 | DOGEUSDT | context |
| data/recorder/2026-03-15/DOGEUSDT_300.csv | regime | 251 | PENDING | context |
| data/recorder/2026-03-15/DOGEUSDT_300.csv | tf_sec | 251 | 300 | context |
| data/recorder/2026-03-15/DOGEUSDT_900.csv | symbol | 83 | DOGEUSDT | context |
| data/recorder/2026-03-15/DOGEUSDT_900.csv | regime | 83 | PENDING | context |
| data/recorder/2026-03-15/DOGEUSDT_900.csv | tf_sec | 83 | 900 | context |
| data/recorder/2026-03-15/ETHUSDT_180.csv | symbol | 419 | ETHUSDT | context |
| data/recorder/2026-03-15/ETHUSDT_180.csv | regime | 419 | PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-15/ETHUSDT_180.csv | tf_sec | 419 | 180 | context |
| data/recorder/2026-03-15/ETHUSDT_300.csv | symbol | 251 | ETHUSDT | context |
| data/recorder/2026-03-15/ETHUSDT_300.csv | regime | 251 | PENDING | context |
| data/recorder/2026-03-15/ETHUSDT_300.csv | tf_sec | 251 | 300 | context |
| data/recorder/2026-03-15/ETHUSDT_900.csv | symbol | 83 | ETHUSDT | context |
| data/recorder/2026-03-15/ETHUSDT_900.csv | regime | 83 | PENDING | context |
| data/recorder/2026-03-15/ETHUSDT_900.csv | tf_sec | 83 | 900 | context |
| data/recorder/2026-03-15/SOLUSDT_180.csv | symbol | 419 | SOLUSDT | context |
| data/recorder/2026-03-15/SOLUSDT_180.csv | regime | 419 | PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-15/SOLUSDT_180.csv | tf_sec | 419 | 180 | context |
| data/recorder/2026-03-15/SOLUSDT_300.csv | symbol | 251 | SOLUSDT | context |
| data/recorder/2026-03-15/SOLUSDT_300.csv | regime | 251 | PENDING | context |
| data/recorder/2026-03-15/SOLUSDT_300.csv | tf_sec | 251 | 300 | context |
| data/recorder/2026-03-15/SOLUSDT_900.csv | symbol | 83 | SOLUSDT | context |
| data/recorder/2026-03-15/SOLUSDT_900.csv | regime | 83 | PENDING | context |
| data/recorder/2026-03-15/SOLUSDT_900.csv | tf_sec | 83 | 900 | context |
| data/recorder/2026-03-15/XRPUSDT_180.csv | symbol | 419 | XRPUSDT | context |
| data/recorder/2026-03-15/XRPUSDT_180.csv | regime | 419 | PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-15/XRPUSDT_180.csv | tf_sec | 419 | 180 | context |
| data/recorder/2026-03-15/XRPUSDT_300.csv | symbol | 251 | XRPUSDT | context |
| data/recorder/2026-03-15/XRPUSDT_300.csv | regime | 251 | PENDING | context |
| data/recorder/2026-03-15/XRPUSDT_300.csv | tf_sec | 251 | 300 | context |
| data/recorder/2026-03-15/XRPUSDT_900.csv | symbol | 83 | XRPUSDT | context |
| data/recorder/2026-03-15/XRPUSDT_900.csv | regime | 83 | PENDING | context |
| data/recorder/2026-03-15/XRPUSDT_900.csv | tf_sec | 83 | 900 | context |
| data/recorder/2026-03-16/1000PEPEUSDT_180.csv | symbol | 348 | 1000PEPEUSDT | context |
| data/recorder/2026-03-16/1000PEPEUSDT_180.csv | regime | 348 | TREND_UP, PENDING, HIGH_VOLATILITY, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-16/1000PEPEUSDT_180.csv | tf_sec | 348 | 180 | context |
| data/recorder/2026-03-16/1000PEPEUSDT_300.csv | symbol | 207 | 1000PEPEUSDT | context |
| data/recorder/2026-03-16/1000PEPEUSDT_300.csv | regime | 207 | PENDING | context |
| data/recorder/2026-03-16/1000PEPEUSDT_300.csv | tf_sec | 207 | 300 | context |
| data/recorder/2026-03-16/1000PEPEUSDT_900.csv | symbol | 69 | 1000PEPEUSDT | context |
| data/recorder/2026-03-16/1000PEPEUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-03-16/1000PEPEUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-03-16/BNBUSDT_180.csv | symbol | 348 | BNBUSDT | context |
| data/recorder/2026-03-16/BNBUSDT_180.csv | regime | 348 | HIGH_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-16/BNBUSDT_180.csv | tf_sec | 348 | 180 | context |
| data/recorder/2026-03-16/BNBUSDT_300.csv | symbol | 208 | BNBUSDT | context |
| data/recorder/2026-03-16/BNBUSDT_300.csv | regime | 208 | PENDING | context |
| data/recorder/2026-03-16/BNBUSDT_300.csv | tf_sec | 208 | 300 | context |
| data/recorder/2026-03-16/BNBUSDT_900.csv | symbol | 197 | BNBUSDT | context |
| data/recorder/2026-03-16/BNBUSDT_900.csv | regime | 197 | PENDING | context |
| data/recorder/2026-03-16/BNBUSDT_900.csv | tf_sec | 197 | 900 | context |
| data/recorder/2026-03-16/BTCUSDT_180.csv | symbol | 348 | BTCUSDT | context |
| data/recorder/2026-03-16/BTCUSDT_180.csv | regime | 348 | HIGH_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-03-16/BTCUSDT_180.csv | tf_sec | 348 | 180 | context |
| data/recorder/2026-03-16/BTCUSDT_300.csv | symbol | 765 | BTCUSDT, True | context |
| data/recorder/2026-03-16/BTCUSDT_300.csv | regime | 765 | PENDING, None | context |
| data/recorder/2026-03-16/BTCUSDT_300.csv | tf_sec | 765 | 300, PENDING | context |
| data/recorder/2026-03-16/BTCUSDT_900.csv | symbol | 69 | BTCUSDT | context |
| data/recorder/2026-03-16/BTCUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-03-16/BTCUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-03-16/DOGEUSDT_180.csv | symbol | 348 | DOGEUSDT | context |
| data/recorder/2026-03-16/DOGEUSDT_180.csv | regime | 348 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-16/DOGEUSDT_180.csv | tf_sec | 348 | 180 | context |
| data/recorder/2026-03-16/DOGEUSDT_300.csv | symbol | 810 | DOGEUSDT | context |
| data/recorder/2026-03-16/DOGEUSDT_300.csv | regime | 810 | PENDING | context |
| data/recorder/2026-03-16/DOGEUSDT_300.csv | tf_sec | 810 | 300 | context |
| data/recorder/2026-03-16/DOGEUSDT_900.csv | symbol | 69 | DOGEUSDT | context |
| data/recorder/2026-03-16/DOGEUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-03-16/DOGEUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-03-16/ETHUSDT_180.csv | symbol | 348 | ETHUSDT | context |
| data/recorder/2026-03-16/ETHUSDT_180.csv | regime | 348 | HIGH_VOLATILITY, PENDING, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-03-16/ETHUSDT_180.csv | tf_sec | 348 | 180 | context |
| data/recorder/2026-03-16/ETHUSDT_300.csv | symbol | 765 | ETHUSDT, True | context |
| data/recorder/2026-03-16/ETHUSDT_300.csv | regime | 765 | PENDING, None | context |
| data/recorder/2026-03-16/ETHUSDT_300.csv | tf_sec | 765 | 300, PENDING | context |
| data/recorder/2026-03-16/ETHUSDT_900.csv | symbol | 69 | ETHUSDT | context |
| data/recorder/2026-03-16/ETHUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-03-16/ETHUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-03-16/SOLUSDT_180.csv | symbol | 348 | SOLUSDT | context |
| data/recorder/2026-03-16/SOLUSDT_180.csv | regime | 348 | HIGH_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-16/SOLUSDT_180.csv | tf_sec | 348 | 180 | context |
| data/recorder/2026-03-16/SOLUSDT_300.csv | symbol | 765 | SOLUSDT, True | context |
| data/recorder/2026-03-16/SOLUSDT_300.csv | regime | 765 | PENDING, None | context |
| data/recorder/2026-03-16/SOLUSDT_300.csv | tf_sec | 765 | 300, PENDING | context |
| data/recorder/2026-03-16/SOLUSDT_900.csv | symbol | 69 | SOLUSDT | context |
| data/recorder/2026-03-16/SOLUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-03-16/SOLUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-03-16/XRPUSDT_180.csv | symbol | 347 | XRPUSDT | context |
| data/recorder/2026-03-16/XRPUSDT_180.csv | regime | 347 | TREND_UP, PENDING, UNCERTAIN | context |
| data/recorder/2026-03-16/XRPUSDT_180.csv | tf_sec | 347 | 180 | context |
| data/recorder/2026-03-16/XRPUSDT_300.csv | symbol | 208 | XRPUSDT | context |
| data/recorder/2026-03-16/XRPUSDT_300.csv | regime | 208 | PENDING | context |
| data/recorder/2026-03-16/XRPUSDT_300.csv | tf_sec | 208 | 300 | context |
| data/recorder/2026-03-16/XRPUSDT_900.csv | symbol | 197 | XRPUSDT | context |
| data/recorder/2026-03-16/XRPUSDT_900.csv | regime | 197 | PENDING | context |
| data/recorder/2026-03-16/XRPUSDT_900.csv | tf_sec | 197 | 900 | context |
| data/recorder/2026-03-17/1000PEPEUSDT_180.csv | symbol | 250 | 1000PEPEUSDT | context |
| data/recorder/2026-03-17/1000PEPEUSDT_180.csv | regime | 250 | LOW_VOLATILITY, PENDING, UNCERTAIN | context |
| data/recorder/2026-03-17/1000PEPEUSDT_180.csv | tf_sec | 250 | 180 | context |
| data/recorder/2026-03-17/1000PEPEUSDT_300.csv | symbol | 150 | 1000PEPEUSDT | context |
| data/recorder/2026-03-17/1000PEPEUSDT_300.csv | regime | 150 | PENDING | context |
| data/recorder/2026-03-17/1000PEPEUSDT_300.csv | tf_sec | 150 | 300 | context |
| data/recorder/2026-03-17/1000PEPEUSDT_900.csv | symbol | 50 | 1000PEPEUSDT | context |
| data/recorder/2026-03-17/1000PEPEUSDT_900.csv | regime | 50 | PENDING | context |
| data/recorder/2026-03-17/1000PEPEUSDT_900.csv | tf_sec | 50 | 900 | context |
| data/recorder/2026-03-17/BNBUSDT_180.csv | symbol | 250 | BNBUSDT | context |
| data/recorder/2026-03-17/BNBUSDT_180.csv | regime | 250 | MEAN_REVERSION, PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-03-17/BNBUSDT_180.csv | tf_sec | 250 | 180 | context |
| data/recorder/2026-03-17/BNBUSDT_300.csv | symbol | 150 | BNBUSDT | context |
| data/recorder/2026-03-17/BNBUSDT_300.csv | regime | 150 | PENDING | context |
| data/recorder/2026-03-17/BNBUSDT_300.csv | tf_sec | 150 | 300 | context |
| data/recorder/2026-03-17/BNBUSDT_900.csv | symbol | 210 | BNBUSDT | context |
| data/recorder/2026-03-17/BNBUSDT_900.csv | regime | 210 | PENDING | context |
| data/recorder/2026-03-17/BNBUSDT_900.csv | tf_sec | 210 | 900 | context |
| data/recorder/2026-03-17/BTCUSDT_180.csv | symbol | 250 | BTCUSDT | context |
| data/recorder/2026-03-17/BTCUSDT_180.csv | regime | 250 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-17/BTCUSDT_180.csv | tf_sec | 250 | 180 | context |
| data/recorder/2026-03-17/BTCUSDT_300.csv | symbol | 752 | BTCUSDT, 1, 2 | context |
| data/recorder/2026-03-17/BTCUSDT_300.csv | regime | 752 | PENDING, 300 | context |
| data/recorder/2026-03-17/BTCUSDT_300.csv | tf_sec | 752 | 300, 1964.198, 9336.008, 95.071, 12000.737 | context |
| data/recorder/2026-03-17/BTCUSDT_900.csv | symbol | 50 | BTCUSDT | context |
| data/recorder/2026-03-17/BTCUSDT_900.csv | regime | 50 | PENDING | context |
| data/recorder/2026-03-17/BTCUSDT_900.csv | tf_sec | 50 | 900 | context |
| data/recorder/2026-03-17/DOGEUSDT_180.csv | symbol | 250 | DOGEUSDT | context |
| data/recorder/2026-03-17/DOGEUSDT_180.csv | regime | 250 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-17/DOGEUSDT_180.csv | tf_sec | 250 | 180 | context |
| data/recorder/2026-03-17/DOGEUSDT_300.csv | symbol | 752 | DOGEUSDT | context |
| data/recorder/2026-03-17/DOGEUSDT_300.csv | regime | 752 | PENDING | context |
| data/recorder/2026-03-17/DOGEUSDT_300.csv | tf_sec | 752 | 300 | context |
| data/recorder/2026-03-17/DOGEUSDT_900.csv | symbol | 50 | DOGEUSDT | context |
| data/recorder/2026-03-17/DOGEUSDT_900.csv | regime | 50 | PENDING | context |
| data/recorder/2026-03-17/DOGEUSDT_900.csv | tf_sec | 50 | 900 | context |
| data/recorder/2026-03-17/ETHUSDT_180.csv | symbol | 250 | ETHUSDT | context |
| data/recorder/2026-03-17/ETHUSDT_180.csv | regime | 250 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-17/ETHUSDT_180.csv | tf_sec | 250 | 180 | context |
| data/recorder/2026-03-17/ETHUSDT_300.csv | symbol | 752 | ETHUSDT, 1, 2 | context |
| data/recorder/2026-03-17/ETHUSDT_300.csv | regime | 752 | PENDING, 300 | context |
| data/recorder/2026-03-17/ETHUSDT_300.csv | tf_sec | 752 | 300, 155969.292, 266032.097, 156420.401, 349686.937 | context |
| data/recorder/2026-03-17/ETHUSDT_900.csv | symbol | 50 | ETHUSDT | context |
| data/recorder/2026-03-17/ETHUSDT_900.csv | regime | 50 | PENDING | context |
| data/recorder/2026-03-17/ETHUSDT_900.csv | tf_sec | 50 | 900 | context |
| data/recorder/2026-03-17/SOLUSDT_180.csv | symbol | 250 | SOLUSDT | context |
| data/recorder/2026-03-17/SOLUSDT_180.csv | regime | 250 | TREND_UP, PENDING, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-03-17/SOLUSDT_180.csv | tf_sec | 250 | 180 | context |
| data/recorder/2026-03-17/SOLUSDT_300.csv | symbol | 752 | SOLUSDT, 1, 3 | context |
| data/recorder/2026-03-17/SOLUSDT_300.csv | regime | 752 | PENDING, 300 | context |
| data/recorder/2026-03-17/SOLUSDT_300.csv | tf_sec | 752 | 300, 26103.12, 35462.19, 8872.12, 57966.57 | context |
| data/recorder/2026-03-17/SOLUSDT_900.csv | symbol | 50 | SOLUSDT | context |
| data/recorder/2026-03-17/SOLUSDT_900.csv | regime | 50 | PENDING | context |
| data/recorder/2026-03-17/SOLUSDT_900.csv | tf_sec | 50 | 900 | context |
| data/recorder/2026-03-17/XRPUSDT_180.csv | symbol | 250 | XRPUSDT | context |
| data/recorder/2026-03-17/XRPUSDT_180.csv | regime | 250 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-17/XRPUSDT_180.csv | tf_sec | 250 | 180 | context |
| data/recorder/2026-03-17/XRPUSDT_300.csv | symbol | 150 | XRPUSDT | context |
| data/recorder/2026-03-17/XRPUSDT_300.csv | regime | 150 | PENDING | context |
| data/recorder/2026-03-17/XRPUSDT_300.csv | tf_sec | 150 | 300 | context |
| data/recorder/2026-03-17/XRPUSDT_900.csv | symbol | 210 | XRPUSDT | context |
| data/recorder/2026-03-17/XRPUSDT_900.csv | regime | 210 | PENDING | context |
| data/recorder/2026-03-17/XRPUSDT_900.csv | tf_sec | 210 | 900 | context |
| data/recorder/2026-03-18/1000PEPEUSDT_180.csv | symbol | 432 | 1000PEPEUSDT | context |
| data/recorder/2026-03-18/1000PEPEUSDT_180.csv | regime | 432 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, TREND_DOWN | context |
| data/recorder/2026-03-18/1000PEPEUSDT_180.csv | tf_sec | 432 | 180 | context |
| data/recorder/2026-03-18/1000PEPEUSDT_300.csv | symbol | 259 | 1000PEPEUSDT | context |
| data/recorder/2026-03-18/1000PEPEUSDT_300.csv | regime | 259 | PENDING | context |
| data/recorder/2026-03-18/1000PEPEUSDT_300.csv | tf_sec | 259 | 300 | context |
| data/recorder/2026-03-18/1000PEPEUSDT_900.csv | symbol | 86 | 1000PEPEUSDT | context |
| data/recorder/2026-03-18/1000PEPEUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-03-18/1000PEPEUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-03-18/BNBUSDT_180.csv | symbol | 432 | BNBUSDT | context |
| data/recorder/2026-03-18/BNBUSDT_180.csv | regime | 432 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-03-18/BNBUSDT_180.csv | tf_sec | 432 | 180 | context |
| data/recorder/2026-03-18/BNBUSDT_300.csv | symbol | 259 | BNBUSDT | context |
| data/recorder/2026-03-18/BNBUSDT_300.csv | regime | 259 | PENDING | context |
| data/recorder/2026-03-18/BNBUSDT_300.csv | tf_sec | 259 | 300 | context |
| data/recorder/2026-03-18/BNBUSDT_900.csv | symbol | 133 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-18/BNBUSDT_900.csv | regime | 133 | PENDING, True | context |
| data/recorder/2026-03-18/BNBUSDT_900.csv | tf_sec | 133 | 900, BNBUSDT | context |
| data/recorder/2026-03-18/BTCUSDT_180.csv | symbol | 432 | BTCUSDT | context |
| data/recorder/2026-03-18/BTCUSDT_180.csv | regime | 432 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-03-18/BTCUSDT_180.csv | tf_sec | 432 | 180 | context |
| data/recorder/2026-03-18/BTCUSDT_300.csv | symbol | 1162 | BTCUSDT, 1, 2 | context |
| data/recorder/2026-03-18/BTCUSDT_300.csv | regime | 1162 | PENDING, 300 | context |
| data/recorder/2026-03-18/BTCUSDT_300.csv | tf_sec | 1162 | 300, 193.69, 5000.237, 316.611, 2361.555 | context |
| data/recorder/2026-03-18/BTCUSDT_900.csv | symbol | 86 | BTCUSDT | context |
| data/recorder/2026-03-18/BTCUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-03-18/BTCUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-03-18/DOGEUSDT_180.csv | symbol | 432 | DOGEUSDT | context |
| data/recorder/2026-03-18/DOGEUSDT_180.csv | regime | 432 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-03-18/DOGEUSDT_180.csv | tf_sec | 432 | 180 | context |
| data/recorder/2026-03-18/DOGEUSDT_300.csv | symbol | 1162 | DOGEUSDT | context |
| data/recorder/2026-03-18/DOGEUSDT_300.csv | regime | 1162 | PENDING | context |
| data/recorder/2026-03-18/DOGEUSDT_300.csv | tf_sec | 1162 | 300 | context |
| data/recorder/2026-03-18/DOGEUSDT_900.csv | symbol | 86 | DOGEUSDT | context |
| data/recorder/2026-03-18/DOGEUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-03-18/DOGEUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-03-18/ETHUSDT_180.csv | symbol | 432 | ETHUSDT | context |
| data/recorder/2026-03-18/ETHUSDT_180.csv | regime | 432 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-03-18/ETHUSDT_180.csv | tf_sec | 432 | 180 | context |
| data/recorder/2026-03-18/ETHUSDT_300.csv | symbol | 1162 | ETHUSDT, 1, 2 | context |
| data/recorder/2026-03-18/ETHUSDT_300.csv | regime | 1162 | PENDING, 300 | context |
| data/recorder/2026-03-18/ETHUSDT_300.csv | tf_sec | 1162 | 300, 15700.229, 375643.54, 62386.774, 135976.881 | context |
| data/recorder/2026-03-18/ETHUSDT_900.csv | symbol | 86 | ETHUSDT | context |
| data/recorder/2026-03-18/ETHUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-03-18/ETHUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-03-18/SOLUSDT_180.csv | symbol | 432 | SOLUSDT | context |
| data/recorder/2026-03-18/SOLUSDT_180.csv | regime | 432 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-03-18/SOLUSDT_180.csv | tf_sec | 432 | 180 | context |
| data/recorder/2026-03-18/SOLUSDT_300.csv | symbol | 1162 | SOLUSDT, 1, 3 | context |
| data/recorder/2026-03-18/SOLUSDT_300.csv | regime | 1162 | PENDING, 300 | context |
| data/recorder/2026-03-18/SOLUSDT_300.csv | tf_sec | 1162 | 300, 2381.71, 12559.88, 2337.39, 563.44 | context |
| data/recorder/2026-03-18/SOLUSDT_900.csv | symbol | 86 | SOLUSDT | context |
| data/recorder/2026-03-18/SOLUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-03-18/SOLUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-03-18/XRPUSDT_180.csv | symbol | 432 | XRPUSDT | context |
| data/recorder/2026-03-18/XRPUSDT_180.csv | regime | 432 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-03-18/XRPUSDT_180.csv | tf_sec | 432 | 180 | context |
| data/recorder/2026-03-18/XRPUSDT_300.csv | symbol | 259 | XRPUSDT | context |
| data/recorder/2026-03-18/XRPUSDT_300.csv | regime | 259 | PENDING | context |
| data/recorder/2026-03-18/XRPUSDT_300.csv | tf_sec | 259 | 300 | context |
| data/recorder/2026-03-18/XRPUSDT_900.csv | symbol | 134 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-18/XRPUSDT_900.csv | regime | 134 | PENDING, True | context |
| data/recorder/2026-03-18/XRPUSDT_900.csv | tf_sec | 134 | 900, XRPUSDT | context |
| data/recorder/2026-03-19/1000PEPEUSDT_180.csv | symbol | 371 | 1000PEPEUSDT | context |
| data/recorder/2026-03-19/1000PEPEUSDT_180.csv | regime | 371 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-03-19/1000PEPEUSDT_180.csv | tf_sec | 371 | 180 | context |
| data/recorder/2026-03-19/1000PEPEUSDT_300.csv | symbol | 223 | 1000PEPEUSDT | context |
| data/recorder/2026-03-19/1000PEPEUSDT_300.csv | regime | 223 | PENDING | context |
| data/recorder/2026-03-19/1000PEPEUSDT_300.csv | tf_sec | 223 | 300 | context |
| data/recorder/2026-03-19/1000PEPEUSDT_900.csv | symbol | 75 | 1000PEPEUSDT | context |
| data/recorder/2026-03-19/1000PEPEUSDT_900.csv | regime | 75 | PENDING | context |
| data/recorder/2026-03-19/1000PEPEUSDT_900.csv | tf_sec | 75 | 900 | context |
| data/recorder/2026-03-19/BNBUSDT_180.csv | symbol | 371 | BNBUSDT | context |
| data/recorder/2026-03-19/BNBUSDT_180.csv | regime | 371 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-03-19/BNBUSDT_180.csv | tf_sec | 371 | 180 | context |
| data/recorder/2026-03-19/BNBUSDT_300.csv | symbol | 223 | BNBUSDT | context |
| data/recorder/2026-03-19/BNBUSDT_300.csv | regime | 223 | PENDING | context |
| data/recorder/2026-03-19/BNBUSDT_300.csv | tf_sec | 223 | 300 | context |
| data/recorder/2026-03-19/BNBUSDT_900.csv | symbol | 18 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-19/BNBUSDT_900.csv | regime | 18 | PENDING, True | context |
| data/recorder/2026-03-19/BNBUSDT_900.csv | tf_sec | 18 | 900, BNBUSDT | context |
| data/recorder/2026-03-19/BTCUSDT_180.csv | symbol | 371 | BTCUSDT | context |
| data/recorder/2026-03-19/BTCUSDT_180.csv | regime | 371 | UNCERTAIN, PENDING, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-03-19/BTCUSDT_180.csv | tf_sec | 371 | 180 | context |
| data/recorder/2026-03-19/BTCUSDT_300.csv | symbol | 1125 | BTCUSDT, 1, 3 | context |
| data/recorder/2026-03-19/BTCUSDT_300.csv | regime | 1125 | PENDING, 300 | context |
| data/recorder/2026-03-19/BTCUSDT_300.csv | tf_sec | 1125 | 300, 6286.333, 5787.378, 4114.1, 14051.447 | context |
| data/recorder/2026-03-19/BTCUSDT_900.csv | symbol | 75 | BTCUSDT | context |
| data/recorder/2026-03-19/BTCUSDT_900.csv | regime | 75 | PENDING | context |
| data/recorder/2026-03-19/BTCUSDT_900.csv | tf_sec | 75 | 900 | context |
| data/recorder/2026-03-19/DOGEUSDT_180.csv | symbol | 371 | DOGEUSDT | context |
| data/recorder/2026-03-19/DOGEUSDT_180.csv | regime | 371 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-03-19/DOGEUSDT_180.csv | tf_sec | 371 | 180 | context |
| data/recorder/2026-03-19/DOGEUSDT_300.csv | symbol | 1126 | DOGEUSDT | context |
| data/recorder/2026-03-19/DOGEUSDT_300.csv | regime | 1126 | PENDING | context |
| data/recorder/2026-03-19/DOGEUSDT_300.csv | tf_sec | 1126 | 300 | context |
| data/recorder/2026-03-19/DOGEUSDT_900.csv | symbol | 75 | DOGEUSDT | context |
| data/recorder/2026-03-19/DOGEUSDT_900.csv | regime | 75 | PENDING | context |
| data/recorder/2026-03-19/DOGEUSDT_900.csv | tf_sec | 75 | 900 | context |
| data/recorder/2026-03-19/ETHUSDT_180.csv | symbol | 371 | ETHUSDT | context |
| data/recorder/2026-03-19/ETHUSDT_180.csv | regime | 371 | UNCERTAIN, PENDING, TREND_DOWN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-19/ETHUSDT_180.csv | tf_sec | 371 | 180 | context |
| data/recorder/2026-03-19/ETHUSDT_300.csv | symbol | 1126 | ETHUSDT, 1 | context |
| data/recorder/2026-03-19/ETHUSDT_300.csv | regime | 1126 | PENDING, 300 | context |
| data/recorder/2026-03-19/ETHUSDT_300.csv | tf_sec | 1126 | 300, 125363.21, 331039.177, 208411.075, 185229.833 | context |
| data/recorder/2026-03-19/ETHUSDT_900.csv | symbol | 75 | ETHUSDT | context |
| data/recorder/2026-03-19/ETHUSDT_900.csv | regime | 75 | PENDING | context |
| data/recorder/2026-03-19/ETHUSDT_900.csv | tf_sec | 75 | 900 | context |
| data/recorder/2026-03-19/SOLUSDT_180.csv | symbol | 371 | SOLUSDT | context |
| data/recorder/2026-03-19/SOLUSDT_180.csv | regime | 371 | UNCERTAIN, PENDING, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-03-19/SOLUSDT_180.csv | tf_sec | 371 | 180 | context |
| data/recorder/2026-03-19/SOLUSDT_300.csv | symbol | 1126 | SOLUSDT, 62, 1, 53 | context |
| data/recorder/2026-03-19/SOLUSDT_300.csv | regime | 1126 | PENDING, 300 | context |
| data/recorder/2026-03-19/SOLUSDT_300.csv | tf_sec | 1126 | 300, 0, 14835.64, 23966.67, 6369.98 | context |
| data/recorder/2026-03-19/SOLUSDT_900.csv | symbol | 75 | SOLUSDT | context |
| data/recorder/2026-03-19/SOLUSDT_900.csv | regime | 75 | PENDING | context |
| data/recorder/2026-03-19/SOLUSDT_900.csv | tf_sec | 75 | 900 | context |
| data/recorder/2026-03-19/XRPUSDT_180.csv | symbol | 371 | XRPUSDT | context |
| data/recorder/2026-03-19/XRPUSDT_180.csv | regime | 371 | UNCERTAIN, PENDING, LOW_VOLATILITY, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-03-19/XRPUSDT_180.csv | tf_sec | 371 | 180 | context |
| data/recorder/2026-03-19/XRPUSDT_300.csv | symbol | 223 | XRPUSDT | context |
| data/recorder/2026-03-19/XRPUSDT_300.csv | regime | 223 | PENDING | context |
| data/recorder/2026-03-19/XRPUSDT_300.csv | tf_sec | 223 | 300 | context |
| data/recorder/2026-03-19/XRPUSDT_900.csv | symbol | 8 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-19/XRPUSDT_900.csv | regime | 8 | PENDING, True | context |
| data/recorder/2026-03-19/XRPUSDT_900.csv | tf_sec | 8 | 900, XRPUSDT | context |
| data/recorder/2026-03-20/1000PEPEUSDT_180.csv | symbol | 477 | 1000PEPEUSDT | context |
| data/recorder/2026-03-20/1000PEPEUSDT_180.csv | regime | 477 | PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-03-20/1000PEPEUSDT_180.csv | tf_sec | 477 | 180 | context |
| data/recorder/2026-03-20/1000PEPEUSDT_300.csv | symbol | 286 | 1000PEPEUSDT | context |
| data/recorder/2026-03-20/1000PEPEUSDT_300.csv | regime | 286 | PENDING | context |
| data/recorder/2026-03-20/1000PEPEUSDT_300.csv | tf_sec | 286 | 300 | context |
| data/recorder/2026-03-20/1000PEPEUSDT_900.csv | symbol | 94 | 1000PEPEUSDT | context |
| data/recorder/2026-03-20/1000PEPEUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-03-20/1000PEPEUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-03-20/BNBUSDT_180.csv | symbol | 477 | BNBUSDT | context |
| data/recorder/2026-03-20/BNBUSDT_180.csv | regime | 477 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-03-20/BNBUSDT_180.csv | tf_sec | 477 | 180 | context |
| data/recorder/2026-03-20/BNBUSDT_300.csv | symbol | 286 | BNBUSDT | context |
| data/recorder/2026-03-20/BNBUSDT_300.csv | regime | 286 | PENDING | context |
| data/recorder/2026-03-20/BNBUSDT_300.csv | tf_sec | 286 | 300 | context |
| data/recorder/2026-03-20/BNBUSDT_900.csv | symbol | 110 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-20/BNBUSDT_900.csv | regime | 110 | PENDING, True | context |
| data/recorder/2026-03-20/BNBUSDT_900.csv | tf_sec | 110 | 900, BNBUSDT | context |
| data/recorder/2026-03-20/BTCUSDT_180.csv | symbol | 477 | BTCUSDT | context |
| data/recorder/2026-03-20/BTCUSDT_180.csv | regime | 477 | PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-03-20/BTCUSDT_180.csv | tf_sec | 477 | 180 | context |
| data/recorder/2026-03-20/BTCUSDT_300.csv | symbol | 302 | BTCUSDT, True | context |
| data/recorder/2026-03-20/BTCUSDT_300.csv | regime | 302 | PENDING, None | context |
| data/recorder/2026-03-20/BTCUSDT_300.csv | tf_sec | 302 | 300, PENDING | context |
| data/recorder/2026-03-20/BTCUSDT_900.csv | symbol | 94 | BTCUSDT | context |
| data/recorder/2026-03-20/BTCUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-03-20/BTCUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-03-20/DOGEUSDT_180.csv | symbol | 477 | DOGEUSDT | context |
| data/recorder/2026-03-20/DOGEUSDT_180.csv | regime | 477 | PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-03-20/DOGEUSDT_180.csv | tf_sec | 477 | 180 | context |
| data/recorder/2026-03-20/DOGEUSDT_300.csv | symbol | 888 | DOGEUSDT | context |
| data/recorder/2026-03-20/DOGEUSDT_300.csv | regime | 888 | PENDING | context |
| data/recorder/2026-03-20/DOGEUSDT_300.csv | tf_sec | 888 | 300 | context |
| data/recorder/2026-03-20/DOGEUSDT_900.csv | symbol | 94 | DOGEUSDT | context |
| data/recorder/2026-03-20/DOGEUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-03-20/DOGEUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-03-20/ETHUSDT_180.csv | symbol | 477 | ETHUSDT | context |
| data/recorder/2026-03-20/ETHUSDT_180.csv | regime | 477 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-03-20/ETHUSDT_180.csv | tf_sec | 477 | 180 | context |
| data/recorder/2026-03-20/ETHUSDT_300.csv | symbol | 302 | ETHUSDT, True | context |
| data/recorder/2026-03-20/ETHUSDT_300.csv | regime | 302 | PENDING, None | context |
| data/recorder/2026-03-20/ETHUSDT_300.csv | tf_sec | 302 | 300, PENDING | context |
| data/recorder/2026-03-20/ETHUSDT_900.csv | symbol | 94 | ETHUSDT | context |
| data/recorder/2026-03-20/ETHUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-03-20/ETHUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-03-20/SOLUSDT_180.csv | symbol | 477 | SOLUSDT | context |
| data/recorder/2026-03-20/SOLUSDT_180.csv | regime | 477 | PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-03-20/SOLUSDT_180.csv | tf_sec | 477 | 180 | context |
| data/recorder/2026-03-20/SOLUSDT_300.csv | symbol | 302 | SOLUSDT, True | context |
| data/recorder/2026-03-20/SOLUSDT_300.csv | regime | 302 | PENDING, None | context |
| data/recorder/2026-03-20/SOLUSDT_300.csv | tf_sec | 302 | 300, PENDING | context |
| data/recorder/2026-03-20/SOLUSDT_900.csv | symbol | 94 | SOLUSDT | context |
| data/recorder/2026-03-20/SOLUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-03-20/SOLUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-03-20/XRPUSDT_180.csv | symbol | 477 | XRPUSDT | context |
| data/recorder/2026-03-20/XRPUSDT_180.csv | regime | 477 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-03-20/XRPUSDT_180.csv | tf_sec | 477 | 180 | context |
| data/recorder/2026-03-20/XRPUSDT_300.csv | symbol | 286 | XRPUSDT | context |
| data/recorder/2026-03-20/XRPUSDT_300.csv | regime | 286 | PENDING | context |
| data/recorder/2026-03-20/XRPUSDT_300.csv | tf_sec | 286 | 300 | context |
| data/recorder/2026-03-20/XRPUSDT_900.csv | symbol | 104 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-20/XRPUSDT_900.csv | regime | 104 | PENDING, True | context |
| data/recorder/2026-03-20/XRPUSDT_900.csv | tf_sec | 104 | 900, XRPUSDT | context |
| data/recorder/2026-03-21/1000PEPEUSDT_180.csv | symbol | 466 | 1000PEPEUSDT | context |
| data/recorder/2026-03-21/1000PEPEUSDT_180.csv | regime | 466 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-03-21/1000PEPEUSDT_180.csv | tf_sec | 466 | 180 | context |
| data/recorder/2026-03-21/1000PEPEUSDT_300.csv | symbol | 281 | 1000PEPEUSDT | context |
| data/recorder/2026-03-21/1000PEPEUSDT_300.csv | regime | 281 | PENDING | context |
| data/recorder/2026-03-21/1000PEPEUSDT_300.csv | tf_sec | 281 | 300 | context |
| data/recorder/2026-03-21/1000PEPEUSDT_900.csv | symbol | 93 | 1000PEPEUSDT | context |
| data/recorder/2026-03-21/1000PEPEUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-03-21/1000PEPEUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-03-21/BNBUSDT_180.csv | symbol | 466 | BNBUSDT | context |
| data/recorder/2026-03-21/BNBUSDT_180.csv | regime | 466 | LOW_VOLATILITY, PENDING, MEAN_REVERSION | context |
| data/recorder/2026-03-21/BNBUSDT_180.csv | tf_sec | 466 | 180 | context |
| data/recorder/2026-03-21/BNBUSDT_300.csv | symbol | 281 | BNBUSDT | context |
| data/recorder/2026-03-21/BNBUSDT_300.csv | regime | 281 | PENDING | context |
| data/recorder/2026-03-21/BNBUSDT_300.csv | tf_sec | 281 | 300 | context |
| data/recorder/2026-03-21/BNBUSDT_900.csv | symbol | 7 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-21/BNBUSDT_900.csv | regime | 7 | PENDING, True | context |
| data/recorder/2026-03-21/BNBUSDT_900.csv | tf_sec | 7 | 900, BNBUSDT | context |
| data/recorder/2026-03-21/BTCUSDT_180.csv | symbol | 466 | BTCUSDT | context |
| data/recorder/2026-03-21/BTCUSDT_180.csv | regime | 466 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-03-21/BTCUSDT_180.csv | tf_sec | 466 | 180 | context |
| data/recorder/2026-03-21/BTCUSDT_300.csv | symbol | 883 | BTCUSDT, 1 | context |
| data/recorder/2026-03-21/BTCUSDT_300.csv | regime | 883 | PENDING, 300 | context |
| data/recorder/2026-03-21/BTCUSDT_300.csv | tf_sec | 883 | 300, 105.951, 3382.7, 5281.337, 10049.637 | context |
| data/recorder/2026-03-21/BTCUSDT_900.csv | symbol | 93 | BTCUSDT | context |
| data/recorder/2026-03-21/BTCUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-03-21/BTCUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-03-21/DOGEUSDT_180.csv | symbol | 466 | DOGEUSDT | context |
| data/recorder/2026-03-21/DOGEUSDT_180.csv | regime | 466 | LOW_VOLATILITY, PENDING, TREND_DOWN, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-03-21/DOGEUSDT_180.csv | tf_sec | 466 | 180 | context |
| data/recorder/2026-03-21/DOGEUSDT_300.csv | symbol | 883 | DOGEUSDT | context |
| data/recorder/2026-03-21/DOGEUSDT_300.csv | regime | 883 | PENDING | context |
| data/recorder/2026-03-21/DOGEUSDT_300.csv | tf_sec | 883 | 300 | context |
| data/recorder/2026-03-21/DOGEUSDT_900.csv | symbol | 93 | DOGEUSDT | context |
| data/recorder/2026-03-21/DOGEUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-03-21/DOGEUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-03-21/ETHUSDT_180.csv | symbol | 466 | ETHUSDT | context |
| data/recorder/2026-03-21/ETHUSDT_180.csv | regime | 466 | LOW_VOLATILITY, PENDING, MEAN_REVERSION | context |
| data/recorder/2026-03-21/ETHUSDT_180.csv | tf_sec | 466 | 180 | context |
| data/recorder/2026-03-21/ETHUSDT_300.csv | symbol | 883 | ETHUSDT, 1, 2 | context |
| data/recorder/2026-03-21/ETHUSDT_300.csv | regime | 883 | PENDING, 300 | context |
| data/recorder/2026-03-21/ETHUSDT_300.csv | tf_sec | 883 | 300, 234471.394, 134391.674, 318473.521, 132703.939 | context |
| data/recorder/2026-03-21/ETHUSDT_900.csv | symbol | 93 | ETHUSDT | context |
| data/recorder/2026-03-21/ETHUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-03-21/ETHUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-03-21/SOLUSDT_180.csv | symbol | 466 | SOLUSDT | context |
| data/recorder/2026-03-21/SOLUSDT_180.csv | regime | 466 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-03-21/SOLUSDT_180.csv | tf_sec | 466 | 180 | context |
| data/recorder/2026-03-21/SOLUSDT_300.csv | symbol | 883 | SOLUSDT, 3, 1 | context |
| data/recorder/2026-03-21/SOLUSDT_300.csv | regime | 883 | PENDING, 300 | context |
| data/recorder/2026-03-21/SOLUSDT_300.csv | tf_sec | 883 | 300, 0, 45328.85, 36316.24, 817.69 | context |
| data/recorder/2026-03-21/SOLUSDT_900.csv | symbol | 93 | SOLUSDT | context |
| data/recorder/2026-03-21/SOLUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-03-21/SOLUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-03-21/XRPUSDT_180.csv | symbol | 466 | XRPUSDT | context |
| data/recorder/2026-03-21/XRPUSDT_180.csv | regime | 466 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-03-21/XRPUSDT_180.csv | tf_sec | 466 | 180 | context |
| data/recorder/2026-03-21/XRPUSDT_300.csv | symbol | 281 | XRPUSDT | context |
| data/recorder/2026-03-21/XRPUSDT_300.csv | regime | 281 | PENDING | context |
| data/recorder/2026-03-21/XRPUSDT_300.csv | tf_sec | 281 | 300 | context |
| data/recorder/2026-03-21/XRPUSDT_900.csv | symbol | 24 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-21/XRPUSDT_900.csv | regime | 24 | PENDING, True | context |
| data/recorder/2026-03-21/XRPUSDT_900.csv | tf_sec | 24 | 900, XRPUSDT | context |
| data/recorder/2026-03-22/1000PEPEUSDT_180.csv | symbol | 480 | 1000PEPEUSDT | context |
| data/recorder/2026-03-22/1000PEPEUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, HIGH_VOLATILITY, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-03-22/1000PEPEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-22/1000PEPEUSDT_300.csv | symbol | 288 | 1000PEPEUSDT | context |
| data/recorder/2026-03-22/1000PEPEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-22/1000PEPEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-22/1000PEPEUSDT_900.csv | symbol | 96 | 1000PEPEUSDT | context |
| data/recorder/2026-03-22/1000PEPEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-22/1000PEPEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-22/BNBUSDT_180.csv | symbol | 480 | BNBUSDT | context |
| data/recorder/2026-03-22/BNBUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, HIGH_VOLATILITY, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-03-22/BNBUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-22/BNBUSDT_300.csv | symbol | 288 | BNBUSDT | context |
| data/recorder/2026-03-22/BNBUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-22/BNBUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-22/BNBUSDT_900.csv | symbol | 26 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-22/BNBUSDT_900.csv | regime | 26 | PENDING, True | context |
| data/recorder/2026-03-22/BNBUSDT_900.csv | tf_sec | 26 | 900, BNBUSDT | context |
| data/recorder/2026-03-22/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-03-22/BTCUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, HIGH_VOLATILITY, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-03-22/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-22/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-03-22/BTCUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-22/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-22/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-03-22/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-22/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-22/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-03-22/DOGEUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, HIGH_VOLATILITY, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-03-22/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-22/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-03-22/DOGEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-22/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-22/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-03-22/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-22/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-22/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-03-22/ETHUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-03-22/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-22/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-03-22/ETHUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-22/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-22/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-03-22/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-22/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-22/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-03-22/SOLUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, HIGH_VOLATILITY, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-03-22/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-22/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-03-22/SOLUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-22/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-22/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-03-22/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-22/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-22/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-03-22/XRPUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, HIGH_VOLATILITY, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-03-22/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-22/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-03-22/XRPUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-22/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-22/XRPUSDT_900.csv | symbol | 24 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-22/XRPUSDT_900.csv | regime | 24 | PENDING, True | context |
| data/recorder/2026-03-22/XRPUSDT_900.csv | tf_sec | 24 | 900, XRPUSDT | context |
| data/recorder/2026-03-23/1000PEPEUSDT_180.csv | symbol | 480 | 1000PEPEUSDT | context |
| data/recorder/2026-03-23/1000PEPEUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, MEAN_REVERSION, TREND_UP, HIGH_VOLATILITY | context |
| data/recorder/2026-03-23/1000PEPEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-23/1000PEPEUSDT_300.csv | symbol | 288 | 1000PEPEUSDT | context |
| data/recorder/2026-03-23/1000PEPEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-23/1000PEPEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-23/1000PEPEUSDT_900.csv | symbol | 96 | 1000PEPEUSDT | context |
| data/recorder/2026-03-23/1000PEPEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-23/1000PEPEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-23/BNBUSDT_180.csv | symbol | 480 | BNBUSDT | context |
| data/recorder/2026-03-23/BNBUSDT_180.csv | regime | 480 | MEAN_REVERSION, PENDING, TREND_DOWN, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-03-23/BNBUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-23/BNBUSDT_300.csv | symbol | 288 | BNBUSDT | context |
| data/recorder/2026-03-23/BNBUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-23/BNBUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-23/BNBUSDT_900.csv | symbol | 4 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-23/BNBUSDT_900.csv | regime | 4 | PENDING, True | context |
| data/recorder/2026-03-23/BNBUSDT_900.csv | tf_sec | 4 | 900, BNBUSDT | context |
| data/recorder/2026-03-23/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-03-23/BTCUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-03-23/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-23/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-03-23/BTCUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-23/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-23/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-03-23/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-23/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-23/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-03-23/DOGEUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-03-23/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-23/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-03-23/DOGEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-23/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-23/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-03-23/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-23/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-23/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-03-23/ETHUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-03-23/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-23/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-03-23/ETHUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-23/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-23/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-03-23/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-23/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-23/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-03-23/SOLUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-03-23/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-23/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-03-23/SOLUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-23/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-23/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-03-23/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-23/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-23/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-03-23/XRPUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, TREND_DOWN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-03-23/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-23/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-03-23/XRPUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-23/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-23/XRPUSDT_900.csv | symbol | 5 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-23/XRPUSDT_900.csv | regime | 5 | PENDING, True | context |
| data/recorder/2026-03-23/XRPUSDT_900.csv | tf_sec | 5 | 900, XRPUSDT | context |
| data/recorder/2026-03-24/1000PEPEUSDT_180.csv | symbol | 428 | 1000PEPEUSDT | context |
| data/recorder/2026-03-24/1000PEPEUSDT_180.csv | regime | 428 | UNCERTAIN, PENDING, LOW_VOLATILITY, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-03-24/1000PEPEUSDT_180.csv | tf_sec | 428 | 180 | context |
| data/recorder/2026-03-24/1000PEPEUSDT_300.csv | symbol | 257 | 1000PEPEUSDT | context |
| data/recorder/2026-03-24/1000PEPEUSDT_300.csv | regime | 257 | PENDING | context |
| data/recorder/2026-03-24/1000PEPEUSDT_300.csv | tf_sec | 257 | 300 | context |
| data/recorder/2026-03-24/1000PEPEUSDT_900.csv | symbol | 86 | 1000PEPEUSDT | context |
| data/recorder/2026-03-24/1000PEPEUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-03-24/1000PEPEUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-03-24/BNBUSDT_180.csv | symbol | 428 | BNBUSDT | context |
| data/recorder/2026-03-24/BNBUSDT_180.csv | regime | 428 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-03-24/BNBUSDT_180.csv | tf_sec | 428 | 180 | context |
| data/recorder/2026-03-24/BNBUSDT_300.csv | symbol | 257 | BNBUSDT | context |
| data/recorder/2026-03-24/BNBUSDT_300.csv | regime | 257 | PENDING | context |
| data/recorder/2026-03-24/BNBUSDT_300.csv | tf_sec | 257 | 300 | context |
| data/recorder/2026-03-24/BNBUSDT_900.csv | symbol | 4 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-24/BNBUSDT_900.csv | regime | 4 | PENDING, True | context |
| data/recorder/2026-03-24/BNBUSDT_900.csv | tf_sec | 4 | 900, BNBUSDT | context |
| data/recorder/2026-03-24/BTCUSDT_180.csv | symbol | 428 | BTCUSDT | context |
| data/recorder/2026-03-24/BTCUSDT_180.csv | regime | 428 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-03-24/BTCUSDT_180.csv | tf_sec | 428 | 180 | context |
| data/recorder/2026-03-24/BTCUSDT_300.csv | symbol | 257 | BTCUSDT | context |
| data/recorder/2026-03-24/BTCUSDT_300.csv | regime | 257 | PENDING | context |
| data/recorder/2026-03-24/BTCUSDT_300.csv | tf_sec | 257 | 300 | context |
| data/recorder/2026-03-24/BTCUSDT_900.csv | symbol | 86 | BTCUSDT | context |
| data/recorder/2026-03-24/BTCUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-03-24/BTCUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-03-24/DOGEUSDT_180.csv | symbol | 428 | DOGEUSDT | context |
| data/recorder/2026-03-24/DOGEUSDT_180.csv | regime | 428 | UNCERTAIN, PENDING, LOW_VOLATILITY, TREND_DOWN, TREND_UP | context |
| data/recorder/2026-03-24/DOGEUSDT_180.csv | tf_sec | 428 | 180 | context |
| data/recorder/2026-03-24/DOGEUSDT_300.csv | symbol | 257 | DOGEUSDT | context |
| data/recorder/2026-03-24/DOGEUSDT_300.csv | regime | 257 | PENDING | context |
| data/recorder/2026-03-24/DOGEUSDT_300.csv | tf_sec | 257 | 300 | context |
| data/recorder/2026-03-24/DOGEUSDT_900.csv | symbol | 86 | DOGEUSDT | context |
| data/recorder/2026-03-24/DOGEUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-03-24/DOGEUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-03-24/ETHUSDT_180.csv | symbol | 428 | ETHUSDT | context |
| data/recorder/2026-03-24/ETHUSDT_180.csv | regime | 428 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-03-24/ETHUSDT_180.csv | tf_sec | 428 | 180 | context |
| data/recorder/2026-03-24/ETHUSDT_300.csv | symbol | 257 | ETHUSDT | context |
| data/recorder/2026-03-24/ETHUSDT_300.csv | regime | 257 | PENDING | context |
| data/recorder/2026-03-24/ETHUSDT_300.csv | tf_sec | 257 | 300 | context |
| data/recorder/2026-03-24/ETHUSDT_900.csv | symbol | 86 | ETHUSDT | context |
| data/recorder/2026-03-24/ETHUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-03-24/ETHUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-03-24/SOLUSDT_180.csv | symbol | 428 | SOLUSDT | context |
| data/recorder/2026-03-24/SOLUSDT_180.csv | regime | 428 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, TREND_DOWN | context |
| data/recorder/2026-03-24/SOLUSDT_180.csv | tf_sec | 428 | 180 | context |
| data/recorder/2026-03-24/SOLUSDT_300.csv | symbol | 257 | SOLUSDT | context |
| data/recorder/2026-03-24/SOLUSDT_300.csv | regime | 257 | PENDING | context |
| data/recorder/2026-03-24/SOLUSDT_300.csv | tf_sec | 257 | 300 | context |
| data/recorder/2026-03-24/SOLUSDT_900.csv | symbol | 86 | SOLUSDT | context |
| data/recorder/2026-03-24/SOLUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-03-24/SOLUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-03-24/XRPUSDT_180.csv | symbol | 428 | XRPUSDT | context |
| data/recorder/2026-03-24/XRPUSDT_180.csv | regime | 428 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-03-24/XRPUSDT_180.csv | tf_sec | 428 | 180 | context |
| data/recorder/2026-03-24/XRPUSDT_300.csv | symbol | 257 | XRPUSDT | context |
| data/recorder/2026-03-24/XRPUSDT_300.csv | regime | 257 | PENDING | context |
| data/recorder/2026-03-24/XRPUSDT_300.csv | tf_sec | 257 | 300 | context |
| data/recorder/2026-03-24/XRPUSDT_900.csv | symbol | 3 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-24/XRPUSDT_900.csv | regime | 3 | PENDING, True | context |
| data/recorder/2026-03-24/XRPUSDT_900.csv | tf_sec | 3 | 900, XRPUSDT | context |
| data/recorder/2026-03-25/1000PEPEUSDT_180.csv | symbol | 349 | 1000PEPEUSDT | context |
| data/recorder/2026-03-25/1000PEPEUSDT_180.csv | regime | 349 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-25/1000PEPEUSDT_180.csv | tf_sec | 349 | 180 | context |
| data/recorder/2026-03-25/1000PEPEUSDT_300.csv | symbol | 209 | 1000PEPEUSDT | context |
| data/recorder/2026-03-25/1000PEPEUSDT_300.csv | regime | 209 | PENDING | context |
| data/recorder/2026-03-25/1000PEPEUSDT_300.csv | tf_sec | 209 | 300 | context |
| data/recorder/2026-03-25/1000PEPEUSDT_900.csv | symbol | 69 | 1000PEPEUSDT | context |
| data/recorder/2026-03-25/1000PEPEUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-03-25/1000PEPEUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-03-25/BNBUSDT_180.csv | symbol | 349 | BNBUSDT | context |
| data/recorder/2026-03-25/BNBUSDT_180.csv | regime | 349 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-25/BNBUSDT_180.csv | tf_sec | 349 | 180 | context |
| data/recorder/2026-03-25/BNBUSDT_300.csv | symbol | 209 | BNBUSDT | context |
| data/recorder/2026-03-25/BNBUSDT_300.csv | regime | 209 | PENDING | context |
| data/recorder/2026-03-25/BNBUSDT_300.csv | tf_sec | 209 | 300 | context |
| data/recorder/2026-03-25/BNBUSDT_900.csv | symbol | 105 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-25/BNBUSDT_900.csv | regime | 105 | PENDING, True | context |
| data/recorder/2026-03-25/BNBUSDT_900.csv | tf_sec | 105 | 900, BNBUSDT | context |
| data/recorder/2026-03-25/BTCUSDT_180.csv | symbol | 349 | BTCUSDT | context |
| data/recorder/2026-03-25/BTCUSDT_180.csv | regime | 349 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-25/BTCUSDT_180.csv | tf_sec | 349 | 180 | context |
| data/recorder/2026-03-25/BTCUSDT_300.csv | symbol | 302 | BTCUSDT, True | context |
| data/recorder/2026-03-25/BTCUSDT_300.csv | regime | 302 | PENDING, None | context |
| data/recorder/2026-03-25/BTCUSDT_300.csv | tf_sec | 302 | 300, PENDING | context |
| data/recorder/2026-03-25/BTCUSDT_900.csv | symbol | 69 | BTCUSDT | context |
| data/recorder/2026-03-25/BTCUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-03-25/BTCUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-03-25/DOGEUSDT_180.csv | symbol | 349 | DOGEUSDT | context |
| data/recorder/2026-03-25/DOGEUSDT_180.csv | regime | 349 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-25/DOGEUSDT_180.csv | tf_sec | 349 | 180 | context |
| data/recorder/2026-03-25/DOGEUSDT_300.csv | symbol | 510 | DOGEUSDT | context |
| data/recorder/2026-03-25/DOGEUSDT_300.csv | regime | 510 | PENDING | context |
| data/recorder/2026-03-25/DOGEUSDT_300.csv | tf_sec | 510 | 300 | context |
| data/recorder/2026-03-25/DOGEUSDT_900.csv | symbol | 69 | DOGEUSDT | context |
| data/recorder/2026-03-25/DOGEUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-03-25/DOGEUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-03-25/ETHUSDT_180.csv | symbol | 349 | ETHUSDT | context |
| data/recorder/2026-03-25/ETHUSDT_180.csv | regime | 349 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-03-25/ETHUSDT_180.csv | tf_sec | 349 | 180 | context |
| data/recorder/2026-03-25/ETHUSDT_300.csv | symbol | 302 | ETHUSDT, True | context |
| data/recorder/2026-03-25/ETHUSDT_300.csv | regime | 302 | PENDING, None | context |
| data/recorder/2026-03-25/ETHUSDT_300.csv | tf_sec | 302 | 300, PENDING | context |
| data/recorder/2026-03-25/ETHUSDT_900.csv | symbol | 69 | ETHUSDT | context |
| data/recorder/2026-03-25/ETHUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-03-25/ETHUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-03-25/SOLUSDT_180.csv | symbol | 349 | SOLUSDT | context |
| data/recorder/2026-03-25/SOLUSDT_180.csv | regime | 349 | PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-03-25/SOLUSDT_180.csv | tf_sec | 349 | 180 | context |
| data/recorder/2026-03-25/SOLUSDT_300.csv | symbol | 302 | SOLUSDT, True | context |
| data/recorder/2026-03-25/SOLUSDT_300.csv | regime | 302 | PENDING, None | context |
| data/recorder/2026-03-25/SOLUSDT_300.csv | tf_sec | 302 | 300, PENDING | context |
| data/recorder/2026-03-25/SOLUSDT_900.csv | symbol | 69 | SOLUSDT | context |
| data/recorder/2026-03-25/SOLUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-03-25/SOLUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-03-25/XRPUSDT_180.csv | symbol | 349 | XRPUSDT | context |
| data/recorder/2026-03-25/XRPUSDT_180.csv | regime | 349 | PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-03-25/XRPUSDT_180.csv | tf_sec | 349 | 180 | context |
| data/recorder/2026-03-25/XRPUSDT_300.csv | symbol | 209 | XRPUSDT | context |
| data/recorder/2026-03-25/XRPUSDT_300.csv | regime | 209 | PENDING | context |
| data/recorder/2026-03-25/XRPUSDT_300.csv | tf_sec | 209 | 300 | context |
| data/recorder/2026-03-25/XRPUSDT_900.csv | symbol | 115 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-25/XRPUSDT_900.csv | regime | 115 | PENDING, True | context |
| data/recorder/2026-03-25/XRPUSDT_900.csv | tf_sec | 115 | 900, XRPUSDT | context |
| data/recorder/2026-03-26/1000PEPEUSDT_180.csv | symbol | 480 | 1000PEPEUSDT | context |
| data/recorder/2026-03-26/1000PEPEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_DOWN, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-03-26/1000PEPEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-26/1000PEPEUSDT_300.csv | symbol | 288 | 1000PEPEUSDT | context |
| data/recorder/2026-03-26/1000PEPEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-26/1000PEPEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-26/1000PEPEUSDT_900.csv | symbol | 96 | 1000PEPEUSDT | context |
| data/recorder/2026-03-26/1000PEPEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-26/1000PEPEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-26/BNBUSDT_180.csv | symbol | 480 | BNBUSDT | context |
| data/recorder/2026-03-26/BNBUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-03-26/BNBUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-26/BNBUSDT_300.csv | symbol | 288 | BNBUSDT | context |
| data/recorder/2026-03-26/BNBUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-26/BNBUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-26/BNBUSDT_900.csv | symbol | 10 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-26/BNBUSDT_900.csv | regime | 10 | PENDING, True | context |
| data/recorder/2026-03-26/BNBUSDT_900.csv | tf_sec | 10 | 900, BNBUSDT | context |
| data/recorder/2026-03-26/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-03-26/BTCUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-03-26/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-26/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-03-26/BTCUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-26/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-26/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-03-26/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-26/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-26/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-03-26/DOGEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-03-26/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-26/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-03-26/DOGEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-26/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-26/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-03-26/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-26/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-26/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-03-26/ETHUSDT_180.csv | regime | 480 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-03-26/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-26/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-03-26/ETHUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-26/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-26/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-03-26/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-26/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-26/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-03-26/SOLUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-03-26/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-26/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-03-26/SOLUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-26/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-26/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-03-26/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-26/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-26/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-03-26/XRPUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-03-26/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-26/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-03-26/XRPUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-26/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-26/XRPUSDT_900.csv | symbol | 8 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-26/XRPUSDT_900.csv | regime | 8 | PENDING, True | context |
| data/recorder/2026-03-26/XRPUSDT_900.csv | tf_sec | 8 | 900, XRPUSDT | context |
| data/recorder/2026-03-27/1000PEPEUSDT_180.csv | symbol | 440 | 1000PEPEUSDT | context |
| data/recorder/2026-03-27/1000PEPEUSDT_180.csv | regime | 440 | MEAN_REVERSION, PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-03-27/1000PEPEUSDT_180.csv | tf_sec | 440 | 180 | context |
| data/recorder/2026-03-27/1000PEPEUSDT_300.csv | symbol | 263 | 1000PEPEUSDT | context |
| data/recorder/2026-03-27/1000PEPEUSDT_300.csv | regime | 263 | PENDING | context |
| data/recorder/2026-03-27/1000PEPEUSDT_300.csv | tf_sec | 263 | 300 | context |
| data/recorder/2026-03-27/1000PEPEUSDT_900.csv | symbol | 88 | 1000PEPEUSDT | context |
| data/recorder/2026-03-27/1000PEPEUSDT_900.csv | regime | 88 | PENDING | context |
| data/recorder/2026-03-27/1000PEPEUSDT_900.csv | tf_sec | 88 | 900 | context |
| data/recorder/2026-03-27/BNBUSDT_180.csv | symbol | 440 | BNBUSDT | context |
| data/recorder/2026-03-27/BNBUSDT_180.csv | regime | 440 | MEAN_REVERSION, PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-03-27/BNBUSDT_180.csv | tf_sec | 440 | 180 | context |
| data/recorder/2026-03-27/BNBUSDT_300.csv | symbol | 263 | BNBUSDT | context |
| data/recorder/2026-03-27/BNBUSDT_300.csv | regime | 263 | PENDING | context |
| data/recorder/2026-03-27/BNBUSDT_300.csv | tf_sec | 263 | 300 | context |
| data/recorder/2026-03-27/BNBUSDT_900.csv | symbol | 7 | BNBUSDT, 0.0 | context |
| data/recorder/2026-03-27/BNBUSDT_900.csv | regime | 7 | PENDING, True | context |
| data/recorder/2026-03-27/BNBUSDT_900.csv | tf_sec | 7 | 900, BNBUSDT | context |
| data/recorder/2026-03-27/BTCUSDT_180.csv | symbol | 440 | BTCUSDT | context |
| data/recorder/2026-03-27/BTCUSDT_180.csv | regime | 440 | TREND_DOWN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-03-27/BTCUSDT_180.csv | tf_sec | 440 | 180 | context |
| data/recorder/2026-03-27/BTCUSDT_300.csv | symbol | 564 | BTCUSDT, 61, 1 | context |
| data/recorder/2026-03-27/BTCUSDT_300.csv | regime | 564 | PENDING, 300 | context |
| data/recorder/2026-03-27/BTCUSDT_300.csv | tf_sec | 564 | 300, 0, 296.071, 10617.454, 3676.197 | context |
| data/recorder/2026-03-27/BTCUSDT_900.csv | symbol | 88 | BTCUSDT | context |
| data/recorder/2026-03-27/BTCUSDT_900.csv | regime | 88 | PENDING | context |
| data/recorder/2026-03-27/BTCUSDT_900.csv | tf_sec | 88 | 900 | context |
| data/recorder/2026-03-27/DOGEUSDT_180.csv | symbol | 440 | DOGEUSDT | context |
| data/recorder/2026-03-27/DOGEUSDT_180.csv | regime | 440 | MEAN_REVERSION, PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-03-27/DOGEUSDT_180.csv | tf_sec | 440 | 180 | context |
| data/recorder/2026-03-27/DOGEUSDT_300.csv | symbol | 564 | DOGEUSDT | context |
| data/recorder/2026-03-27/DOGEUSDT_300.csv | regime | 564 | PENDING | context |
| data/recorder/2026-03-27/DOGEUSDT_300.csv | tf_sec | 564 | 300 | context |
| data/recorder/2026-03-27/DOGEUSDT_900.csv | symbol | 88 | DOGEUSDT | context |
| data/recorder/2026-03-27/DOGEUSDT_900.csv | regime | 88 | PENDING | context |
| data/recorder/2026-03-27/DOGEUSDT_900.csv | tf_sec | 88 | 900 | context |
| data/recorder/2026-03-27/ETHUSDT_180.csv | symbol | 440 | ETHUSDT | context |
| data/recorder/2026-03-27/ETHUSDT_180.csv | regime | 440 | TREND_DOWN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-03-27/ETHUSDT_180.csv | tf_sec | 440 | 180 | context |
| data/recorder/2026-03-27/ETHUSDT_300.csv | symbol | 565 | ETHUSDT, 1 | context |
| data/recorder/2026-03-27/ETHUSDT_300.csv | regime | 565 | PENDING, 300 | context |
| data/recorder/2026-03-27/ETHUSDT_300.csv | tf_sec | 565 | 300, 178884.267, 109998.722, 440322.602, 107337.999 | context |
| data/recorder/2026-03-27/ETHUSDT_900.csv | symbol | 88 | ETHUSDT | context |
| data/recorder/2026-03-27/ETHUSDT_900.csv | regime | 88 | PENDING | context |
| data/recorder/2026-03-27/ETHUSDT_900.csv | tf_sec | 88 | 900 | context |
| data/recorder/2026-03-27/SOLUSDT_180.csv | symbol | 440 | SOLUSDT | context |
| data/recorder/2026-03-27/SOLUSDT_180.csv | regime | 440 | TREND_DOWN, PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-27/SOLUSDT_180.csv | tf_sec | 440 | 180 | context |
| data/recorder/2026-03-27/SOLUSDT_300.csv | symbol | 565 | SOLUSDT, 1 | context |
| data/recorder/2026-03-27/SOLUSDT_300.csv | regime | 565 | PENDING, 300 | context |
| data/recorder/2026-03-27/SOLUSDT_300.csv | tf_sec | 565 | 300, 23805.46, 15744.99, 10601.02, 60554.72 | context |
| data/recorder/2026-03-27/SOLUSDT_900.csv | symbol | 88 | SOLUSDT | context |
| data/recorder/2026-03-27/SOLUSDT_900.csv | regime | 88 | PENDING | context |
| data/recorder/2026-03-27/SOLUSDT_900.csv | tf_sec | 88 | 900 | context |
| data/recorder/2026-03-27/XRPUSDT_180.csv | symbol | 440 | XRPUSDT | context |
| data/recorder/2026-03-27/XRPUSDT_180.csv | regime | 440 | MEAN_REVERSION, PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-03-27/XRPUSDT_180.csv | tf_sec | 440 | 180 | context |
| data/recorder/2026-03-27/XRPUSDT_300.csv | symbol | 263 | XRPUSDT | context |
| data/recorder/2026-03-27/XRPUSDT_300.csv | regime | 263 | PENDING | context |
| data/recorder/2026-03-27/XRPUSDT_300.csv | tf_sec | 263 | 300 | context |
| data/recorder/2026-03-27/XRPUSDT_900.csv | symbol | 6 | XRPUSDT, 0.0 | context |
| data/recorder/2026-03-27/XRPUSDT_900.csv | regime | 6 | PENDING, True | context |
| data/recorder/2026-03-27/XRPUSDT_900.csv | tf_sec | 6 | 900, XRPUSDT | context |
| data/recorder/2026-03-28/1000PEPEUSDT_180.csv | symbol | 480 | 1000PEPEUSDT | context |
| data/recorder/2026-03-28/1000PEPEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-03-28/1000PEPEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-28/1000PEPEUSDT_300.csv | symbol | 288 | 1000PEPEUSDT | context |
| data/recorder/2026-03-28/1000PEPEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-28/1000PEPEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-28/1000PEPEUSDT_900.csv | symbol | 96 | 1000PEPEUSDT | context |
| data/recorder/2026-03-28/1000PEPEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-28/1000PEPEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-28/BNBUSDT_180.csv | symbol | 480 | BNBUSDT | context |
| data/recorder/2026-03-28/BNBUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-03-28/BNBUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-28/BNBUSDT_300.csv | symbol | 288 | BNBUSDT | context |
| data/recorder/2026-03-28/BNBUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-28/BNBUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-28/BNBUSDT_900.csv | symbol | 96 | BNBUSDT | context |
| data/recorder/2026-03-28/BNBUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-28/BNBUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-28/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-03-28/BTCUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-03-28/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-28/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-03-28/BTCUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-28/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-28/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-03-28/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-28/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-28/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-03-28/DOGEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-03-28/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-28/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-03-28/DOGEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-28/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-28/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-03-28/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-28/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-28/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-03-28/ETHUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-03-28/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-28/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-03-28/ETHUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-28/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-28/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-03-28/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-28/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-28/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-03-28/SOLUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-03-28/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-28/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-03-28/SOLUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-28/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-28/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-03-28/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-28/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-28/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-03-28/XRPUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-03-28/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-28/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-03-28/XRPUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-28/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-28/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-03-28/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-28/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-29/1000PEPEUSDT_180.csv | symbol | 178 | 1000PEPEUSDT | context |
| data/recorder/2026-03-29/1000PEPEUSDT_180.csv | regime | 178 | TREND_DOWN, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-29/1000PEPEUSDT_180.csv | tf_sec | 178 | 180 | context |
| data/recorder/2026-03-29/1000PEPEUSDT_300.csv | symbol | 107 | 1000PEPEUSDT | context |
| data/recorder/2026-03-29/1000PEPEUSDT_300.csv | regime | 107 | PENDING | context |
| data/recorder/2026-03-29/1000PEPEUSDT_300.csv | tf_sec | 107 | 300 | context |
| data/recorder/2026-03-29/1000PEPEUSDT_900.csv | symbol | 36 | 1000PEPEUSDT | context |
| data/recorder/2026-03-29/1000PEPEUSDT_900.csv | regime | 36 | PENDING | context |
| data/recorder/2026-03-29/1000PEPEUSDT_900.csv | tf_sec | 36 | 900 | context |
| data/recorder/2026-03-29/BNBUSDT_180.csv | symbol | 178 | BNBUSDT | context |
| data/recorder/2026-03-29/BNBUSDT_180.csv | regime | 178 | UNCERTAIN, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-03-29/BNBUSDT_180.csv | tf_sec | 178 | 180 | context |
| data/recorder/2026-03-29/BNBUSDT_300.csv | symbol | 107 | BNBUSDT | context |
| data/recorder/2026-03-29/BNBUSDT_300.csv | regime | 107 | PENDING | context |
| data/recorder/2026-03-29/BNBUSDT_300.csv | tf_sec | 107 | 300 | context |
| data/recorder/2026-03-29/BNBUSDT_900.csv | symbol | 324 | BNBUSDT | context |
| data/recorder/2026-03-29/BNBUSDT_900.csv | regime | 324 | PENDING | context |
| data/recorder/2026-03-29/BNBUSDT_900.csv | tf_sec | 324 | 900 | context |
| data/recorder/2026-03-29/BTCUSDT_180.csv | symbol | 178 | BTCUSDT | context |
| data/recorder/2026-03-29/BTCUSDT_180.csv | regime | 178 | UNCERTAIN, PENDING, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-03-29/BTCUSDT_180.csv | tf_sec | 178 | 180 | context |
| data/recorder/2026-03-29/BTCUSDT_300.csv | symbol | 2495 | BTCUSDT, 1, 9 | context |
| data/recorder/2026-03-29/BTCUSDT_300.csv | regime | 2495 | PENDING, 300 | context |
| data/recorder/2026-03-29/BTCUSDT_300.csv | tf_sec | 2495 | 300, 5260.589, 1210.533, 1681.059, 59.176 | context |
| data/recorder/2026-03-29/BTCUSDT_900.csv | symbol | 36 | BTCUSDT | context |
| data/recorder/2026-03-29/BTCUSDT_900.csv | regime | 36 | PENDING | context |
| data/recorder/2026-03-29/BTCUSDT_900.csv | tf_sec | 36 | 900 | context |
| data/recorder/2026-03-29/DOGEUSDT_180.csv | symbol | 178 | DOGEUSDT | context |
| data/recorder/2026-03-29/DOGEUSDT_180.csv | regime | 178 | TREND_DOWN, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-29/DOGEUSDT_180.csv | tf_sec | 178 | 180 | context |
| data/recorder/2026-03-29/DOGEUSDT_300.csv | symbol | 961 | DOGEUSDT | context |
| data/recorder/2026-03-29/DOGEUSDT_300.csv | regime | 961 | PENDING | context |
| data/recorder/2026-03-29/DOGEUSDT_300.csv | tf_sec | 961 | 300 | context |
| data/recorder/2026-03-29/DOGEUSDT_900.csv | symbol | 36 | DOGEUSDT | context |
| data/recorder/2026-03-29/DOGEUSDT_900.csv | regime | 36 | PENDING | context |
| data/recorder/2026-03-29/DOGEUSDT_900.csv | tf_sec | 36 | 900 | context |
| data/recorder/2026-03-29/ETHUSDT_180.csv | symbol | 178 | ETHUSDT | context |
| data/recorder/2026-03-29/ETHUSDT_180.csv | regime | 178 | UNCERTAIN, PENDING, TREND_DOWN, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-03-29/ETHUSDT_180.csv | tf_sec | 178 | 180 | context |
| data/recorder/2026-03-29/ETHUSDT_300.csv | symbol | 2096 | ETHUSDT, 1, 3 | context |
| data/recorder/2026-03-29/ETHUSDT_300.csv | regime | 2096 | PENDING, 300 | context |
| data/recorder/2026-03-29/ETHUSDT_300.csv | tf_sec | 2096 | 300, 1673.903, 100984.54, 289711.126, 167933.143 | context |
| data/recorder/2026-03-29/ETHUSDT_900.csv | symbol | 36 | ETHUSDT | context |
| data/recorder/2026-03-29/ETHUSDT_900.csv | regime | 36 | PENDING | context |
| data/recorder/2026-03-29/ETHUSDT_900.csv | tf_sec | 36 | 900 | context |
| data/recorder/2026-03-29/SOLUSDT_180.csv | symbol | 178 | SOLUSDT | context |
| data/recorder/2026-03-29/SOLUSDT_180.csv | regime | 178 | TREND_DOWN, PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-29/SOLUSDT_180.csv | tf_sec | 178 | 180 | context |
| data/recorder/2026-03-29/SOLUSDT_300.csv | symbol | 1913 | SOLUSDT, 1, 23 | context |
| data/recorder/2026-03-29/SOLUSDT_300.csv | regime | 1913 | PENDING, 300 | context |
| data/recorder/2026-03-29/SOLUSDT_300.csv | tf_sec | 1913 | 300, 7153.43, 18454.26, 22409.47, 26636.04 | context |
| data/recorder/2026-03-29/SOLUSDT_900.csv | symbol | 36 | SOLUSDT | context |
| data/recorder/2026-03-29/SOLUSDT_900.csv | regime | 36 | PENDING | context |
| data/recorder/2026-03-29/SOLUSDT_900.csv | tf_sec | 36 | 900 | context |
| data/recorder/2026-03-29/XRPUSDT_180.csv | symbol | 178 | XRPUSDT | context |
| data/recorder/2026-03-29/XRPUSDT_180.csv | regime | 178 | UNCERTAIN, PENDING, TREND_DOWN, LOW_VOLATILITY, HIGH_VOLATILITY | context |
| data/recorder/2026-03-29/XRPUSDT_180.csv | tf_sec | 178 | 180 | context |
| data/recorder/2026-03-29/XRPUSDT_300.csv | symbol | 107 | XRPUSDT | context |
| data/recorder/2026-03-29/XRPUSDT_300.csv | regime | 107 | PENDING | context |
| data/recorder/2026-03-29/XRPUSDT_300.csv | tf_sec | 107 | 300 | context |
| data/recorder/2026-03-29/XRPUSDT_900.csv | symbol | 228 | XRPUSDT | context |
| data/recorder/2026-03-29/XRPUSDT_900.csv | regime | 228 | PENDING | context |
| data/recorder/2026-03-29/XRPUSDT_900.csv | tf_sec | 228 | 900 | context |
| data/recorder/2026-03-30/1000PEPEUSDT_180.csv | symbol | 479 | 1000PEPEUSDT | context |
| data/recorder/2026-03-30/1000PEPEUSDT_180.csv | regime | 479 | MEAN_REVERSION, PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-03-30/1000PEPEUSDT_180.csv | tf_sec | 479 | 180 | context |
| data/recorder/2026-03-30/1000PEPEUSDT_300.csv | symbol | 288 | 1000PEPEUSDT | context |
| data/recorder/2026-03-30/1000PEPEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-30/1000PEPEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-30/1000PEPEUSDT_900.csv | symbol | 96 | 1000PEPEUSDT | context |
| data/recorder/2026-03-30/1000PEPEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-30/1000PEPEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-30/BNBUSDT_180.csv | symbol | 479 | BNBUSDT | context |
| data/recorder/2026-03-30/BNBUSDT_180.csv | regime | 479 | TREND_DOWN, PENDING, HIGH_VOLATILITY, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-03-30/BNBUSDT_180.csv | tf_sec | 479 | 180 | context |
| data/recorder/2026-03-30/BNBUSDT_300.csv | symbol | 288 | BNBUSDT | context |
| data/recorder/2026-03-30/BNBUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-30/BNBUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-30/BNBUSDT_900.csv | symbol | 96 | BNBUSDT | context |
| data/recorder/2026-03-30/BNBUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-30/BNBUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-30/BTCUSDT_180.csv | symbol | 479 | BTCUSDT | context |
| data/recorder/2026-03-30/BTCUSDT_180.csv | regime | 479 | UNCERTAIN, PENDING, TREND_DOWN, HIGH_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-03-30/BTCUSDT_180.csv | tf_sec | 479 | 180 | context |
| data/recorder/2026-03-30/BTCUSDT_300.csv | symbol | 589 | BTCUSDT, 1 | context |
| data/recorder/2026-03-30/BTCUSDT_300.csv | regime | 589 | PENDING, 300 | context |
| data/recorder/2026-03-30/BTCUSDT_300.csv | tf_sec | 589 | 300, 22712.37, 2285.421, 5077.952, 601.241 | context |
| data/recorder/2026-03-30/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-03-30/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-30/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-30/DOGEUSDT_180.csv | symbol | 479 | DOGEUSDT | context |
| data/recorder/2026-03-30/DOGEUSDT_180.csv | regime | 479 | MEAN_REVERSION, PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-03-30/DOGEUSDT_180.csv | tf_sec | 479 | 180 | context |
| data/recorder/2026-03-30/DOGEUSDT_300.csv | symbol | 589 | DOGEUSDT | context |
| data/recorder/2026-03-30/DOGEUSDT_300.csv | regime | 589 | PENDING | context |
| data/recorder/2026-03-30/DOGEUSDT_300.csv | tf_sec | 589 | 300 | context |
| data/recorder/2026-03-30/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-03-30/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-30/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-30/ETHUSDT_180.csv | symbol | 479 | ETHUSDT | context |
| data/recorder/2026-03-30/ETHUSDT_180.csv | regime | 479 | UNCERTAIN, PENDING, HIGH_VOLATILITY, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-03-30/ETHUSDT_180.csv | tf_sec | 479 | 180 | context |
| data/recorder/2026-03-30/ETHUSDT_300.csv | symbol | 589 | ETHUSDT, 1, 2 | context |
| data/recorder/2026-03-30/ETHUSDT_300.csv | regime | 589 | PENDING, 300 | context |
| data/recorder/2026-03-30/ETHUSDT_300.csv | tf_sec | 589 | 300, 110164.881, 130291.595, 59039.999, 168148.362 | context |
| data/recorder/2026-03-30/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-03-30/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-30/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-30/SOLUSDT_180.csv | symbol | 479 | SOLUSDT | context |
| data/recorder/2026-03-30/SOLUSDT_180.csv | regime | 479 | TREND_DOWN, PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-03-30/SOLUSDT_180.csv | tf_sec | 479 | 180 | context |
| data/recorder/2026-03-30/SOLUSDT_300.csv | symbol | 589 | SOLUSDT, 1, 3 | context |
| data/recorder/2026-03-30/SOLUSDT_300.csv | regime | 589 | PENDING, 300 | context |
| data/recorder/2026-03-30/SOLUSDT_300.csv | tf_sec | 589 | 300, 7074.6, 3753.3, 5962.11, 9202.28 | context |
| data/recorder/2026-03-30/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-03-30/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-30/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-30/XRPUSDT_180.csv | symbol | 479 | XRPUSDT | context |
| data/recorder/2026-03-30/XRPUSDT_180.csv | regime | 479 | UNCERTAIN, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, TREND_UP | context |
| data/recorder/2026-03-30/XRPUSDT_180.csv | tf_sec | 479 | 180 | context |
| data/recorder/2026-03-30/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-03-30/XRPUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-30/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-30/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-03-30/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-30/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-31/1000PEPEUSDT_180.csv | symbol | 480 | 1000PEPEUSDT | context |
| data/recorder/2026-03-31/1000PEPEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, TREND_DOWN | context |
| data/recorder/2026-03-31/1000PEPEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-31/1000PEPEUSDT_300.csv | symbol | 288 | 1000PEPEUSDT | context |
| data/recorder/2026-03-31/1000PEPEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-31/1000PEPEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-31/1000PEPEUSDT_900.csv | symbol | 96 | 1000PEPEUSDT | context |
| data/recorder/2026-03-31/1000PEPEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-31/1000PEPEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-31/BNBUSDT_180.csv | symbol | 480 | BNBUSDT | context |
| data/recorder/2026-03-31/BNBUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-03-31/BNBUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-31/BNBUSDT_300.csv | symbol | 214 | BNBUSDT, True | context |
| data/recorder/2026-03-31/BNBUSDT_300.csv | regime | 214 | PENDING, None | context |
| data/recorder/2026-03-31/BNBUSDT_300.csv | tf_sec | 214 | 300, PENDING | context |
| data/recorder/2026-03-31/BNBUSDT_900.csv | symbol | 96 | BNBUSDT | context |
| data/recorder/2026-03-31/BNBUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-31/BNBUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-31/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-03-31/BTCUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, TREND_DOWN | context |
| data/recorder/2026-03-31/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-31/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-03-31/BTCUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-31/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-31/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-03-31/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-31/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-31/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-03-31/DOGEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-03-31/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-31/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-03-31/DOGEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-31/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-31/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-03-31/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-31/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-31/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-03-31/ETHUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-03-31/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-31/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-03-31/ETHUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-31/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-31/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-03-31/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-31/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-31/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-03-31/SOLUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_DOWN, TREND_UP | context |
| data/recorder/2026-03-31/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-31/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-03-31/SOLUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-03-31/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-03-31/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-03-31/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-31/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-03-31/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-03-31/XRPUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-03-31/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-03-31/XRPUSDT_300.csv | symbol | 214 | XRPUSDT, True | context |
| data/recorder/2026-03-31/XRPUSDT_300.csv | regime | 214 | PENDING, None | context |
| data/recorder/2026-03-31/XRPUSDT_300.csv | tf_sec | 214 | 300, PENDING | context |
| data/recorder/2026-03-31/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-03-31/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-03-31/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-01/1000PEPEUSDT_180.csv | symbol | 174 | 1000PEPEUSDT | context |
| data/recorder/2026-04-01/1000PEPEUSDT_180.csv | regime | 174 | UNCERTAIN, PENDING, TREND_UP, TREND_DOWN | context |
| data/recorder/2026-04-01/1000PEPEUSDT_180.csv | tf_sec | 174 | 180 | context |
| data/recorder/2026-04-01/1000PEPEUSDT_300.csv | symbol | 104 | 1000PEPEUSDT | context |
| data/recorder/2026-04-01/1000PEPEUSDT_300.csv | regime | 104 | PENDING | context |
| data/recorder/2026-04-01/1000PEPEUSDT_300.csv | tf_sec | 104 | 300 | context |
| data/recorder/2026-04-01/1000PEPEUSDT_900.csv | symbol | 35 | 1000PEPEUSDT | context |
| data/recorder/2026-04-01/1000PEPEUSDT_900.csv | regime | 35 | PENDING | context |
| data/recorder/2026-04-01/1000PEPEUSDT_900.csv | tf_sec | 35 | 900 | context |
| data/recorder/2026-04-01/BNBUSDT_180.csv | symbol | 174 | BNBUSDT | context |
| data/recorder/2026-04-01/BNBUSDT_180.csv | regime | 174 | UNCERTAIN, PENDING, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-01/BNBUSDT_180.csv | tf_sec | 174 | 180 | context |
| data/recorder/2026-04-01/BNBUSDT_300.csv | symbol | 104 | BNBUSDT, 32, 59, 60 | context |
| data/recorder/2026-04-01/BNBUSDT_300.csv | regime | 104 | PENDING, 300 | context |
| data/recorder/2026-04-01/BNBUSDT_300.csv | tf_sec | 104 | 300, 0 | context |
| data/recorder/2026-04-01/BNBUSDT_900.csv | symbol | 35 | BNBUSDT | context |
| data/recorder/2026-04-01/BNBUSDT_900.csv | regime | 35 | PENDING | context |
| data/recorder/2026-04-01/BNBUSDT_900.csv | tf_sec | 35 | 900 | context |
| data/recorder/2026-04-01/BTCUSDT_180.csv | symbol | 174 | BTCUSDT | context |
| data/recorder/2026-04-01/BTCUSDT_180.csv | regime | 174 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-01/BTCUSDT_180.csv | tf_sec | 174 | 180 | context |
| data/recorder/2026-04-01/BTCUSDT_300.csv | symbol | 405 | BTCUSDT, 1 | context |
| data/recorder/2026-04-01/BTCUSDT_300.csv | regime | 405 | PENDING, 300 | context |
| data/recorder/2026-04-01/BTCUSDT_300.csv | tf_sec | 405 | 300, 9170.7032, 5687.3713, 7625.923, 9986.4961 | context |
| data/recorder/2026-04-01/BTCUSDT_900.csv | symbol | 35 | BTCUSDT | context |
| data/recorder/2026-04-01/BTCUSDT_900.csv | regime | 35 | PENDING | context |
| data/recorder/2026-04-01/BTCUSDT_900.csv | tf_sec | 35 | 900 | context |
| data/recorder/2026-04-01/DOGEUSDT_180.csv | symbol | 174 | DOGEUSDT | context |
| data/recorder/2026-04-01/DOGEUSDT_180.csv | regime | 174 | TREND_UP, PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-04-01/DOGEUSDT_180.csv | tf_sec | 174 | 180 | context |
| data/recorder/2026-04-01/DOGEUSDT_300.csv | symbol | 405 | DOGEUSDT | context |
| data/recorder/2026-04-01/DOGEUSDT_300.csv | regime | 405 | PENDING | context |
| data/recorder/2026-04-01/DOGEUSDT_300.csv | tf_sec | 405 | 300 | context |
| data/recorder/2026-04-01/DOGEUSDT_900.csv | symbol | 35 | DOGEUSDT | context |
| data/recorder/2026-04-01/DOGEUSDT_900.csv | regime | 35 | PENDING | context |
| data/recorder/2026-04-01/DOGEUSDT_900.csv | tf_sec | 35 | 900 | context |
| data/recorder/2026-04-01/ETHUSDT_180.csv | symbol | 174 | ETHUSDT | context |
| data/recorder/2026-04-01/ETHUSDT_180.csv | regime | 174 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-01/ETHUSDT_180.csv | tf_sec | 174 | 180 | context |
| data/recorder/2026-04-01/ETHUSDT_300.csv | symbol | 405 | ETHUSDT, 1, 2 | context |
| data/recorder/2026-04-01/ETHUSDT_300.csv | regime | 405 | PENDING, 300 | context |
| data/recorder/2026-04-01/ETHUSDT_300.csv | tf_sec | 405 | 300, 214671.368, 194845.751, 225672.088, 335543.452 | context |
| data/recorder/2026-04-01/ETHUSDT_900.csv | symbol | 35 | ETHUSDT | context |
| data/recorder/2026-04-01/ETHUSDT_900.csv | regime | 35 | PENDING | context |
| data/recorder/2026-04-01/ETHUSDT_900.csv | tf_sec | 35 | 900 | context |
| data/recorder/2026-04-01/SOLUSDT_180.csv | symbol | 174 | SOLUSDT | context |
| data/recorder/2026-04-01/SOLUSDT_180.csv | regime | 174 | TREND_UP, PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-01/SOLUSDT_180.csv | tf_sec | 174 | 180 | context |
| data/recorder/2026-04-01/SOLUSDT_300.csv | symbol | 405 | SOLUSDT, 1, 3 | context |
| data/recorder/2026-04-01/SOLUSDT_300.csv | regime | 405 | PENDING, 300 | context |
| data/recorder/2026-04-01/SOLUSDT_300.csv | tf_sec | 405 | 300, 17762.91, 11787.33, 39117.38, 35478.94 | context |
| data/recorder/2026-04-01/SOLUSDT_900.csv | symbol | 35 | SOLUSDT | context |
| data/recorder/2026-04-01/SOLUSDT_900.csv | regime | 35 | PENDING | context |
| data/recorder/2026-04-01/SOLUSDT_900.csv | tf_sec | 35 | 900 | context |
| data/recorder/2026-04-01/XRPUSDT_180.csv | symbol | 174 | XRPUSDT | context |
| data/recorder/2026-04-01/XRPUSDT_180.csv | regime | 174 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-04-01/XRPUSDT_180.csv | tf_sec | 174 | 180 | context |
| data/recorder/2026-04-01/XRPUSDT_300.csv | symbol | 104 | XRPUSDT, 32, 59, 60 | context |
| data/recorder/2026-04-01/XRPUSDT_300.csv | regime | 104 | PENDING, 300 | context |
| data/recorder/2026-04-01/XRPUSDT_300.csv | tf_sec | 104 | 300, 0 | context |
| data/recorder/2026-04-01/XRPUSDT_900.csv | symbol | 35 | XRPUSDT | context |
| data/recorder/2026-04-01/XRPUSDT_900.csv | regime | 35 | PENDING | context |
| data/recorder/2026-04-01/XRPUSDT_900.csv | tf_sec | 35 | 900 | context |
| data/recorder/2026-04-02/1000PEPEUSDT_180.csv | symbol | 480 | 1000PEPEUSDT | context |
| data/recorder/2026-04-02/1000PEPEUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-04-02/1000PEPEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-02/1000PEPEUSDT_300.csv | symbol | 288 | 1000PEPEUSDT | context |
| data/recorder/2026-04-02/1000PEPEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-04-02/1000PEPEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-02/1000PEPEUSDT_900.csv | symbol | 96 | 1000PEPEUSDT | context |
| data/recorder/2026-04-02/1000PEPEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-02/1000PEPEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-02/BNBUSDT_180.csv | symbol | 480 | BNBUSDT | context |
| data/recorder/2026-04-02/BNBUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, LOW_VOLATILITY, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-04-02/BNBUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-02/BNBUSDT_300.csv | symbol | 288 | BNBUSDT | context |
| data/recorder/2026-04-02/BNBUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-04-02/BNBUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-02/BNBUSDT_900.csv | symbol | 96 | BNBUSDT | context |
| data/recorder/2026-04-02/BNBUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-02/BNBUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-02/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-04-02/BTCUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-02/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-02/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-04-02/BTCUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-04-02/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-02/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-04-02/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-02/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-02/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-04-02/DOGEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-04-02/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-02/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-04-02/DOGEUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-04-02/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-02/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-04-02/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-02/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-02/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-04-02/ETHUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-04-02/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-02/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-04-02/ETHUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-04-02/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-02/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-04-02/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-02/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-02/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-04-02/SOLUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-02/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-02/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-04-02/SOLUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-04-02/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-02/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-04-02/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-02/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-02/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-04-02/XRPUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-02/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-02/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-04-02/XRPUSDT_300.csv | regime | 288 | PENDING | context |
| data/recorder/2026-04-02/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-02/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-04-02/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-02/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-03/1000PEPEUSDT_180.csv | symbol | 263 | 1000PEPEUSDT, 0.0 | context |
| data/recorder/2026-04-03/1000PEPEUSDT_180.csv | regime | 263 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-03/1000PEPEUSDT_180.csv | tf_sec | 262 | 180 | context |
| data/recorder/2026-04-03/1000PEPEUSDT_300.csv | symbol | 158 | 1000PEPEUSDT, 0.0 | context |
| data/recorder/2026-04-03/1000PEPEUSDT_300.csv | regime | 158 | PENDING | context |
| data/recorder/2026-04-03/1000PEPEUSDT_300.csv | tf_sec | 157 | 300 | context |
| data/recorder/2026-04-03/1000PEPEUSDT_900.csv | symbol | 53 | 1000PEPEUSDT, 0.0 | context |
| data/recorder/2026-04-03/1000PEPEUSDT_900.csv | regime | 53 | PENDING | context |
| data/recorder/2026-04-03/1000PEPEUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-04-03/BNBUSDT_180.csv | symbol | 263 | BNBUSDT, 0.0 | context |
| data/recorder/2026-04-03/BNBUSDT_180.csv | regime | 263 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-03/BNBUSDT_180.csv | tf_sec | 262 | 180 | context |
| data/recorder/2026-04-03/BNBUSDT_300.csv | symbol | 157 | BNBUSDT, 40, 60, 59 | context |
| data/recorder/2026-04-03/BNBUSDT_300.csv | regime | 157 | PENDING, 300 | context |
| data/recorder/2026-04-03/BNBUSDT_300.csv | tf_sec | 158 | 300, 0, missing_timeout | context |
| data/recorder/2026-04-03/BNBUSDT_900.csv | symbol | 53 | BNBUSDT, 0.0 | context |
| data/recorder/2026-04-03/BNBUSDT_900.csv | regime | 53 | PENDING | context |
| data/recorder/2026-04-03/BNBUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-04-03/BTCUSDT_180.csv | symbol | 263 | BTCUSDT, 0.0 | context |
| data/recorder/2026-04-03/BTCUSDT_180.csv | regime | 263 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-03/BTCUSDT_180.csv | tf_sec | 262 | 180 | context |
| data/recorder/2026-04-03/BTCUSDT_300.csv | symbol | 459 | BTCUSDT, 1, 3, 1775155199999 | context |
| data/recorder/2026-04-03/BTCUSDT_300.csv | regime | 459 | PENDING, 300, stale_features | context |
| data/recorder/2026-04-03/BTCUSDT_300.csv | tf_sec | 459 | 300, 8260.4122, 1463.329, 8385.115, 166.56 | context |
| data/recorder/2026-04-03/BTCUSDT_900.csv | symbol | 53 | BTCUSDT, 0.0 | context |
| data/recorder/2026-04-03/BTCUSDT_900.csv | regime | 53 | PENDING | context |
| data/recorder/2026-04-03/BTCUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-04-03/DOGEUSDT_180.csv | symbol | 263 | DOGEUSDT, 0.0 | context |
| data/recorder/2026-04-03/DOGEUSDT_180.csv | regime | 263 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-03/DOGEUSDT_180.csv | tf_sec | 262 | 180 | context |
| data/recorder/2026-04-03/DOGEUSDT_300.csv | symbol | 459 | DOGEUSDT, 0.15 | context |
| data/recorder/2026-04-03/DOGEUSDT_300.csv | regime | 459 | PENDING, UNCERTAIN | context |
| data/recorder/2026-04-03/DOGEUSDT_300.csv | tf_sec | 459 | 300, stale_features | context |
| data/recorder/2026-04-03/DOGEUSDT_900.csv | symbol | 53 | DOGEUSDT, 0.0 | context |
| data/recorder/2026-04-03/DOGEUSDT_900.csv | regime | 53 | PENDING | context |
| data/recorder/2026-04-03/DOGEUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-04-03/ETHUSDT_180.csv | symbol | 263 | ETHUSDT, 0.0 | context |
| data/recorder/2026-04-03/ETHUSDT_180.csv | regime | 263 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-03/ETHUSDT_180.csv | tf_sec | 262 | 180 | context |
| data/recorder/2026-04-03/ETHUSDT_300.csv | symbol | 459 | ETHUSDT, 1, 1775155199999 | context |
| data/recorder/2026-04-03/ETHUSDT_300.csv | regime | 459 | PENDING, 300, stale_features | context |
| data/recorder/2026-04-03/ETHUSDT_300.csv | tf_sec | 459 | 300, 54234.355, 21297.52, 707.087, 83892.432 | context |
| data/recorder/2026-04-03/ETHUSDT_900.csv | symbol | 53 | ETHUSDT, 0.0 | context |
| data/recorder/2026-04-03/ETHUSDT_900.csv | regime | 53 | PENDING | context |
| data/recorder/2026-04-03/ETHUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-04-03/SOLUSDT_180.csv | symbol | 263 | SOLUSDT, 0.0 | context |
| data/recorder/2026-04-03/SOLUSDT_180.csv | regime | 263 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-03/SOLUSDT_180.csv | tf_sec | 262 | 180 | context |
| data/recorder/2026-04-03/SOLUSDT_300.csv | symbol | 459 | SOLUSDT, 1, 1775155199999 | context |
| data/recorder/2026-04-03/SOLUSDT_300.csv | regime | 459 | PENDING, 300, stale_features | context |
| data/recorder/2026-04-03/SOLUSDT_300.csv | tf_sec | 459 | 300, 16534.34, 10308.19, 4916.29, 5481.2 | context |
| data/recorder/2026-04-03/SOLUSDT_900.csv | symbol | 53 | SOLUSDT, 0.0 | context |
| data/recorder/2026-04-03/SOLUSDT_900.csv | regime | 53 | PENDING | context |
| data/recorder/2026-04-03/SOLUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-04-03/XRPUSDT_180.csv | symbol | 263 | XRPUSDT, 0.0 | context |
| data/recorder/2026-04-03/XRPUSDT_180.csv | regime | 263 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-03/XRPUSDT_180.csv | tf_sec | 262 | 180 | context |
| data/recorder/2026-04-03/XRPUSDT_300.csv | symbol | 157 | XRPUSDT, 40, 60, 59 | context |
| data/recorder/2026-04-03/XRPUSDT_300.csv | regime | 157 | PENDING, 300 | context |
| data/recorder/2026-04-03/XRPUSDT_300.csv | tf_sec | 158 | 300, 0, missing_timeout | context |
| data/recorder/2026-04-03/XRPUSDT_900.csv | symbol | 53 | XRPUSDT, 0.0 | context |
| data/recorder/2026-04-03/XRPUSDT_900.csv | regime | 53 | PENDING | context |
| data/recorder/2026-04-03/XRPUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-04-04/1000PEPEUSDT_180.csv | symbol | 465 | 1000PEPEUSDT | context |
| data/recorder/2026-04-04/1000PEPEUSDT_180.csv | regime | 465 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-04/1000PEPEUSDT_180.csv | tf_sec | 465 | 180 | context |
| data/recorder/2026-04-04/1000PEPEUSDT_300.csv | symbol | 279 | 1000PEPEUSDT | context |
| data/recorder/2026-04-04/1000PEPEUSDT_300.csv | regime | 279 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-04/1000PEPEUSDT_300.csv | tf_sec | 279 | 300 | context |
| data/recorder/2026-04-04/1000PEPEUSDT_900.csv | symbol | 92 | 1000PEPEUSDT | context |
| data/recorder/2026-04-04/1000PEPEUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-04/1000PEPEUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-04/BNBUSDT_180.csv | symbol | 465 | BNBUSDT | context |
| data/recorder/2026-04-04/BNBUSDT_180.csv | regime | 465 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-04/BNBUSDT_180.csv | tf_sec | 465 | 180 | context |
| data/recorder/2026-04-04/BNBUSDT_300.csv | symbol | 279 | BNBUSDT | context |
| data/recorder/2026-04-04/BNBUSDT_300.csv | regime | 279 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-04/BNBUSDT_300.csv | tf_sec | 279 | 300 | context |
| data/recorder/2026-04-04/BNBUSDT_900.csv | symbol | 92 | BNBUSDT | context |
| data/recorder/2026-04-04/BNBUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-04/BNBUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-04/BTCUSDT_180.csv | symbol | 465 | BTCUSDT | context |
| data/recorder/2026-04-04/BTCUSDT_180.csv | regime | 465 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-04/BTCUSDT_180.csv | tf_sec | 465 | 180 | context |
| data/recorder/2026-04-04/BTCUSDT_300.csv | symbol | 301 | BTCUSDT | context |
| data/recorder/2026-04-04/BTCUSDT_300.csv | regime | 302 | UNCERTAIN, PENDING, None | context |
| data/recorder/2026-04-04/BTCUSDT_300.csv | tf_sec | 301 | 300 | context |
| data/recorder/2026-04-04/BTCUSDT_900.csv | symbol | 92 | BTCUSDT | context |
| data/recorder/2026-04-04/BTCUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-04/BTCUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-04/DOGEUSDT_180.csv | symbol | 465 | DOGEUSDT | context |
| data/recorder/2026-04-04/DOGEUSDT_180.csv | regime | 465 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-04/DOGEUSDT_180.csv | tf_sec | 465 | 180 | context |
| data/recorder/2026-04-04/DOGEUSDT_300.csv | symbol | 881 | DOGEUSDT | context |
| data/recorder/2026-04-04/DOGEUSDT_300.csv | regime | 881 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-04/DOGEUSDT_300.csv | tf_sec | 881 | 300 | context |
| data/recorder/2026-04-04/DOGEUSDT_900.csv | symbol | 92 | DOGEUSDT | context |
| data/recorder/2026-04-04/DOGEUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-04/DOGEUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-04/ETHUSDT_180.csv | symbol | 465 | ETHUSDT | context |
| data/recorder/2026-04-04/ETHUSDT_180.csv | regime | 465 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-04-04/ETHUSDT_180.csv | tf_sec | 465 | 180 | context |
| data/recorder/2026-04-04/ETHUSDT_300.csv | symbol | 302 | ETHUSDT | context |
| data/recorder/2026-04-04/ETHUSDT_300.csv | regime | 303 | UNCERTAIN, PENDING, None | context |
| data/recorder/2026-04-04/ETHUSDT_300.csv | tf_sec | 302 | 300 | context |
| data/recorder/2026-04-04/ETHUSDT_900.csv | symbol | 92 | ETHUSDT | context |
| data/recorder/2026-04-04/ETHUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-04/ETHUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-04/SOLUSDT_180.csv | symbol | 465 | SOLUSDT | context |
| data/recorder/2026-04-04/SOLUSDT_180.csv | regime | 465 | PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-04-04/SOLUSDT_180.csv | tf_sec | 465 | 180 | context |
| data/recorder/2026-04-04/SOLUSDT_300.csv | symbol | 301 | SOLUSDT | context |
| data/recorder/2026-04-04/SOLUSDT_300.csv | regime | 302 | UNCERTAIN, PENDING, None | context |
| data/recorder/2026-04-04/SOLUSDT_300.csv | tf_sec | 301 | 300 | context |
| data/recorder/2026-04-04/SOLUSDT_900.csv | symbol | 92 | SOLUSDT | context |
| data/recorder/2026-04-04/SOLUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-04/SOLUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-04/XRPUSDT_180.csv | symbol | 465 | XRPUSDT | context |
| data/recorder/2026-04-04/XRPUSDT_180.csv | regime | 465 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-04/XRPUSDT_180.csv | tf_sec | 465 | 180 | context |
| data/recorder/2026-04-04/XRPUSDT_300.csv | symbol | 279 | XRPUSDT | context |
| data/recorder/2026-04-04/XRPUSDT_300.csv | regime | 279 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-04/XRPUSDT_300.csv | tf_sec | 279 | 300 | context |
| data/recorder/2026-04-04/XRPUSDT_900.csv | symbol | 92 | XRPUSDT | context |
| data/recorder/2026-04-04/XRPUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-04/XRPUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-05/1000PEPEUSDT_180.csv | symbol | 212 | 1000PEPEUSDT | context |
| data/recorder/2026-04-05/1000PEPEUSDT_180.csv | regime | 212 | UNCERTAIN, PENDING, TREND_UP, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-04-05/1000PEPEUSDT_180.csv | tf_sec | 212 | 180 | context |
| data/recorder/2026-04-05/1000PEPEUSDT_300.csv | symbol | 128 | 1000PEPEUSDT | context |
| data/recorder/2026-04-05/1000PEPEUSDT_300.csv | regime | 128 | PENDING, UNCERTAIN, TREND_UP, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-04-05/1000PEPEUSDT_300.csv | tf_sec | 128 | 300 | context |
| data/recorder/2026-04-05/1000PEPEUSDT_900.csv | symbol | 42 | 1000PEPEUSDT | context |
| data/recorder/2026-04-05/1000PEPEUSDT_900.csv | regime | 42 | PENDING | context |
| data/recorder/2026-04-05/1000PEPEUSDT_900.csv | tf_sec | 42 | 900 | context |
| data/recorder/2026-04-05/BNBUSDT_180.csv | symbol | 212 | BNBUSDT | context |
| data/recorder/2026-04-05/BNBUSDT_180.csv | regime | 212 | MEAN_REVERSION, PENDING, UNCERTAIN | context |
| data/recorder/2026-04-05/BNBUSDT_180.csv | tf_sec | 212 | 180 | context |
| data/recorder/2026-04-05/BNBUSDT_300.csv | symbol | 128 | BNBUSDT | context |
| data/recorder/2026-04-05/BNBUSDT_300.csv | regime | 128 | PENDING, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-05/BNBUSDT_300.csv | tf_sec | 128 | 300 | context |
| data/recorder/2026-04-05/BNBUSDT_900.csv | symbol | 42 | BNBUSDT | context |
| data/recorder/2026-04-05/BNBUSDT_900.csv | regime | 42 | PENDING | context |
| data/recorder/2026-04-05/BNBUSDT_900.csv | tf_sec | 42 | 900 | context |
| data/recorder/2026-04-05/BTCUSDT_180.csv | symbol | 212 | BTCUSDT | context |
| data/recorder/2026-04-05/BTCUSDT_180.csv | regime | 212 | MEAN_REVERSION, PENDING, UNCERTAIN, TREND_UP, HIGH_VOLATILITY | context |
| data/recorder/2026-04-05/BTCUSDT_180.csv | tf_sec | 212 | 180 | context |
| data/recorder/2026-04-05/BTCUSDT_300.csv | symbol | 730 | BTCUSDT, 1 | context |
| data/recorder/2026-04-05/BTCUSDT_300.csv | regime | 728 | PENDING, MEAN_REVERSION, UNCERTAIN, stale_features, TREND_UP | context |
| data/recorder/2026-04-05/BTCUSDT_300.csv | tf_sec | 730 | 300, 55.2134, 186.0413, 785.6544, 855.204 | context |
| data/recorder/2026-04-05/BTCUSDT_900.csv | symbol | 42 | BTCUSDT | context |
| data/recorder/2026-04-05/BTCUSDT_900.csv | regime | 42 | PENDING | context |
| data/recorder/2026-04-05/BTCUSDT_900.csv | tf_sec | 42 | 900 | context |
| data/recorder/2026-04-05/DOGEUSDT_180.csv | symbol | 212 | DOGEUSDT | context |
| data/recorder/2026-04-05/DOGEUSDT_180.csv | regime | 212 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-05/DOGEUSDT_180.csv | tf_sec | 212 | 180 | context |
| data/recorder/2026-04-05/DOGEUSDT_300.csv | symbol | 730 | DOGEUSDT | context |
| data/recorder/2026-04-05/DOGEUSDT_300.csv | regime | 730 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-05/DOGEUSDT_300.csv | tf_sec | 730 | 300 | context |
| data/recorder/2026-04-05/DOGEUSDT_900.csv | symbol | 42 | DOGEUSDT | context |
| data/recorder/2026-04-05/DOGEUSDT_900.csv | regime | 42 | PENDING | context |
| data/recorder/2026-04-05/DOGEUSDT_900.csv | tf_sec | 42 | 900 | context |
| data/recorder/2026-04-05/ETHUSDT_180.csv | symbol | 212 | ETHUSDT | context |
| data/recorder/2026-04-05/ETHUSDT_180.csv | regime | 212 | MEAN_REVERSION, PENDING, UNCERTAIN, TREND_UP, HIGH_VOLATILITY | context |
| data/recorder/2026-04-05/ETHUSDT_180.csv | tf_sec | 212 | 180 | context |
| data/recorder/2026-04-05/ETHUSDT_300.csv | symbol | 730 | ETHUSDT, 1, 2 | context |
| data/recorder/2026-04-05/ETHUSDT_300.csv | regime | 727 | PENDING, MEAN_REVERSION, UNCERTAIN, stale_features, TREND_UP | context |
| data/recorder/2026-04-05/ETHUSDT_300.csv | tf_sec | 730 | 300, 596.093, 691.681, 88614.976, 2539.81 | context |
| data/recorder/2026-04-05/ETHUSDT_900.csv | symbol | 42 | ETHUSDT | context |
| data/recorder/2026-04-05/ETHUSDT_900.csv | regime | 42 | PENDING | context |
| data/recorder/2026-04-05/ETHUSDT_900.csv | tf_sec | 42 | 900 | context |
| data/recorder/2026-04-05/SOLUSDT_180.csv | symbol | 212 | SOLUSDT | context |
| data/recorder/2026-04-05/SOLUSDT_180.csv | regime | 212 | MEAN_REVERSION, PENDING, UNCERTAIN, HIGH_VOLATILITY, LOW_VOLATILITY | context |
| data/recorder/2026-04-05/SOLUSDT_180.csv | tf_sec | 212 | 180 | context |
| data/recorder/2026-04-05/SOLUSDT_300.csv | symbol | 730 | SOLUSDT, 1, 3 | context |
| data/recorder/2026-04-05/SOLUSDT_300.csv | regime | 727 | PENDING, MEAN_REVERSION, UNCERTAIN, stale_features, HIGH_VOLATILITY | context |
| data/recorder/2026-04-05/SOLUSDT_300.csv | tf_sec | 730 | 300, 9791.58, 31535.12, 4446.8, 1785.39 | context |
| data/recorder/2026-04-05/SOLUSDT_900.csv | symbol | 42 | SOLUSDT | context |
| data/recorder/2026-04-05/SOLUSDT_900.csv | regime | 42 | PENDING | context |
| data/recorder/2026-04-05/SOLUSDT_900.csv | tf_sec | 42 | 900 | context |
| data/recorder/2026-04-05/XRPUSDT_180.csv | symbol | 212 | XRPUSDT | context |
| data/recorder/2026-04-05/XRPUSDT_180.csv | regime | 212 | MEAN_REVERSION, PENDING, UNCERTAIN, TREND_DOWN, TREND_UP | context |
| data/recorder/2026-04-05/XRPUSDT_180.csv | tf_sec | 212 | 180 | context |
| data/recorder/2026-04-05/XRPUSDT_300.csv | symbol | 128 | XRPUSDT | context |
| data/recorder/2026-04-05/XRPUSDT_300.csv | regime | 128 | PENDING, MEAN_REVERSION, UNCERTAIN, TREND_DOWN, TREND_UP | context |
| data/recorder/2026-04-05/XRPUSDT_300.csv | tf_sec | 128 | 300 | context |
| data/recorder/2026-04-05/XRPUSDT_900.csv | symbol | 42 | XRPUSDT | context |
| data/recorder/2026-04-05/XRPUSDT_900.csv | regime | 42 | PENDING | context |
| data/recorder/2026-04-05/XRPUSDT_900.csv | tf_sec | 42 | 900 | context |
| data/recorder/2026-04-06/1000PEPEUSDT_180.csv | symbol | 458 | 1000PEPEUSDT | context |
| data/recorder/2026-04-06/1000PEPEUSDT_180.csv | regime | 458 | HIGH_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-04-06/1000PEPEUSDT_180.csv | tf_sec | 458 | 180 | context |
| data/recorder/2026-04-06/1000PEPEUSDT_300.csv | symbol | 275 | 1000PEPEUSDT | context |
| data/recorder/2026-04-06/1000PEPEUSDT_300.csv | regime | 275 | PENDING, HIGH_VOLATILITY, UNCERTAIN, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-04-06/1000PEPEUSDT_300.csv | tf_sec | 275 | 300 | context |
| data/recorder/2026-04-06/1000PEPEUSDT_900.csv | symbol | 92 | 1000PEPEUSDT | context |
| data/recorder/2026-04-06/1000PEPEUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-06/1000PEPEUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-06/BNBUSDT_180.csv | symbol | 458 | BNBUSDT | context |
| data/recorder/2026-04-06/BNBUSDT_180.csv | regime | 458 | UNCERTAIN, PENDING, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-06/BNBUSDT_180.csv | tf_sec | 458 | 180 | context |
| data/recorder/2026-04-06/BNBUSDT_300.csv | symbol | 275 | BNBUSDT | context |
| data/recorder/2026-04-06/BNBUSDT_300.csv | regime | 275 | PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-06/BNBUSDT_300.csv | tf_sec | 275 | 300 | context |
| data/recorder/2026-04-06/BNBUSDT_900.csv | symbol | 92 | BNBUSDT | context |
| data/recorder/2026-04-06/BNBUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-06/BNBUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-06/BTCUSDT_180.csv | symbol | 458 | BTCUSDT | context |
| data/recorder/2026-04-06/BTCUSDT_180.csv | regime | 458 | HIGH_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-04-06/BTCUSDT_180.csv | tf_sec | 458 | 180 | context |
| data/recorder/2026-04-06/BTCUSDT_300.csv | symbol | 877 | BTCUSDT, 1 | context |
| data/recorder/2026-04-06/BTCUSDT_300.csv | regime | 876 | PENDING, HIGH_VOLATILITY, UNCERTAIN, TREND_UP, stale_features | context |
| data/recorder/2026-04-06/BTCUSDT_300.csv | tf_sec | 877 | 300, 3277.9655, 4289.6945, 1558.8073, 2687.3408 | context |
| data/recorder/2026-04-06/BTCUSDT_900.csv | symbol | 92 | BTCUSDT | context |
| data/recorder/2026-04-06/BTCUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-06/BTCUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-06/DOGEUSDT_180.csv | symbol | 458 | DOGEUSDT | context |
| data/recorder/2026-04-06/DOGEUSDT_180.csv | regime | 458 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-06/DOGEUSDT_180.csv | tf_sec | 458 | 180 | context |
| data/recorder/2026-04-06/DOGEUSDT_300.csv | symbol | 877 | DOGEUSDT | context |
| data/recorder/2026-04-06/DOGEUSDT_300.csv | regime | 877 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-06/DOGEUSDT_300.csv | tf_sec | 877 | 300 | context |
| data/recorder/2026-04-06/DOGEUSDT_900.csv | symbol | 92 | DOGEUSDT | context |
| data/recorder/2026-04-06/DOGEUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-06/DOGEUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-06/ETHUSDT_180.csv | symbol | 458 | ETHUSDT | context |
| data/recorder/2026-04-06/ETHUSDT_180.csv | regime | 458 | HIGH_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-06/ETHUSDT_180.csv | tf_sec | 458 | 180 | context |
| data/recorder/2026-04-06/ETHUSDT_300.csv | symbol | 877 | ETHUSDT, 1 | context |
| data/recorder/2026-04-06/ETHUSDT_300.csv | regime | 876 | PENDING, HIGH_VOLATILITY, TREND_UP, UNCERTAIN, stale_features | context |
| data/recorder/2026-04-06/ETHUSDT_300.csv | tf_sec | 877 | 300, 73739.13, 44556.832, 29660.8, 6293.875 | context |
| data/recorder/2026-04-06/ETHUSDT_900.csv | symbol | 92 | ETHUSDT | context |
| data/recorder/2026-04-06/ETHUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-06/ETHUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-06/SOLUSDT_180.csv | symbol | 458 | SOLUSDT | context |
| data/recorder/2026-04-06/SOLUSDT_180.csv | regime | 458 | TREND_UP, PENDING, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-06/SOLUSDT_180.csv | tf_sec | 458 | 180 | context |
| data/recorder/2026-04-06/SOLUSDT_300.csv | symbol | 877 | SOLUSDT, 1, 4 | context |
| data/recorder/2026-04-06/SOLUSDT_300.csv | regime | 874 | PENDING, TREND_UP, LOW_VOLATILITY, stale_features, UNCERTAIN | context |
| data/recorder/2026-04-06/SOLUSDT_300.csv | tf_sec | 877 | 300, 20994.22, 8604.02, 11529.0, 8730.85 | context |
| data/recorder/2026-04-06/SOLUSDT_900.csv | symbol | 92 | SOLUSDT | context |
| data/recorder/2026-04-06/SOLUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-06/SOLUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-06/XRPUSDT_180.csv | symbol | 458 | XRPUSDT | context |
| data/recorder/2026-04-06/XRPUSDT_180.csv | regime | 458 | TREND_UP, PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-06/XRPUSDT_180.csv | tf_sec | 458 | 180 | context |
| data/recorder/2026-04-06/XRPUSDT_300.csv | symbol | 275 | XRPUSDT | context |
| data/recorder/2026-04-06/XRPUSDT_300.csv | regime | 275 | PENDING, TREND_UP, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-06/XRPUSDT_300.csv | tf_sec | 275 | 300 | context |
| data/recorder/2026-04-06/XRPUSDT_900.csv | symbol | 92 | XRPUSDT | context |
| data/recorder/2026-04-06/XRPUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-06/XRPUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-07/1000PEPEUSDT_180.csv | symbol | 470 | 1000PEPEUSDT | context |
| data/recorder/2026-04-07/1000PEPEUSDT_180.csv | regime | 470 | TREND_DOWN, PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-07/1000PEPEUSDT_180.csv | tf_sec | 470 | 180 | context |
| data/recorder/2026-04-07/1000PEPEUSDT_300.csv | symbol | 282 | 1000PEPEUSDT | context |
| data/recorder/2026-04-07/1000PEPEUSDT_300.csv | regime | 282 | PENDING, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-07/1000PEPEUSDT_300.csv | tf_sec | 282 | 300 | context |
| data/recorder/2026-04-07/1000PEPEUSDT_900.csv | symbol | 94 | 1000PEPEUSDT | context |
| data/recorder/2026-04-07/1000PEPEUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-07/1000PEPEUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-07/BNBUSDT_180.csv | symbol | 470 | BNBUSDT | context |
| data/recorder/2026-04-07/BNBUSDT_180.csv | regime | 470 | UNCERTAIN, PENDING, TREND_DOWN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-07/BNBUSDT_180.csv | tf_sec | 470 | 180 | context |
| data/recorder/2026-04-07/BNBUSDT_300.csv | symbol | 282 | BNBUSDT | context |
| data/recorder/2026-04-07/BNBUSDT_300.csv | regime | 282 | PENDING, UNCERTAIN, TREND_DOWN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-07/BNBUSDT_300.csv | tf_sec | 282 | 300 | context |
| data/recorder/2026-04-07/BNBUSDT_900.csv | symbol | 94 | BNBUSDT | context |
| data/recorder/2026-04-07/BNBUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-07/BNBUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-07/BTCUSDT_180.csv | symbol | 470 | BTCUSDT | context |
| data/recorder/2026-04-07/BTCUSDT_180.csv | regime | 470 | UNCERTAIN, PENDING, TREND_DOWN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-07/BTCUSDT_180.csv | tf_sec | 470 | 180 | context |
| data/recorder/2026-04-07/BTCUSDT_300.csv | symbol | 583 | BTCUSDT, 1 | context |
| data/recorder/2026-04-07/BTCUSDT_300.csv | regime | 582 | PENDING, UNCERTAIN, TREND_DOWN, LOW_VOLATILITY, stale_features | context |
| data/recorder/2026-04-07/BTCUSDT_300.csv | tf_sec | 583 | 300, 14045.7292, 13763.4109, 2485.9241, 1290.9192 | context |
| data/recorder/2026-04-07/BTCUSDT_900.csv | symbol | 94 | BTCUSDT | context |
| data/recorder/2026-04-07/BTCUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-07/BTCUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-07/DOGEUSDT_180.csv | symbol | 470 | DOGEUSDT | context |
| data/recorder/2026-04-07/DOGEUSDT_180.csv | regime | 470 | TREND_DOWN, PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-07/DOGEUSDT_180.csv | tf_sec | 470 | 180 | context |
| data/recorder/2026-04-07/DOGEUSDT_300.csv | symbol | 583 | DOGEUSDT | context |
| data/recorder/2026-04-07/DOGEUSDT_300.csv | regime | 583 | PENDING, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-07/DOGEUSDT_300.csv | tf_sec | 583 | 300 | context |
| data/recorder/2026-04-07/DOGEUSDT_900.csv | symbol | 94 | DOGEUSDT | context |
| data/recorder/2026-04-07/DOGEUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-07/DOGEUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-07/ETHUSDT_180.csv | symbol | 470 | ETHUSDT | context |
| data/recorder/2026-04-07/ETHUSDT_180.csv | regime | 470 | TREND_DOWN, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-07/ETHUSDT_180.csv | tf_sec | 470 | 180 | context |
| data/recorder/2026-04-07/ETHUSDT_300.csv | symbol | 583 | ETHUSDT, 1 | context |
| data/recorder/2026-04-07/ETHUSDT_300.csv | regime | 582 | PENDING, TREND_DOWN, UNCERTAIN, LOW_VOLATILITY, stale_features | context |
| data/recorder/2026-04-07/ETHUSDT_300.csv | tf_sec | 583 | 300, 366021.903, 284371.867, 15691.762, 12187.103 | context |
| data/recorder/2026-04-07/ETHUSDT_900.csv | symbol | 94 | ETHUSDT | context |
| data/recorder/2026-04-07/ETHUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-07/ETHUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-07/SOLUSDT_180.csv | symbol | 470 | SOLUSDT | context |
| data/recorder/2026-04-07/SOLUSDT_180.csv | regime | 470 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-07/SOLUSDT_180.csv | tf_sec | 470 | 180 | context |
| data/recorder/2026-04-07/SOLUSDT_300.csv | symbol | 583 | SOLUSDT, 1, 43, 60 | context |
| data/recorder/2026-04-07/SOLUSDT_300.csv | regime | 582 | PENDING, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN, stale_features | context |
| data/recorder/2026-04-07/SOLUSDT_300.csv | tf_sec | 583 | 300, 473.03, 237027.16, 43115.66, 49510.28 | context |
| data/recorder/2026-04-07/SOLUSDT_900.csv | symbol | 94 | SOLUSDT | context |
| data/recorder/2026-04-07/SOLUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-07/SOLUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-07/XRPUSDT_180.csv | symbol | 470 | XRPUSDT | context |
| data/recorder/2026-04-07/XRPUSDT_180.csv | regime | 470 | TREND_DOWN, PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-07/XRPUSDT_180.csv | tf_sec | 470 | 180 | context |
| data/recorder/2026-04-07/XRPUSDT_300.csv | symbol | 282 | XRPUSDT | context |
| data/recorder/2026-04-07/XRPUSDT_300.csv | regime | 282 | PENDING, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-07/XRPUSDT_300.csv | tf_sec | 282 | 300 | context |
| data/recorder/2026-04-07/XRPUSDT_900.csv | symbol | 94 | XRPUSDT | context |
| data/recorder/2026-04-07/XRPUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-07/XRPUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-08/1000PEPEUSDT_180.csv | symbol | 365 | 1000PEPEUSDT | context |
| data/recorder/2026-04-08/1000PEPEUSDT_180.csv | regime | 365 | HIGH_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-04-08/1000PEPEUSDT_180.csv | tf_sec | 365 | 180 | context |
| data/recorder/2026-04-08/1000PEPEUSDT_300.csv | symbol | 219 | 1000PEPEUSDT | context |
| data/recorder/2026-04-08/1000PEPEUSDT_300.csv | regime | 219 | PENDING, HIGH_VOLATILITY, UNCERTAIN, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-04-08/1000PEPEUSDT_300.csv | tf_sec | 219 | 300 | context |
| data/recorder/2026-04-08/1000PEPEUSDT_900.csv | symbol | 73 | 1000PEPEUSDT | context |
| data/recorder/2026-04-08/1000PEPEUSDT_900.csv | regime | 73 | PENDING | context |
| data/recorder/2026-04-08/1000PEPEUSDT_900.csv | tf_sec | 73 | 900 | context |
| data/recorder/2026-04-08/BNBUSDT_180.csv | symbol | 365 | BNBUSDT | context |
| data/recorder/2026-04-08/BNBUSDT_180.csv | regime | 365 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-08/BNBUSDT_180.csv | tf_sec | 365 | 180 | context |
| data/recorder/2026-04-08/BNBUSDT_300.csv | symbol | 219 | BNBUSDT | context |
| data/recorder/2026-04-08/BNBUSDT_300.csv | regime | 219 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-08/BNBUSDT_300.csv | tf_sec | 219 | 300 | context |
| data/recorder/2026-04-08/BNBUSDT_900.csv | symbol | 73 | BNBUSDT | context |
| data/recorder/2026-04-08/BNBUSDT_900.csv | regime | 73 | PENDING | context |
| data/recorder/2026-04-08/BNBUSDT_900.csv | tf_sec | 73 | 900 | context |
| data/recorder/2026-04-08/BTCUSDT_180.csv | symbol | 365 | BTCUSDT | context |
| data/recorder/2026-04-08/BTCUSDT_180.csv | regime | 365 | HIGH_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-08/BTCUSDT_180.csv | tf_sec | 365 | 180 | context |
| data/recorder/2026-04-08/BTCUSDT_300.csv | symbol | 821 | BTCUSDT, 1, 2 | context |
| data/recorder/2026-04-08/BTCUSDT_300.csv | regime | 819 | PENDING, HIGH_VOLATILITY, TREND_UP, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-08/BTCUSDT_300.csv | tf_sec | 821 | 300, 9345.3699, 891.8995, 1547.5616, 5100.224 | context |
| data/recorder/2026-04-08/BTCUSDT_900.csv | symbol | 73 | BTCUSDT | context |
| data/recorder/2026-04-08/BTCUSDT_900.csv | regime | 73 | PENDING | context |
| data/recorder/2026-04-08/BTCUSDT_900.csv | tf_sec | 73 | 900 | context |
| data/recorder/2026-04-08/DOGEUSDT_180.csv | symbol | 365 | DOGEUSDT | context |
| data/recorder/2026-04-08/DOGEUSDT_180.csv | regime | 365 | HIGH_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-08/DOGEUSDT_180.csv | tf_sec | 365 | 180 | context |
| data/recorder/2026-04-08/DOGEUSDT_300.csv | symbol | 821 | DOGEUSDT | context |
| data/recorder/2026-04-08/DOGEUSDT_300.csv | regime | 821 | PENDING, HIGH_VOLATILITY, TREND_UP, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-08/DOGEUSDT_300.csv | tf_sec | 821 | 300 | context |
| data/recorder/2026-04-08/DOGEUSDT_900.csv | symbol | 73 | DOGEUSDT | context |
| data/recorder/2026-04-08/DOGEUSDT_900.csv | regime | 73 | PENDING | context |
| data/recorder/2026-04-08/DOGEUSDT_900.csv | tf_sec | 73 | 900 | context |
| data/recorder/2026-04-08/ETHUSDT_180.csv | symbol | 365 | ETHUSDT | context |
| data/recorder/2026-04-08/ETHUSDT_180.csv | regime | 365 | HIGH_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-08/ETHUSDT_180.csv | tf_sec | 365 | 180 | context |
| data/recorder/2026-04-08/ETHUSDT_300.csv | symbol | 821 | ETHUSDT, 1, 3 | context |
| data/recorder/2026-04-08/ETHUSDT_300.csv | regime | 819 | PENDING, HIGH_VOLATILITY, TREND_UP, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-08/ETHUSDT_300.csv | tf_sec | 821 | 300, 10715.62, 221521.759, 5366.038, 2410.312 | context |
| data/recorder/2026-04-08/ETHUSDT_900.csv | symbol | 73 | ETHUSDT | context |
| data/recorder/2026-04-08/ETHUSDT_900.csv | regime | 73 | PENDING | context |
| data/recorder/2026-04-08/ETHUSDT_900.csv | tf_sec | 73 | 900 | context |
| data/recorder/2026-04-08/SOLUSDT_180.csv | symbol | 365 | SOLUSDT | context |
| data/recorder/2026-04-08/SOLUSDT_180.csv | regime | 365 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-08/SOLUSDT_180.csv | tf_sec | 365 | 180 | context |
| data/recorder/2026-04-08/SOLUSDT_300.csv | symbol | 821 | SOLUSDT, 1, 4 | context |
| data/recorder/2026-04-08/SOLUSDT_300.csv | regime | 819 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, stale_features | context |
| data/recorder/2026-04-08/SOLUSDT_300.csv | tf_sec | 821 | 300, 12502.57, 4905.08, 1701.53, 842.11 | context |
| data/recorder/2026-04-08/SOLUSDT_900.csv | symbol | 73 | SOLUSDT | context |
| data/recorder/2026-04-08/SOLUSDT_900.csv | regime | 73 | PENDING | context |
| data/recorder/2026-04-08/SOLUSDT_900.csv | tf_sec | 73 | 900 | context |
| data/recorder/2026-04-08/XRPUSDT_180.csv | symbol | 365 | XRPUSDT | context |
| data/recorder/2026-04-08/XRPUSDT_180.csv | regime | 365 | HIGH_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-04-08/XRPUSDT_180.csv | tf_sec | 365 | 180 | context |
| data/recorder/2026-04-08/XRPUSDT_300.csv | symbol | 219 | XRPUSDT | context |
| data/recorder/2026-04-08/XRPUSDT_300.csv | regime | 219 | PENDING, HIGH_VOLATILITY, UNCERTAIN, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-04-08/XRPUSDT_300.csv | tf_sec | 219 | 300 | context |
| data/recorder/2026-04-08/XRPUSDT_900.csv | symbol | 73 | XRPUSDT | context |
| data/recorder/2026-04-08/XRPUSDT_900.csv | regime | 73 | PENDING | context |
| data/recorder/2026-04-08/XRPUSDT_900.csv | tf_sec | 73 | 900 | context |
| data/recorder/2026-04-09/1000PEPEUSDT_180.csv | symbol | 456 | 1000PEPEUSDT | context |
| data/recorder/2026-04-09/1000PEPEUSDT_180.csv | regime | 456 | TREND_DOWN, PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-09/1000PEPEUSDT_180.csv | tf_sec | 456 | 180 | context |
| data/recorder/2026-04-09/1000PEPEUSDT_300.csv | symbol | 274 | 1000PEPEUSDT | context |
| data/recorder/2026-04-09/1000PEPEUSDT_300.csv | regime | 274 | PENDING, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-09/1000PEPEUSDT_300.csv | tf_sec | 274 | 300 | context |
| data/recorder/2026-04-09/1000PEPEUSDT_900.csv | symbol | 91 | 1000PEPEUSDT | context |
| data/recorder/2026-04-09/1000PEPEUSDT_900.csv | regime | 91 | PENDING | context |
| data/recorder/2026-04-09/1000PEPEUSDT_900.csv | tf_sec | 91 | 900 | context |
| data/recorder/2026-04-09/BNBUSDT_180.csv | symbol | 456 | BNBUSDT | context |
| data/recorder/2026-04-09/BNBUSDT_180.csv | regime | 456 | TREND_DOWN, PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-09/BNBUSDT_180.csv | tf_sec | 456 | 180 | context |
| data/recorder/2026-04-09/BNBUSDT_300.csv | symbol | 274 | BNBUSDT | context |
| data/recorder/2026-04-09/BNBUSDT_300.csv | regime | 274 | PENDING, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-09/BNBUSDT_300.csv | tf_sec | 274 | 300 | context |
| data/recorder/2026-04-09/BNBUSDT_900.csv | symbol | 91 | BNBUSDT | context |
| data/recorder/2026-04-09/BNBUSDT_900.csv | regime | 91 | PENDING | context |
| data/recorder/2026-04-09/BNBUSDT_900.csv | tf_sec | 91 | 900 | context |
| data/recorder/2026-04-09/BTCUSDT_180.csv | symbol | 456 | BTCUSDT | context |
| data/recorder/2026-04-09/BTCUSDT_180.csv | regime | 456 | TREND_DOWN, PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-09/BTCUSDT_180.csv | tf_sec | 456 | 180 | context |
| data/recorder/2026-04-09/BTCUSDT_300.csv | symbol | 575 | BTCUSDT, 1, 3 | context |
| data/recorder/2026-04-09/BTCUSDT_300.csv | regime | 573 | PENDING, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN, stale_features | context |
| data/recorder/2026-04-09/BTCUSDT_300.csv | tf_sec | 575 | 300, 1734.5402, 2701.8751, 20264.6519, 2843.8405 | context |
| data/recorder/2026-04-09/BTCUSDT_900.csv | symbol | 91 | BTCUSDT | context |
| data/recorder/2026-04-09/BTCUSDT_900.csv | regime | 91 | PENDING | context |
| data/recorder/2026-04-09/BTCUSDT_900.csv | tf_sec | 91 | 900 | context |
| data/recorder/2026-04-09/DOGEUSDT_180.csv | symbol | 456 | DOGEUSDT | context |
| data/recorder/2026-04-09/DOGEUSDT_180.csv | regime | 456 | TREND_DOWN, PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-09/DOGEUSDT_180.csv | tf_sec | 456 | 180 | context |
| data/recorder/2026-04-09/DOGEUSDT_300.csv | symbol | 575 | DOGEUSDT | context |
| data/recorder/2026-04-09/DOGEUSDT_300.csv | regime | 575 | PENDING, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-09/DOGEUSDT_300.csv | tf_sec | 575 | 300 | context |
| data/recorder/2026-04-09/DOGEUSDT_900.csv | symbol | 91 | DOGEUSDT | context |
| data/recorder/2026-04-09/DOGEUSDT_900.csv | regime | 91 | PENDING | context |
| data/recorder/2026-04-09/DOGEUSDT_900.csv | tf_sec | 91 | 900 | context |
| data/recorder/2026-04-09/ETHUSDT_180.csv | symbol | 456 | ETHUSDT | context |
| data/recorder/2026-04-09/ETHUSDT_180.csv | regime | 456 | TREND_DOWN, PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-09/ETHUSDT_180.csv | tf_sec | 456 | 180 | context |
| data/recorder/2026-04-09/ETHUSDT_300.csv | symbol | 575 | ETHUSDT, 1, 4 | context |
| data/recorder/2026-04-09/ETHUSDT_300.csv | regime | 573 | PENDING, TREND_DOWN, LOW_VOLATILITY, stale_features, UNCERTAIN | context |
| data/recorder/2026-04-09/ETHUSDT_300.csv | tf_sec | 575 | 300, 159447.098, 121624.312, 131787.225, 228582.381 | context |
| data/recorder/2026-04-09/ETHUSDT_900.csv | symbol | 91 | ETHUSDT | context |
| data/recorder/2026-04-09/ETHUSDT_900.csv | regime | 91 | PENDING | context |
| data/recorder/2026-04-09/ETHUSDT_900.csv | tf_sec | 91 | 900 | context |
| data/recorder/2026-04-09/SOLUSDT_180.csv | symbol | 456 | SOLUSDT | context |
| data/recorder/2026-04-09/SOLUSDT_180.csv | regime | 456 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-09/SOLUSDT_180.csv | tf_sec | 456 | 180 | context |
| data/recorder/2026-04-09/SOLUSDT_300.csv | symbol | 575 | SOLUSDT, 1, 6 | context |
| data/recorder/2026-04-09/SOLUSDT_300.csv | regime | 573 | PENDING, LOW_VOLATILITY, stale_features, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-09/SOLUSDT_300.csv | tf_sec | 575 | 300, 5727.56, 41107.16, 22756.02, 14931.33 | context |
| data/recorder/2026-04-09/SOLUSDT_900.csv | symbol | 91 | SOLUSDT | context |
| data/recorder/2026-04-09/SOLUSDT_900.csv | regime | 91 | PENDING | context |
| data/recorder/2026-04-09/SOLUSDT_900.csv | tf_sec | 91 | 900 | context |
| data/recorder/2026-04-09/XRPUSDT_180.csv | symbol | 456 | XRPUSDT | context |
| data/recorder/2026-04-09/XRPUSDT_180.csv | regime | 456 | TREND_DOWN, PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-09/XRPUSDT_180.csv | tf_sec | 456 | 180 | context |
| data/recorder/2026-04-09/XRPUSDT_300.csv | symbol | 274 | XRPUSDT | context |
| data/recorder/2026-04-09/XRPUSDT_300.csv | regime | 274 | PENDING, TREND_DOWN, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-09/XRPUSDT_300.csv | tf_sec | 274 | 300 | context |
| data/recorder/2026-04-09/XRPUSDT_900.csv | symbol | 91 | XRPUSDT | context |
| data/recorder/2026-04-09/XRPUSDT_900.csv | regime | 91 | PENDING | context |
| data/recorder/2026-04-09/XRPUSDT_900.csv | tf_sec | 91 | 900 | context |
| data/recorder/2026-04-10/1000PEPEUSDT_180.csv | symbol | 397 | 1000PEPEUSDT | context |
| data/recorder/2026-04-10/1000PEPEUSDT_180.csv | regime | 397 | UNCERTAIN, PENDING, MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-04-10/1000PEPEUSDT_180.csv | tf_sec | 397 | 180 | context |
| data/recorder/2026-04-10/1000PEPEUSDT_300.csv | symbol | 238 | 1000PEPEUSDT | context |
| data/recorder/2026-04-10/1000PEPEUSDT_300.csv | regime | 238 | PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-04-10/1000PEPEUSDT_300.csv | tf_sec | 238 | 300 | context |
| data/recorder/2026-04-10/1000PEPEUSDT_900.csv | symbol | 80 | 1000PEPEUSDT | context |
| data/recorder/2026-04-10/1000PEPEUSDT_900.csv | regime | 80 | PENDING | context |
| data/recorder/2026-04-10/1000PEPEUSDT_900.csv | tf_sec | 80 | 900 | context |
| data/recorder/2026-04-10/BNBUSDT_180.csv | symbol | 397 | BNBUSDT | context |
| data/recorder/2026-04-10/BNBUSDT_180.csv | regime | 397 | UNCERTAIN, PENDING, MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-04-10/BNBUSDT_180.csv | tf_sec | 397 | 180 | context |
| data/recorder/2026-04-10/BNBUSDT_300.csv | symbol | 132 | BNBUSDT | context |
| data/recorder/2026-04-10/BNBUSDT_300.csv | regime | 133 | PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-04-10/BNBUSDT_300.csv | tf_sec | 132 | 300 | context |
| data/recorder/2026-04-10/BNBUSDT_900.csv | symbol | 267 | BNBUSDT | context |
| data/recorder/2026-04-10/BNBUSDT_900.csv | regime | 268 | PENDING, True | context |
| data/recorder/2026-04-10/BNBUSDT_900.csv | tf_sec | 268 | 900, BNBUSDT | context |
| data/recorder/2026-04-10/BTCUSDT_180.csv | symbol | 397 | BTCUSDT | context |
| data/recorder/2026-04-10/BTCUSDT_180.csv | regime | 397 | UNCERTAIN, PENDING, MEAN_REVERSION, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-04-10/BTCUSDT_180.csv | tf_sec | 397 | 180 | context |
| data/recorder/2026-04-10/BTCUSDT_300.csv | symbol | 1140 | BTCUSDT, 1, 2 | context |
| data/recorder/2026-04-10/BTCUSDT_300.csv | regime | 1137 | PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-04-10/BTCUSDT_300.csv | tf_sec | 1140 | 300, 15050.3622, 12028.6781, 5548.9971, 3952.7382 | context |
| data/recorder/2026-04-10/BTCUSDT_900.csv | symbol | 80 | BTCUSDT | context |
| data/recorder/2026-04-10/BTCUSDT_900.csv | regime | 80 | PENDING | context |
| data/recorder/2026-04-10/BTCUSDT_900.csv | tf_sec | 80 | 900 | context |
| data/recorder/2026-04-10/DOGEUSDT_180.csv | symbol | 397 | DOGEUSDT | context |
| data/recorder/2026-04-10/DOGEUSDT_180.csv | regime | 397 | UNCERTAIN, PENDING, MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-04-10/DOGEUSDT_180.csv | tf_sec | 397 | 180 | context |
| data/recorder/2026-04-10/DOGEUSDT_300.csv | symbol | 840 | DOGEUSDT | context |
| data/recorder/2026-04-10/DOGEUSDT_300.csv | regime | 840 | PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-04-10/DOGEUSDT_300.csv | tf_sec | 840 | 300 | context |
| data/recorder/2026-04-10/DOGEUSDT_900.csv | symbol | 80 | DOGEUSDT | context |
| data/recorder/2026-04-10/DOGEUSDT_900.csv | regime | 80 | PENDING | context |
| data/recorder/2026-04-10/DOGEUSDT_900.csv | tf_sec | 80 | 900 | context |
| data/recorder/2026-04-10/ETHUSDT_180.csv | symbol | 397 | ETHUSDT | context |
| data/recorder/2026-04-10/ETHUSDT_180.csv | regime | 397 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-10/ETHUSDT_180.csv | tf_sec | 397 | 180 | context |
| data/recorder/2026-04-10/ETHUSDT_300.csv | symbol | 840 | ETHUSDT, 1, 3 | context |
| data/recorder/2026-04-10/ETHUSDT_300.csv | regime | 837 | PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-10/ETHUSDT_300.csv | tf_sec | 840 | 300, 359748.444, 296099.179, 146071.581, 234805.175 | context |
| data/recorder/2026-04-10/ETHUSDT_900.csv | symbol | 80 | ETHUSDT | context |
| data/recorder/2026-04-10/ETHUSDT_900.csv | regime | 80 | PENDING | context |
| data/recorder/2026-04-10/ETHUSDT_900.csv | tf_sec | 80 | 900 | context |
| data/recorder/2026-04-10/SOLUSDT_180.csv | symbol | 397 | SOLUSDT | context |
| data/recorder/2026-04-10/SOLUSDT_180.csv | regime | 397 | UNCERTAIN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-10/SOLUSDT_180.csv | tf_sec | 397 | 180 | context |
| data/recorder/2026-04-10/SOLUSDT_300.csv | symbol | 840 | SOLUSDT, 1, 4 | context |
| data/recorder/2026-04-10/SOLUSDT_300.csv | regime | 837 | PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-10/SOLUSDT_300.csv | tf_sec | 840 | 300, 95800.32, 107632.25, 13664.83, 3963.07 | context |
| data/recorder/2026-04-10/SOLUSDT_900.csv | symbol | 80 | SOLUSDT | context |
| data/recorder/2026-04-10/SOLUSDT_900.csv | regime | 80 | PENDING | context |
| data/recorder/2026-04-10/SOLUSDT_900.csv | tf_sec | 80 | 900 | context |
| data/recorder/2026-04-10/XRPUSDT_180.csv | symbol | 397 | XRPUSDT | context |
| data/recorder/2026-04-10/XRPUSDT_180.csv | regime | 397 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-10/XRPUSDT_180.csv | tf_sec | 397 | 180 | context |
| data/recorder/2026-04-10/XRPUSDT_300.csv | symbol | 132 | XRPUSDT | context |
| data/recorder/2026-04-10/XRPUSDT_300.csv | regime | 133 | PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-10/XRPUSDT_300.csv | tf_sec | 132 | 300 | context |
| data/recorder/2026-04-10/XRPUSDT_900.csv | symbol | 266 | XRPUSDT | context |
| data/recorder/2026-04-10/XRPUSDT_900.csv | regime | 267 | PENDING, True | context |
| data/recorder/2026-04-10/XRPUSDT_900.csv | tf_sec | 267 | 900, XRPUSDT | context |
| data/recorder/2026-04-11/1000PEPEUSDT_180.csv | symbol | 386 | 1000PEPEUSDT | context |
| data/recorder/2026-04-11/1000PEPEUSDT_180.csv | regime | 386 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-11/1000PEPEUSDT_180.csv | tf_sec | 386 | 180 | context |
| data/recorder/2026-04-11/1000PEPEUSDT_300.csv | symbol | 235 | 1000PEPEUSDT | context |
| data/recorder/2026-04-11/1000PEPEUSDT_300.csv | regime | 235 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-11/1000PEPEUSDT_300.csv | tf_sec | 235 | 300 | context |
| data/recorder/2026-04-11/1000PEPEUSDT_900.csv | symbol | 81 | 1000PEPEUSDT | context |
| data/recorder/2026-04-11/1000PEPEUSDT_900.csv | regime | 81 | PENDING | context |
| data/recorder/2026-04-11/1000PEPEUSDT_900.csv | tf_sec | 81 | 900 | context |
| data/recorder/2026-04-11/BNBUSDT_180.csv | symbol | 386 | BNBUSDT | context |
| data/recorder/2026-04-11/BNBUSDT_180.csv | regime | 386 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-04-11/BNBUSDT_180.csv | tf_sec | 386 | 180 | context |
| data/recorder/2026-04-11/BNBUSDT_300.csv | symbol | 235 | BNBUSDT | context |
| data/recorder/2026-04-11/BNBUSDT_300.csv | regime | 235 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY | context |
| data/recorder/2026-04-11/BNBUSDT_300.csv | tf_sec | 235 | 300 | context |
| data/recorder/2026-04-11/BNBUSDT_900.csv | symbol | 81 | BNBUSDT | context |
| data/recorder/2026-04-11/BNBUSDT_900.csv | regime | 81 | PENDING | context |
| data/recorder/2026-04-11/BNBUSDT_900.csv | tf_sec | 81 | 900 | context |
| data/recorder/2026-04-11/BTCUSDT_180.csv | symbol | 386 | BTCUSDT | context |
| data/recorder/2026-04-11/BTCUSDT_180.csv | regime | 386 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-11/BTCUSDT_180.csv | tf_sec | 386 | 180 | context |
| data/recorder/2026-04-11/BTCUSDT_300.csv | symbol | 235 | BTCUSDT | context |
| data/recorder/2026-04-11/BTCUSDT_300.csv | regime | 235 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-11/BTCUSDT_300.csv | tf_sec | 235 | 300 | context |
| data/recorder/2026-04-11/BTCUSDT_900.csv | symbol | 81 | BTCUSDT | context |
| data/recorder/2026-04-11/BTCUSDT_900.csv | regime | 81 | PENDING | context |
| data/recorder/2026-04-11/BTCUSDT_900.csv | tf_sec | 81 | 900 | context |
| data/recorder/2026-04-11/DOGEUSDT_180.csv | symbol | 386 | DOGEUSDT | context |
| data/recorder/2026-04-11/DOGEUSDT_180.csv | regime | 386 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-04-11/DOGEUSDT_180.csv | tf_sec | 386 | 180 | context |
| data/recorder/2026-04-11/DOGEUSDT_300.csv | symbol | 235 | DOGEUSDT | context |
| data/recorder/2026-04-11/DOGEUSDT_300.csv | regime | 235 | PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-04-11/DOGEUSDT_300.csv | tf_sec | 235 | 300 | context |
| data/recorder/2026-04-11/DOGEUSDT_900.csv | symbol | 81 | DOGEUSDT | context |
| data/recorder/2026-04-11/DOGEUSDT_900.csv | regime | 81 | PENDING | context |
| data/recorder/2026-04-11/DOGEUSDT_900.csv | tf_sec | 81 | 900 | context |
| data/recorder/2026-04-11/ETHUSDT_180.csv | symbol | 386 | ETHUSDT | context |
| data/recorder/2026-04-11/ETHUSDT_180.csv | regime | 386 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-11/ETHUSDT_180.csv | tf_sec | 386 | 180 | context |
| data/recorder/2026-04-11/ETHUSDT_300.csv | symbol | 235 | ETHUSDT | context |
| data/recorder/2026-04-11/ETHUSDT_300.csv | regime | 235 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-11/ETHUSDT_300.csv | tf_sec | 235 | 300 | context |
| data/recorder/2026-04-11/ETHUSDT_900.csv | symbol | 81 | ETHUSDT | context |
| data/recorder/2026-04-11/ETHUSDT_900.csv | regime | 81 | PENDING | context |
| data/recorder/2026-04-11/ETHUSDT_900.csv | tf_sec | 81 | 900 | context |
| data/recorder/2026-04-11/SOLUSDT_180.csv | symbol | 386 | SOLUSDT | context |
| data/recorder/2026-04-11/SOLUSDT_180.csv | regime | 386 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-04-11/SOLUSDT_180.csv | tf_sec | 386 | 180 | context |
| data/recorder/2026-04-11/SOLUSDT_300.csv | symbol | 235 | SOLUSDT, 12, 29, 50, 58 | context |
| data/recorder/2026-04-11/SOLUSDT_300.csv | regime | 232 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-04-11/SOLUSDT_300.csv | tf_sec | 235 | 300, 0 | context |
| data/recorder/2026-04-11/SOLUSDT_900.csv | symbol | 81 | SOLUSDT | context |
| data/recorder/2026-04-11/SOLUSDT_900.csv | regime | 81 | PENDING | context |
| data/recorder/2026-04-11/SOLUSDT_900.csv | tf_sec | 81 | 900 | context |
| data/recorder/2026-04-11/XRPUSDT_180.csv | symbol | 386 | XRPUSDT | context |
| data/recorder/2026-04-11/XRPUSDT_180.csv | regime | 386 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-04-11/XRPUSDT_180.csv | tf_sec | 386 | 180 | context |
| data/recorder/2026-04-11/XRPUSDT_300.csv | symbol | 235 | XRPUSDT | context |
| data/recorder/2026-04-11/XRPUSDT_300.csv | regime | 235 | PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-04-11/XRPUSDT_300.csv | tf_sec | 235 | 300 | context |
| data/recorder/2026-04-11/XRPUSDT_900.csv | symbol | 39 | XRPUSDT | context |
| data/recorder/2026-04-11/XRPUSDT_900.csv | regime | 40 | PENDING, True | context |
| data/recorder/2026-04-11/XRPUSDT_900.csv | tf_sec | 40 | 900, XRPUSDT | context |
| data/recorder/2026-04-12/1000PEPEUSDT_180.csv | symbol | 464 | 1000PEPEUSDT | context |
| data/recorder/2026-04-12/1000PEPEUSDT_180.csv | regime | 464 | UNCERTAIN, PENDING, TREND_UP, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-12/1000PEPEUSDT_180.csv | tf_sec | 464 | 180 | context |
| data/recorder/2026-04-12/1000PEPEUSDT_300.csv | symbol | 278 | 1000PEPEUSDT | context |
| data/recorder/2026-04-12/1000PEPEUSDT_300.csv | regime | 278 | PENDING, UNCERTAIN, TREND_UP, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-12/1000PEPEUSDT_300.csv | tf_sec | 278 | 300 | context |
| data/recorder/2026-04-12/1000PEPEUSDT_900.csv | symbol | 93 | 1000PEPEUSDT | context |
| data/recorder/2026-04-12/1000PEPEUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-04-12/1000PEPEUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-04-12/BNBUSDT_180.csv | symbol | 464 | BNBUSDT | context |
| data/recorder/2026-04-12/BNBUSDT_180.csv | regime | 464 | MEAN_REVERSION, PENDING, UNCERTAIN, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-12/BNBUSDT_180.csv | tf_sec | 464 | 180 | context |
| data/recorder/2026-04-12/BNBUSDT_300.csv | symbol | 278 | BNBUSDT | context |
| data/recorder/2026-04-12/BNBUSDT_300.csv | regime | 278 | PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-12/BNBUSDT_300.csv | tf_sec | 278 | 300 | context |
| data/recorder/2026-04-12/BNBUSDT_900.csv | symbol | 179 | BNBUSDT | context |
| data/recorder/2026-04-12/BNBUSDT_900.csv | regime | 180 | PENDING, True | context |
| data/recorder/2026-04-12/BNBUSDT_900.csv | tf_sec | 180 | 900, BNBUSDT | context |
| data/recorder/2026-04-12/BTCUSDT_180.csv | symbol | 464 | BTCUSDT | context |
| data/recorder/2026-04-12/BTCUSDT_180.csv | regime | 464 | MEAN_REVERSION, PENDING, HIGH_VOLATILITY, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-12/BTCUSDT_180.csv | tf_sec | 464 | 180 | context |
| data/recorder/2026-04-12/BTCUSDT_300.csv | symbol | 579 | BTCUSDT, 1 | context |
| data/recorder/2026-04-12/BTCUSDT_300.csv | regime | 578 | PENDING, MEAN_REVERSION, HIGH_VOLATILITY, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-12/BTCUSDT_300.csv | tf_sec | 579 | 300, 7999.344, 4514.0958, 3053.3805, 71.2961 | context |
| data/recorder/2026-04-12/BTCUSDT_900.csv | symbol | 93 | BTCUSDT | context |
| data/recorder/2026-04-12/BTCUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-04-12/BTCUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-04-12/DOGEUSDT_180.csv | symbol | 464 | DOGEUSDT | context |
| data/recorder/2026-04-12/DOGEUSDT_180.csv | regime | 464 | UNCERTAIN, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-12/DOGEUSDT_180.csv | tf_sec | 464 | 180 | context |
| data/recorder/2026-04-12/DOGEUSDT_300.csv | symbol | 579 | DOGEUSDT | context |
| data/recorder/2026-04-12/DOGEUSDT_300.csv | regime | 579 | PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-12/DOGEUSDT_300.csv | tf_sec | 579 | 300 | context |
| data/recorder/2026-04-12/DOGEUSDT_900.csv | symbol | 93 | DOGEUSDT | context |
| data/recorder/2026-04-12/DOGEUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-04-12/DOGEUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-04-12/ETHUSDT_180.csv | symbol | 464 | ETHUSDT | context |
| data/recorder/2026-04-12/ETHUSDT_180.csv | regime | 464 | UNCERTAIN, PENDING, TREND_UP, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-12/ETHUSDT_180.csv | tf_sec | 464 | 180 | context |
| data/recorder/2026-04-12/ETHUSDT_300.csv | symbol | 579 | ETHUSDT, 1, 3 | context |
| data/recorder/2026-04-12/ETHUSDT_300.csv | regime | 577 | PENDING, UNCERTAIN, TREND_UP, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-12/ETHUSDT_300.csv | tf_sec | 579 | 300, 24096.742, 207398.121, 98186.238, 109543.664 | context |
| data/recorder/2026-04-12/ETHUSDT_900.csv | symbol | 93 | ETHUSDT | context |
| data/recorder/2026-04-12/ETHUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-04-12/ETHUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-04-12/SOLUSDT_180.csv | symbol | 464 | SOLUSDT | context |
| data/recorder/2026-04-12/SOLUSDT_180.csv | regime | 464 | TREND_UP, PENDING, UNCERTAIN, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-12/SOLUSDT_180.csv | tf_sec | 464 | 180 | context |
| data/recorder/2026-04-12/SOLUSDT_300.csv | symbol | 579 | SOLUSDT, 1, 3 | context |
| data/recorder/2026-04-12/SOLUSDT_300.csv | regime | 577 | PENDING, TREND_UP, UNCERTAIN, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-12/SOLUSDT_300.csv | tf_sec | 579 | 300, 6915.79, 45883.9, 8911.35, 5854.87 | context |
| data/recorder/2026-04-12/SOLUSDT_900.csv | symbol | 93 | SOLUSDT | context |
| data/recorder/2026-04-12/SOLUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-04-12/SOLUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-04-12/XRPUSDT_180.csv | symbol | 464 | XRPUSDT | context |
| data/recorder/2026-04-12/XRPUSDT_180.csv | regime | 464 | UNCERTAIN, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-12/XRPUSDT_180.csv | tf_sec | 464 | 180 | context |
| data/recorder/2026-04-12/XRPUSDT_300.csv | symbol | 278 | XRPUSDT | context |
| data/recorder/2026-04-12/XRPUSDT_300.csv | regime | 278 | PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-12/XRPUSDT_300.csv | tf_sec | 278 | 300 | context |
| data/recorder/2026-04-12/XRPUSDT_900.csv | symbol | 177 | XRPUSDT | context |
| data/recorder/2026-04-12/XRPUSDT_900.csv | regime | 178 | PENDING, True | context |
| data/recorder/2026-04-12/XRPUSDT_900.csv | tf_sec | 178 | 900, XRPUSDT | context |
| data/recorder/2026-04-13/1000PEPEUSDT_180.csv | symbol | 480 | 1000PEPEUSDT | context |
| data/recorder/2026-04-13/1000PEPEUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, MEAN_REVERSION, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-13/1000PEPEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-13/1000PEPEUSDT_300.csv | symbol | 288 | 1000PEPEUSDT | context |
| data/recorder/2026-04-13/1000PEPEUSDT_300.csv | regime | 288 | PENDING, TREND_DOWN, MEAN_REVERSION, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-13/1000PEPEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-13/1000PEPEUSDT_900.csv | symbol | 96 | 1000PEPEUSDT | context |
| data/recorder/2026-04-13/1000PEPEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-13/1000PEPEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-13/BNBUSDT_180.csv | symbol | 480 | BNBUSDT | context |
| data/recorder/2026-04-13/BNBUSDT_180.csv | regime | 480 | MEAN_REVERSION, PENDING, TREND_UP, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-13/BNBUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-13/BNBUSDT_300.csv | symbol | 288 | BNBUSDT | context |
| data/recorder/2026-04-13/BNBUSDT_300.csv | regime | 288 | PENDING, MEAN_REVERSION, TREND_UP, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-13/BNBUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-13/BNBUSDT_900.csv | symbol | 3 | BNBUSDT | context |
| data/recorder/2026-04-13/BNBUSDT_900.csv | regime | 4 | PENDING, True | context |
| data/recorder/2026-04-13/BNBUSDT_900.csv | tf_sec | 4 | 900, BNBUSDT | context |
| data/recorder/2026-04-13/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-04-13/BTCUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-13/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-13/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-04-13/BTCUSDT_300.csv | regime | 288 | PENDING, TREND_DOWN, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-13/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-13/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-04-13/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-13/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-13/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-04-13/DOGEUSDT_180.csv | regime | 480 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-13/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-13/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-04-13/DOGEUSDT_300.csv | regime | 288 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-13/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-13/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-04-13/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-13/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-13/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-04-13/ETHUSDT_180.csv | regime | 480 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-13/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-13/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-04-13/ETHUSDT_300.csv | regime | 288 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-13/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-13/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-04-13/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-13/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-13/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-04-13/SOLUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-04-13/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-13/SOLUSDT_300.csv | symbol | 288 | SOLUSDT, 70 | context |
| data/recorder/2026-04-13/SOLUSDT_300.csv | regime | 288 | PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-04-13/SOLUSDT_300.csv | tf_sec | 288 | 300, 0 | context |
| data/recorder/2026-04-13/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-04-13/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-13/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-13/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-04-13/XRPUSDT_180.csv | regime | 480 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-13/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-13/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-04-13/XRPUSDT_300.csv | regime | 288 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-13/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-13/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-04-13/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-13/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-14/1000PEPEUSDT_180.csv | symbol | 265 | 1000PEPEUSDT | context |
| data/recorder/2026-04-14/1000PEPEUSDT_180.csv | regime | 265 | HIGH_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-14/1000PEPEUSDT_180.csv | tf_sec | 265 | 180 | context |
| data/recorder/2026-04-14/1000PEPEUSDT_300.csv | symbol | 159 | 1000PEPEUSDT | context |
| data/recorder/2026-04-14/1000PEPEUSDT_300.csv | regime | 159 | PENDING, HIGH_VOLATILITY, TREND_UP, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-14/1000PEPEUSDT_300.csv | tf_sec | 159 | 300 | context |
| data/recorder/2026-04-14/1000PEPEUSDT_900.csv | symbol | 53 | 1000PEPEUSDT | context |
| data/recorder/2026-04-14/1000PEPEUSDT_900.csv | regime | 53 | PENDING | context |
| data/recorder/2026-04-14/1000PEPEUSDT_900.csv | tf_sec | 53 | 900 | context |
| data/recorder/2026-04-14/BNBUSDT_180.csv | symbol | 264 | BNBUSDT | context |
| data/recorder/2026-04-14/BNBUSDT_180.csv | regime | 264 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-14/BNBUSDT_180.csv | tf_sec | 264 | 180 | context |
| data/recorder/2026-04-14/BNBUSDT_300.csv | symbol | 385 | BNBUSDT | context |
| data/recorder/2026-04-14/BNBUSDT_300.csv | regime | 386 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, None | context |
| data/recorder/2026-04-14/BNBUSDT_300.csv | tf_sec | 385 | 300 | context |
| data/recorder/2026-04-14/BNBUSDT_900.csv | symbol | 141 | BNBUSDT | context |
| data/recorder/2026-04-14/BNBUSDT_900.csv | regime | 142 | PENDING, True | context |
| data/recorder/2026-04-14/BNBUSDT_900.csv | tf_sec | 142 | 900, BNBUSDT | context |
| data/recorder/2026-04-14/BTCUSDT_180.csv | symbol | 265 | BTCUSDT | context |
| data/recorder/2026-04-14/BTCUSDT_180.csv | regime | 265 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-14/BTCUSDT_180.csv | tf_sec | 265 | 180 | context |
| data/recorder/2026-04-14/BTCUSDT_300.csv | symbol | 460 | BTCUSDT, 1, 2 | context |
| data/recorder/2026-04-14/BTCUSDT_300.csv | regime | 458 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, stale_features | context |
| data/recorder/2026-04-14/BTCUSDT_300.csv | tf_sec | 460 | 300, 4049.2807, 10595.5025, 6395.7443, 3996.3082 | context |
| data/recorder/2026-04-14/BTCUSDT_900.csv | symbol | 53 | BTCUSDT | context |
| data/recorder/2026-04-14/BTCUSDT_900.csv | regime | 53 | PENDING | context |
| data/recorder/2026-04-14/BTCUSDT_900.csv | tf_sec | 53 | 900 | context |
| data/recorder/2026-04-14/DOGEUSDT_180.csv | symbol | 265 | DOGEUSDT | context |
| data/recorder/2026-04-14/DOGEUSDT_180.csv | regime | 265 | TREND_UP, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-04-14/DOGEUSDT_180.csv | tf_sec | 265 | 180 | context |
| data/recorder/2026-04-14/DOGEUSDT_300.csv | symbol | 387 | DOGEUSDT, structural:DOGEUSDT:1776188999999 | context |
| data/recorder/2026-04-14/DOGEUSDT_300.csv | regime | 387 | PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION, None | context |
| data/recorder/2026-04-14/DOGEUSDT_300.csv | tf_sec | 387 | 300, True | context |
| data/recorder/2026-04-14/DOGEUSDT_900.csv | symbol | 53 | DOGEUSDT | context |
| data/recorder/2026-04-14/DOGEUSDT_900.csv | regime | 53 | PENDING | context |
| data/recorder/2026-04-14/DOGEUSDT_900.csv | tf_sec | 53 | 900 | context |
| data/recorder/2026-04-14/ETHUSDT_180.csv | symbol | 265 | ETHUSDT | context |
| data/recorder/2026-04-14/ETHUSDT_180.csv | regime | 265 | HIGH_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-14/ETHUSDT_180.csv | tf_sec | 265 | 180 | context |
| data/recorder/2026-04-14/ETHUSDT_300.csv | symbol | 460 | ETHUSDT, 1, 4 | context |
| data/recorder/2026-04-14/ETHUSDT_300.csv | regime | 458 | PENDING, HIGH_VOLATILITY, TREND_UP, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-14/ETHUSDT_300.csv | tf_sec | 460 | 300, 360429.772, 41383.039, 390102.3, 84540.94 | context |
| data/recorder/2026-04-14/ETHUSDT_900.csv | symbol | 53 | ETHUSDT | context |
| data/recorder/2026-04-14/ETHUSDT_900.csv | regime | 53 | PENDING | context |
| data/recorder/2026-04-14/ETHUSDT_900.csv | tf_sec | 53 | 900 | context |
| data/recorder/2026-04-14/SOLUSDT_180.csv | symbol | 265 | SOLUSDT | context |
| data/recorder/2026-04-14/SOLUSDT_180.csv | regime | 265 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-14/SOLUSDT_180.csv | tf_sec | 265 | 180 | context |
| data/recorder/2026-04-14/SOLUSDT_300.csv | symbol | 460 | SOLUSDT, 1, 5 | context |
| data/recorder/2026-04-14/SOLUSDT_300.csv | regime | 458 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, stale_features | context |
| data/recorder/2026-04-14/SOLUSDT_300.csv | tf_sec | 460 | 300, 12366.75, 22222.91, 67591.06, 37320.06 | context |
| data/recorder/2026-04-14/SOLUSDT_900.csv | symbol | 53 | SOLUSDT | context |
| data/recorder/2026-04-14/SOLUSDT_900.csv | regime | 53 | PENDING | context |
| data/recorder/2026-04-14/SOLUSDT_900.csv | tf_sec | 53 | 900 | context |
| data/recorder/2026-04-14/XRPUSDT_180.csv | symbol | 265 | XRPUSDT | context |
| data/recorder/2026-04-14/XRPUSDT_180.csv | regime | 265 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-14/XRPUSDT_180.csv | tf_sec | 265 | 180 | context |
| data/recorder/2026-04-14/XRPUSDT_300.csv | symbol | 387 | XRPUSDT, structural:XRPUSDT:1776188999999 | context |
| data/recorder/2026-04-14/XRPUSDT_300.csv | regime | 387 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, None | context |
| data/recorder/2026-04-14/XRPUSDT_300.csv | tf_sec | 387 | 300, True | context |
| data/recorder/2026-04-14/XRPUSDT_900.csv | symbol | 132 | XRPUSDT | context |
| data/recorder/2026-04-14/XRPUSDT_900.csv | regime | 133 | PENDING, True | context |
| data/recorder/2026-04-14/XRPUSDT_900.csv | tf_sec | 133 | 900, XRPUSDT | context |
| data/recorder/2026-04-15/1000PEPEUSDT_180.csv | symbol | 463 | 1000PEPEUSDT | context |
| data/recorder/2026-04-15/1000PEPEUSDT_180.csv | regime | 463 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-15/1000PEPEUSDT_180.csv | tf_sec | 463 | 180 | context |
| data/recorder/2026-04-15/1000PEPEUSDT_300.csv | symbol | 278 | 1000PEPEUSDT | context |
| data/recorder/2026-04-15/1000PEPEUSDT_300.csv | regime | 278 | PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-15/1000PEPEUSDT_300.csv | tf_sec | 278 | 300 | context |
| data/recorder/2026-04-15/1000PEPEUSDT_900.csv | symbol | 93 | 1000PEPEUSDT | context |
| data/recorder/2026-04-15/1000PEPEUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-04-15/1000PEPEUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-04-15/BNBUSDT_180.csv | symbol | 463 | BNBUSDT | context |
| data/recorder/2026-04-15/BNBUSDT_180.csv | regime | 463 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-15/BNBUSDT_180.csv | tf_sec | 463 | 180 | context |
| data/recorder/2026-04-15/BNBUSDT_300.csv | symbol | 579 | BNBUSDT, 1, 2 | context |
| data/recorder/2026-04-15/BNBUSDT_300.csv | regime | 577 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN, stale_features | context |
| data/recorder/2026-04-15/BNBUSDT_300.csv | tf_sec | 579 | 300, 268091.58, 669442.86, 879544.27, 19322.27 | context |
| data/recorder/2026-04-15/BNBUSDT_900.csv | symbol | 2 | BNBUSDT | context |
| data/recorder/2026-04-15/BNBUSDT_900.csv | regime | 3 | PENDING, True | context |
| data/recorder/2026-04-15/BNBUSDT_900.csv | tf_sec | 3 | 900, BNBUSDT | context |
| data/recorder/2026-04-15/BTCUSDT_180.csv | symbol | 463 | BTCUSDT | context |
| data/recorder/2026-04-15/BTCUSDT_180.csv | regime | 463 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-04-15/BTCUSDT_180.csv | tf_sec | 463 | 180 | context |
| data/recorder/2026-04-15/BTCUSDT_300.csv | symbol | 579 | BTCUSDT, 1, 3 | context |
| data/recorder/2026-04-15/BTCUSDT_300.csv | regime | 577 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, stale_features | context |
| data/recorder/2026-04-15/BTCUSDT_300.csv | tf_sec | 579 | 300, 2712.4608, 221.4161, 604.7524, 14636.962 | context |
| data/recorder/2026-04-15/BTCUSDT_900.csv | symbol | 93 | BTCUSDT | context |
| data/recorder/2026-04-15/BTCUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-04-15/BTCUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-04-15/DOGEUSDT_180.csv | symbol | 463 | DOGEUSDT | context |
| data/recorder/2026-04-15/DOGEUSDT_180.csv | regime | 463 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-15/DOGEUSDT_180.csv | tf_sec | 463 | 180 | context |
| data/recorder/2026-04-15/DOGEUSDT_300.csv | symbol | 579 | DOGEUSDT, 1, 4 | context |
| data/recorder/2026-04-15/DOGEUSDT_300.csv | regime | 577 | PENDING, LOW_VOLATILITY, stale_features, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-15/DOGEUSDT_300.csv | tf_sec | 579 | 300, 2512951802.0, 3960119841.0, 4220376051.0, 589868300.0 | context |
| data/recorder/2026-04-15/DOGEUSDT_900.csv | symbol | 93 | DOGEUSDT | context |
| data/recorder/2026-04-15/DOGEUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-04-15/DOGEUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-04-15/ETHUSDT_180.csv | symbol | 463 | ETHUSDT | context |
| data/recorder/2026-04-15/ETHUSDT_180.csv | regime | 463 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-15/ETHUSDT_180.csv | tf_sec | 463 | 180 | context |
| data/recorder/2026-04-15/ETHUSDT_300.csv | symbol | 579 | ETHUSDT, 1, 5 | context |
| data/recorder/2026-04-15/ETHUSDT_300.csv | regime | 577 | PENDING, LOW_VOLATILITY, stale_features, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-15/ETHUSDT_300.csv | tf_sec | 579 | 300, 107517.712, 94943.943, 146416.737, 223450.14 | context |
| data/recorder/2026-04-15/ETHUSDT_900.csv | symbol | 93 | ETHUSDT | context |
| data/recorder/2026-04-15/ETHUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-04-15/ETHUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-04-15/SOLUSDT_180.csv | symbol | 463 | SOLUSDT | context |
| data/recorder/2026-04-15/SOLUSDT_180.csv | regime | 463 | LOW_VOLATILITY, PENDING, TREND_UP, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-15/SOLUSDT_180.csv | tf_sec | 463 | 180 | context |
| data/recorder/2026-04-15/SOLUSDT_300.csv | symbol | 579 | SOLUSDT, 1, 6 | context |
| data/recorder/2026-04-15/SOLUSDT_300.csv | regime | 577 | PENDING, LOW_VOLATILITY, stale_features, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-15/SOLUSDT_300.csv | tf_sec | 579 | 300, 10867.57, 11731.1, 38614.87, 14543.62 | context |
| data/recorder/2026-04-15/SOLUSDT_900.csv | symbol | 93 | SOLUSDT | context |
| data/recorder/2026-04-15/SOLUSDT_900.csv | regime | 93 | PENDING | context |
| data/recorder/2026-04-15/SOLUSDT_900.csv | tf_sec | 93 | 900 | context |
| data/recorder/2026-04-15/XRPUSDT_180.csv | symbol | 463 | XRPUSDT | context |
| data/recorder/2026-04-15/XRPUSDT_180.csv | regime | 463 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-15/XRPUSDT_180.csv | tf_sec | 463 | 180 | context |
| data/recorder/2026-04-15/XRPUSDT_300.csv | symbol | 579 | XRPUSDT, 1, 7 | context |
| data/recorder/2026-04-15/XRPUSDT_300.csv | regime | 577 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-15/XRPUSDT_300.csv | tf_sec | 579 | 300, 222968069.9, 234772913.9, 123019904.2, 135309815.1 | context |
| data/recorder/2026-04-15/XRPUSDT_900.csv | symbol | 11 | XRPUSDT | context |
| data/recorder/2026-04-15/XRPUSDT_900.csv | regime | 12 | PENDING, True | context |
| data/recorder/2026-04-15/XRPUSDT_900.csv | tf_sec | 12 | 900, XRPUSDT | context |
| data/recorder/2026-04-16/1000PEPEUSDT_180.csv | symbol | 376 | 1000PEPEUSDT | context |
| data/recorder/2026-04-16/1000PEPEUSDT_180.csv | regime | 376 | UNCERTAIN, PENDING, TREND_UP, HIGH_VOLATILITY, LOW_VOLATILITY | context |
| data/recorder/2026-04-16/1000PEPEUSDT_180.csv | tf_sec | 376 | 180 | context |
| data/recorder/2026-04-16/1000PEPEUSDT_300.csv | symbol | 225 | 1000PEPEUSDT | context |
| data/recorder/2026-04-16/1000PEPEUSDT_300.csv | regime | 225 | PENDING, UNCERTAIN, TREND_UP, HIGH_VOLATILITY, LOW_VOLATILITY | context |
| data/recorder/2026-04-16/1000PEPEUSDT_300.csv | tf_sec | 225 | 300 | context |
| data/recorder/2026-04-16/1000PEPEUSDT_900.csv | symbol | 74 | 1000PEPEUSDT | context |
| data/recorder/2026-04-16/1000PEPEUSDT_900.csv | regime | 74 | PENDING | context |
| data/recorder/2026-04-16/1000PEPEUSDT_900.csv | tf_sec | 74 | 900 | context |
| data/recorder/2026-04-16/BNBUSDT_180.csv | symbol | 376 | BNBUSDT | context |
| data/recorder/2026-04-16/BNBUSDT_180.csv | regime | 376 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-04-16/BNBUSDT_180.csv | tf_sec | 376 | 180 | context |
| data/recorder/2026-04-16/BNBUSDT_300.csv | symbol | 1068 | BNBUSDT, 1, 26, 33, 3 | context |
| data/recorder/2026-04-16/BNBUSDT_300.csv | regime | 1064 | PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-04-16/BNBUSDT_300.csv | tf_sec | 1068 | 300, 106289.82, 114.75, 121.0, 633669.39 | context |
| data/recorder/2026-04-16/BNBUSDT_900.csv | symbol | 74 | BNBUSDT | context |
| data/recorder/2026-04-16/BNBUSDT_900.csv | regime | 74 | PENDING | context |
| data/recorder/2026-04-16/BNBUSDT_900.csv | tf_sec | 74 | 900 | context |
| data/recorder/2026-04-16/BTCUSDT_180.csv | symbol | 376 | BTCUSDT | context |
| data/recorder/2026-04-16/BTCUSDT_180.csv | regime | 376 | UNCERTAIN, PENDING, MEAN_REVERSION, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-04-16/BTCUSDT_180.csv | tf_sec | 376 | 180 | context |
| data/recorder/2026-04-16/BTCUSDT_300.csv | symbol | 1068 | BTCUSDT, 1, 3, 4, 44 | context |
| data/recorder/2026-04-16/BTCUSDT_300.csv | regime | 1062 | PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP, stale_features | context |
| data/recorder/2026-04-16/BTCUSDT_300.csv | tf_sec | 1068 | 300, 3586.7763, 2062.4018, 6689.325, 1971.4193 | context |
| data/recorder/2026-04-16/BTCUSDT_900.csv | symbol | 74 | BTCUSDT | context |
| data/recorder/2026-04-16/BTCUSDT_900.csv | regime | 74 | PENDING | context |
| data/recorder/2026-04-16/BTCUSDT_900.csv | tf_sec | 74 | 900 | context |
| data/recorder/2026-04-16/DOGEUSDT_180.csv | symbol | 376 | DOGEUSDT | context |
| data/recorder/2026-04-16/DOGEUSDT_180.csv | regime | 376 | UNCERTAIN, PENDING, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-16/DOGEUSDT_180.csv | tf_sec | 376 | 180 | context |
| data/recorder/2026-04-16/DOGEUSDT_300.csv | symbol | 1068 | DOGEUSDT, 1, 4, 6, 23 | context |
| data/recorder/2026-04-16/DOGEUSDT_300.csv | regime | 1061 | PENDING, UNCERTAIN, TREND_UP, stale_features, LOW_VOLATILITY | context |
| data/recorder/2026-04-16/DOGEUSDT_300.csv | tf_sec | 1068 | 300, 4229187650.0, 3396212170.0, 2739256338.0, 3663902660.0 | context |
| data/recorder/2026-04-16/DOGEUSDT_900.csv | symbol | 74 | DOGEUSDT | context |
| data/recorder/2026-04-16/DOGEUSDT_900.csv | regime | 74 | PENDING | context |
| data/recorder/2026-04-16/DOGEUSDT_900.csv | tf_sec | 74 | 900 | context |
| data/recorder/2026-04-16/ETHUSDT_180.csv | symbol | 376 | ETHUSDT | context |
| data/recorder/2026-04-16/ETHUSDT_180.csv | regime | 376 | UNCERTAIN, PENDING, MEAN_REVERSION, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-04-16/ETHUSDT_180.csv | tf_sec | 376 | 180 | context |
| data/recorder/2026-04-16/ETHUSDT_300.csv | symbol | 1068 | ETHUSDT, 1, 5, 7, 9 | context |
| data/recorder/2026-04-16/ETHUSDT_300.csv | regime | 1062 | PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP, stale_features | context |
| data/recorder/2026-04-16/ETHUSDT_300.csv | tf_sec | 1068 | 300, 194073.963, 90817.675, 47098.013, 121119.637 | context |
| data/recorder/2026-04-16/ETHUSDT_900.csv | symbol | 74 | ETHUSDT | context |
| data/recorder/2026-04-16/ETHUSDT_900.csv | regime | 74 | PENDING | context |
| data/recorder/2026-04-16/ETHUSDT_900.csv | tf_sec | 74 | 900 | context |
| data/recorder/2026-04-16/SOLUSDT_180.csv | symbol | 376 | SOLUSDT | context |
| data/recorder/2026-04-16/SOLUSDT_180.csv | regime | 376 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-16/SOLUSDT_180.csv | tf_sec | 376 | 180 | context |
| data/recorder/2026-04-16/SOLUSDT_300.csv | symbol | 1068 | SOLUSDT, 1, 6, 8, 82 | context |
| data/recorder/2026-04-16/SOLUSDT_300.csv | regime | 1062 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, stale_features | context |
| data/recorder/2026-04-16/SOLUSDT_300.csv | tf_sec | 1068 | 300, 7732.44, 40372.73, 16888.51, 49839.96 | context |
| data/recorder/2026-04-16/SOLUSDT_900.csv | symbol | 74 | SOLUSDT | context |
| data/recorder/2026-04-16/SOLUSDT_900.csv | regime | 74 | PENDING | context |
| data/recorder/2026-04-16/SOLUSDT_900.csv | tf_sec | 74 | 900 | context |
| data/recorder/2026-04-16/XRPUSDT_180.csv | symbol | 376 | XRPUSDT | context |
| data/recorder/2026-04-16/XRPUSDT_180.csv | regime | 376 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-16/XRPUSDT_180.csv | tf_sec | 376 | 180 | context |
| data/recorder/2026-04-16/XRPUSDT_300.csv | symbol | 1066 | XRPUSDT, 1, 60, 10, 29 | context |
| data/recorder/2026-04-16/XRPUSDT_300.csv | regime | 1062 | PENDING, TREND_UP, UNCERTAIN, stale_features, LOW_VOLATILITY | context |
| data/recorder/2026-04-16/XRPUSDT_300.csv | tf_sec | 1066 | 300, 142842903.6, 96757143.1, 104465468.5, 223874292.1 | context |
| data/recorder/2026-04-16/XRPUSDT_900.csv | symbol | 362 | XRPUSDT | context |
| data/recorder/2026-04-16/XRPUSDT_900.csv | regime | 362 | PENDING | context |
| data/recorder/2026-04-16/XRPUSDT_900.csv | tf_sec | 362 | 900 | context |
| data/recorder/2026-04-17/1000PEPEUSDT_180.csv | symbol | 475 | 1000PEPEUSDT | context |
| data/recorder/2026-04-17/1000PEPEUSDT_180.csv | regime | 475 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-17/1000PEPEUSDT_180.csv | tf_sec | 475 | 180 | context |
| data/recorder/2026-04-17/1000PEPEUSDT_300.csv | symbol | 285 | 1000PEPEUSDT | context |
| data/recorder/2026-04-17/1000PEPEUSDT_300.csv | regime | 285 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-17/1000PEPEUSDT_300.csv | tf_sec | 285 | 300 | context |
| data/recorder/2026-04-17/1000PEPEUSDT_900.csv | symbol | 95 | 1000PEPEUSDT | context |
| data/recorder/2026-04-17/1000PEPEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-17/1000PEPEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-17/BNBUSDT_180.csv | symbol | 475 | BNBUSDT | context |
| data/recorder/2026-04-17/BNBUSDT_180.csv | regime | 475 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-17/BNBUSDT_180.csv | tf_sec | 475 | 180 | context |
| data/recorder/2026-04-17/BNBUSDT_300.csv | symbol | 70 | BNBUSDT | context |
| data/recorder/2026-04-17/BNBUSDT_300.csv | regime | 1188 | PENDING, LOW_VOLATILITY, UNCERTAIN, MATCHED, MISSING | context |
| data/recorder/2026-04-17/BNBUSDT_300.csv | tf_sec | 70 | 300 | context |
| data/recorder/2026-04-17/BNBUSDT_900.csv | symbol | 95 | BNBUSDT | context |
| data/recorder/2026-04-17/BNBUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-17/BNBUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-17/BTCUSDT_180.csv | symbol | 475 | BTCUSDT | context |
| data/recorder/2026-04-17/BTCUSDT_180.csv | regime | 475 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-17/BTCUSDT_180.csv | tf_sec | 475 | 180 | context |
| data/recorder/2026-04-17/BTCUSDT_300.csv | symbol | 70 | BTCUSDT | context |
| data/recorder/2026-04-17/BTCUSDT_300.csv | regime | 1188 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, MATCHED, MISSING | context |
| data/recorder/2026-04-17/BTCUSDT_300.csv | tf_sec | 70 | 300 | context |
| data/recorder/2026-04-17/BTCUSDT_900.csv | symbol | 95 | BTCUSDT | context |
| data/recorder/2026-04-17/BTCUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-17/BTCUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-17/DOGEUSDT_180.csv | symbol | 475 | DOGEUSDT | context |
| data/recorder/2026-04-17/DOGEUSDT_180.csv | regime | 475 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, TREND_DOWN | context |
| data/recorder/2026-04-17/DOGEUSDT_180.csv | tf_sec | 475 | 180 | context |
| data/recorder/2026-04-17/DOGEUSDT_300.csv | symbol | 70 | DOGEUSDT | context |
| data/recorder/2026-04-17/DOGEUSDT_300.csv | regime | 1188 | PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_UP, MATCHED | context |
| data/recorder/2026-04-17/DOGEUSDT_300.csv | tf_sec | 70 | 300 | context |
| data/recorder/2026-04-17/DOGEUSDT_900.csv | symbol | 95 | DOGEUSDT | context |
| data/recorder/2026-04-17/DOGEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-17/DOGEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-17/ETHUSDT_180.csv | symbol | 475 | ETHUSDT | context |
| data/recorder/2026-04-17/ETHUSDT_180.csv | regime | 475 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-17/ETHUSDT_180.csv | tf_sec | 475 | 180 | context |
| data/recorder/2026-04-17/ETHUSDT_300.csv | symbol | 70 | ETHUSDT | context |
| data/recorder/2026-04-17/ETHUSDT_300.csv | regime | 1188 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN, MATCHED | context |
| data/recorder/2026-04-17/ETHUSDT_300.csv | tf_sec | 70 | 300 | context |
| data/recorder/2026-04-17/ETHUSDT_900.csv | symbol | 95 | ETHUSDT | context |
| data/recorder/2026-04-17/ETHUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-17/ETHUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-17/SOLUSDT_180.csv | symbol | 475 | SOLUSDT | context |
| data/recorder/2026-04-17/SOLUSDT_180.csv | regime | 475 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_DOWN, TREND_UP | context |
| data/recorder/2026-04-17/SOLUSDT_180.csv | tf_sec | 475 | 180 | context |
| data/recorder/2026-04-17/SOLUSDT_300.csv | symbol | 70 | SOLUSDT | context |
| data/recorder/2026-04-17/SOLUSDT_300.csv | regime | 1187 | PENDING, LOW_VOLATILITY, MATCHED, MISSING | context |
| data/recorder/2026-04-17/SOLUSDT_300.csv | tf_sec | 70 | 300 | context |
| data/recorder/2026-04-17/SOLUSDT_900.csv | symbol | 95 | SOLUSDT | context |
| data/recorder/2026-04-17/SOLUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-17/SOLUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-17/XRPUSDT_180.csv | symbol | 475 | XRPUSDT | context |
| data/recorder/2026-04-17/XRPUSDT_180.csv | regime | 475 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-04-17/XRPUSDT_180.csv | tf_sec | 475 | 180 | context |
| data/recorder/2026-04-17/XRPUSDT_300.csv | symbol | 70 | XRPUSDT | context |
| data/recorder/2026-04-17/XRPUSDT_300.csv | regime | 1188 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, MATCHED | context |
| data/recorder/2026-04-17/XRPUSDT_300.csv | tf_sec | 70 | 300 | context |
| data/recorder/2026-04-17/XRPUSDT_900.csv | symbol | 383 | XRPUSDT | context |
| data/recorder/2026-04-17/XRPUSDT_900.csv | regime | 383 | PENDING | context |
| data/recorder/2026-04-17/XRPUSDT_900.csv | tf_sec | 383 | 900 | context |
| data/recorder/2026-04-18/1000PEPEUSDT_180.csv | symbol | 421 | 1000PEPEUSDT | context |
| data/recorder/2026-04-18/1000PEPEUSDT_180.csv | regime | 421 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-18/1000PEPEUSDT_180.csv | tf_sec | 421 | 180 | context |
| data/recorder/2026-04-18/1000PEPEUSDT_300.csv | symbol | 252 | 1000PEPEUSDT | context |
| data/recorder/2026-04-18/1000PEPEUSDT_300.csv | regime | 252 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-18/1000PEPEUSDT_300.csv | tf_sec | 252 | 300 | context |
| data/recorder/2026-04-18/1000PEPEUSDT_900.csv | symbol | 84 | 1000PEPEUSDT | context |
| data/recorder/2026-04-18/1000PEPEUSDT_900.csv | regime | 84 | PENDING | context |
| data/recorder/2026-04-18/1000PEPEUSDT_900.csv | tf_sec | 84 | 900 | context |
| data/recorder/2026-04-18/BNBUSDT_180.csv | symbol | 421 | BNBUSDT | context |
| data/recorder/2026-04-18/BNBUSDT_180.csv | regime | 421 | TREND_UP, PENDING, MEAN_REVERSION, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-18/BNBUSDT_180.csv | tf_sec | 421 | 180 | context |
| data/recorder/2026-04-18/BNBUSDT_300.csv | symbol | 853 | BNBUSDT | context |
| data/recorder/2026-04-18/BNBUSDT_300.csv | regime | 853 | PENDING, TREND_UP, MEAN_REVERSION, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-18/BNBUSDT_300.csv | tf_sec | 853 | 300 | context |
| data/recorder/2026-04-18/BNBUSDT_900.csv | symbol | 84 | BNBUSDT | context |
| data/recorder/2026-04-18/BNBUSDT_900.csv | regime | 84 | PENDING | context |
| data/recorder/2026-04-18/BNBUSDT_900.csv | tf_sec | 84 | 900 | context |
| data/recorder/2026-04-18/BTCUSDT_180.csv | symbol | 421 | BTCUSDT | context |
| data/recorder/2026-04-18/BTCUSDT_180.csv | regime | 421 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-04-18/BTCUSDT_180.csv | tf_sec | 421 | 180 | context |
| data/recorder/2026-04-18/BTCUSDT_300.csv | symbol | 853 | BTCUSDT | context |
| data/recorder/2026-04-18/BTCUSDT_300.csv | regime | 853 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, TREND_DOWN | context |
| data/recorder/2026-04-18/BTCUSDT_300.csv | tf_sec | 853 | 300 | context |
| data/recorder/2026-04-18/BTCUSDT_900.csv | symbol | 84 | BTCUSDT | context |
| data/recorder/2026-04-18/BTCUSDT_900.csv | regime | 84 | PENDING | context |
| data/recorder/2026-04-18/BTCUSDT_900.csv | tf_sec | 84 | 900 | context |
| data/recorder/2026-04-18/DOGEUSDT_180.csv | symbol | 421 | DOGEUSDT | context |
| data/recorder/2026-04-18/DOGEUSDT_180.csv | regime | 421 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-18/DOGEUSDT_180.csv | tf_sec | 421 | 180 | context |
| data/recorder/2026-04-18/DOGEUSDT_300.csv | symbol | 853 | DOGEUSDT | context |
| data/recorder/2026-04-18/DOGEUSDT_300.csv | regime | 853 | PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-18/DOGEUSDT_300.csv | tf_sec | 853 | 300 | context |
| data/recorder/2026-04-18/DOGEUSDT_900.csv | symbol | 84 | DOGEUSDT | context |
| data/recorder/2026-04-18/DOGEUSDT_900.csv | regime | 84 | PENDING | context |
| data/recorder/2026-04-18/DOGEUSDT_900.csv | tf_sec | 84 | 900 | context |
| data/recorder/2026-04-18/ETHUSDT_180.csv | symbol | 421 | ETHUSDT | context |
| data/recorder/2026-04-18/ETHUSDT_180.csv | regime | 421 | UNCERTAIN, PENDING, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-18/ETHUSDT_180.csv | tf_sec | 421 | 180 | context |
| data/recorder/2026-04-18/ETHUSDT_300.csv | symbol | 853 | ETHUSDT | context |
| data/recorder/2026-04-18/ETHUSDT_300.csv | regime | 853 | PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-18/ETHUSDT_300.csv | tf_sec | 853 | 300 | context |
| data/recorder/2026-04-18/ETHUSDT_900.csv | symbol | 84 | ETHUSDT | context |
| data/recorder/2026-04-18/ETHUSDT_900.csv | regime | 84 | PENDING | context |
| data/recorder/2026-04-18/ETHUSDT_900.csv | tf_sec | 84 | 900 | context |
| data/recorder/2026-04-18/SOLUSDT_180.csv | symbol | 421 | SOLUSDT | context |
| data/recorder/2026-04-18/SOLUSDT_180.csv | regime | 421 | LOW_VOLATILITY, PENDING, UNCERTAIN | context |
| data/recorder/2026-04-18/SOLUSDT_180.csv | tf_sec | 421 | 180 | context |
| data/recorder/2026-04-18/SOLUSDT_300.csv | symbol | 854 | SOLUSDT | context |
| data/recorder/2026-04-18/SOLUSDT_300.csv | regime | 854 | PENDING, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-18/SOLUSDT_300.csv | tf_sec | 854 | 300 | context |
| data/recorder/2026-04-18/SOLUSDT_900.csv | symbol | 84 | SOLUSDT | context |
| data/recorder/2026-04-18/SOLUSDT_900.csv | regime | 84 | PENDING | context |
| data/recorder/2026-04-18/SOLUSDT_900.csv | tf_sec | 84 | 900 | context |
| data/recorder/2026-04-18/XRPUSDT_180.csv | symbol | 421 | XRPUSDT | context |
| data/recorder/2026-04-18/XRPUSDT_180.csv | regime | 421 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-18/XRPUSDT_180.csv | tf_sec | 421 | 180 | context |
| data/recorder/2026-04-18/XRPUSDT_300.csv | symbol | 854 | XRPUSDT | context |
| data/recorder/2026-04-18/XRPUSDT_300.csv | regime | 854 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-18/XRPUSDT_300.csv | tf_sec | 854 | 300 | context |
| data/recorder/2026-04-18/XRPUSDT_900.csv | symbol | 276 | XRPUSDT | context |
| data/recorder/2026-04-18/XRPUSDT_900.csv | regime | 276 | PENDING | context |
| data/recorder/2026-04-18/XRPUSDT_900.csv | tf_sec | 276 | 900 | context |
| data/recorder/2026-04-19/1000PEPEUSDT_180.csv | symbol | 480 | 1000PEPEUSDT | context |
| data/recorder/2026-04-19/1000PEPEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-19/1000PEPEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-19/1000PEPEUSDT_300.csv | symbol | 288 | 1000PEPEUSDT | context |
| data/recorder/2026-04-19/1000PEPEUSDT_300.csv | regime | 288 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-19/1000PEPEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-19/1000PEPEUSDT_900.csv | symbol | 96 | 1000PEPEUSDT | context |
| data/recorder/2026-04-19/1000PEPEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-19/1000PEPEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-19/BNBUSDT_180.csv | symbol | 480 | BNBUSDT | context |
| data/recorder/2026-04-19/BNBUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-19/BNBUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-19/BNBUSDT_300.csv | symbol | 288 | BNBUSDT | context |
| data/recorder/2026-04-19/BNBUSDT_300.csv | regime | 288 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-19/BNBUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-19/BNBUSDT_900.csv | symbol | 96 | BNBUSDT | context |
| data/recorder/2026-04-19/BNBUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-19/BNBUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-19/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-04-19/BTCUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_DOWN, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-19/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-19/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-04-19/BTCUSDT_300.csv | regime | 288 | PENDING, LOW_VOLATILITY, TREND_DOWN, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-19/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-19/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-04-19/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-19/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-19/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-04-19/DOGEUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-19/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-19/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-04-19/DOGEUSDT_300.csv | regime | 288 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-19/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-19/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-04-19/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-19/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-19/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-04-19/ETHUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_DOWN, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-19/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-19/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-04-19/ETHUSDT_300.csv | regime | 288 | PENDING, LOW_VOLATILITY, TREND_DOWN, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-19/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-19/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-04-19/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-19/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-19/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-04-19/SOLUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-19/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-19/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-04-19/SOLUSDT_300.csv | regime | 288 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-19/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-19/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-04-19/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-19/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-19/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-04-19/XRPUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-19/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-19/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-04-19/XRPUSDT_300.csv | regime | 288 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-19/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-19/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-04-19/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-19/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-20/1000PEPEUSDT_180.csv | symbol | 480 | 1000PEPEUSDT | context |
| data/recorder/2026-04-20/1000PEPEUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-20/1000PEPEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-20/1000PEPEUSDT_300.csv | symbol | 288 | 1000PEPEUSDT | context |
| data/recorder/2026-04-20/1000PEPEUSDT_300.csv | regime | 288 | PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-20/1000PEPEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-20/1000PEPEUSDT_900.csv | symbol | 96 | 1000PEPEUSDT | context |
| data/recorder/2026-04-20/1000PEPEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-20/1000PEPEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-20/BNBUSDT_180.csv | symbol | 480 | BNBUSDT | context |
| data/recorder/2026-04-20/BNBUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, MEAN_REVERSION, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-20/BNBUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-20/BNBUSDT_300.csv | symbol | 288 | BNBUSDT | context |
| data/recorder/2026-04-20/BNBUSDT_300.csv | regime | 288 | PENDING, TREND_DOWN, MEAN_REVERSION, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-04-20/BNBUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-20/BNBUSDT_900.csv | symbol | 96 | BNBUSDT | context |
| data/recorder/2026-04-20/BNBUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-20/BNBUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-20/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-04-20/BTCUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-20/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-20/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-04-20/BTCUSDT_300.csv | regime | 288 | PENDING, TREND_DOWN, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-20/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-20/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-04-20/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-20/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-20/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-04-20/DOGEUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-20/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-20/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-04-20/DOGEUSDT_300.csv | regime | 288 | PENDING, TREND_DOWN, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-20/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-20/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-04-20/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-20/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-20/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-04-20/ETHUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-20/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-20/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-04-20/ETHUSDT_300.csv | regime | 288 | PENDING, TREND_DOWN, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-20/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-20/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-04-20/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-20/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-20/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-04-20/SOLUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-20/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-20/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-04-20/SOLUSDT_300.csv | regime | 288 | PENDING, TREND_DOWN, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-20/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-20/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-04-20/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-20/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-20/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-04-20/XRPUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-20/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-04-20/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-04-20/XRPUSDT_300.csv | regime | 288 | PENDING, TREND_DOWN, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-04-20/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-04-20/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-04-20/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-04-20/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-04-21/1000PEPEUSDT_180.csv | symbol | 429 | 1000PEPEUSDT | context |
| data/recorder/2026-04-21/1000PEPEUSDT_180.csv | regime | 429 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-21/1000PEPEUSDT_180.csv | tf_sec | 429 | 180 | context |
| data/recorder/2026-04-21/1000PEPEUSDT_300.csv | symbol | 258 | 1000PEPEUSDT | context |
| data/recorder/2026-04-21/1000PEPEUSDT_300.csv | regime | 258 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-21/1000PEPEUSDT_300.csv | tf_sec | 258 | 300 | context |
| data/recorder/2026-04-21/1000PEPEUSDT_900.csv | symbol | 86 | 1000PEPEUSDT | context |
| data/recorder/2026-04-21/1000PEPEUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-04-21/1000PEPEUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-04-21/BNBUSDT_180.csv | symbol | 427 | BNBUSDT | context |
| data/recorder/2026-04-21/BNBUSDT_180.csv | regime | 427 | LOW_VOLATILITY, PENDING, TREND_UP, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-21/BNBUSDT_180.csv | tf_sec | 427 | 180 | context |
| data/recorder/2026-04-21/BNBUSDT_300.csv | symbol | 559 | BNBUSDT | context |
| data/recorder/2026-04-21/BNBUSDT_300.csv | regime | 559 | PENDING, LOW_VOLATILITY, TREND_UP, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-21/BNBUSDT_300.csv | tf_sec | 559 | 300 | context |
| data/recorder/2026-04-21/BNBUSDT_900.csv | symbol | 86 | BNBUSDT | context |
| data/recorder/2026-04-21/BNBUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-04-21/BNBUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-04-21/BTCUSDT_180.csv | symbol | 429 | BTCUSDT | context |
| data/recorder/2026-04-21/BTCUSDT_180.csv | regime | 429 | UNCERTAIN, PENDING, LOW_VOLATILITY, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-04-21/BTCUSDT_180.csv | tf_sec | 429 | 180 | context |
| data/recorder/2026-04-21/BTCUSDT_300.csv | symbol | 559 | BTCUSDT | context |
| data/recorder/2026-04-21/BTCUSDT_300.csv | regime | 559 | PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-04-21/BTCUSDT_300.csv | tf_sec | 559 | 300 | context |
| data/recorder/2026-04-21/BTCUSDT_900.csv | symbol | 86 | BTCUSDT | context |
| data/recorder/2026-04-21/BTCUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-04-21/BTCUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-04-21/DOGEUSDT_180.csv | symbol | 429 | DOGEUSDT | context |
| data/recorder/2026-04-21/DOGEUSDT_180.csv | regime | 429 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-21/DOGEUSDT_180.csv | tf_sec | 429 | 180 | context |
| data/recorder/2026-04-21/DOGEUSDT_300.csv | symbol | 559 | DOGEUSDT | context |
| data/recorder/2026-04-21/DOGEUSDT_300.csv | regime | 559 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-21/DOGEUSDT_300.csv | tf_sec | 559 | 300 | context |
| data/recorder/2026-04-21/DOGEUSDT_900.csv | symbol | 86 | DOGEUSDT | context |
| data/recorder/2026-04-21/DOGEUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-04-21/DOGEUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-04-21/ETHUSDT_180.csv | symbol | 428 | ETHUSDT | context |
| data/recorder/2026-04-21/ETHUSDT_180.csv | regime | 428 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-21/ETHUSDT_180.csv | tf_sec | 428 | 180 | context |
| data/recorder/2026-04-21/ETHUSDT_300.csv | symbol | 559 | ETHUSDT | context |
| data/recorder/2026-04-21/ETHUSDT_300.csv | regime | 559 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-21/ETHUSDT_300.csv | tf_sec | 559 | 300 | context |
| data/recorder/2026-04-21/ETHUSDT_900.csv | symbol | 86 | ETHUSDT | context |
| data/recorder/2026-04-21/ETHUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-04-21/ETHUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-04-21/SOLUSDT_180.csv | symbol | 428 | SOLUSDT | context |
| data/recorder/2026-04-21/SOLUSDT_180.csv | regime | 428 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-21/SOLUSDT_180.csv | tf_sec | 428 | 180 | context |
| data/recorder/2026-04-21/SOLUSDT_300.csv | symbol | 559 | SOLUSDT | context |
| data/recorder/2026-04-21/SOLUSDT_300.csv | regime | 559 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-21/SOLUSDT_300.csv | tf_sec | 559 | 300 | context |
| data/recorder/2026-04-21/SOLUSDT_900.csv | symbol | 86 | SOLUSDT | context |
| data/recorder/2026-04-21/SOLUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-04-21/SOLUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-04-21/XRPUSDT_180.csv | symbol | 427 | XRPUSDT | context |
| data/recorder/2026-04-21/XRPUSDT_180.csv | regime | 427 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-04-21/XRPUSDT_180.csv | tf_sec | 427 | 180 | context |
| data/recorder/2026-04-21/XRPUSDT_300.csv | symbol | 559 | XRPUSDT | context |
| data/recorder/2026-04-21/XRPUSDT_300.csv | regime | 559 | PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-04-21/XRPUSDT_300.csv | tf_sec | 559 | 300 | context |
| data/recorder/2026-04-21/XRPUSDT_900.csv | symbol | 182 | XRPUSDT | context |
| data/recorder/2026-04-21/XRPUSDT_900.csv | regime | 182 | PENDING | context |
| data/recorder/2026-04-21/XRPUSDT_900.csv | tf_sec | 182 | 900 | context |
| data/recorder/2026-04-22/1000PEPEUSDT_180.csv | symbol | 460 | 1000PEPEUSDT | context |
| data/recorder/2026-04-22/1000PEPEUSDT_180.csv | regime | 460 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-22/1000PEPEUSDT_180.csv | tf_sec | 460 | 180 | context |
| data/recorder/2026-04-22/1000PEPEUSDT_300.csv | symbol | 276 | 1000PEPEUSDT | context |
| data/recorder/2026-04-22/1000PEPEUSDT_300.csv | regime | 276 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-22/1000PEPEUSDT_300.csv | tf_sec | 276 | 300 | context |
| data/recorder/2026-04-22/1000PEPEUSDT_900.csv | symbol | 92 | 1000PEPEUSDT | context |
| data/recorder/2026-04-22/1000PEPEUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-22/1000PEPEUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-22/BNBUSDT_180.csv | symbol | 460 | BNBUSDT | context |
| data/recorder/2026-04-22/BNBUSDT_180.csv | regime | 460 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-22/BNBUSDT_180.csv | tf_sec | 460 | 180 | context |
| data/recorder/2026-04-22/BNBUSDT_300.csv | symbol | 577 | BNBUSDT | context |
| data/recorder/2026-04-22/BNBUSDT_300.csv | regime | 577 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-22/BNBUSDT_300.csv | tf_sec | 577 | 300 | context |
| data/recorder/2026-04-22/BNBUSDT_900.csv | symbol | 92 | BNBUSDT | context |
| data/recorder/2026-04-22/BNBUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-22/BNBUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-22/BTCUSDT_180.csv | symbol | 460 | BTCUSDT | context |
| data/recorder/2026-04-22/BTCUSDT_180.csv | regime | 460 | UNCERTAIN, PENDING, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-04-22/BTCUSDT_180.csv | tf_sec | 460 | 180 | context |
| data/recorder/2026-04-22/BTCUSDT_300.csv | symbol | 577 | BTCUSDT | context |
| data/recorder/2026-04-22/BTCUSDT_300.csv | regime | 577 | PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-04-22/BTCUSDT_300.csv | tf_sec | 577 | 300 | context |
| data/recorder/2026-04-22/BTCUSDT_900.csv | symbol | 92 | BTCUSDT | context |
| data/recorder/2026-04-22/BTCUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-22/BTCUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-22/DOGEUSDT_180.csv | symbol | 460 | DOGEUSDT | context |
| data/recorder/2026-04-22/DOGEUSDT_180.csv | regime | 460 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-22/DOGEUSDT_180.csv | tf_sec | 460 | 180 | context |
| data/recorder/2026-04-22/DOGEUSDT_300.csv | symbol | 276 | DOGEUSDT | context |
| data/recorder/2026-04-22/DOGEUSDT_300.csv | regime | 276 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-22/DOGEUSDT_300.csv | tf_sec | 276 | 300 | context |
| data/recorder/2026-04-22/DOGEUSDT_900.csv | symbol | 92 | DOGEUSDT | context |
| data/recorder/2026-04-22/DOGEUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-22/DOGEUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-22/ETHUSDT_180.csv | symbol | 460 | ETHUSDT | context |
| data/recorder/2026-04-22/ETHUSDT_180.csv | regime | 460 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-22/ETHUSDT_180.csv | tf_sec | 460 | 180 | context |
| data/recorder/2026-04-22/ETHUSDT_300.csv | symbol | 276 | ETHUSDT | context |
| data/recorder/2026-04-22/ETHUSDT_300.csv | regime | 276 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-22/ETHUSDT_300.csv | tf_sec | 276 | 300 | context |
| data/recorder/2026-04-22/ETHUSDT_900.csv | symbol | 92 | ETHUSDT | context |
| data/recorder/2026-04-22/ETHUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-22/ETHUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-22/SOLUSDT_180.csv | symbol | 460 | SOLUSDT | context |
| data/recorder/2026-04-22/SOLUSDT_180.csv | regime | 460 | UNCERTAIN, PENDING, TREND_UP, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-22/SOLUSDT_180.csv | tf_sec | 460 | 180 | context |
| data/recorder/2026-04-22/SOLUSDT_300.csv | symbol | 577 | SOLUSDT | context |
| data/recorder/2026-04-22/SOLUSDT_300.csv | regime | 577 | PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-22/SOLUSDT_300.csv | tf_sec | 577 | 300 | context |
| data/recorder/2026-04-22/SOLUSDT_900.csv | symbol | 92 | SOLUSDT | context |
| data/recorder/2026-04-22/SOLUSDT_900.csv | regime | 92 | PENDING | context |
| data/recorder/2026-04-22/SOLUSDT_900.csv | tf_sec | 92 | 900 | context |
| data/recorder/2026-04-22/XRPUSDT_180.csv | symbol | 460 | XRPUSDT | context |
| data/recorder/2026-04-22/XRPUSDT_180.csv | regime | 460 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-04-22/XRPUSDT_180.csv | tf_sec | 460 | 180 | context |
| data/recorder/2026-04-22/XRPUSDT_300.csv | symbol | 577 | XRPUSDT | context |
| data/recorder/2026-04-22/XRPUSDT_300.csv | regime | 577 | PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-04-22/XRPUSDT_300.csv | tf_sec | 577 | 300 | context |
| data/recorder/2026-04-22/XRPUSDT_900.csv | symbol | 188 | XRPUSDT | context |
| data/recorder/2026-04-22/XRPUSDT_900.csv | regime | 188 | PENDING | context |
| data/recorder/2026-04-22/XRPUSDT_900.csv | tf_sec | 188 | 900 | context |
| data/recorder/2026-04-23/1000PEPEUSDT_180.csv | symbol | 472 | 1000PEPEUSDT | context |
| data/recorder/2026-04-23/1000PEPEUSDT_180.csv | regime | 472 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-23/1000PEPEUSDT_180.csv | tf_sec | 472 | 180 | context |
| data/recorder/2026-04-23/1000PEPEUSDT_300.csv | symbol | 283 | 1000PEPEUSDT | context |
| data/recorder/2026-04-23/1000PEPEUSDT_300.csv | regime | 283 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-23/1000PEPEUSDT_300.csv | tf_sec | 283 | 300 | context |
| data/recorder/2026-04-23/1000PEPEUSDT_900.csv | symbol | 95 | 1000PEPEUSDT | context |
| data/recorder/2026-04-23/1000PEPEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-23/1000PEPEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-23/BNBUSDT_180.csv | symbol | 421 | BNBUSDT | context |
| data/recorder/2026-04-23/BNBUSDT_180.csv | regime | 421 | TREND_DOWN, PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-23/BNBUSDT_180.csv | tf_sec | 421 | 180 | context |
| data/recorder/2026-04-23/BNBUSDT_300.csv | symbol | 554 | BNBUSDT | context |
| data/recorder/2026-04-23/BNBUSDT_300.csv | regime | 554 | PENDING, TREND_DOWN, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-23/BNBUSDT_300.csv | tf_sec | 554 | 300 | context |
| data/recorder/2026-04-23/BNBUSDT_900.csv | symbol | 85 | BNBUSDT | context |
| data/recorder/2026-04-23/BNBUSDT_900.csv | regime | 85 | PENDING | context |
| data/recorder/2026-04-23/BNBUSDT_900.csv | tf_sec | 85 | 900 | context |
| data/recorder/2026-04-23/BTCUSDT_180.csv | symbol | 421 | BTCUSDT | context |
| data/recorder/2026-04-23/BTCUSDT_180.csv | regime | 421 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-23/BTCUSDT_180.csv | tf_sec | 421 | 180 | context |
| data/recorder/2026-04-23/BTCUSDT_300.csv | symbol | 554 | BTCUSDT | context |
| data/recorder/2026-04-23/BTCUSDT_300.csv | regime | 554 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-23/BTCUSDT_300.csv | tf_sec | 554 | 300 | context |
| data/recorder/2026-04-23/BTCUSDT_900.csv | symbol | 85 | BTCUSDT | context |
| data/recorder/2026-04-23/BTCUSDT_900.csv | regime | 85 | PENDING | context |
| data/recorder/2026-04-23/BTCUSDT_900.csv | tf_sec | 85 | 900 | context |
| data/recorder/2026-04-23/DOGEUSDT_180.csv | symbol | 472 | DOGEUSDT | context |
| data/recorder/2026-04-23/DOGEUSDT_180.csv | regime | 472 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-23/DOGEUSDT_180.csv | tf_sec | 472 | 180 | context |
| data/recorder/2026-04-23/DOGEUSDT_300.csv | symbol | 283 | DOGEUSDT | context |
| data/recorder/2026-04-23/DOGEUSDT_300.csv | regime | 283 | PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-04-23/DOGEUSDT_300.csv | tf_sec | 283 | 300 | context |
| data/recorder/2026-04-23/DOGEUSDT_900.csv | symbol | 95 | DOGEUSDT | context |
| data/recorder/2026-04-23/DOGEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-23/DOGEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-23/ETHUSDT_180.csv | symbol | 421 | ETHUSDT | context |
| data/recorder/2026-04-23/ETHUSDT_180.csv | regime | 421 | TREND_DOWN, PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-23/ETHUSDT_180.csv | tf_sec | 421 | 180 | context |
| data/recorder/2026-04-23/ETHUSDT_300.csv | symbol | 554 | ETHUSDT | context |
| data/recorder/2026-04-23/ETHUSDT_300.csv | regime | 554 | PENDING, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-23/ETHUSDT_300.csv | tf_sec | 554 | 300 | context |
| data/recorder/2026-04-23/ETHUSDT_900.csv | symbol | 85 | ETHUSDT | context |
| data/recorder/2026-04-23/ETHUSDT_900.csv | regime | 85 | PENDING | context |
| data/recorder/2026-04-23/ETHUSDT_900.csv | tf_sec | 85 | 900 | context |
| data/recorder/2026-04-23/SOLUSDT_180.csv | symbol | 421 | SOLUSDT | context |
| data/recorder/2026-04-23/SOLUSDT_180.csv | regime | 421 | LOW_VOLATILITY, PENDING, TREND_DOWN, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-23/SOLUSDT_180.csv | tf_sec | 421 | 180 | context |
| data/recorder/2026-04-23/SOLUSDT_300.csv | symbol | 554 | SOLUSDT | context |
| data/recorder/2026-04-23/SOLUSDT_300.csv | regime | 554 | PENDING, LOW_VOLATILITY, TREND_DOWN, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-23/SOLUSDT_300.csv | tf_sec | 554 | 300 | context |
| data/recorder/2026-04-23/SOLUSDT_900.csv | symbol | 85 | SOLUSDT | context |
| data/recorder/2026-04-23/SOLUSDT_900.csv | regime | 85 | PENDING | context |
| data/recorder/2026-04-23/SOLUSDT_900.csv | tf_sec | 85 | 900 | context |
| data/recorder/2026-04-23/XRPUSDT_180.csv | symbol | 421 | XRPUSDT | context |
| data/recorder/2026-04-23/XRPUSDT_180.csv | regime | 421 | LOW_VOLATILITY, PENDING, TREND_DOWN, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-23/XRPUSDT_180.csv | tf_sec | 421 | 180 | context |
| data/recorder/2026-04-23/XRPUSDT_300.csv | symbol | 554 | XRPUSDT | context |
| data/recorder/2026-04-23/XRPUSDT_300.csv | regime | 554 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-23/XRPUSDT_300.csv | tf_sec | 554 | 300 | context |
| data/recorder/2026-04-23/XRPUSDT_900.csv | symbol | 181 | XRPUSDT | context |
| data/recorder/2026-04-23/XRPUSDT_900.csv | regime | 181 | PENDING | context |
| data/recorder/2026-04-23/XRPUSDT_900.csv | tf_sec | 181 | 900 | context |
| data/recorder/2026-04-24/1000PEPEUSDT_180.csv | symbol | 247 | 1000PEPEUSDT | context |
| data/recorder/2026-04-24/1000PEPEUSDT_180.csv | regime | 247 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-24/1000PEPEUSDT_180.csv | tf_sec | 247 | 180 | context |
| data/recorder/2026-04-24/1000PEPEUSDT_300.csv | symbol | 148 | 1000PEPEUSDT | context |
| data/recorder/2026-04-24/1000PEPEUSDT_300.csv | regime | 148 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-24/1000PEPEUSDT_300.csv | tf_sec | 148 | 300 | context |
| data/recorder/2026-04-24/1000PEPEUSDT_900.csv | symbol | 49 | 1000PEPEUSDT | context |
| data/recorder/2026-04-24/1000PEPEUSDT_900.csv | regime | 49 | PENDING | context |
| data/recorder/2026-04-24/1000PEPEUSDT_900.csv | tf_sec | 49 | 900 | context |
| data/recorder/2026-04-24/BNBUSDT_180.csv | symbol | 247 | BNBUSDT | context |
| data/recorder/2026-04-24/BNBUSDT_180.csv | regime | 247 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-24/BNBUSDT_180.csv | tf_sec | 247 | 180 | context |
| data/recorder/2026-04-24/BNBUSDT_300.csv | symbol | 750 | BNBUSDT | context |
| data/recorder/2026-04-24/BNBUSDT_300.csv | regime | 750 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-24/BNBUSDT_300.csv | tf_sec | 750 | 300 | context |
| data/recorder/2026-04-24/BNBUSDT_900.csv | symbol | 49 | BNBUSDT | context |
| data/recorder/2026-04-24/BNBUSDT_900.csv | regime | 49 | PENDING | context |
| data/recorder/2026-04-24/BNBUSDT_900.csv | tf_sec | 49 | 900 | context |
| data/recorder/2026-04-24/BTCUSDT_180.csv | symbol | 247 | BTCUSDT | context |
| data/recorder/2026-04-24/BTCUSDT_180.csv | regime | 247 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-24/BTCUSDT_180.csv | tf_sec | 247 | 180 | context |
| data/recorder/2026-04-24/BTCUSDT_300.csv | symbol | 750 | BTCUSDT | context |
| data/recorder/2026-04-24/BTCUSDT_300.csv | regime | 750 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-24/BTCUSDT_300.csv | tf_sec | 750 | 300 | context |
| data/recorder/2026-04-24/BTCUSDT_900.csv | symbol | 49 | BTCUSDT | context |
| data/recorder/2026-04-24/BTCUSDT_900.csv | regime | 49 | PENDING | context |
| data/recorder/2026-04-24/BTCUSDT_900.csv | tf_sec | 49 | 900 | context |
| data/recorder/2026-04-24/DOGEUSDT_180.csv | symbol | 247 | DOGEUSDT | context |
| data/recorder/2026-04-24/DOGEUSDT_180.csv | regime | 247 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-24/DOGEUSDT_180.csv | tf_sec | 247 | 180 | context |
| data/recorder/2026-04-24/DOGEUSDT_300.csv | symbol | 148 | DOGEUSDT | context |
| data/recorder/2026-04-24/DOGEUSDT_300.csv | regime | 148 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-24/DOGEUSDT_300.csv | tf_sec | 148 | 300 | context |
| data/recorder/2026-04-24/DOGEUSDT_900.csv | symbol | 49 | DOGEUSDT | context |
| data/recorder/2026-04-24/DOGEUSDT_900.csv | regime | 49 | PENDING | context |
| data/recorder/2026-04-24/DOGEUSDT_900.csv | tf_sec | 49 | 900 | context |
| data/recorder/2026-04-24/ETHUSDT_180.csv | symbol | 247 | ETHUSDT | context |
| data/recorder/2026-04-24/ETHUSDT_180.csv | regime | 247 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-24/ETHUSDT_180.csv | tf_sec | 247 | 180 | context |
| data/recorder/2026-04-24/ETHUSDT_300.csv | symbol | 750 | ETHUSDT | context |
| data/recorder/2026-04-24/ETHUSDT_300.csv | regime | 750 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-24/ETHUSDT_300.csv | tf_sec | 750 | 300 | context |
| data/recorder/2026-04-24/ETHUSDT_900.csv | symbol | 49 | ETHUSDT | context |
| data/recorder/2026-04-24/ETHUSDT_900.csv | regime | 49 | PENDING | context |
| data/recorder/2026-04-24/ETHUSDT_900.csv | tf_sec | 49 | 900 | context |
| data/recorder/2026-04-24/SOLUSDT_180.csv | symbol | 247 | SOLUSDT | context |
| data/recorder/2026-04-24/SOLUSDT_180.csv | regime | 247 | LOW_VOLATILITY, PENDING, TREND_UP | context |
| data/recorder/2026-04-24/SOLUSDT_180.csv | tf_sec | 247 | 180 | context |
| data/recorder/2026-04-24/SOLUSDT_300.csv | symbol | 750 | SOLUSDT | context |
| data/recorder/2026-04-24/SOLUSDT_300.csv | regime | 750 | PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-24/SOLUSDT_300.csv | tf_sec | 750 | 300 | context |
| data/recorder/2026-04-24/SOLUSDT_900.csv | symbol | 49 | SOLUSDT | context |
| data/recorder/2026-04-24/SOLUSDT_900.csv | regime | 49 | PENDING | context |
| data/recorder/2026-04-24/SOLUSDT_900.csv | tf_sec | 49 | 900 | context |
| data/recorder/2026-04-24/XRPUSDT_180.csv | symbol | 247 | XRPUSDT | context |
| data/recorder/2026-04-24/XRPUSDT_180.csv | regime | 247 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-24/XRPUSDT_180.csv | tf_sec | 247 | 180 | context |
| data/recorder/2026-04-24/XRPUSDT_300.csv | symbol | 750 | XRPUSDT | context |
| data/recorder/2026-04-24/XRPUSDT_300.csv | regime | 750 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-24/XRPUSDT_300.csv | tf_sec | 750 | 300 | context |
| data/recorder/2026-04-24/XRPUSDT_900.csv | symbol | 241 | XRPUSDT | context |
| data/recorder/2026-04-24/XRPUSDT_900.csv | regime | 241 | PENDING | context |
| data/recorder/2026-04-24/XRPUSDT_900.csv | tf_sec | 241 | 900 | context |
| data/recorder/2026-04-25/1000PEPEUSDT_180.csv | symbol | 449 | 1000PEPEUSDT | context |
| data/recorder/2026-04-25/1000PEPEUSDT_180.csv | regime | 449 | LOW_VOLATILITY, PENDING | context |
| data/recorder/2026-04-25/1000PEPEUSDT_180.csv | tf_sec | 449 | 180 | context |
| data/recorder/2026-04-25/1000PEPEUSDT_300.csv | symbol | 270 | 1000PEPEUSDT | context |
| data/recorder/2026-04-25/1000PEPEUSDT_300.csv | regime | 270 | PENDING, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-25/1000PEPEUSDT_300.csv | tf_sec | 270 | 300 | context |
| data/recorder/2026-04-25/1000PEPEUSDT_900.csv | symbol | 90 | 1000PEPEUSDT | context |
| data/recorder/2026-04-25/1000PEPEUSDT_900.csv | regime | 90 | PENDING | context |
| data/recorder/2026-04-25/1000PEPEUSDT_900.csv | tf_sec | 90 | 900 | context |
| data/recorder/2026-04-25/BNBUSDT_180.csv | symbol | 449 | BNBUSDT | context |
| data/recorder/2026-04-25/BNBUSDT_180.csv | regime | 449 | LOW_VOLATILITY, PENDING, TREND_DOWN | context |
| data/recorder/2026-04-25/BNBUSDT_180.csv | tf_sec | 449 | 180 | context |
| data/recorder/2026-04-25/BNBUSDT_300.csv | symbol | 872 | BNBUSDT | context |
| data/recorder/2026-04-25/BNBUSDT_300.csv | regime | 872 | PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-25/BNBUSDT_300.csv | tf_sec | 872 | 300 | context |
| data/recorder/2026-04-25/BNBUSDT_900.csv | symbol | 90 | BNBUSDT | context |
| data/recorder/2026-04-25/BNBUSDT_900.csv | regime | 90 | PENDING | context |
| data/recorder/2026-04-25/BNBUSDT_900.csv | tf_sec | 90 | 900 | context |
| data/recorder/2026-04-25/BTCUSDT_180.csv | symbol | 449 | BTCUSDT | context |
| data/recorder/2026-04-25/BTCUSDT_180.csv | regime | 449 | LOW_VOLATILITY, PENDING, MEAN_REVERSION | context |
| data/recorder/2026-04-25/BTCUSDT_180.csv | tf_sec | 449 | 180 | context |
| data/recorder/2026-04-25/BTCUSDT_300.csv | symbol | 872 | BTCUSDT | context |
| data/recorder/2026-04-25/BTCUSDT_300.csv | regime | 872 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-25/BTCUSDT_300.csv | tf_sec | 872 | 300 | context |
| data/recorder/2026-04-25/BTCUSDT_900.csv | symbol | 90 | BTCUSDT | context |
| data/recorder/2026-04-25/BTCUSDT_900.csv | regime | 90 | PENDING | context |
| data/recorder/2026-04-25/BTCUSDT_900.csv | tf_sec | 90 | 900 | context |
| data/recorder/2026-04-25/DOGEUSDT_180.csv | symbol | 449 | DOGEUSDT | context |
| data/recorder/2026-04-25/DOGEUSDT_180.csv | regime | 449 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-25/DOGEUSDT_180.csv | tf_sec | 449 | 180 | context |
| data/recorder/2026-04-25/DOGEUSDT_300.csv | symbol | 270 | DOGEUSDT | context |
| data/recorder/2026-04-25/DOGEUSDT_300.csv | regime | 270 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-25/DOGEUSDT_300.csv | tf_sec | 270 | 300 | context |
| data/recorder/2026-04-25/DOGEUSDT_900.csv | symbol | 90 | DOGEUSDT | context |
| data/recorder/2026-04-25/DOGEUSDT_900.csv | regime | 90 | PENDING | context |
| data/recorder/2026-04-25/DOGEUSDT_900.csv | tf_sec | 90 | 900 | context |
| data/recorder/2026-04-25/ETHUSDT_180.csv | symbol | 449 | ETHUSDT | context |
| data/recorder/2026-04-25/ETHUSDT_180.csv | regime | 449 | LOW_VOLATILITY, PENDING | context |
| data/recorder/2026-04-25/ETHUSDT_180.csv | tf_sec | 449 | 180 | context |
| data/recorder/2026-04-25/ETHUSDT_300.csv | symbol | 872 | ETHUSDT | context |
| data/recorder/2026-04-25/ETHUSDT_300.csv | regime | 872 | PENDING, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-25/ETHUSDT_300.csv | tf_sec | 872 | 300 | context |
| data/recorder/2026-04-25/ETHUSDT_900.csv | symbol | 90 | ETHUSDT | context |
| data/recorder/2026-04-25/ETHUSDT_900.csv | regime | 90 | PENDING | context |
| data/recorder/2026-04-25/ETHUSDT_900.csv | tf_sec | 90 | 900 | context |
| data/recorder/2026-04-25/SOLUSDT_180.csv | symbol | 449 | SOLUSDT | context |
| data/recorder/2026-04-25/SOLUSDT_180.csv | regime | 449 | LOW_VOLATILITY, PENDING | context |
| data/recorder/2026-04-25/SOLUSDT_180.csv | tf_sec | 449 | 180 | context |
| data/recorder/2026-04-25/SOLUSDT_300.csv | symbol | 872 | SOLUSDT | context |
| data/recorder/2026-04-25/SOLUSDT_300.csv | regime | 872 | PENDING, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-25/SOLUSDT_300.csv | tf_sec | 872 | 300 | context |
| data/recorder/2026-04-25/SOLUSDT_900.csv | symbol | 90 | SOLUSDT | context |
| data/recorder/2026-04-25/SOLUSDT_900.csv | regime | 90 | PENDING | context |
| data/recorder/2026-04-25/SOLUSDT_900.csv | tf_sec | 90 | 900 | context |
| data/recorder/2026-04-25/XRPUSDT_180.csv | symbol | 449 | XRPUSDT | context |
| data/recorder/2026-04-25/XRPUSDT_180.csv | regime | 449 | LOW_VOLATILITY, PENDING | context |
| data/recorder/2026-04-25/XRPUSDT_180.csv | tf_sec | 449 | 180 | context |
| data/recorder/2026-04-25/XRPUSDT_300.csv | symbol | 872 | XRPUSDT | context |
| data/recorder/2026-04-25/XRPUSDT_300.csv | regime | 872 | PENDING, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-25/XRPUSDT_300.csv | tf_sec | 872 | 300 | context |
| data/recorder/2026-04-25/XRPUSDT_900.csv | symbol | 282 | XRPUSDT | context |
| data/recorder/2026-04-25/XRPUSDT_900.csv | regime | 282 | PENDING | context |
| data/recorder/2026-04-25/XRPUSDT_900.csv | tf_sec | 282 | 900 | context |
| data/recorder/2026-04-26/1000PEPEUSDT_180.csv | symbol | 478 | 1000PEPEUSDT | context |
| data/recorder/2026-04-26/1000PEPEUSDT_180.csv | regime | 478 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-26/1000PEPEUSDT_180.csv | tf_sec | 478 | 180 | context |
| data/recorder/2026-04-26/1000PEPEUSDT_300.csv | symbol | 287 | 1000PEPEUSDT | context |
| data/recorder/2026-04-26/1000PEPEUSDT_300.csv | regime | 287 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-26/1000PEPEUSDT_300.csv | tf_sec | 287 | 300 | context |
| data/recorder/2026-04-26/1000PEPEUSDT_900.csv | symbol | 95 | 1000PEPEUSDT | context |
| data/recorder/2026-04-26/1000PEPEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-26/1000PEPEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-26/BNBUSDT_180.csv | symbol | 478 | BNBUSDT | context |
| data/recorder/2026-04-26/BNBUSDT_180.csv | regime | 478 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-26/BNBUSDT_180.csv | tf_sec | 478 | 180 | context |
| data/recorder/2026-04-26/BNBUSDT_300.csv | symbol | 588 | BNBUSDT | context |
| data/recorder/2026-04-26/BNBUSDT_300.csv | regime | 588 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-26/BNBUSDT_300.csv | tf_sec | 588 | 300 | context |
| data/recorder/2026-04-26/BNBUSDT_900.csv | symbol | 95 | BNBUSDT | context |
| data/recorder/2026-04-26/BNBUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-26/BNBUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-26/BTCUSDT_180.csv | symbol | 478 | BTCUSDT | context |
| data/recorder/2026-04-26/BTCUSDT_180.csv | regime | 478 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, HIGH_VOLATILITY, TREND_UP | context |
| data/recorder/2026-04-26/BTCUSDT_180.csv | tf_sec | 478 | 180 | context |
| data/recorder/2026-04-26/BTCUSDT_300.csv | symbol | 588 | BTCUSDT | context |
| data/recorder/2026-04-26/BTCUSDT_300.csv | regime | 588 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, HIGH_VOLATILITY, TREND_UP | context |
| data/recorder/2026-04-26/BTCUSDT_300.csv | tf_sec | 588 | 300 | context |
| data/recorder/2026-04-26/BTCUSDT_900.csv | symbol | 95 | BTCUSDT | context |
| data/recorder/2026-04-26/BTCUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-26/BTCUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-26/DOGEUSDT_180.csv | symbol | 478 | DOGEUSDT | context |
| data/recorder/2026-04-26/DOGEUSDT_180.csv | regime | 478 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-26/DOGEUSDT_180.csv | tf_sec | 478 | 180 | context |
| data/recorder/2026-04-26/DOGEUSDT_300.csv | symbol | 287 | DOGEUSDT | context |
| data/recorder/2026-04-26/DOGEUSDT_300.csv | regime | 287 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-26/DOGEUSDT_300.csv | tf_sec | 287 | 300 | context |
| data/recorder/2026-04-26/DOGEUSDT_900.csv | symbol | 95 | DOGEUSDT | context |
| data/recorder/2026-04-26/DOGEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-26/DOGEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-26/ETHUSDT_180.csv | symbol | 478 | ETHUSDT | context |
| data/recorder/2026-04-26/ETHUSDT_180.csv | regime | 478 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-26/ETHUSDT_180.csv | tf_sec | 478 | 180 | context |
| data/recorder/2026-04-26/ETHUSDT_300.csv | symbol | 588 | ETHUSDT | context |
| data/recorder/2026-04-26/ETHUSDT_300.csv | regime | 588 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-26/ETHUSDT_300.csv | tf_sec | 588 | 300 | context |
| data/recorder/2026-04-26/ETHUSDT_900.csv | symbol | 95 | ETHUSDT | context |
| data/recorder/2026-04-26/ETHUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-26/ETHUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-26/SOLUSDT_180.csv | symbol | 478 | SOLUSDT | context |
| data/recorder/2026-04-26/SOLUSDT_180.csv | regime | 478 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-26/SOLUSDT_180.csv | tf_sec | 478 | 180 | context |
| data/recorder/2026-04-26/SOLUSDT_300.csv | symbol | 588 | SOLUSDT | context |
| data/recorder/2026-04-26/SOLUSDT_300.csv | regime | 588 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-26/SOLUSDT_300.csv | tf_sec | 588 | 300 | context |
| data/recorder/2026-04-26/SOLUSDT_900.csv | symbol | 95 | SOLUSDT | context |
| data/recorder/2026-04-26/SOLUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-04-26/SOLUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-04-26/XRPUSDT_180.csv | symbol | 478 | XRPUSDT | context |
| data/recorder/2026-04-26/XRPUSDT_180.csv | regime | 478 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-26/XRPUSDT_180.csv | tf_sec | 478 | 180 | context |
| data/recorder/2026-04-26/XRPUSDT_300.csv | symbol | 588 | XRPUSDT | context |
| data/recorder/2026-04-26/XRPUSDT_300.csv | regime | 588 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-04-26/XRPUSDT_300.csv | tf_sec | 588 | 300 | context |
| data/recorder/2026-04-26/XRPUSDT_900.csv | symbol | 15 | XRPUSDT | context |
| data/recorder/2026-04-26/XRPUSDT_900.csv | regime | 16 | PENDING, True | context |
| data/recorder/2026-04-26/XRPUSDT_900.csv | tf_sec | 16 | 900, XRPUSDT | context |
| data/recorder/2026-04-27/1000PEPEUSDT_180.csv | symbol | 299 | 1000PEPEUSDT | context |
| data/recorder/2026-04-27/1000PEPEUSDT_180.csv | regime | 299 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-27/1000PEPEUSDT_180.csv | tf_sec | 299 | 180 | context |
| data/recorder/2026-04-27/1000PEPEUSDT_300.csv | symbol | 179 | 1000PEPEUSDT | context |
| data/recorder/2026-04-27/1000PEPEUSDT_300.csv | regime | 179 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-27/1000PEPEUSDT_300.csv | tf_sec | 179 | 300 | context |
| data/recorder/2026-04-27/1000PEPEUSDT_900.csv | symbol | 60 | 1000PEPEUSDT | context |
| data/recorder/2026-04-27/1000PEPEUSDT_900.csv | regime | 60 | PENDING | context |
| data/recorder/2026-04-27/1000PEPEUSDT_900.csv | tf_sec | 60 | 900 | context |
| data/recorder/2026-04-27/BNBUSDT_180.csv | symbol | 299 | BNBUSDT | context |
| data/recorder/2026-04-27/BNBUSDT_180.csv | regime | 299 | MEAN_REVERSION, PENDING, TREND_UP, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-27/BNBUSDT_180.csv | tf_sec | 299 | 180 | context |
| data/recorder/2026-04-27/BNBUSDT_300.csv | symbol | 480 | BNBUSDT | context |
| data/recorder/2026-04-27/BNBUSDT_300.csv | regime | 480 | PENDING, MEAN_REVERSION, TREND_UP, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-27/BNBUSDT_300.csv | tf_sec | 480 | 300 | context |
| data/recorder/2026-04-27/BNBUSDT_900.csv | symbol | 60 | BNBUSDT | context |
| data/recorder/2026-04-27/BNBUSDT_900.csv | regime | 60 | PENDING | context |
| data/recorder/2026-04-27/BNBUSDT_900.csv | tf_sec | 60 | 900 | context |
| data/recorder/2026-04-27/BTCUSDT_180.csv | symbol | 299 | BTCUSDT | context |
| data/recorder/2026-04-27/BTCUSDT_180.csv | regime | 299 | TREND_UP, PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-27/BTCUSDT_180.csv | tf_sec | 299 | 180 | context |
| data/recorder/2026-04-27/BTCUSDT_300.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-04-27/BTCUSDT_300.csv | regime | 480 | PENDING, TREND_UP, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-27/BTCUSDT_300.csv | tf_sec | 480 | 300 | context |
| data/recorder/2026-04-27/BTCUSDT_900.csv | symbol | 60 | BTCUSDT | context |
| data/recorder/2026-04-27/BTCUSDT_900.csv | regime | 60 | PENDING | context |
| data/recorder/2026-04-27/BTCUSDT_900.csv | tf_sec | 60 | 900 | context |
| data/recorder/2026-04-27/DOGEUSDT_180.csv | symbol | 299 | DOGEUSDT | context |
| data/recorder/2026-04-27/DOGEUSDT_180.csv | regime | 299 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-27/DOGEUSDT_180.csv | tf_sec | 299 | 180 | context |
| data/recorder/2026-04-27/DOGEUSDT_300.csv | symbol | 179 | DOGEUSDT | context |
| data/recorder/2026-04-27/DOGEUSDT_300.csv | regime | 179 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-27/DOGEUSDT_300.csv | tf_sec | 179 | 300 | context |
| data/recorder/2026-04-27/DOGEUSDT_900.csv | symbol | 60 | DOGEUSDT | context |
| data/recorder/2026-04-27/DOGEUSDT_900.csv | regime | 60 | PENDING | context |
| data/recorder/2026-04-27/DOGEUSDT_900.csv | tf_sec | 60 | 900 | context |
| data/recorder/2026-04-27/ETHUSDT_180.csv | symbol | 299 | ETHUSDT | context |
| data/recorder/2026-04-27/ETHUSDT_180.csv | regime | 299 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-27/ETHUSDT_180.csv | tf_sec | 299 | 180 | context |
| data/recorder/2026-04-27/ETHUSDT_300.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-04-27/ETHUSDT_300.csv | regime | 480 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-04-27/ETHUSDT_300.csv | tf_sec | 480 | 300 | context |
| data/recorder/2026-04-27/ETHUSDT_900.csv | symbol | 60 | ETHUSDT | context |
| data/recorder/2026-04-27/ETHUSDT_900.csv | regime | 60 | PENDING | context |
| data/recorder/2026-04-27/ETHUSDT_900.csv | tf_sec | 60 | 900 | context |
| data/recorder/2026-04-27/SOLUSDT_180.csv | symbol | 299 | SOLUSDT | context |
| data/recorder/2026-04-27/SOLUSDT_180.csv | regime | 299 | MEAN_REVERSION, PENDING, TREND_UP, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-27/SOLUSDT_180.csv | tf_sec | 299 | 180 | context |
| data/recorder/2026-04-27/SOLUSDT_300.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-04-27/SOLUSDT_300.csv | regime | 480 | PENDING, MEAN_REVERSION, TREND_UP, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-27/SOLUSDT_300.csv | tf_sec | 480 | 300 | context |
| data/recorder/2026-04-27/SOLUSDT_900.csv | symbol | 60 | SOLUSDT | context |
| data/recorder/2026-04-27/SOLUSDT_900.csv | regime | 60 | PENDING | context |
| data/recorder/2026-04-27/SOLUSDT_900.csv | tf_sec | 60 | 900 | context |
| data/recorder/2026-04-27/XRPUSDT_180.csv | symbol | 299 | XRPUSDT | context |
| data/recorder/2026-04-27/XRPUSDT_180.csv | regime | 299 | MEAN_REVERSION, PENDING, TREND_UP, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-27/XRPUSDT_180.csv | tf_sec | 299 | 180 | context |
| data/recorder/2026-04-27/XRPUSDT_300.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-04-27/XRPUSDT_300.csv | regime | 480 | PENDING, MEAN_REVERSION, TREND_UP, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-27/XRPUSDT_300.csv | tf_sec | 480 | 300 | context |
| data/recorder/2026-04-27/XRPUSDT_900.csv | symbol | 156 | XRPUSDT | context |
| data/recorder/2026-04-27/XRPUSDT_900.csv | regime | 156 | PENDING | context |
| data/recorder/2026-04-27/XRPUSDT_900.csv | tf_sec | 156 | 900 | context |
| data/recorder/2026-04-28/1000PEPEUSDT_180.csv | symbol | 471 | 1000PEPEUSDT | context |
| data/recorder/2026-04-28/1000PEPEUSDT_180.csv | regime | 471 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-28/1000PEPEUSDT_180.csv | tf_sec | 471 | 180 | context |
| data/recorder/2026-04-28/1000PEPEUSDT_300.csv | symbol | 282 | 1000PEPEUSDT | context |
| data/recorder/2026-04-28/1000PEPEUSDT_300.csv | regime | 282 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-28/1000PEPEUSDT_300.csv | tf_sec | 282 | 300 | context |
| data/recorder/2026-04-28/1000PEPEUSDT_900.csv | symbol | 94 | 1000PEPEUSDT | context |
| data/recorder/2026-04-28/1000PEPEUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-28/1000PEPEUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-28/BNBUSDT_180.csv | symbol | 471 | BNBUSDT | context |
| data/recorder/2026-04-28/BNBUSDT_180.csv | regime | 471 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-28/BNBUSDT_180.csv | tf_sec | 471 | 180 | context |
| data/recorder/2026-04-28/BNBUSDT_300.csv | symbol | 884 | BNBUSDT | context |
| data/recorder/2026-04-28/BNBUSDT_300.csv | regime | 884 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-04-28/BNBUSDT_300.csv | tf_sec | 884 | 300 | context |
| data/recorder/2026-04-28/BNBUSDT_900.csv | symbol | 94 | BNBUSDT | context |
| data/recorder/2026-04-28/BNBUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-28/BNBUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-28/BTCUSDT_180.csv | symbol | 471 | BTCUSDT | context |
| data/recorder/2026-04-28/BTCUSDT_180.csv | regime | 471 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-28/BTCUSDT_180.csv | tf_sec | 471 | 180 | context |
| data/recorder/2026-04-28/BTCUSDT_300.csv | symbol | 884 | BTCUSDT | context |
| data/recorder/2026-04-28/BTCUSDT_300.csv | regime | 884 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-28/BTCUSDT_300.csv | tf_sec | 884 | 300 | context |
| data/recorder/2026-04-28/BTCUSDT_900.csv | symbol | 94 | BTCUSDT | context |
| data/recorder/2026-04-28/BTCUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-28/BTCUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-28/DOGEUSDT_180.csv | symbol | 471 | DOGEUSDT | context |
| data/recorder/2026-04-28/DOGEUSDT_180.csv | regime | 471 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-28/DOGEUSDT_180.csv | tf_sec | 471 | 180 | context |
| data/recorder/2026-04-28/DOGEUSDT_300.csv | symbol | 282 | DOGEUSDT | context |
| data/recorder/2026-04-28/DOGEUSDT_300.csv | regime | 282 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-28/DOGEUSDT_300.csv | tf_sec | 282 | 300 | context |
| data/recorder/2026-04-28/DOGEUSDT_900.csv | symbol | 94 | DOGEUSDT | context |
| data/recorder/2026-04-28/DOGEUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-28/DOGEUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-28/ETHUSDT_180.csv | symbol | 471 | ETHUSDT | context |
| data/recorder/2026-04-28/ETHUSDT_180.csv | regime | 471 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-28/ETHUSDT_180.csv | tf_sec | 471 | 180 | context |
| data/recorder/2026-04-28/ETHUSDT_300.csv | symbol | 884 | ETHUSDT | context |
| data/recorder/2026-04-28/ETHUSDT_300.csv | regime | 884 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-28/ETHUSDT_300.csv | tf_sec | 884 | 300 | context |
| data/recorder/2026-04-28/ETHUSDT_900.csv | symbol | 94 | ETHUSDT | context |
| data/recorder/2026-04-28/ETHUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-28/ETHUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-28/SOLUSDT_180.csv | symbol | 471 | SOLUSDT | context |
| data/recorder/2026-04-28/SOLUSDT_180.csv | regime | 471 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-28/SOLUSDT_180.csv | tf_sec | 471 | 180 | context |
| data/recorder/2026-04-28/SOLUSDT_300.csv | symbol | 884 | SOLUSDT | context |
| data/recorder/2026-04-28/SOLUSDT_300.csv | regime | 884 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-04-28/SOLUSDT_300.csv | tf_sec | 884 | 300 | context |
| data/recorder/2026-04-28/SOLUSDT_900.csv | symbol | 94 | SOLUSDT | context |
| data/recorder/2026-04-28/SOLUSDT_900.csv | regime | 94 | PENDING | context |
| data/recorder/2026-04-28/SOLUSDT_900.csv | tf_sec | 94 | 900 | context |
| data/recorder/2026-04-28/XRPUSDT_180.csv | symbol | 471 | XRPUSDT | context |
| data/recorder/2026-04-28/XRPUSDT_180.csv | regime | 471 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-28/XRPUSDT_180.csv | tf_sec | 471 | 180 | context |
| data/recorder/2026-04-28/XRPUSDT_300.csv | symbol | 884 | XRPUSDT | context |
| data/recorder/2026-04-28/XRPUSDT_300.csv | regime | 884 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-28/XRPUSDT_300.csv | tf_sec | 884 | 300 | context |
| data/recorder/2026-04-28/XRPUSDT_900.csv | symbol | 155 | XRPUSDT | context |
| data/recorder/2026-04-28/XRPUSDT_900.csv | regime | 156 | PENDING, True | context |
| data/recorder/2026-04-28/XRPUSDT_900.csv | tf_sec | 156 | 900, XRPUSDT | context |
| data/recorder/2026-04-29/1000PEPEUSDT_180.csv | symbol | 439 | 1000PEPEUSDT | context |
| data/recorder/2026-04-29/1000PEPEUSDT_180.csv | regime | 439 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-29/1000PEPEUSDT_180.csv | tf_sec | 439 | 180 | context |
| data/recorder/2026-04-29/1000PEPEUSDT_300.csv | symbol | 265 | 1000PEPEUSDT | context |
| data/recorder/2026-04-29/1000PEPEUSDT_300.csv | regime | 265 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-29/1000PEPEUSDT_300.csv | tf_sec | 265 | 300 | context |
| data/recorder/2026-04-29/1000PEPEUSDT_900.csv | symbol | 87 | 1000PEPEUSDT | context |
| data/recorder/2026-04-29/1000PEPEUSDT_900.csv | regime | 87 | PENDING | context |
| data/recorder/2026-04-29/1000PEPEUSDT_900.csv | tf_sec | 87 | 900 | context |
| data/recorder/2026-04-29/BNBUSDT_180.csv | symbol | 439 | BNBUSDT | context |
| data/recorder/2026-04-29/BNBUSDT_180.csv | regime | 439 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-29/BNBUSDT_180.csv | tf_sec | 439 | 180 | context |
| data/recorder/2026-04-29/BNBUSDT_300.csv | symbol | 2071 | BNBUSDT | context |
| data/recorder/2026-04-29/BNBUSDT_300.csv | regime | 2071 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-29/BNBUSDT_300.csv | tf_sec | 2071 | 300 | context |
| data/recorder/2026-04-29/BNBUSDT_900.csv | symbol | 87 | BNBUSDT | context |
| data/recorder/2026-04-29/BNBUSDT_900.csv | regime | 87 | PENDING | context |
| data/recorder/2026-04-29/BNBUSDT_900.csv | tf_sec | 87 | 900 | context |
| data/recorder/2026-04-29/BTCUSDT_180.csv | symbol | 439 | BTCUSDT | context |
| data/recorder/2026-04-29/BTCUSDT_180.csv | regime | 439 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-29/BTCUSDT_180.csv | tf_sec | 439 | 180 | context |
| data/recorder/2026-04-29/BTCUSDT_300.csv | symbol | 2071 | BTCUSDT | context |
| data/recorder/2026-04-29/BTCUSDT_300.csv | regime | 2071 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-29/BTCUSDT_300.csv | tf_sec | 2071 | 300 | context |
| data/recorder/2026-04-29/BTCUSDT_900.csv | symbol | 87 | BTCUSDT | context |
| data/recorder/2026-04-29/BTCUSDT_900.csv | regime | 87 | PENDING | context |
| data/recorder/2026-04-29/BTCUSDT_900.csv | tf_sec | 87 | 900 | context |
| data/recorder/2026-04-29/DOGEUSDT_180.csv | symbol | 439 | DOGEUSDT | context |
| data/recorder/2026-04-29/DOGEUSDT_180.csv | regime | 439 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-29/DOGEUSDT_180.csv | tf_sec | 439 | 180 | context |
| data/recorder/2026-04-29/DOGEUSDT_300.csv | symbol | 265 | DOGEUSDT | context |
| data/recorder/2026-04-29/DOGEUSDT_300.csv | regime | 265 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-29/DOGEUSDT_300.csv | tf_sec | 265 | 300 | context |
| data/recorder/2026-04-29/DOGEUSDT_900.csv | symbol | 87 | DOGEUSDT | context |
| data/recorder/2026-04-29/DOGEUSDT_900.csv | regime | 87 | PENDING | context |
| data/recorder/2026-04-29/DOGEUSDT_900.csv | tf_sec | 87 | 900 | context |
| data/recorder/2026-04-29/ETHUSDT_180.csv | symbol | 439 | ETHUSDT | context |
| data/recorder/2026-04-29/ETHUSDT_180.csv | regime | 439 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-29/ETHUSDT_180.csv | tf_sec | 439 | 180 | context |
| data/recorder/2026-04-29/ETHUSDT_300.csv | symbol | 2071 | ETHUSDT | context |
| data/recorder/2026-04-29/ETHUSDT_300.csv | regime | 2071 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-29/ETHUSDT_300.csv | tf_sec | 2071 | 300 | context |
| data/recorder/2026-04-29/ETHUSDT_900.csv | symbol | 87 | ETHUSDT | context |
| data/recorder/2026-04-29/ETHUSDT_900.csv | regime | 87 | PENDING | context |
| data/recorder/2026-04-29/ETHUSDT_900.csv | tf_sec | 87 | 900 | context |
| data/recorder/2026-04-29/SOLUSDT_180.csv | symbol | 439 | SOLUSDT | context |
| data/recorder/2026-04-29/SOLUSDT_180.csv | regime | 439 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-29/SOLUSDT_180.csv | tf_sec | 439 | 180 | context |
| data/recorder/2026-04-29/SOLUSDT_300.csv | symbol | 2071 | SOLUSDT | context |
| data/recorder/2026-04-29/SOLUSDT_300.csv | regime | 2071 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-04-29/SOLUSDT_300.csv | tf_sec | 2071 | 300 | context |
| data/recorder/2026-04-29/SOLUSDT_900.csv | symbol | 87 | SOLUSDT | context |
| data/recorder/2026-04-29/SOLUSDT_900.csv | regime | 87 | PENDING | context |
| data/recorder/2026-04-29/SOLUSDT_900.csv | tf_sec | 87 | 900 | context |
| data/recorder/2026-04-29/XRPUSDT_180.csv | symbol | 439 | XRPUSDT | context |
| data/recorder/2026-04-29/XRPUSDT_180.csv | regime | 439 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-29/XRPUSDT_180.csv | tf_sec | 439 | 180 | context |
| data/recorder/2026-04-29/XRPUSDT_300.csv | symbol | 2071 | XRPUSDT | context |
| data/recorder/2026-04-29/XRPUSDT_300.csv | regime | 2071 | PENDING, LOW_VOLATILITY, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-04-29/XRPUSDT_300.csv | tf_sec | 2071 | 300 | context |
| data/recorder/2026-04-29/XRPUSDT_900.csv | symbol | 531 | XRPUSDT | context |
| data/recorder/2026-04-29/XRPUSDT_900.csv | regime | 532 | PENDING, True | context |
| data/recorder/2026-04-29/XRPUSDT_900.csv | tf_sec | 532 | 900, XRPUSDT | context |
| data/recorder/2026-04-30/1000PEPEUSDT_180.csv | symbol | 433 | 1000PEPEUSDT | context |
| data/recorder/2026-04-30/1000PEPEUSDT_180.csv | regime | 433 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-30/1000PEPEUSDT_180.csv | tf_sec | 433 | 180 | context |
| data/recorder/2026-04-30/1000PEPEUSDT_300.csv | symbol | 260 | 1000PEPEUSDT | context |
| data/recorder/2026-04-30/1000PEPEUSDT_300.csv | regime | 260 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-04-30/1000PEPEUSDT_300.csv | tf_sec | 260 | 300 | context |
| data/recorder/2026-04-30/1000PEPEUSDT_900.csv | symbol | 86 | 1000PEPEUSDT | context |
| data/recorder/2026-04-30/1000PEPEUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-04-30/1000PEPEUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-04-30/BNBUSDT_180.csv | symbol | 433 | BNBUSDT | context |
| data/recorder/2026-04-30/BNBUSDT_180.csv | regime | 433 | LOW_VOLATILITY, PENDING, UNCERTAIN | context |
| data/recorder/2026-04-30/BNBUSDT_180.csv | tf_sec | 433 | 180 | context |
| data/recorder/2026-04-30/BNBUSDT_300.csv | symbol | 561 | BNBUSDT | context |
| data/recorder/2026-04-30/BNBUSDT_300.csv | regime | 561 | PENDING, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-30/BNBUSDT_300.csv | tf_sec | 561 | 300 | context |
| data/recorder/2026-04-30/BNBUSDT_900.csv | symbol | 86 | BNBUSDT | context |
| data/recorder/2026-04-30/BNBUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-04-30/BNBUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-04-30/BTCUSDT_180.csv | symbol | 433 | BTCUSDT | context |
| data/recorder/2026-04-30/BTCUSDT_180.csv | regime | 433 | LOW_VOLATILITY, PENDING, UNCERTAIN | context |
| data/recorder/2026-04-30/BTCUSDT_180.csv | tf_sec | 433 | 180 | context |
| data/recorder/2026-04-30/BTCUSDT_300.csv | symbol | 561 | BTCUSDT | context |
| data/recorder/2026-04-30/BTCUSDT_300.csv | regime | 561 | PENDING, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-30/BTCUSDT_300.csv | tf_sec | 561 | 300 | context |
| data/recorder/2026-04-30/BTCUSDT_900.csv | symbol | 86 | BTCUSDT | context |
| data/recorder/2026-04-30/BTCUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-04-30/BTCUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-04-30/DOGEUSDT_180.csv | symbol | 433 | DOGEUSDT | context |
| data/recorder/2026-04-30/DOGEUSDT_180.csv | regime | 433 | TREND_UP, PENDING, UNCERTAIN | context |
| data/recorder/2026-04-30/DOGEUSDT_180.csv | tf_sec | 433 | 180 | context |
| data/recorder/2026-04-30/DOGEUSDT_300.csv | symbol | 260 | DOGEUSDT | context |
| data/recorder/2026-04-30/DOGEUSDT_300.csv | regime | 260 | PENDING, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-04-30/DOGEUSDT_300.csv | tf_sec | 260 | 300 | context |
| data/recorder/2026-04-30/DOGEUSDT_900.csv | symbol | 86 | DOGEUSDT | context |
| data/recorder/2026-04-30/DOGEUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-04-30/DOGEUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-04-30/ETHUSDT_180.csv | symbol | 433 | ETHUSDT | context |
| data/recorder/2026-04-30/ETHUSDT_180.csv | regime | 433 | LOW_VOLATILITY, PENDING, UNCERTAIN | context |
| data/recorder/2026-04-30/ETHUSDT_180.csv | tf_sec | 433 | 180 | context |
| data/recorder/2026-04-30/ETHUSDT_300.csv | symbol | 561 | ETHUSDT | context |
| data/recorder/2026-04-30/ETHUSDT_300.csv | regime | 561 | PENDING, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-04-30/ETHUSDT_300.csv | tf_sec | 561 | 300 | context |
| data/recorder/2026-04-30/ETHUSDT_900.csv | symbol | 86 | ETHUSDT | context |
| data/recorder/2026-04-30/ETHUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-04-30/ETHUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-04-30/SOLUSDT_180.csv | symbol | 433 | SOLUSDT | context |
| data/recorder/2026-04-30/SOLUSDT_180.csv | regime | 433 | UNCERTAIN, PENDING, TREND_DOWN, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-04-30/SOLUSDT_180.csv | tf_sec | 433 | 180 | context |
| data/recorder/2026-04-30/SOLUSDT_300.csv | symbol | 561 | SOLUSDT | context |
| data/recorder/2026-04-30/SOLUSDT_300.csv | regime | 561 | PENDING, UNCERTAIN, TREND_DOWN, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-04-30/SOLUSDT_300.csv | tf_sec | 561 | 300 | context |
| data/recorder/2026-04-30/SOLUSDT_900.csv | symbol | 86 | SOLUSDT | context |
| data/recorder/2026-04-30/SOLUSDT_900.csv | regime | 86 | PENDING | context |
| data/recorder/2026-04-30/SOLUSDT_900.csv | tf_sec | 86 | 900 | context |
| data/recorder/2026-04-30/XRPUSDT_180.csv | symbol | 433 | XRPUSDT | context |
| data/recorder/2026-04-30/XRPUSDT_180.csv | regime | 433 | UNCERTAIN, PENDING, MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-04-30/XRPUSDT_180.csv | tf_sec | 433 | 180 | context |
| data/recorder/2026-04-30/XRPUSDT_300.csv | symbol | 561 | XRPUSDT | context |
| data/recorder/2026-04-30/XRPUSDT_300.csv | regime | 561 | PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-04-30/XRPUSDT_300.csv | tf_sec | 561 | 300 | context |
| data/recorder/2026-04-30/XRPUSDT_900.csv | symbol | 4 | XRPUSDT | context |
| data/recorder/2026-04-30/XRPUSDT_900.csv | regime | 5 | PENDING, True | context |
| data/recorder/2026-04-30/XRPUSDT_900.csv | tf_sec | 5 | 900, XRPUSDT | context |
| data/recorder/2026-05-01/1000PEPEUSDT_180.csv | symbol | 480 | 1000PEPEUSDT | context |
| data/recorder/2026-05-01/1000PEPEUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-05-01/1000PEPEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-01/1000PEPEUSDT_300.csv | symbol | 288 | 1000PEPEUSDT | context |
| data/recorder/2026-05-01/1000PEPEUSDT_300.csv | regime | 288 | PENDING, UNCERTAIN, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-05-01/1000PEPEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-01/1000PEPEUSDT_900.csv | symbol | 96 | 1000PEPEUSDT | context |
| data/recorder/2026-05-01/1000PEPEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-01/1000PEPEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-01/BNBUSDT_180.csv | symbol | 480 | BNBUSDT | context |
| data/recorder/2026-05-01/BNBUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-05-01/BNBUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-01/BNBUSDT_300.csv | symbol | 288 | BNBUSDT | context |
| data/recorder/2026-05-01/BNBUSDT_300.csv | regime | 288 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-05-01/BNBUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-01/BNBUSDT_900.csv | symbol | 96 | BNBUSDT | context |
| data/recorder/2026-05-01/BNBUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-01/BNBUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-01/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-05-01/BTCUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-05-01/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-01/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-05-01/BTCUSDT_300.csv | regime | 288 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-05-01/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-01/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-05-01/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-01/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-01/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-05-01/DOGEUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, TREND_UP, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-05-01/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-01/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-05-01/DOGEUSDT_300.csv | regime | 288 | PENDING, UNCERTAIN, TREND_UP, MEAN_REVERSION, LOW_VOLATILITY | context |
| data/recorder/2026-05-01/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-01/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-05-01/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-01/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-01/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-05-01/ETHUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-05-01/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-01/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-05-01/ETHUSDT_300.csv | regime | 288 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-05-01/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-01/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-05-01/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-01/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-01/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-05-01/SOLUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-05-01/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-01/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-05-01/SOLUSDT_300.csv | regime | 288 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-05-01/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-01/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-05-01/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-01/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-01/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-05-01/XRPUSDT_180.csv | regime | 480 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-05-01/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-01/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-05-01/XRPUSDT_300.csv | regime | 288 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-05-01/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-01/XRPUSDT_900.csv | symbol | 5 | XRPUSDT | context |
| data/recorder/2026-05-01/XRPUSDT_900.csv | regime | 6 | PENDING, True | context |
| data/recorder/2026-05-01/XRPUSDT_900.csv | tf_sec | 6 | 900, XRPUSDT | context |
| data/recorder/2026-05-02/1000PEPEUSDT_180.csv | symbol | 343 | 1000PEPEUSDT | context |
| data/recorder/2026-05-02/1000PEPEUSDT_180.csv | regime | 343 | UNCERTAIN, PENDING, MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-05-02/1000PEPEUSDT_180.csv | tf_sec | 343 | 180 | context |
| data/recorder/2026-05-02/1000PEPEUSDT_300.csv | symbol | 206 | 1000PEPEUSDT | context |
| data/recorder/2026-05-02/1000PEPEUSDT_300.csv | regime | 206 | PENDING, UNCERTAIN, MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-05-02/1000PEPEUSDT_300.csv | tf_sec | 206 | 300 | context |
| data/recorder/2026-05-02/1000PEPEUSDT_900.csv | symbol | 69 | 1000PEPEUSDT | context |
| data/recorder/2026-05-02/1000PEPEUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-05-02/1000PEPEUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-05-02/BNBUSDT_180.csv | symbol | 343 | BNBUSDT | context |
| data/recorder/2026-05-02/BNBUSDT_180.csv | regime | 343 | TREND_DOWN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-02/BNBUSDT_180.csv | tf_sec | 343 | 180 | context |
| data/recorder/2026-05-02/BNBUSDT_300.csv | symbol | 808 | BNBUSDT | context |
| data/recorder/2026-05-02/BNBUSDT_300.csv | regime | 808 | PENDING, TREND_DOWN, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-02/BNBUSDT_300.csv | tf_sec | 808 | 300 | context |
| data/recorder/2026-05-02/BNBUSDT_900.csv | symbol | 69 | BNBUSDT | context |
| data/recorder/2026-05-02/BNBUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-05-02/BNBUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-05-02/BTCUSDT_180.csv | symbol | 343 | BTCUSDT | context |
| data/recorder/2026-05-02/BTCUSDT_180.csv | regime | 343 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-05-02/BTCUSDT_180.csv | tf_sec | 343 | 180 | context |
| data/recorder/2026-05-02/BTCUSDT_300.csv | symbol | 808 | BTCUSDT | context |
| data/recorder/2026-05-02/BTCUSDT_300.csv | regime | 808 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-05-02/BTCUSDT_300.csv | tf_sec | 808 | 300 | context |
| data/recorder/2026-05-02/BTCUSDT_900.csv | symbol | 69 | BTCUSDT | context |
| data/recorder/2026-05-02/BTCUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-05-02/BTCUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-05-02/DOGEUSDT_180.csv | symbol | 343 | DOGEUSDT | context |
| data/recorder/2026-05-02/DOGEUSDT_180.csv | regime | 343 | MEAN_REVERSION, PENDING, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-02/DOGEUSDT_180.csv | tf_sec | 343 | 180 | context |
| data/recorder/2026-05-02/DOGEUSDT_300.csv | symbol | 206 | DOGEUSDT | context |
| data/recorder/2026-05-02/DOGEUSDT_300.csv | regime | 206 | PENDING, MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-02/DOGEUSDT_300.csv | tf_sec | 206 | 300 | context |
| data/recorder/2026-05-02/DOGEUSDT_900.csv | symbol | 69 | DOGEUSDT | context |
| data/recorder/2026-05-02/DOGEUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-05-02/DOGEUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-05-02/ETHUSDT_180.csv | symbol | 343 | ETHUSDT | context |
| data/recorder/2026-05-02/ETHUSDT_180.csv | regime | 343 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-05-02/ETHUSDT_180.csv | tf_sec | 343 | 180 | context |
| data/recorder/2026-05-02/ETHUSDT_300.csv | symbol | 808 | ETHUSDT | context |
| data/recorder/2026-05-02/ETHUSDT_300.csv | regime | 808 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-05-02/ETHUSDT_300.csv | tf_sec | 808 | 300 | context |
| data/recorder/2026-05-02/ETHUSDT_900.csv | symbol | 69 | ETHUSDT | context |
| data/recorder/2026-05-02/ETHUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-05-02/ETHUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-05-02/SOLUSDT_180.csv | symbol | 343 | SOLUSDT | context |
| data/recorder/2026-05-02/SOLUSDT_180.csv | regime | 343 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-05-02/SOLUSDT_180.csv | tf_sec | 343 | 180 | context |
| data/recorder/2026-05-02/SOLUSDT_300.csv | symbol | 808 | SOLUSDT | context |
| data/recorder/2026-05-02/SOLUSDT_300.csv | regime | 808 | PENDING, MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-02/SOLUSDT_300.csv | tf_sec | 808 | 300 | context |
| data/recorder/2026-05-02/SOLUSDT_900.csv | symbol | 69 | SOLUSDT | context |
| data/recorder/2026-05-02/SOLUSDT_900.csv | regime | 69 | PENDING | context |
| data/recorder/2026-05-02/SOLUSDT_900.csv | tf_sec | 69 | 900 | context |
| data/recorder/2026-05-02/XRPUSDT_180.csv | symbol | 343 | XRPUSDT | context |
| data/recorder/2026-05-02/XRPUSDT_180.csv | regime | 343 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-02/XRPUSDT_180.csv | tf_sec | 343 | 180 | context |
| data/recorder/2026-05-02/XRPUSDT_300.csv | symbol | 808 | XRPUSDT | context |
| data/recorder/2026-05-02/XRPUSDT_300.csv | regime | 808 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-02/XRPUSDT_300.csv | tf_sec | 808 | 300 | context |
| data/recorder/2026-05-02/XRPUSDT_900.csv | symbol | 261 | XRPUSDT | context |
| data/recorder/2026-05-02/XRPUSDT_900.csv | regime | 261 | PENDING | context |
| data/recorder/2026-05-02/XRPUSDT_900.csv | tf_sec | 261 | 900 | context |
| data/recorder/2026-05-03/1000PEPEUSDT_180.csv | symbol | 403 | 1000PEPEUSDT | context |
| data/recorder/2026-05-03/1000PEPEUSDT_180.csv | regime | 403 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-05-03/1000PEPEUSDT_180.csv | tf_sec | 403 | 180 | context |
| data/recorder/2026-05-03/1000PEPEUSDT_300.csv | symbol | 243 | 1000PEPEUSDT | context |
| data/recorder/2026-05-03/1000PEPEUSDT_300.csv | regime | 243 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-05-03/1000PEPEUSDT_300.csv | tf_sec | 243 | 300 | context |
| data/recorder/2026-05-03/1000PEPEUSDT_900.csv | symbol | 80 | 1000PEPEUSDT | context |
| data/recorder/2026-05-03/1000PEPEUSDT_900.csv | regime | 80 | PENDING | context |
| data/recorder/2026-05-03/1000PEPEUSDT_900.csv | tf_sec | 80 | 900 | context |
| data/recorder/2026-05-03/BNBUSDT_180.csv | symbol | 403 | BNBUSDT | context |
| data/recorder/2026-05-03/BNBUSDT_180.csv | regime | 403 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-03/BNBUSDT_180.csv | tf_sec | 403 | 180 | context |
| data/recorder/2026-05-03/BNBUSDT_300.csv | symbol | 2350 | BNBUSDT | context |
| data/recorder/2026-05-03/BNBUSDT_300.csv | regime | 2350 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-03/BNBUSDT_300.csv | tf_sec | 2350 | 300 | context |
| data/recorder/2026-05-03/BNBUSDT_900.csv | symbol | 80 | BNBUSDT | context |
| data/recorder/2026-05-03/BNBUSDT_900.csv | regime | 80 | PENDING | context |
| data/recorder/2026-05-03/BNBUSDT_900.csv | tf_sec | 80 | 900 | context |
| data/recorder/2026-05-03/BTCUSDT_180.csv | symbol | 403 | BTCUSDT | context |
| data/recorder/2026-05-03/BTCUSDT_180.csv | regime | 403 | MEAN_REVERSION, PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-05-03/BTCUSDT_180.csv | tf_sec | 403 | 180 | context |
| data/recorder/2026-05-03/BTCUSDT_300.csv | symbol | 2349 | BTCUSDT | context |
| data/recorder/2026-05-03/BTCUSDT_300.csv | regime | 2349 | PENDING, MEAN_REVERSION, UNCERTAIN, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-05-03/BTCUSDT_300.csv | tf_sec | 2349 | 300 | context |
| data/recorder/2026-05-03/BTCUSDT_900.csv | symbol | 80 | BTCUSDT | context |
| data/recorder/2026-05-03/BTCUSDT_900.csv | regime | 80 | PENDING | context |
| data/recorder/2026-05-03/BTCUSDT_900.csv | tf_sec | 80 | 900 | context |
| data/recorder/2026-05-03/DOGEUSDT_180.csv | symbol | 403 | DOGEUSDT | context |
| data/recorder/2026-05-03/DOGEUSDT_180.csv | regime | 403 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-05-03/DOGEUSDT_180.csv | tf_sec | 403 | 180 | context |
| data/recorder/2026-05-03/DOGEUSDT_300.csv | symbol | 243 | DOGEUSDT | context |
| data/recorder/2026-05-03/DOGEUSDT_300.csv | regime | 243 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN, TREND_DOWN | context |
| data/recorder/2026-05-03/DOGEUSDT_300.csv | tf_sec | 243 | 300 | context |
| data/recorder/2026-05-03/DOGEUSDT_900.csv | symbol | 80 | DOGEUSDT | context |
| data/recorder/2026-05-03/DOGEUSDT_900.csv | regime | 80 | PENDING | context |
| data/recorder/2026-05-03/DOGEUSDT_900.csv | tf_sec | 80 | 900 | context |
| data/recorder/2026-05-03/ETHUSDT_180.csv | symbol | 403 | ETHUSDT | context |
| data/recorder/2026-05-03/ETHUSDT_180.csv | regime | 403 | MEAN_REVERSION, PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-05-03/ETHUSDT_180.csv | tf_sec | 403 | 180 | context |
| data/recorder/2026-05-03/ETHUSDT_300.csv | symbol | 2350 | ETHUSDT | context |
| data/recorder/2026-05-03/ETHUSDT_300.csv | regime | 2350 | PENDING, MEAN_REVERSION, UNCERTAIN, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-05-03/ETHUSDT_300.csv | tf_sec | 2350 | 300 | context |
| data/recorder/2026-05-03/ETHUSDT_900.csv | symbol | 80 | ETHUSDT | context |
| data/recorder/2026-05-03/ETHUSDT_900.csv | regime | 80 | PENDING | context |
| data/recorder/2026-05-03/ETHUSDT_900.csv | tf_sec | 80 | 900 | context |
| data/recorder/2026-05-03/SOLUSDT_180.csv | symbol | 403 | SOLUSDT | context |
| data/recorder/2026-05-03/SOLUSDT_180.csv | regime | 403 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-05-03/SOLUSDT_180.csv | tf_sec | 403 | 180 | context |
| data/recorder/2026-05-03/SOLUSDT_300.csv | symbol | 2350 | SOLUSDT | context |
| data/recorder/2026-05-03/SOLUSDT_300.csv | regime | 2350 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN, TREND_UP | context |
| data/recorder/2026-05-03/SOLUSDT_300.csv | tf_sec | 2350 | 300 | context |
| data/recorder/2026-05-03/SOLUSDT_900.csv | symbol | 80 | SOLUSDT | context |
| data/recorder/2026-05-03/SOLUSDT_900.csv | regime | 80 | PENDING | context |
| data/recorder/2026-05-03/SOLUSDT_900.csv | tf_sec | 80 | 900 | context |
| data/recorder/2026-05-03/XRPUSDT_180.csv | symbol | 403 | XRPUSDT | context |
| data/recorder/2026-05-03/XRPUSDT_180.csv | regime | 403 | MEAN_REVERSION, PENDING, UNCERTAIN, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-05-03/XRPUSDT_180.csv | tf_sec | 403 | 180 | context |
| data/recorder/2026-05-03/XRPUSDT_300.csv | symbol | 2349 | XRPUSDT | context |
| data/recorder/2026-05-03/XRPUSDT_300.csv | regime | 2349 | PENDING, MEAN_REVERSION, UNCERTAIN, TREND_DOWN, LOW_VOLATILITY | context |
| data/recorder/2026-05-03/XRPUSDT_300.csv | tf_sec | 2349 | 300 | context |
| data/recorder/2026-05-03/XRPUSDT_900.csv | symbol | 3 | XRPUSDT | context |
| data/recorder/2026-05-03/XRPUSDT_900.csv | regime | 4 | PENDING, True | context |
| data/recorder/2026-05-03/XRPUSDT_900.csv | tf_sec | 4 | 900, XRPUSDT | context |
| data/recorder/2026-05-04/1000PEPEUSDT_180.csv | symbol | 474 | 1000PEPEUSDT | context |
| data/recorder/2026-05-04/1000PEPEUSDT_180.csv | regime | 474 | MEAN_REVERSION, PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-05-04/1000PEPEUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-05-04/1000PEPEUSDT_300.csv | symbol | 284 | 1000PEPEUSDT | context |
| data/recorder/2026-05-04/1000PEPEUSDT_300.csv | regime | 284 | PENDING, UNCERTAIN, MEAN_REVERSION, TREND_UP, LOW_VOLATILITY | context |
| data/recorder/2026-05-04/1000PEPEUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-05-04/1000PEPEUSDT_900.csv | symbol | 95 | 1000PEPEUSDT | context |
| data/recorder/2026-05-04/1000PEPEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-05-04/1000PEPEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-05-04/BNBUSDT_180.csv | symbol | 474 | BNBUSDT | context |
| data/recorder/2026-05-04/BNBUSDT_180.csv | regime | 474 | MEAN_REVERSION, PENDING, UNCERTAIN, TREND_UP, HIGH_VOLATILITY | context |
| data/recorder/2026-05-04/BNBUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-05-04/BNBUSDT_300.csv | symbol | 1789 | BNBUSDT | context |
| data/recorder/2026-05-04/BNBUSDT_300.csv | regime | 1789 | PENDING, MEAN_REVERSION, UNCERTAIN, TREND_UP, HIGH_VOLATILITY | context |
| data/recorder/2026-05-04/BNBUSDT_300.csv | tf_sec | 1789 | 300 | context |
| data/recorder/2026-05-04/BNBUSDT_900.csv | symbol | 95 | BNBUSDT | context |
| data/recorder/2026-05-04/BNBUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-05-04/BNBUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-05-04/BTCUSDT_180.csv | symbol | 474 | BTCUSDT | context |
| data/recorder/2026-05-04/BTCUSDT_180.csv | regime | 474 | MEAN_REVERSION, PENDING, UNCERTAIN, HIGH_VOLATILITY, TREND_UP | context |
| data/recorder/2026-05-04/BTCUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-05-04/BTCUSDT_300.csv | symbol | 1788 | BTCUSDT | context |
| data/recorder/2026-05-04/BTCUSDT_300.csv | regime | 1788 | PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY, TREND_UP | context |
| data/recorder/2026-05-04/BTCUSDT_300.csv | tf_sec | 1788 | 300 | context |
| data/recorder/2026-05-04/BTCUSDT_900.csv | symbol | 95 | BTCUSDT | context |
| data/recorder/2026-05-04/BTCUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-05-04/BTCUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-05-04/DOGEUSDT_180.csv | symbol | 474 | DOGEUSDT | context |
| data/recorder/2026-05-04/DOGEUSDT_180.csv | regime | 474 | UNCERTAIN, PENDING, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-05-04/DOGEUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-05-04/DOGEUSDT_300.csv | symbol | 284 | DOGEUSDT | context |
| data/recorder/2026-05-04/DOGEUSDT_300.csv | regime | 284 | PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-05-04/DOGEUSDT_300.csv | tf_sec | 284 | 300 | context |
| data/recorder/2026-05-04/DOGEUSDT_900.csv | symbol | 95 | DOGEUSDT | context |
| data/recorder/2026-05-04/DOGEUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-05-04/DOGEUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-05-04/ETHUSDT_180.csv | symbol | 474 | ETHUSDT | context |
| data/recorder/2026-05-04/ETHUSDT_180.csv | regime | 474 | MEAN_REVERSION, PENDING, UNCERTAIN, HIGH_VOLATILITY, TREND_UP | context |
| data/recorder/2026-05-04/ETHUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-05-04/ETHUSDT_300.csv | symbol | 1488 | ETHUSDT | context |
| data/recorder/2026-05-04/ETHUSDT_300.csv | regime | 1488 | PENDING, MEAN_REVERSION, UNCERTAIN, HIGH_VOLATILITY, TREND_UP | context |
| data/recorder/2026-05-04/ETHUSDT_300.csv | tf_sec | 1488 | 300 | context |
| data/recorder/2026-05-04/ETHUSDT_900.csv | symbol | 95 | ETHUSDT | context |
| data/recorder/2026-05-04/ETHUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-05-04/ETHUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-05-04/SOLUSDT_180.csv | symbol | 474 | SOLUSDT | context |
| data/recorder/2026-05-04/SOLUSDT_180.csv | regime | 474 | UNCERTAIN, PENDING, TREND_DOWN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-05-04/SOLUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-05-04/SOLUSDT_300.csv | symbol | 1789 | SOLUSDT | context |
| data/recorder/2026-05-04/SOLUSDT_300.csv | regime | 1789 | PENDING, UNCERTAIN, TREND_DOWN, MEAN_REVERSION, TREND_UP | context |
| data/recorder/2026-05-04/SOLUSDT_300.csv | tf_sec | 1789 | 300 | context |
| data/recorder/2026-05-04/SOLUSDT_900.csv | symbol | 95 | SOLUSDT | context |
| data/recorder/2026-05-04/SOLUSDT_900.csv | regime | 95 | PENDING | context |
| data/recorder/2026-05-04/SOLUSDT_900.csv | tf_sec | 95 | 900 | context |
| data/recorder/2026-05-04/XRPUSDT_180.csv | symbol | 474 | XRPUSDT | context |
| data/recorder/2026-05-04/XRPUSDT_180.csv | regime | 474 | MEAN_REVERSION, PENDING, UNCERTAIN, TREND_DOWN, HIGH_VOLATILITY | context |
| data/recorder/2026-05-04/XRPUSDT_180.csv | tf_sec | 474 | 180 | context |
| data/recorder/2026-05-04/XRPUSDT_300.csv | symbol | 1789 | XRPUSDT | context |
| data/recorder/2026-05-04/XRPUSDT_300.csv | regime | 1789 | PENDING, MEAN_REVERSION, UNCERTAIN, TREND_DOWN, HIGH_VOLATILITY | context |
| data/recorder/2026-05-04/XRPUSDT_300.csv | tf_sec | 1789 | 300 | context |
| data/recorder/2026-05-04/XRPUSDT_900.csv | symbol | 3 | XRPUSDT | context |
| data/recorder/2026-05-04/XRPUSDT_900.csv | regime | 4 | PENDING, True | context |
| data/recorder/2026-05-04/XRPUSDT_900.csv | tf_sec | 4 | 900, XRPUSDT | context |
| data/recorder/2026-05-05/1000PEPEUSDT_180.csv | symbol | 434 | 1000PEPEUSDT | context |
| data/recorder/2026-05-05/1000PEPEUSDT_180.csv | regime | 434 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-05-05/1000PEPEUSDT_180.csv | tf_sec | 434 | 180 | context |
| data/recorder/2026-05-05/1000PEPEUSDT_300.csv | symbol | 262 | 1000PEPEUSDT | context |
| data/recorder/2026-05-05/1000PEPEUSDT_300.csv | regime | 262 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-05-05/1000PEPEUSDT_300.csv | tf_sec | 262 | 300 | context |
| data/recorder/2026-05-05/1000PEPEUSDT_900.csv | symbol | 88 | 1000PEPEUSDT | context |
| data/recorder/2026-05-05/1000PEPEUSDT_900.csv | regime | 88 | PENDING | context |
| data/recorder/2026-05-05/1000PEPEUSDT_900.csv | tf_sec | 88 | 900 | context |
| data/recorder/2026-05-05/BNBUSDT_180.csv | symbol | 434 | BNBUSDT | context |
| data/recorder/2026-05-05/BNBUSDT_180.csv | regime | 434 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-05-05/BNBUSDT_180.csv | tf_sec | 434 | 180 | context |
| data/recorder/2026-05-05/BNBUSDT_300.csv | symbol | 1165 | BNBUSDT | context |
| data/recorder/2026-05-05/BNBUSDT_300.csv | regime | 1165 | PENDING, LOW_VOLATILITY, TREND_UP, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-05-05/BNBUSDT_300.csv | tf_sec | 1165 | 300 | context |
| data/recorder/2026-05-05/BNBUSDT_900.csv | symbol | 88 | BNBUSDT | context |
| data/recorder/2026-05-05/BNBUSDT_900.csv | regime | 88 | PENDING | context |
| data/recorder/2026-05-05/BNBUSDT_900.csv | tf_sec | 88 | 900 | context |
| data/recorder/2026-05-05/BTCUSDT_180.csv | symbol | 434 | BTCUSDT | context |
| data/recorder/2026-05-05/BTCUSDT_180.csv | regime | 434 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-05-05/BTCUSDT_180.csv | tf_sec | 434 | 180 | context |
| data/recorder/2026-05-05/BTCUSDT_300.csv | symbol | 1165 | BTCUSDT | context |
| data/recorder/2026-05-05/BTCUSDT_300.csv | regime | 1165 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-05-05/BTCUSDT_300.csv | tf_sec | 1165 | 300 | context |
| data/recorder/2026-05-05/BTCUSDT_900.csv | symbol | 88 | BTCUSDT | context |
| data/recorder/2026-05-05/BTCUSDT_900.csv | regime | 88 | PENDING | context |
| data/recorder/2026-05-05/BTCUSDT_900.csv | tf_sec | 88 | 900 | context |
| data/recorder/2026-05-05/DOGEUSDT_180.csv | symbol | 434 | DOGEUSDT | context |
| data/recorder/2026-05-05/DOGEUSDT_180.csv | regime | 434 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, HIGH_VOLATILITY | context |
| data/recorder/2026-05-05/DOGEUSDT_180.csv | tf_sec | 434 | 180 | context |
| data/recorder/2026-05-05/DOGEUSDT_300.csv | symbol | 262 | DOGEUSDT | context |
| data/recorder/2026-05-05/DOGEUSDT_300.csv | regime | 262 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN, HIGH_VOLATILITY | context |
| data/recorder/2026-05-05/DOGEUSDT_300.csv | tf_sec | 262 | 300 | context |
| data/recorder/2026-05-05/DOGEUSDT_900.csv | symbol | 88 | DOGEUSDT | context |
| data/recorder/2026-05-05/DOGEUSDT_900.csv | regime | 88 | PENDING | context |
| data/recorder/2026-05-05/DOGEUSDT_900.csv | tf_sec | 88 | 900 | context |
| data/recorder/2026-05-05/ETHUSDT_180.csv | symbol | 434 | ETHUSDT | context |
| data/recorder/2026-05-05/ETHUSDT_180.csv | regime | 434 | LOW_VOLATILITY, PENDING, UNCERTAIN, TREND_UP, MEAN_REVERSION | context |
| data/recorder/2026-05-05/ETHUSDT_180.csv | tf_sec | 434 | 180 | context |
| data/recorder/2026-05-05/ETHUSDT_300.csv | symbol | 1165 | ETHUSDT | context |
| data/recorder/2026-05-05/ETHUSDT_300.csv | regime | 1165 | PENDING, LOW_VOLATILITY, TREND_UP, MEAN_REVERSION, UNCERTAIN | context |
| data/recorder/2026-05-05/ETHUSDT_300.csv | tf_sec | 1165 | 300 | context |
| data/recorder/2026-05-05/ETHUSDT_900.csv | symbol | 88 | ETHUSDT | context |
| data/recorder/2026-05-05/ETHUSDT_900.csv | regime | 88 | PENDING | context |
| data/recorder/2026-05-05/ETHUSDT_900.csv | tf_sec | 88 | 900 | context |
| data/recorder/2026-05-05/SOLUSDT_180.csv | symbol | 434 | SOLUSDT | context |
| data/recorder/2026-05-05/SOLUSDT_180.csv | regime | 434 | LOW_VOLATILITY, PENDING, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-05-05/SOLUSDT_180.csv | tf_sec | 434 | 180 | context |
| data/recorder/2026-05-05/SOLUSDT_300.csv | symbol | 1165 | SOLUSDT | context |
| data/recorder/2026-05-05/SOLUSDT_300.csv | regime | 1165 | PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-05-05/SOLUSDT_300.csv | tf_sec | 1165 | 300 | context |
| data/recorder/2026-05-05/SOLUSDT_900.csv | symbol | 88 | SOLUSDT | context |
| data/recorder/2026-05-05/SOLUSDT_900.csv | regime | 88 | PENDING | context |
| data/recorder/2026-05-05/SOLUSDT_900.csv | tf_sec | 88 | 900 | context |
| data/recorder/2026-05-05/XRPUSDT_180.csv | symbol | 434 | XRPUSDT | context |
| data/recorder/2026-05-05/XRPUSDT_180.csv | regime | 434 | LOW_VOLATILITY, PENDING, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-05-05/XRPUSDT_180.csv | tf_sec | 434 | 180 | context |
| data/recorder/2026-05-05/XRPUSDT_300.csv | symbol | 1165 | XRPUSDT | context |
| data/recorder/2026-05-05/XRPUSDT_300.csv | regime | 1165 | PENDING, LOW_VOLATILITY, MEAN_REVERSION, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-05-05/XRPUSDT_300.csv | tf_sec | 1165 | 300 | context |
| data/recorder/2026-05-05/XRPUSDT_900.csv | symbol | 59 | XRPUSDT | context |
| data/recorder/2026-05-05/XRPUSDT_900.csv | regime | 60 | PENDING, True | context |
| data/recorder/2026-05-05/XRPUSDT_900.csv | tf_sec | 60 | 900, XRPUSDT | context |
| data/recorder/2026-05-06/1000PEPEUSDT_180.csv | symbol | 480 | 1000PEPEUSDT | context |
| data/recorder/2026-05-06/1000PEPEUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, LOW_VOLATILITY, TREND_UP, TREND_DOWN | context |
| data/recorder/2026-05-06/1000PEPEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-06/1000PEPEUSDT_300.csv | symbol | 288 | 1000PEPEUSDT | context |
| data/recorder/2026-05-06/1000PEPEUSDT_300.csv | regime | 288 | PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_UP, TREND_DOWN | context |
| data/recorder/2026-05-06/1000PEPEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-06/1000PEPEUSDT_900.csv | symbol | 96 | 1000PEPEUSDT | context |
| data/recorder/2026-05-06/1000PEPEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-06/1000PEPEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-06/BNBUSDT_180.csv | symbol | 480 | BNBUSDT | context |
| data/recorder/2026-05-06/BNBUSDT_180.csv | regime | 480 | MEAN_REVERSION, PENDING, TREND_UP, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-06/BNBUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-06/BNBUSDT_300.csv | symbol | 288 | BNBUSDT | context |
| data/recorder/2026-05-06/BNBUSDT_300.csv | regime | 288 | PENDING, MEAN_REVERSION, TREND_UP, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-06/BNBUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-06/BNBUSDT_900.csv | symbol | 96 | BNBUSDT | context |
| data/recorder/2026-05-06/BNBUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-06/BNBUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-06/BTCUSDT_180.csv | symbol | 480 | BTCUSDT | context |
| data/recorder/2026-05-06/BTCUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-05-06/BTCUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-06/BTCUSDT_300.csv | symbol | 288 | BTCUSDT | context |
| data/recorder/2026-05-06/BTCUSDT_300.csv | regime | 288 | PENDING, UNCERTAIN, MEAN_REVERSION, LOW_VOLATILITY, TREND_UP | context |
| data/recorder/2026-05-06/BTCUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-06/BTCUSDT_900.csv | symbol | 96 | BTCUSDT | context |
| data/recorder/2026-05-06/BTCUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-06/BTCUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-06/DOGEUSDT_180.csv | symbol | 480 | DOGEUSDT | context |
| data/recorder/2026-05-06/DOGEUSDT_180.csv | regime | 480 | TREND_UP, PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-05-06/DOGEUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-06/DOGEUSDT_300.csv | symbol | 288 | DOGEUSDT | context |
| data/recorder/2026-05-06/DOGEUSDT_300.csv | regime | 288 | PENDING, TREND_UP, UNCERTAIN, LOW_VOLATILITY, TREND_DOWN | context |
| data/recorder/2026-05-06/DOGEUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-06/DOGEUSDT_900.csv | symbol | 96 | DOGEUSDT | context |
| data/recorder/2026-05-06/DOGEUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-06/DOGEUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-06/ETHUSDT_180.csv | symbol | 480 | ETHUSDT | context |
| data/recorder/2026-05-06/ETHUSDT_180.csv | regime | 480 | TREND_DOWN, PENDING, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-06/ETHUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-06/ETHUSDT_300.csv | symbol | 288 | ETHUSDT | context |
| data/recorder/2026-05-06/ETHUSDT_300.csv | regime | 288 | PENDING, TREND_DOWN, MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-06/ETHUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-06/ETHUSDT_900.csv | symbol | 96 | ETHUSDT | context |
| data/recorder/2026-05-06/ETHUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-06/ETHUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-06/SOLUSDT_180.csv | symbol | 480 | SOLUSDT | context |
| data/recorder/2026-05-06/SOLUSDT_180.csv | regime | 480 | UNCERTAIN, PENDING, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-05-06/SOLUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-06/SOLUSDT_300.csv | symbol | 288 | SOLUSDT | context |
| data/recorder/2026-05-06/SOLUSDT_300.csv | regime | 288 | PENDING, UNCERTAIN, TREND_UP, LOW_VOLATILITY, MEAN_REVERSION | context |
| data/recorder/2026-05-06/SOLUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-06/SOLUSDT_900.csv | symbol | 96 | SOLUSDT | context |
| data/recorder/2026-05-06/SOLUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-06/SOLUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-06/XRPUSDT_180.csv | symbol | 480 | XRPUSDT | context |
| data/recorder/2026-05-06/XRPUSDT_180.csv | regime | 480 | MEAN_REVERSION, PENDING, LOW_VOLATILITY, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-05-06/XRPUSDT_180.csv | tf_sec | 480 | 180 | context |
| data/recorder/2026-05-06/XRPUSDT_300.csv | symbol | 288 | XRPUSDT | context |
| data/recorder/2026-05-06/XRPUSDT_300.csv | regime | 288 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, TREND_UP, UNCERTAIN | context |
| data/recorder/2026-05-06/XRPUSDT_300.csv | tf_sec | 288 | 300 | context |
| data/recorder/2026-05-06/XRPUSDT_900.csv | symbol | 96 | XRPUSDT | context |
| data/recorder/2026-05-06/XRPUSDT_900.csv | regime | 96 | PENDING | context |
| data/recorder/2026-05-06/XRPUSDT_900.csv | tf_sec | 96 | 900 | context |
| data/recorder/2026-05-07/1000PEPEUSDT_180.csv | symbol | 254 | 1000PEPEUSDT | context |
| data/recorder/2026-05-07/1000PEPEUSDT_180.csv | regime | 254 | UNCERTAIN, PENDING, TREND_DOWN, TREND_UP | context |
| data/recorder/2026-05-07/1000PEPEUSDT_180.csv | tf_sec | 254 | 180 | context |
| data/recorder/2026-05-07/1000PEPEUSDT_300.csv | symbol | 153 | 1000PEPEUSDT | context |
| data/recorder/2026-05-07/1000PEPEUSDT_300.csv | regime | 153 | PENDING, UNCERTAIN, TREND_DOWN, TREND_UP | context |
| data/recorder/2026-05-07/1000PEPEUSDT_300.csv | tf_sec | 153 | 300 | context |
| data/recorder/2026-05-07/1000PEPEUSDT_900.csv | symbol | 52 | 1000PEPEUSDT | context |
| data/recorder/2026-05-07/1000PEPEUSDT_900.csv | regime | 52 | PENDING | context |
| data/recorder/2026-05-07/1000PEPEUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-05-07/BNBUSDT_180.csv | symbol | 254 | BNBUSDT | context |
| data/recorder/2026-05-07/BNBUSDT_180.csv | regime | 254 | MEAN_REVERSION, PENDING, TREND_DOWN, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-05-07/BNBUSDT_180.csv | tf_sec | 254 | 180 | context |
| data/recorder/2026-05-07/BNBUSDT_300.csv | symbol | 454 | BNBUSDT | context |
| data/recorder/2026-05-07/BNBUSDT_300.csv | regime | 454 | PENDING, MEAN_REVERSION, TREND_DOWN, UNCERTAIN, LOW_VOLATILITY | context |
| data/recorder/2026-05-07/BNBUSDT_300.csv | tf_sec | 454 | 300 | context |
| data/recorder/2026-05-07/BNBUSDT_900.csv | symbol | 52 | BNBUSDT | context |
| data/recorder/2026-05-07/BNBUSDT_900.csv | regime | 52 | PENDING | context |
| data/recorder/2026-05-07/BNBUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-05-07/BTCUSDT_180.csv | symbol | 254 | BTCUSDT | context |
| data/recorder/2026-05-07/BTCUSDT_180.csv | regime | 254 | MEAN_REVERSION, PENDING, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN | context |
| data/recorder/2026-05-07/BTCUSDT_180.csv | tf_sec | 254 | 180 | context |
| data/recorder/2026-05-07/BTCUSDT_300.csv | symbol | 454 | BTCUSDT | context |
| data/recorder/2026-05-07/BTCUSDT_300.csv | regime | 454 | PENDING, MEAN_REVERSION, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN | context |
| data/recorder/2026-05-07/BTCUSDT_300.csv | tf_sec | 454 | 300 | context |
| data/recorder/2026-05-07/BTCUSDT_900.csv | symbol | 52 | BTCUSDT | context |
| data/recorder/2026-05-07/BTCUSDT_900.csv | regime | 52 | PENDING | context |
| data/recorder/2026-05-07/BTCUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-05-07/DOGEUSDT_180.csv | symbol | 254 | DOGEUSDT | context |
| data/recorder/2026-05-07/DOGEUSDT_180.csv | regime | 254 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-05-07/DOGEUSDT_180.csv | tf_sec | 254 | 180 | context |
| data/recorder/2026-05-07/DOGEUSDT_300.csv | symbol | 153 | DOGEUSDT | context |
| data/recorder/2026-05-07/DOGEUSDT_300.csv | regime | 153 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-05-07/DOGEUSDT_300.csv | tf_sec | 153 | 300 | context |
| data/recorder/2026-05-07/DOGEUSDT_900.csv | symbol | 52 | DOGEUSDT | context |
| data/recorder/2026-05-07/DOGEUSDT_900.csv | regime | 52 | PENDING | context |
| data/recorder/2026-05-07/DOGEUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-05-07/ETHUSDT_180.csv | symbol | 254 | ETHUSDT | context |
| data/recorder/2026-05-07/ETHUSDT_180.csv | regime | 254 | UNCERTAIN, PENDING, LOW_VOLATILITY, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-05-07/ETHUSDT_180.csv | tf_sec | 254 | 180 | context |
| data/recorder/2026-05-07/ETHUSDT_300.csv | symbol | 424 | ETHUSDT | context |
| data/recorder/2026-05-07/ETHUSDT_300.csv | regime | 424 | PENDING, UNCERTAIN, LOW_VOLATILITY, TREND_DOWN, MEAN_REVERSION | context |
| data/recorder/2026-05-07/ETHUSDT_300.csv | tf_sec | 424 | 300 | context |
| data/recorder/2026-05-07/ETHUSDT_900.csv | symbol | 52 | ETHUSDT | context |
| data/recorder/2026-05-07/ETHUSDT_900.csv | regime | 52 | PENDING | context |
| data/recorder/2026-05-07/ETHUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-05-07/SOLUSDT_180.csv | symbol | 254 | SOLUSDT | context |
| data/recorder/2026-05-07/SOLUSDT_180.csv | regime | 254 | MEAN_REVERSION, PENDING, UNCERTAIN, TREND_DOWN, TREND_UP | context |
| data/recorder/2026-05-07/SOLUSDT_180.csv | tf_sec | 254 | 180 | context |
| data/recorder/2026-05-07/SOLUSDT_300.csv | symbol | 424 | SOLUSDT | context |
| data/recorder/2026-05-07/SOLUSDT_300.csv | regime | 424 | PENDING, MEAN_REVERSION, UNCERTAIN, TREND_DOWN, TREND_UP | context |
| data/recorder/2026-05-07/SOLUSDT_300.csv | tf_sec | 424 | 300 | context |
| data/recorder/2026-05-07/SOLUSDT_900.csv | symbol | 52 | SOLUSDT | context |
| data/recorder/2026-05-07/SOLUSDT_900.csv | regime | 52 | PENDING | context |
| data/recorder/2026-05-07/SOLUSDT_900.csv | tf_sec | 52 | 900 | context |
| data/recorder/2026-05-07/XRPUSDT_180.csv | symbol | 254 | XRPUSDT | context |
| data/recorder/2026-05-07/XRPUSDT_180.csv | regime | 254 | LOW_VOLATILITY, PENDING, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-05-07/XRPUSDT_180.csv | tf_sec | 254 | 180 | context |
| data/recorder/2026-05-07/XRPUSDT_300.csv | symbol | 424 | XRPUSDT | context |
| data/recorder/2026-05-07/XRPUSDT_300.csv | regime | 424 | PENDING, LOW_VOLATILITY, TREND_DOWN, UNCERTAIN, MEAN_REVERSION | context |
| data/recorder/2026-05-07/XRPUSDT_300.csv | tf_sec | 424 | 300 | context |
| data/recorder/2026-05-07/XRPUSDT_900.csv | symbol | 148 | XRPUSDT | context |
| data/recorder/2026-05-07/XRPUSDT_900.csv | regime | 148 | PENDING | context |
| data/recorder/2026-05-07/XRPUSDT_900.csv | tf_sec | 148 | 900 | context |
| logs/order_log_v1.jsonl | rid | 1495 | boot-1778021998605, reserve_6092224c-1ee1-4b28-9a10-20cb2f49c2b3, aurora_BTCUSDT_1778021998579, ENTRY-03612c01042d, reserve_b030b306-4787-4e90-934f-c3d42445964f | canonical |
| logs/order_log_v1.jsonl | order_id | 128 | 13110839121, 8686294809, 1356782045, 1626342501, 1000000067500756 | canonical |
| logs/order_log_v1.jsonl | client_order_id | 119 | ENTRY-03612c01042d, ENTRY-432eb3538ada, ENTRY-0cb4ae6ebde9, ENTRY-d166657774fc, CLOSE-4f6c0a48f6df | canonical |
| logs/order_log_v1.jsonl | lifecycle_id | 927 | 6092224c-1ee1-4b28-9a10-20cb2f49c2b3, aurora_BTCUSDT_1778021998579, b030b306-4787-4e90-934f-c3d42445964f, aurora_ETHUSDT_1778023800471, d2ae99c8-bae8-41b4-af25-c6cbe7c0fb79 | canonical |
| logs/order_log_v1.jsonl | trade_id | 44 | 270155297, 270180452, 485348894, 103825609, 120989515 | canonical |
| logs/order_log_v1.jsonl | symbol | 1495 | _SYSTEM_, BTCUSDT, ETHUSDT, BNBUSDT, XRPUSDT | context |
| logs/order_log_v1.jsonl | strategy_id | 309 | aurora | context |
| logs/order_log_v1.jsonl | side | 1410 | SELL, BUY, UNKNOWN_CLOSE_SIDE | context |
| logs/order_log_v1.jsonl | regime | 365 | MEAN_REVERSION, TREND_DOWN, LOW_VOLATILITY, TREND_UP | context |
| logs/regime_confidence_audit_v1.jsonl | rid | 322 | aurora_BTCUSDT_1778021998579, aurora_ETHUSDT_1778023800471, aurora_BNBUSDT_1778024100899, aurora_XRPUSDT_1778025002049, aurora_ETHUSDT_1778026799203 | canonical |
| logs/regime_confidence_audit_v1.jsonl | lifecycle_id | 83 | 6092224c-1ee1-4b28-9a10-20cb2f49c2b3, b030b306-4787-4e90-934f-c3d42445964f, d2ae99c8-bae8-41b4-af25-c6cbe7c0fb79, 26c2ceb0-490a-4e1a-a69f-45b67a5f1a9b, 3a72d64a-26c4-432d-9995-69bc28d0b4bc | canonical |
| logs/regime_confidence_audit_v1.jsonl | symbol | 3488 | SOLUSDT, ETHUSDT, BTCUSDT, DOGEUSDT, XRPUSDT | context |
| logs/regime_confidence_audit_v1.jsonl | strategy_id | 322 | aurora | context |
| logs/regime_confidence_audit_v1.jsonl | regime | 3166 | UNCERTAIN, HIGH_VOLATILITY, MEAN_REVERSION, TREND_UP, TREND_DOWN | context |
| logs/regime_confidence_audit_v1.jsonl | ts_ms | 3488 | 1778021399999, 1778021699999, 1778021999999, 1778021998580, 1778022299999 | context |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | decision_id | 31 | 2518ba5f-191d-4569-9683-cd3202e1f9d1, 86cd3355-b95e-43a7-9fad-c71a31edaca5, d9ed9b47-dba3-41bd-bbd6-ae1a1413d7bf, 93b7a545-9c57-456f-9f53-c321f492b9d6, b6a190af-786b-4efa-aa5f-3f017cd07652 | canonical |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | rid | 31 | aurora_BNBUSDT_1778117100696, aurora_BTCUSDT_1778118302649, aurora_BNBUSDT_1778118303655, aurora_BTCUSDT_1778118903181, aurora_XRPUSDT_1778123703440 | canonical |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | lifecycle_id | 24 | 62b36e3c-c348-4f62-8ce0-9346a3ef6c04, 0d115ffe-2f7d-4371-959d-d200d42d457d, 45fc7b54-cb43-4e6f-ba21-494058a2db0c, 7b139a7b-8529-459e-9b37-4cd446750da9, aurora_BTCUSDT_1778130003092 | canonical |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | trade_id | 14 | 121508284, 121516555, 485862848, 485920475, 485948686 | canonical |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | symbol | 31 | BNBUSDT, BTCUSDT, XRPUSDT, ETHUSDT | context |
| logs/trade_lifecycle.jsonl | request_id | 86 | ppsreq:pps:ETHUSDT:1778025903063:9567, ppsreq:pps:BNBUSDT:1778030099420:15590, ppsreq:pps:ETHUSDT:1778030398789:15972, ppsreq:pps:XRPUSDT:1778030399110:15978, ppsreq:pps:BTCUSDT:1778032201233:18358 | canonical |
| logs/trade_lifecycle.jsonl | rid | 1864 | aurora_BTCUSDT_1778021998579, aurora_ETHUSDT_1778023800471, aurora_BNBUSDT_1778024100899, aurora_XRPUSDT_1778025002049, aurora_ETHUSDT_1778026799203 | canonical |
| logs/trade_lifecycle.jsonl | trace_id | 191549 | pps:__DOMAIN__:1778020932890:1, pps:BNBUSDT:1778020949335:2, pps:BNBUSDT:1778020949338:3, pps:BNBUSDT:1778020949350:4, pps:BNBUSDT:1778020949352:5 | canonical |
| logs/trade_lifecycle.jsonl | order_id | 1660 | 13110839121, 8686294809, 1356782045, 1626342501, 8686360073 | canonical |
| logs/trade_lifecycle.jsonl | client_order_id | 871 | ENTRY-03612c01042d, ENTRY-432eb3538ada, ENTRY-0cb4ae6ebde9, ENTRY-d166657774fc, CLOSE-4f6c0a48f6df | canonical |
| logs/trade_lifecycle.jsonl | exchange_order_id | 58 | 8686339143, 8686376546, 13111120553, 1626389674, 1356854997 | canonical |
| logs/trade_lifecycle.jsonl | entry_order_id | 97 | 13110839121, 8686294809, 1356782045, 1626342501, 8686360073 | canonical |
| logs/trade_lifecycle.jsonl | symbol | 193437 | __DOMAIN__, BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT | context |
| logs/trade_lifecycle.jsonl | strategy_id | 941 | aurora | context |
| logs/trade_lifecycle.jsonl | side | 861 | SHORT, LONG | context |
| logs/trade_lifecycle.jsonl | regime | 861 | MEAN_REVERSION, TREND_DOWN, TREND_UP | context |
| logs/trade_lifecycle.jsonl | ts_ms | 192576 | 1778020932890, 1778020949335, 1778020949338, 1778020949350, 1778020949352 | context |
| logs/trade_lifecycle.jsonl | event_ts_ms | 58 | 1778025906669, 1778027549603, 1778028570049, 1778030102791, 1778030402395 | context |
| ops/wal/2026-04-30.jsonl | rid | 11155 | c1ba747a-02b9-4cec-862b-dd1ebfa2647b, e66569e7-8f15-4893-925d-4c1a42d8054e, tap-1777554960845, tap-1777554960862, tap-1777554960879 | canonical |
| ops/wal/2026-05-01.jsonl | rid | 31078 | bar:SOLUSDT:180:1777582799999, tap-1777582801488, tap-1777582801507, bar:SOLUSDT:900:1777582799999, bar:ETHUSDT:180:1777582799999 | canonical |
| ops/wal/2026-05-01.jsonl | event_ts_ms | 196 | 1777606774915, 1777610108220, 1777610716982, 1777610718998, 1777611921791 | context |
| ops/wal/2026-05-02.jsonl | rid | 22413 | bar:SOLUSDT:180:1777669199999, tap-1777669201252, bar:SOLUSDT:300:1777669199999, tap-1777669201270, bar:SOLUSDT:900:1777669199999 | canonical |
| ops/wal/2026-05-02.jsonl | event_ts_ms | 80 | 1777672856101, 1777675228561, 1777675229323, 1777675229480, 1777675229617 | context |
| ops/wal/2026-05-03.jsonl | rid | 28445 | 6106118a-b535-4896-90b0-06cc65515adc, be8bcc8b-45af-42c2-8338-bc1d4ba460fd, tap-1777756433537, tap-1777756433560, tap-1777756433580 | canonical |
| ops/wal/2026-05-03.jsonl | event_ts_ms | 353 | 1777761616312, 1777761616533, 1777761616593, 1777761617018, 1777761617123 | context |
| ops/wal/2026-05-04.jsonl | rid | 31283 | bar:SOLUSDT:180:1777841999999, bar:SOLUSDT:300:1777841999999, tap-1777842002647, tap-1777842002670, bar:SOLUSDT:900:1777841999999 | canonical |
| ops/wal/2026-05-05.jsonl | rid | 28141 | bar:SOLUSDT:180:1777928399999, bar:SOLUSDT:300:1777928399999, tap-1777928401769, tap-1777928401810, bar:SOLUSDT:900:1777928399999 | canonical |
| ops/wal/2026-05-06.jsonl | rid | 21888 | bar:ETHUSDT:300:1778014799999, aurora_ETHUSDT_1778014800044, bar:ETHUSDT:900:1778014799999, bar:BTCUSDT:180:1778014799999, bar:BTCUSDT:300:1778014799999 | canonical |
| ops/wal/2026-05-06.jsonl | event_ts_ms | 213 | 1778022061257, 1778023950469, 1778024595444, 1778025110780, 1778027458852 | context |
| ops/wal/2026-05-07.jsonl | rid | 14963 | 226343db-36fa-4251-83a6-1ad3e398bab7, bar:SOLUSDT:180:1778101199999, bar:SOLUSDT:300:1778101199999, bar:SOLUSDT:900:1778101199999, bar:ETHUSDT:180:1778101199999 | canonical |
| ops/wal/2026-05-07.jsonl | event_ts_ms | 600 | 1778102420132, 1778102420567, 1778106192049, 1778106526188, 1778106526613 | context |
| ops/wal/execution_position_pending_brackets_v1.jsonl | rid | 137 | aurora_ETHUSDT_1777761604540, clear:8679270880:1777761663945, aurora_ETHUSDT_1777765204919, clear:8679348795:1777765267436, aurora_BTCUSDT_1777767904005 | canonical |
| reports/AURORA_TREND_DOWN_BD1_ETH_STATEFUL_TRADES_2026_05_04.csv | symbol | 19805 | ETHUSDT | context |
| reports/AURORA_TREND_DOWN_SEGMENT_LEVEL_BEST_TRADES_2026_05_04.csv | symbol | 1326 | BTCUSDT, ETHUSDT | context |
| reports/AURORA_TREND_DOWN_SEGMENT_LEVEL_BEST_TRADES_2026_05_04.csv | exit_ts | 1326 | 2025-05-05T01:34:59.999000, 2025-05-06T13:54:59.999000, 2025-05-13T05:54:59.999000, 2025-05-25T00:44:59.999000, 2025-05-25T08:49:59.999000 | context |
| reports/AURORA_TREND_UP_BEST_CANDIDATE_TRADES_2026_05_04.csv | symbol | 25 | BTCUSDT, ETHUSDT | context |
| reports/BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_smoke_trades.csv | symbol | 6 | BTCUSDT | context |
| reports/BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_smoke_trades.csv | side | 6 | LONG | context |
| reports/BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_trades.csv | symbol | 9407 | BTCUSDT, ETHUSDT | context |
| reports/BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_trades.csv | side | 9407 | LONG, SHORT | context |
| reports/md_amr_integrated_validation_trades.csv | trade_id | 346 | XRPUSDT:1, XRPUSDT:2, XRPUSDT:3, XRPUSDT:4, XRPUSDT:5 | canonical |
| reports/md_amr_integrated_validation_trades.csv | symbol | 346 | XRPUSDT, SOLUSDT | context |
| reports/md_amr_integrated_validation_trades.csv | side | 346 | SELL, BUY | context |
| reports/md_amr_integrated_validation_trades.csv | entry_ts_ms | 346 | 1775096100000, 1775097900000, 1775099700000, 1775111400000, 1775113200000 | context |
| reports/md_amr_integrated_validation_trades.csv | exit_ts_ms | 346 | 1775097000000, 1775098800000, 1775100600000, 1775112300000, 1775114100000 | context |
| reports/order_attempts_master.csv | attempt_id | 4 | SYN_723a771f8e9f, SYN_55c5298718fb | canonical |
| reports/order_attempts_master.csv | synthetic_id | 4 | True | canonical |
| reports/order_attempts_master.csv | symbol | 4 | ETHUSDT | context |
| reports/order_attempts_master.csv | side | 4 | UNKNOWN | context |
| reports/order_attempts_master.csv | intent_ts | 4 | 2026-04-26T20:20:04.606000+00:00, 2026-04-26T22:10:00.538000+00:00 | context |
| reports/rejected_attempts_master.csv | attempt_id | 4 | SYN_723a771f8e9f, SYN_55c5298718fb | canonical |
| reports/rejected_attempts_master.csv | synthetic_id | 4 | True | canonical |
| reports/rejected_attempts_master.csv | symbol | 4 | ETHUSDT | context |
| reports/rejected_attempts_master.csv | side | 4 | UNKNOWN | context |
| reports/rejected_attempts_master.csv | intent_ts | 4 | 2026-04-26T20:20:04.606000+00:00, 2026-04-26T22:10:00.538000+00:00 | context |