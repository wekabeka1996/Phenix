# REPORT_BINANCE_TESTNET_TRADES_2026-05-13_2026-05-24

Status: **PARTIAL_FAIL_CLOSED**

## Scope

- Requested local window: 2026-05-13T00:00:00+03:00 .. 2026-05-24T23:59:59.999999+03:00
- Requested UTC window: 2026-05-12T21:00:00+00:00 .. 2026-05-24T20:59:59.999000+00:00
- Effective extracted UTC end: 2026-05-24T15:04:07.668000+00:00
- Binance server time at extraction: 2026-05-24T15:04:07.668000+00:00
- Base URL: https://testnet.binancefuture.com
- Artifact directory: C:/Users/wekab/Music/Phenix/reports/binance_testnet_trades_2026-05-13_2026-05-24

## Facts

- Exchange access proved against Binance Futures Testnet public time endpoint and signed user endpoints.
- The requested local timezone was handled via Europe/Zaporozhye, including the DST change inside the requested interval.
- The requested right boundary extends beyond current Binance server time, so the requested interval is only partially observable right now.
- Absolute left-boundary position state cannot be exchange-proved for this account because /fapi/v1/userTrades rejects intervals longer than 7 days with code -4165.
- Config symbols: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT
- Local runtime symbols in effective window: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT, _SYSTEM_
- Exchange income symbols in effective window: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT
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
- 440 reconstructed episode(s) lack provable local intent attribution, so strategy-level blame remains incomplete for symbols: BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT.

## Validation

| check | value |
| --- | --- |
| base_url_is_testnet | True |
| right_boundary_truncated | True |
| left_boundary_exchange_truth | UNKNOWN: /fapi/v1/userTrades max interval is 7 days (-4165) |
| income_rows | 1839 |
| trade_rows | 1749 |
| order_rows | 115 |
| commission_reconciliation_delta | 0.00100747 |
| realized_pnl_reconciliation_delta | 0.00000000 |
| missing_trade_order_count | 0 |
| unattributed_episode_count | 440 |
| unattributed_closed_episode_count | 440 |
| unattributed_closed_episode_net_pnl | -597.93638126 |
| boundary_close_only_events | 0 |


## Symbol Summary

| symbol | trade_fills | orders_total | income_net | closed_episodes | win_rate | fill_rate | close_unknown_rate | rating |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SOLUSDT | 59 | 9 | 66.4363 | 55 | 0.8909 | 0.6667 | 1.0000 | 77.27 |
| BNBUSDT | 203 | 12 | -106.0498 | 199 | 0.9849 | 0.7500 | 1.0000 | 64.20 |
| ETHUSDT | 125 | 18 | -16.5512 | 117 | 0.0598 | 0.8889 | 1.0000 | 51.81 |
| 1000PEPEUSDT | 1249 | 26 | -191.7976 | 1221 | 0.1368 | 0.7308 | 0.0254 | 49.04 |
| BTCUSDT | 21 | 12 | -166.6295 | 15 | 0.2667 | 1.0000 | 0.9333 | 42.64 |
| XRPUSDT | 64 | 14 | -252.7445 | 57 | 0.1053 | 1.0000 | 0.8772 | 33.63 |
| DOGEUSDT | 28 | 24 | -295.7259 | 16 | 0.1250 | 1.0000 | 1.0000 | 26.12 |


## Daily Summary

