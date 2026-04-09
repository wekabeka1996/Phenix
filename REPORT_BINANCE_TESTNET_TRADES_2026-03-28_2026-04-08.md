# REPORT_BINANCE_TESTNET_TRADES_2026-03-28_2026-04-08

Status: **PARTIAL_FAIL_CLOSED**

## Scope

- Requested local window: 2026-03-28T00:00:00+02:00 .. 2026-04-08T23:59:59.999999+03:00
- Requested UTC window: 2026-03-27T22:00:00+00:00 .. 2026-04-08T20:59:59.999000+00:00
- Effective extracted UTC end: 2026-04-08T17:16:01.044000+00:00
- Binance server time at extraction: 2026-04-08T17:16:01.044000+00:00
- Base URL: https://testnet.binancefuture.com
- Artifact directory: C:/Users/user/Music/Phenix/reports/binance_testnet_trades_2026-03-28_2026-04-08

## Facts

- Exchange access proved against Binance Futures Testnet public time endpoint and signed user endpoints.
- The requested local timezone was handled via Europe/Zaporozhye, including the DST change inside the requested interval.
- The requested right boundary extends beyond current Binance server time, so the requested interval is only partially observable right now.
- Absolute left-boundary position state cannot be exchange-proved for this account because /fapi/v1/userTrades rejects intervals longer than 7 days with code -4165.
- Config symbols: 1000PEPEUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT
- Local runtime symbols in effective window: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT, _SYSTEM_
- Exchange income symbols in effective window: BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT
- Candidate symbols rejected by current testnet exchangeInfo: _SYSTEM_
- Final fetched symbol set: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT

## Inferences

- Position episodes were reconstructed by FIFO pairing of non-reduceOnly opening fills to subsequent reducing fills inside the effective window.
- close_reason_inferred uses planned strategy stop/target levels from shadow intents only when the exit price is within 0.2500% relative tolerance of the planned level; otherwise it remains UNKNOWN.

## Assumptions

- None for exchange-proof statements. All non-exchange lifecycle pairing is explicitly represented as inference, not fact.

## Unknowns

- Absolute account position at the exact requested left boundary is UNKNOWN at exchange-proof level because older than 7-day userTrades history is unavailable from the endpoint.
- The missing right-edge slice remains UNKNOWN until Binance server time passes the requested end boundary and the extraction is rerun.

## Validation

| check | value |
| --- | --- |
| base_url_is_testnet | True |
| right_boundary_truncated | True |
| left_boundary_exchange_truth | UNKNOWN: /fapi/v1/userTrades max interval is 7 days (-4165) |
| income_rows | 1729 |
| trade_rows | 1402 |
| order_rows | 388 |
| commission_reconciliation_delta | 1.47503840 |
| realized_pnl_reconciliation_delta | 0.00000000 |
| missing_trade_order_count | 0 |
| boundary_close_only_events | 5 |


## Symbol Summary

| symbol | trade_fills | orders_total | income_net | closed_episodes | win_rate | fill_rate | close_unknown_rate | rating |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTCUSDT | 244 | 88 | -104.6207 | 205 | 0.1707 | 0.8750 | 0.9854 | 57.25 |
| DOGEUSDT | 129 | 88 | -332.9383 | 85 | 0.4118 | 1.0000 | 0.9765 | 56.52 |
| BNBUSDT | 1 | 1 | 35.1112 | 0 | n/a | 1.0000 | n/a | 50.00 |
| ETHUSDT | 311 | 99 | -480.2753 | 268 | 0.1567 | 0.8586 | 0.9963 | 42.07 |
| SOLUSDT | 717 | 112 | -876.7533 | 669 | 0.3737 | 0.8125 | 1.0000 | 31.53 |
| 1000PEPEUSDT | 0 | 0 | 0.0000 | 0 | n/a | n/a | n/a | n/a |
| XRPUSDT | 0 | 0 | 0.0000 | 0 | n/a | n/a | n/a | n/a |


