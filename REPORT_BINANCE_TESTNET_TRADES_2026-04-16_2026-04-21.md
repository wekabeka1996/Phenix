# REPORT_BINANCE_TESTNET_TRADES_2026-04-16_2026-04-21

Status: **COMPLETE_WITH_LEFT_BOUNDARY_UNKNOWN**

## Scope

- Requested local window: 2026-04-16T00:00:00+03:00 .. 2026-04-21T23:59:59.999999+03:00
- Requested UTC window: 2026-04-15T21:00:00+00:00 .. 2026-04-21T20:59:59.999000+00:00
- Effective extracted UTC end: 2026-04-21T20:59:59.999000+00:00
- Binance server time at extraction: 2026-04-22T09:09:08.799000+00:00
- Base URL: https://testnet.binancefuture.com
- Artifact directory: C:/Users/user/Music/Phenix/reports/binance_testnet_trades_2026-04-16_2026-04-21

## Facts

- Exchange access proved against Binance Futures Testnet public time endpoint and signed user endpoints.
- The requested local timezone was handled via Europe/Zaporozhye, including the DST change inside the requested interval.
- Absolute left-boundary position state cannot be exchange-proved for this account because /fapi/v1/userTrades rejects intervals longer than 7 days with code -4165.
- Config symbols: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT
- Local runtime symbols in effective window: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT, _SYSTEM_
- Exchange income symbols in effective window: BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, XRPUSDT
- Candidate symbols rejected by current testnet exchangeInfo: _SYSTEM_
- Final fetched symbol set: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT

## Inferences

- Position episodes were reconstructed by FIFO pairing of non-reduceOnly opening fills to subsequent reducing fills inside the effective window.
- close_reason_inferred uses planned strategy stop/target levels from shadow intents only when the exit price is within 0.2500% relative tolerance of the planned level; otherwise it remains UNKNOWN.

## Assumptions

- None for exchange-proof statements. All non-exchange lifecycle pairing is explicitly represented as inference, not fact.

## Unknowns

- Absolute account position at the exact requested left boundary is UNKNOWN at exchange-proof level because older than 7-day userTrades history is unavailable from the endpoint.

## Validation

| check | value |
| --- | --- |
| base_url_is_testnet | True |
| right_boundary_truncated | False |
| left_boundary_exchange_truth | UNKNOWN: /fapi/v1/userTrades max interval is 7 days (-4165) |
| income_rows | 1007 |
| trade_rows | 843 |
| order_rows | 198 |
| commission_reconciliation_delta | 0.00000000 |
| realized_pnl_reconciliation_delta | 0.00000000 |
| missing_trade_order_count | 0 |
| boundary_close_only_events | 4 |


## Symbol Summary

| symbol | trade_fills | orders_total | income_net | closed_episodes | win_rate | fill_rate | close_unknown_rate | rating |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTCUSDT | 148 | 32 | 132.4585 | 133 | 0.8421 | 0.9375 | 1.0000 | 80.12 |
| XRPUSDT | 188 | 56 | 103.6859 | 162 | 0.7160 | 0.9286 | 0.9938 | 72.29 |
| BNBUSDT | 217 | 24 | -13.9333 | 208 | 0.3798 | 0.7500 | 1.0000 | 42.18 |
| DOGEUSDT | 136 | 38 | -85.0057 | 118 | 0.1017 | 0.9474 | 0.3898 | 35.91 |
| ETHUSDT | 154 | 48 | -77.2261 | 129 | 0.3411 | 0.9583 | 0.9690 | 34.62 |
| 1000PEPEUSDT | 0 | 0 | 0.0000 | 0 | n/a | n/a | n/a | n/a |
| SOLUSDT | 0 | 0 | 0.0000 | 0 | n/a | n/a | n/a | n/a |


## Daily Summary

