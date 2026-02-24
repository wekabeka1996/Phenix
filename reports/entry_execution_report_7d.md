# Entry/Execution (7d)
Source: `reports/testnet_transactions_7d_detailed.md`
Range: `2026-02-16 06:04:55 UTC` -> `2026-02-23 06:04:55 UTC`

Definitions:
- `ENTRY_PLACED`: entry orders (`clientOrderId` starts with `ENTRY-`).
- `ENTRY_FILLED`: entry orders with `executedQty > 0` (includes partial fills later canceled).
- `AVG_PL->RES_s`: placement -> first fill (from `userTrades`) if filled, else placement -> cancel (from order `update_time`).
- `QUICK_EXITS`: closed trades with `duration < 120s` and `realized_pnl <= 0` (from `userTrades`).
- `FLIPS`: close + immediate open opposite within 30s (ACCOUNT_UPDATE-based from `ops/wal`).

```text
========================================================================================
Entry/Execution report | window: 2026-02-16 06:04:55Z -> 2026-02-23 06:04:55Z
========================================================================================
+------------+------------+------------+----------+------------------+--------------+----------+
|   SYMBOL   |ENTRY_PLACED|ENTRY_FILLED|  FILL-%  |  AVG_PL->RES_s   | QUICK_EXITS  |  FLIPS   |
+------------+------------+------------+----------+------------------+--------------+----------+
|  BTCUSDT   |    106     |     46     |  43.4%   |      41.8s       |      0       |    0     |
|  DOGEUSDT  |     52     |     52     |  100.0%  |       0.0s       |      1       |    0     |
|  SOLUSDT   |    110     |     47     |  42.7%   |      41.0s       |      0       |    0     |
|  XRPUSDT   |     29     |     29     |  100.0%  |       0.0s       |      1       |    0     |
+------------+------------+------------+----------+------------------+--------------+----------+
|   TOTAL    |    297     |    174     |  58.6%   |      30.1s       |      2       |    0     |
+------------+------------+------------+----------+------------------+--------------+----------+

System-wide fill-rate (real): 58.6%
========================================================================================
```