## Daily Summary

| local_date | symbol | trade_fills | orders_total | realized_pnl | commission | funding_fee | income_net |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-28 | BNBUSDT | 1 | 1 | 39.1243 | -4.0131 | 0.0000 | 35.1112 |
| 2026-03-28 | BTCUSDT | 6 | 7 | -97.4651 | -16.3495 | 0.1336 | -113.6810 |
| 2026-03-28 | DOGEUSDT | 32 | 18 | -110.1927 | -72.0541 | 0.0000 | -182.2468 |
| 2026-03-28 | ETHUSDT | 3 | 3 | -31.0129 | -10.0119 | 0.3618 | -40.6631 |
| 2026-03-28 | SOLUSDT | 5 | 3 | -126.7200 | -9.8842 | 0.2953 | -136.3088 |
| 2026-03-29 | BTCUSDT | 2 | 1 | 52.1858 | -3.9691 | 2.4875 | 50.7042 |
| 2026-03-29 | DOGEUSDT | 2 | 2 | -39.1928 | -7.9779 | 0.0000 | -47.1708 |
| 2026-03-29 | SOLUSDT | 4 | 2 | 64.8000 | -5.8874 | 0.9889 | 59.9014 |
| 2026-03-30 | BTCUSDT | 71 | 14 | 8.0883 | -26.2266 | 0.6042 | -17.5341 |
| 2026-03-30 | ETHUSDT | 12 | 8 | -166.1937 | -18.0658 | -0.8225 | -185.0820 |
| 2026-03-30 | SOLUSDT | 0 | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| 2026-03-31 | BTCUSDT | 8 | 8 | 89.7051 | -22.5589 | 0.6657 | 67.8119 |
| 2026-03-31 | DOGEUSDT | 25 | 18 | -29.2571 | -69.5401 | 0.3109 | -98.4863 |
| 2026-03-31 | ETHUSDT | 7 | 5 | 104.6238 | -13.9576 | 0.9793 | 91.6455 |
| 2026-03-31 | SOLUSDT | 4 | 4 | -334.9000 | -11.6305 | -0.2122 | -346.7427 |
| 2026-04-01 | BTCUSDT | 35 | 6 | -16.4630 | -17.9412 | 0.2995 | -34.1047 |
| 2026-04-01 | ETHUSDT | 3 | 4 | 115.9263 | -9.9532 | 0.1491 | 106.1222 |
| 2026-04-01 | SOLUSDT | 29 | 4 | -117.7100 | -10.6630 | -0.3560 | -128.7290 |
| 2026-04-02 | BTCUSDT | 25 | 8 | 39.2721 | -20.4704 | 0.9966 | 19.7984 |
| 2026-04-02 | DOGEUSDT | 29 | 22 | 121.6269 | -78.2244 | -0.7984 | 42.6041 |
| 2026-04-02 | ETHUSDT | 33 | 22 | -8.1380 | -54.0012 | 0.0393 | -62.0998 |
| 2026-04-02 | SOLUSDT | 151 | 37 | -51.6703 | -74.8657 | -0.8960 | -127.4320 |
| 2026-04-03 | BTCUSDT | 28 | 7 | -35.7055 | -13.3956 | 0.1320 | -48.9691 |
| 2026-04-03 | DOGEUSDT | 26 | 14 | 41.5233 | -48.0091 | 0.0000 | -6.4858 |
| 2026-04-03 | ETHUSDT | 140 | 25 | -44.8106 | -66.0191 | 0.0000 | -110.8297 |
| 2026-04-03 | SOLUSDT | 77 | 13 | 36.9000 | -25.0686 | 0.0000 | 11.8314 |
| 2026-04-04 | BTCUSDT | 10 | 5 | -31.4868 | -10.4488 | 0.5754 | -41.3602 |
| 2026-04-04 | DOGEUSDT | 6 | 6 | -10.6548 | -19.6577 | 0.0000 | -30.3125 |
| 2026-04-04 | ETHUSDT | 72 | 4 | -3.3654 | -12.0047 | 0.0000 | -15.3701 |
| 2026-04-04 | SOLUSDT | 55 | 7 | -20.2700 | -11.7977 | 0.0000 | -32.0677 |
| 2026-04-05 | BTCUSDT | 2 | 2 | -6.1938 | -3.7608 | -1.0600 | -11.0146 |
| 2026-04-05 | ETHUSDT | 1 | 2 | 0.0000 | -2.0001 | 0.0000 | -2.0001 |
| 2026-04-05 | SOLUSDT | 19 | 5 | -63.9000 | -4.9607 | 0.0000 | -68.8607 |
| 2026-04-06 | BTCUSDT | 9 | 7 | 43.0999 | -11.9645 | 0.0000 | 31.1354 |
| 2026-04-06 | DOGEUSDT | 4 | 4 | 34.0594 | -12.6208 | 0.0000 | 21.4387 |
| 2026-04-06 | ETHUSDT | 13 | 6 | -12.5599 | -18.0043 | -0.0524 | -30.6166 |
| 2026-04-06 | SOLUSDT | 201 | 18 | -111.7093 | -24.5388 | -0.6990 | -136.9472 |
| 2026-04-07 | BTCUSDT | 41 | 17 | 56.3307 | -30.2611 | 0.6242 | 26.6938 |
| 2026-04-07 | DOGEUSDT | 2 | 2 | -11.2537 | -6.2699 | 0.0000 | -17.5236 |
| 2026-04-07 | ETHUSDT | 23 | 15 | -62.0272 | -40.0218 | 1.3100 | -100.7390 |
| 2026-04-07 | SOLUSDT | 149 | 11 | 65.7128 | -20.8179 | 0.0000 | 44.8949 |
| 2026-04-08 | BTCUSDT | 7 | 6 | -21.2427 | -12.8581 | 0.0000 | -34.1008 |
| 2026-04-08 | DOGEUSDT | 3 | 2 | -9.0365 | -5.7189 | 0.0000 | -14.7554 |
| 2026-04-08 | ETHUSDT | 4 | 5 | -118.5894 | -12.0532 | 0.0000 | -130.6426 |
| 2026-04-08 | SOLUSDT | 23 | 7 | -4.1500 | -12.7927 | 0.6498 | -16.2930 |


