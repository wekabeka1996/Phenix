# Testnet Transactions — Summary

Input: `reports/testnet_transactions_7d.md`

Input generated: `2026-02-16 09:28:12 UTC`

Base URL: `https://testnet.binancefuture.com`

Range: `2026-02-09 07:28:08 UTC` → `2026-02-16 07:28:08 UTC`

Observed time coverage: `2026-02-09 23:05:04 UTC` → `2026-02-16 05:35:05 UTC`

## Totals

- Income rows: **3**, total: **0.40263991**

- Trade rows: **478**

- Realized PnL (sum): **45.24640995**

- Commission (sum): **38.14298849**

- Net (realized - commission): **7.10342146**


## Win Rate & PnL Split (realizedPnl)

- `Flat` = trade with `realizedPnl == 0` (break-even by realized PnL; commission may still make net negative).

- Wins: **112**, Losses: **79**, Flats: **287**

- Win rate (excluding flats): **58.64%**

- Win rate (all trades): **23.43%**

- Gross profit (sum of positive realizedPnl): **173.61020992**

- Gross loss (sum of negative realizedPnl): **-128.36379997**

- Gross loss (abs): **128.36379997**

- Profit factor (gross_profit / abs(gross_loss)): **1.3525**

- Avg win: **1.55009116**, Avg loss: **-1.62485823**


## Net After Commission (USDT)

- Wins: **111**, Losses: **367**, Flats: **0**

- Win rate (excluding flats): **23.22%**


## Profitability By Symbol

| symbol | trades | realized_sum | commission_sum | net_sum | gross_profit | gross_loss_abs |
| --- | --- | --- | --- | --- | --- | --- |
| SOLUSDT | 216 | 18.7687 | 11.63249908 | 7.13620092 | 59.1881 | 40.4194 |
| DOGEUSDT | 123 | 21.13846998 | 15.62125918 | 5.5172108 | 74.94190998 | 53.80344 |
| XRPUSDT | 82 | 7.62703997 | 6.68248649 | 0.94455348 | 25.18829994 | 17.56125997 |
| BTCUSDT | 57 | -2.2878 | 4.20674374 | -6.49454374 | 14.2919 | 16.5797 |


Best symbol: **SOLUSDT**

Worst symbol: **BTCUSDT**


## Profitability By UTC Hour

| hour(UTC) | trades | realized_sum | commission_sum | net_sum | W/L/F | win_rate(excl F) |
| --- | --- | --- | --- | --- | --- | --- |
| 00:00 | 7 | -5.64586 | 0.86697919 | -6.51283919 | 0/3/4 | 0.00% |
| 01:00 | 3 | 1.74 | 0.25175437 | 1.48824563 | 1/0/2 | 100.00% |
| 02:00 | 13 | 4.38592 | 1.58954353 | 2.79637647 | 3/3/7 | 50.00% |
| 03:00 | 22 | -4.13708 | 1.75483718 | -5.89191718 | 1/4/17 | 20.00% |
| 04:00 | 16 | 3.1167 | 1.49998169 | 1.61671831 | 6/2/8 | 75.00% |
| 05:00 | 18 | 14.54352 | 1.9991073 | 12.5444127 | 9/1/8 | 90.00% |
| 06:00 | 33 | 4.22506998 | 2.968797 | 1.25627298 | 8/4/21 | 66.67% |
| 07:00 | 25 | 9.23462 | 3.72943025 | 5.50518975 | 9/4/12 | 69.23% |
| 08:00 | 15 | 6.05811 | 1.83552658 | 4.22258342 | 7/3/5 | 70.00% |
| 09:00 | 6 | 2.39768 | 0.45702349 | 1.94065651 | 3/1/2 | 75.00% |
| 10:00 | 10 | -2.84881 | 1.04820297 | -3.89701297 | 0/2/8 | 0.00% |
| 11:00 | 5 | 2.19788 | 0.31016139 | 1.88771861 | 1/2/2 | 33.33% |
| 12:00 | 13 | -3.71386 | 1.45560601 | -5.16946601 | 1/3/9 | 25.00% |
| 13:00 | 22 | 7.36487998 | 1.62288136 | 5.74199862 | 8/4/10 | 66.67% |
| 14:00 | 20 | -6.63497999 | 1.82441294 | -8.45939293 | 5/4/11 | 55.56% |
| 15:00 | 17 | 7.20698 | 1.04284615 | 6.16413385 | 12/1/4 | 92.31% |
| 16:00 | 19 | -3.28688 | 1.62987134 | -4.91675134 | 7/3/9 | 70.00% |
| 17:00 | 13 | -5.4286 | 1.65563876 | -7.08423876 | 1/4/8 | 20.00% |
| 18:00 | 56 | -9.57726 | 1.28231444 | -10.85957444 | 2/3/51 | 40.00% |
| 19:00 | 18 | 10.15197 | 1.93227641 | 8.21969359 | 5/4/9 | 55.56% |
| 20:00 | 10 | 8.09221999 | 0.98615902 | 7.10606097 | 4/0/6 | 100.00% |
| 21:00 | 48 | 0.66931999 | 1.96865061 | -1.29933062 | 5/6/37 | 45.45% |
| 22:00 | 40 | 2.06091001 | 2.16261566 | -0.10170565 | 8/9/23 | 47.06% |
| 23:00 | 29 | 3.07395999 | 2.26837085 | 0.80558914 | 6/9/14 | 40.00% |


Best UTC hour (net): **05:00**

Worst UTC hour (net): **18:00**


## Income Breakdown

| incomeType | sum | count |
| --- | --- | --- |
| FUNDING_FEE | 0.40263991 | 3 |


## Income By Symbol

| symbol | sum |
| --- | --- |
| XRPUSDT | 0.35222898 |
| BTCUSDT | 0.05041093 |


## Trades Breakdown

| symbol | count |
| --- | --- |
| SOLUSDT | 216 |
| DOGEUSDT | 123 |
| XRPUSDT | 82 |
| BTCUSDT | 57 |



| side | count |
| --- | --- |
| BUY | 261 |
| SELL | 217 |


## Sanity Checks

- Duplicate income tranIds: **0**

- Duplicate tradeIds: **0**

- Commission assets observed: `USDT`