| local_date | symbol | trade_fills | orders_total | realized_pnl | commission | funding_fee | income_net |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-13 | ETHUSDT | 85 | 3 | -46.0191 | -6.0177 | 0.0000 | -52.0368 |
| 2026-05-13 | SOLUSDT | 1 | 1 | 0.0000 | -1.9941 | 0.0000 | -1.9941 |
| 2026-05-14 | BNBUSDT | 180 | 3 | 29.4545 | -5.9846 | 0.0000 | 23.4699 |
| 2026-05-14 | BTCUSDT | 5 | 4 | -71.5860 | -10.5498 | 0.0000 | -82.1358 |
| 2026-05-14 | DOGEUSDT | 13 | 12 | 7.5343 | -25.5908 | 0.5130 | -17.5435 |
| 2026-05-14 | ETHUSDT | 24 | 6 | -105.7733 | -14.9190 | 1.0013 | -119.6911 |
| 2026-05-14 | SOLUSDT | 6 | 1 | -72.6000 | -4.0172 | 1.0023 | -75.6149 |
| 2026-05-14 | XRPUSDT | 47 | 6 | 17.2182 | -18.0350 | 0.0000 | -0.8168 |
| 2026-05-15 | BTCUSDT | 7 | 2 | -32.2812 | -6.0001 | 0.9969 | -37.2843 |
| 2026-05-15 | DOGEUSDT | 4 | 4 | -115.5213 | -8.1712 | 0.0000 | -123.6925 |
| 2026-05-15 | ETHUSDT | 13 | 6 | 57.5647 | -13.9776 | 2.0046 | 45.5918 |
| 2026-05-16 | BNBUSDT | 21 | 7 | -71.5137 | -11.8120 | 0.0000 | -83.3257 |
| 2026-05-16 | DOGEUSDT | 11 | 8 | -138.7529 | -15.7369 | 0.0000 | -154.4898 |
| 2026-05-16 | ETHUSDT | 3 | 3 | 118.5475 | -9.9627 | 1.0002 | 109.5850 |
| 2026-05-16 | SOLUSDT | 52 | 7 | 154.9100 | -11.8394 | 0.9747 | 144.0453 |
| 2026-05-17 | BNBUSDT | 2 | 2 | -40.2127 | -5.9814 | 0.0000 | -46.1941 |
| 2026-05-18 | BTCUSDT | 2 | 2 | -38.8244 | -4.6848 | 0.7781 | -42.7311 |
| 2026-05-18 | XRPUSDT | 8 | 5 | -224.8777 | -13.6226 | -0.9690 | -239.4693 |
| 2026-05-19 | XRPUSDT | 8 | 2 | 118.5079 | -5.6979 | -0.2190 | 112.5910 |
| 2026-05-20 | XRPUSDT | 0 | 0 | 0.0000 | 0.0000 | -0.8463 | -0.8463 |
| 2026-05-21 | 1000PEPEUSDT | 1062 | 8 | -38.3326 | -21.2801 | 1.9389 | -57.6739 |
| 2026-05-21 | BTCUSDT | 7 | 4 | 7.4520 | -11.9302 | 0.0000 | -4.4782 |
| 2026-05-21 | XRPUSDT | 0 | 0 | 0.0000 | 0.0000 | -2.5313 | -2.5313 |
| 2026-05-22 | 1000PEPEUSDT | 152 | 8 | -75.7514 | -16.2890 | -0.9656 | -93.0059 |
| 2026-05-22 | XRPUSDT | 1 | 1 | -117.1722 | -3.7863 | -0.7133 | -121.6718 |
| 2026-05-23 | 1000PEPEUSDT | 16 | 9 | -26.4125 | -14.5893 | 0.7715 | -40.2303 |
| 2026-05-24 | 1000PEPEUSDT | 19 | 1 | 0.0000 | -0.8874 | 0.0000 | -0.8874 |


## Direction Summary

| symbol | direction | closed_episodes | wins | losses | win_rate | net_pnl_after_trade_fees | avg_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1000PEPEUSDT | LONG | 1035 | 1 | 1034 | 0.0010 | -115.0212 | 1171.30 |
| 1000PEPEUSDT | SHORT | 186 | 166 | 20 | 0.8925 | -77.6347 | 219.26 |
| BNBUSDT | LONG | 20 | 17 | 3 | 0.8500 | -129.5198 | 84.41 |
| BNBUSDT | SHORT | 179 | 179 | 0 | 1.0000 | 23.4699 | 254.45 |
| BTCUSDT | LONG | 4 | 0 | 4 | 0.0000 | -100.7625 | 36.53 |
| BTCUSDT | SHORT | 11 | 4 | 7 | 0.3636 | -67.6420 | 288.02 |
| DOGEUSDT | LONG | 13 | 1 | 12 | 0.0769 | -276.5172 | 64.31 |
| DOGEUSDT | SHORT | 3 | 1 | 2 | 0.3333 | -19.7217 | 33.12 |
| ETHUSDT | SHORT | 117 | 7 | 110 | 0.0598 | -20.5573 | 134.33 |
| SOLUSDT | SHORT | 55 | 49 | 6 | 0.8909 | 64.4593 | 54.45 |
| XRPUSDT | LONG | 14 | 5 | 9 | 0.3571 | -201.4647 | 2375.60 |
| XRPUSDT | SHORT | 43 | 1 | 42 | 0.0233 | -46.0010 | 89.59 |


## Close Reason Summary

| symbol | close_reason_proven | close_reason_inferred | closed_episodes |
| --- | --- | --- | --- |
| 1000PEPEUSDT | REDUCE_ONLY_CLOSE_MARKET | STOP_LOSS | 1054 |
| 1000PEPEUSDT | REDUCE_ONLY_CLOSE_MARKET | TAKE_PROFIT | 136 |
| 1000PEPEUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 31 |
| BNBUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 199 |
| BTCUSDT | REDUCE_ONLY_CLOSE_MARKET | STOP_LOSS | 1 |
| BTCUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 14 |
| DOGEUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 16 |
| ETHUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 117 |
| SOLUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 55 |
| XRPUSDT | REDUCE_ONLY_CLOSE_MARKET | STOP_LOSS | 7 |
| XRPUSDT | REDUCE_ONLY_CLOSE_MARKET | UNKNOWN | 50 |


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

