# ACCEPTED_CLOSED_TRADE_ECONOMICS_DEEPDIVE

## Overall

| Metric | Value | Notes |
| --- | --- | --- |
| trade_count | 12 | canonical realized rows only |
| exact_roundtrip_count | 11 | canonical realized rows only |
| gross_pnl | 171.06727 | sum gross pnl |
| net_pnl | 139.184041 | sum realized pnl net |
| fees | 31.883229 | fees + commission |
| fees_over_gross_profit_abs | 16.089237 | percent |
| fees_over_abs_net_pnl | 22.907245 | percent when denominator valid |
| win_rate | 75 | net pnl > 0 |
| profit_factor | 4.666288 | sum wins / abs(sum losses) |
| median_pnl | 10.315075 | median net pnl |
| mean_pnl | 11.59867 | mean net pnl |

## By Symbol

| Symbol | Trades | Net PnL | Fees | Win Rate | Profit Factor |
| --- | --- | --- | --- | --- | --- |
| BNBUSDT | 5 | 55.791206 | 14.385294 | 60 | 6.522614 |
| BTCUSDT | 4 | 75.191689 | 9.888031 | 100 |  |
| ETHUSDT | 1 | 12.119093 | 2.561967 | 100 |  |
| XRPUSDT | 2 | -3.917947 | 5.047937 | 50 | 0.859375 |

## By Close Reason

| Close Reason | Trades | Net PnL | Fees | Win Rate | Profit Factor |
| --- | --- | --- | --- | --- | --- |
| CLOSE | 2 | -10.102319 | 7.489119 | 0 | 0 |
| SL | 1 | -27.86089 | 3.37641 | 0 | 0 |
| TP | 9 | 177.14725 | 21.0177 | 100 |  |

## Fee Drag

| Metric | Value | Notes |
| --- | --- | --- |
| total_fees | 31.883229 | canonical cohort only |
| fees_per_trade | 2.656936 | mean fees per canonical trade |
| fees_as_pct_of_total_gross_profit | 16.089237 | percent |
| fees_as_pct_of_losing_trade_abs_net | 28.621208 | percent |
| gross_positive_but_net_negative_count | 0 | strict fee drag rows |
| fee_dominated_count | 2 | fees >= abs(gross pnl) |
| near_fee_only_count | 0 | fees/abs(gross pnl) >= 0.8 |