| local_date | symbol | trade_fills | orders_total | realized_pnl | commission | funding_fee | income_net |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-04-15 | ETHUSDT | 0 | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| 2026-04-16 | BTCUSDT | 8 | 4 | 54.9364 | -10.7709 | 0.0000 | 44.1655 |
| 2026-04-16 | DOGEUSDT | 10 | 10 | 41.8049 | -12.4191 | 0.0000 | 29.3858 |
| 2026-04-16 | ETHUSDT | 27 | 7 | -28.8620 | -15.3901 | 0.0000 | -44.2521 |
| 2026-04-16 | XRPUSDT | 39 | 18 | -3.7389 | -37.6964 | 0.0000 | -41.4352 |
| 2026-04-17 | BNBUSDT | 2 | 3 | -19.0218 | -2.4958 | 0.0000 | -21.5176 |
| 2026-04-17 | BTCUSDT | 29 | 10 | 112.8457 | -21.9787 | 0.8335 | 91.7005 |
| 2026-04-17 | DOGEUSDT | 27 | 7 | -10.9114 | -8.0719 | 0.0000 | -18.9833 |
| 2026-04-17 | ETHUSDT | 11 | 8 | 87.1752 | -14.7263 | 1.0067 | 73.4556 |
| 2026-04-17 | XRPUSDT | 28 | 13 | 28.4334 | -17.3753 | 0.0000 | 11.0581 |
| 2026-04-18 | BNBUSDT | 136 | 7 | 6.0592 | -14.8202 | 0.0000 | -8.7610 |
| 2026-04-18 | BTCUSDT | 33 | 1 | 0.0000 | -1.8883 | 0.0000 | -1.8883 |
| 2026-04-18 | DOGEUSDT | 12 | 8 | 11.8934 | -7.2898 | -0.4385 | 4.1651 |
| 2026-04-18 | ETHUSDT | 23 | 5 | 2.9418 | -11.3169 | 0.0000 | -8.3751 |
| 2026-04-18 | XRPUSDT | 2 | 2 | 44.5249 | -4.7579 | 0.0000 | 39.7670 |
| 2026-04-19 | BNBUSDT | 4 | 7 | -23.9090 | -7.5792 | 0.0000 | -31.4882 |
| 2026-04-19 | BTCUSDT | 4 | 1 | 21.3204 | -3.7680 | 0.2742 | 17.8265 |
| 2026-04-19 | DOGEUSDT | 4 | 3 | -7.3429 | -3.0126 | 0.0000 | -10.3555 |
| 2026-04-19 | ETHUSDT | 17 | 7 | 111.9554 | -13.3394 | 0.1152 | 98.7312 |
| 2026-04-19 | XRPUSDT | 3 | 4 | -8.6089 | -2.6429 | 0.0000 | -11.2518 |
| 2026-04-20 | BNBUSDT | 71 | 3 | -20.1933 | -4.3650 | 0.0000 | -24.5583 |
| 2026-04-20 | BTCUSDT | 70 | 13 | 48.8215 | -27.7423 | 0.9957 | 22.0748 |
| 2026-04-20 | DOGEUSDT | 8 | 6 | -44.8750 | -5.3628 | 0.2096 | -50.0282 |
| 2026-04-20 | ETHUSDT | 63 | 11 | -119.3743 | -24.6113 | 0.8828 | -143.1027 |
| 2026-04-20 | XRPUSDT | 107 | 13 | 168.7374 | -29.5253 | 1.2305 | 140.4427 |
| 2026-04-21 | BNBUSDT | 4 | 4 | 78.3273 | -5.9355 | 0.0000 | 72.3918 |
| 2026-04-21 | BTCUSDT | 4 | 3 | -34.8263 | -6.5942 | 0.0000 | -41.4205 |
| 2026-04-21 | DOGEUSDT | 75 | 4 | -32.8663 | -3.6939 | -2.6293 | -39.1895 |
| 2026-04-21 | ETHUSDT | 13 | 9 | -40.4417 | -13.6776 | 0.4362 | -53.6830 |
| 2026-04-21 | XRPUSDT | 9 | 6 | -24.6441 | -10.6858 | 0.4351 | -34.8949 |


## Direction Summary

| symbol | direction | closed_episodes | wins | losses | win_rate | net_pnl_after_trade_fees | avg_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BNBUSDT | LONG | 89 | 75 | 14 | 0.8427 | 25.6772 | 573.66 |
| BNBUSDT | SHORT | 119 | 4 | 115 | 0.0336 | -39.6105 | 72.58 |
| BTCUSDT | LONG | 68 | 61 | 7 | 0.8971 | 162.5488 | 83.93 |
| BTCUSDT | SHORT | 65 | 51 | 14 | 0.7846 | -32.1936 | 451.80 |
| DOGEUSDT | LONG | 26 | 2 | 24 | 0.0769 | -16.3315 | 122.01 |
| DOGEUSDT | SHORT | 92 | 10 | 82 | 0.1087 | -65.8160 | 73.42 |
| ETHUSDT | LONG | 75 | 11 | 64 | 0.1467 | -29.0550 | 85.63 |
| ETHUSDT | SHORT | 54 | 33 | 21 | 0.6111 | -68.9454 | 182.31 |
| XRPUSDT | LONG | 122 | 93 | 29 | 0.7623 | -68.6891 | 86.30 |
| XRPUSDT | SHORT | 40 | 23 | 17 | 0.5750 | 124.8600 | 39.16 |


## Close Reason Summary

| symbol | close_reason_proven | close_reason_inferred | closed_episodes |
| --- | --- | --- | --- |
| BNBUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 208 |
| BTCUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 133 |
| DOGEUSDT | REDUCE_ONLY_CLOSE_MARKET | STOP_LOSS | 72 |
| DOGEUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 46 |
| ETHUSDT | REDUCE_ONLY_CLOSE_MARKET | STOP_LOSS | 4 |
| ETHUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 125 |
| XRPUSDT | REDUCE_ONLY_CLOSE_MARKET | TAKE_PROFIT | 1 |
| XRPUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 161 |


## Rating Formula

- rating = 100 * (0.35 * relative_net_income + 0.25 * win_rate + 0.15 * fill_rate + 0.15 * evidence_score + 0.10 * activity_score)
- relative_net_income is min-max normalized across observed symbols in this dataset only.
- evidence_score = 1 - close_reason_unknown_rate.
- activity_score = min(closed_episodes / 20, 1).

## Artifacts

- raw/access_proof.json
- raw/income.json
- raw/orders/*.json
- raw/orders_context_7d/*.json
- raw/trades/*.json
- raw/local_order_log_window.jsonl
- raw/local_shadow_intents_window.jsonl
- normalized/income.csv
- normalized/orders.csv
- normalized/trades.csv
- normalized/episodes.csv
- normalized/boundary_events.csv
- normalized/daily_symbol_summary.csv
- normalized/direction_summary.csv
- normalized/close_reason_summary.csv
- normalized/symbol_summary.csv
- summary.json