## Direction Summary

| symbol | direction | closed_episodes | wins | losses | win_rate | net_pnl_after_trade_fees | avg_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BTCUSDT | SHORT | 205 | 35 | 170 | 0.1707 | -66.8342 | 229.60 |
| DOGEUSDT | LONG | 21 | 8 | 13 | 0.3810 | -71.9415 | 37.51 |
| DOGEUSDT | SHORT | 64 | 27 | 37 | 0.4219 | -260.5094 | 37.47 |
| ETHUSDT | SHORT | 268 | 42 | 226 | 0.1567 | -387.2574 | 136.33 |
| SOLUSDT | LONG | 6 | 0 | 6 | 0.0000 | -99.8346 | 43.76 |
| SOLUSDT | SHORT | 663 | 250 | 413 | 0.3771 | -620.3938 | 32.24 |


## Close Reason Summary

| symbol | close_reason_proven | close_reason_inferred | closed_episodes |
| --- | --- | --- | --- |
| BTCUSDT | REDUCE_ONLY_CLOSE_MARKET | STOP_LOSS | 3 |
| BTCUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 202 |
| DOGEUSDT | REDUCE_ONLY_CLOSE_MARKET | STOP_LOSS | 2 |
| DOGEUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 83 |
| ETHUSDT | REDUCE_ONLY_CLOSE_MARKET | STOP_LOSS | 1 |
| ETHUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 267 |
| SOLUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 669 |


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

