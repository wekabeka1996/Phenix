# Testnet Transactions — Summary

Input: `reports/testnet_transactions_30d.md`

Input generated: `2026-02-16 09:22:42 UTC`

Base URL: `https://testnet.binancefuture.com`

Range: `2026-01-17 07:22:36 UTC` → `2026-02-16 07:22:36 UTC`

Observed time coverage: `2026-01-17 07:55:02 UTC` → `2026-02-16 05:12:49 UTC`

## Totals

- Income rows: **4**, total: **0.37392683**

- Trade rows: **225**

- Realized PnL (sum): **19.9287**

- Commission (sum): **12.32351108**

- Net (realized - commission): **7.60518892**


## Win Rate & PnL Split (realizedPnl)

- `Flat` = trade with `realizedPnl == 0` (break-even by realized PnL; commission may still make net negative).

- Wins: **33**, Losses: **28**, Flats: **164**

- Win rate (excluding flats): **54.10%**

- Win rate (all trades): **14.67%**

- Gross profit (sum of positive realizedPnl): **60.7281**

- Gross loss (sum of negative realizedPnl): **-40.7994**

- Gross loss (abs): **40.7994**

- Profit factor (gross_profit / abs(gross_loss)): **1.4885**

- Avg win: **1.84024545**, Avg loss: **-1.45712143**


## Net After Commission (USDT)

- Wins: **32**, Losses: **193**, Flats: **0**

- Win rate (excluding flats): **14.22%**


## Profitability By Symbol

| symbol | trades | realized_sum | commission_sum | net_sum | gross_profit | gross_loss_abs |
| --- | --- | --- | --- | --- | --- | --- |
| SOLUSDT | 225 | 19.9287 | 12.32351108 | 7.60518892 | 60.7281 | 40.7994 |


Best symbol: **SOLUSDT**

Worst symbol: **SOLUSDT**


## Profitability By UTC Hour

| hour(UTC) | trades | realized_sum | commission_sum | net_sum | W/L/F | win_rate(excl F) |
| --- | --- | --- | --- | --- | --- | --- |
| 00:00 | 2 | -2.24 | 0.19364 | -2.43364 | 0/1/1 | 0.00% |
| 01:00 | 2 | 1.74 | 0.10293599 | 1.63706401 | 1/0/1 | 100.00% |
| 02:00 | 5 | -2.1923 | 0.67097491 | -2.86327491 | 0/2/3 | 0.00% |
| 03:00 | 11 | 0 | 0.197952 | -0.197952 | 0/0/11 | 0.00% |
| 04:00 | 8 | 2.3 | 0.61527 | 1.68473 | 2/0/6 | 100.00% |
| 05:00 | 4 | 3.99 | 0.824574 | 3.165426 | 2/0/2 | 100.00% |
| 06:00 | 15 | -0.46 | 1.14933 | -1.60933 | 2/3/10 | 40.00% |
| 07:00 | 13 | 8.138 | 1.90953022 | 6.22846978 | 7/0/6 | 100.00% |
| 08:00 | 4 | 4.25 | 0.86866 | 3.38134 | 3/0/1 | 100.00% |
| 09:00 | 1 | 0 | 0.07964 | -0.07964 | 0/0/1 | 0.00% |
| 10:00 | 5 | -0.19 | 0.263154 | -0.453154 | 0/1/4 | 0.00% |
| 11:00 | 4 | -0.24 | 0.161178 | -0.401178 | 0/2/2 | 0.00% |
| 12:00 | 3 | 0 | 0.138724 | -0.138724 | 0/0/3 | 0.00% |
| 13:00 | 2 | 3.57 | 0.27846 | 3.29154 | 2/0/0 | 100.00% |
| 14:00 | 5 | -8.8 | 0.24422 | -9.04422 | 0/1/4 | 0.00% |
| 15:00 | 3 | 3.4578 | 0.21008687 | 3.24771313 | 2/0/1 | 100.00% |
| 16:00 | 8 | -1.43 | 0.44052598 | -1.87052598 | 1/1/6 | 50.00% |
| 17:00 | 9 | -5.94 | 1.04778999 | -6.98778999 | 0/3/6 | 0.00% |
| 18:00 | 50 | -1.8 | 0.64082799 | -2.44082799 | 2/1/47 | 66.67% |
| 19:00 | 8 | 16.85 | 0.874012 | 15.975988 | 4/1/3 | 80.00% |
| 20:00 | 2 | 0 | 0.07716 | -0.07716 | 0/0/2 | 0.00% |
| 21:00 | 33 | 0.6243 | 0.49100445 | 0.13329555 | 1/4/28 | 20.00% |
| 22:00 | 21 | 0.9445 | 0.58485124 | 0.35964876 | 3/2/16 | 60.00% |
| 23:00 | 7 | -2.6436 | 0.25900944 | -2.90260944 | 1/6/0 | 14.29% |


Best UTC hour (net): **19:00**

Worst UTC hour (net): **14:00**


## Income Breakdown

| incomeType | sum | count |
| --- | --- | --- |
| FUNDING_FEE | 0.37392683 | 4 |


## Income By Symbol

| symbol | sum |
| --- | --- |
| XRPUSDT | 0.35222898 |
| BTCUSDT | 0.05041093 |
| SOLUSDT | -0.02871308 |


## Trades Breakdown

| symbol | count |
| --- | --- |
| SOLUSDT | 225 |



| side | count |
| --- | --- |
| BUY | 129 |
| SELL | 96 |


## Sanity Checks

- Duplicate income tranIds: **0**

- Duplicate tradeIds: **0**

- Commission assets observed: `USDT`
