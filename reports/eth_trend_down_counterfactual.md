# ETHUSDT TREND_DOWN Counterfactual Research
*Scope: offline filters on existing ETHUSDT x TREND_DOWN LONG trades and 5m processed bars*
*Source run: 20260312_010242*

---

## 1. Executive Verdict

- Best balanced candidate: F6 (anti-exhaustion-green-bounce) with March improvement 66.88 USDT and Jan+Feb winner pnl retention 79.23%.
- Entry-phase filtering still looks viable enough to test before a full TP/SL or regime redesign.
- Best raw March improvement: F6 (anti-exhaustion-green-bounce) at 66.88 USDT vs F0.
- Best Jan+Feb winner retention: F0 (baseline) at 100.00% retained positive pnl.
- Intent linkage coverage from order log: 0/103 LONG trades.

---

## 2. Baseline ETH TREND_DOWN LONG Stats

| cohort | n | total_pnl | EV/trade | WR | avg_win | avg_loss | payoff | SL count | TP count | largest_loss |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Jan+Feb | 32 | 371.98 | 11.62 | 68.75% | 56.03 | -86.07 | 0.65 | 11 | 21 | -104.50 |
| March | 71 | -154.72 | -2.18 | 59.15% | 37.66 | -59.88 | 0.63 | 29 | 42 | -135.92 |
| Q1 | 103 | 217.26 | 2.11 | 62.14% | 43.97 | -66.59 | 0.66 | 40 | 63 | -135.92 |

---

## 3. Counterfactual Filters F0..F6

| filter | cohort | n | kept_share | total_pnl | EV/trade | WR | avg_win | avg_loss | payoff | largest_loss | SL count | TP count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F0 | Jan+Feb | 32 | 100.00% | 371.98 | 11.62 | 68.75% | 56.03 | -86.07 | 0.65 | -104.50 | 11 | 21 |
| F0 | March | 71 | 100.00% | -154.72 | -2.18 | 59.15% | 37.66 | -59.88 | 0.63 | -135.92 | 29 | 42 |
| F0 | Q1 | 103 | 100.00% | 217.26 | 2.11 | 62.14% | 43.97 | -66.59 | 0.66 | -135.92 | 40 | 63 |
| F1 | Jan+Feb | 20 | 62.50% | 193.35 | 9.67 | 70.00% | 47.29 | -78.11 | 0.61 | -102.54 | 6 | 14 |
| F1 | March | 33 | 46.48% | -128.78 | -3.90 | 54.55% | 34.63 | -50.14 | 0.69 | -85.29 | 15 | 18 |
| F1 | Q1 | 53 | 51.46% | 64.58 | 1.22 | 60.38% | 40.16 | -58.13 | 0.69 | -102.54 | 21 | 32 |
| F2 | Jan+Feb | 20 | 62.50% | 193.35 | 9.67 | 70.00% | 47.29 | -78.11 | 0.61 | -102.54 | 6 | 14 |
| F2 | March | 33 | 46.48% | -128.78 | -3.90 | 54.55% | 34.63 | -50.14 | 0.69 | -85.29 | 15 | 18 |
| F2 | Q1 | 53 | 51.46% | 64.58 | 1.22 | 60.38% | 40.16 | -58.13 | 0.69 | -102.54 | 21 | 32 |
| F3 | Jan+Feb | 20 | 62.50% | 193.35 | 9.67 | 70.00% | 47.29 | -78.11 | 0.61 | -102.54 | 6 | 14 |
| F3 | March | 33 | 46.48% | -128.78 | -3.90 | 54.55% | 34.63 | -50.14 | 0.69 | -85.29 | 15 | 18 |
| F3 | Q1 | 53 | 51.46% | 64.58 | 1.22 | 60.38% | 40.16 | -58.13 | 0.69 | -102.54 | 21 | 32 |
| F4 | Jan+Feb | 20 | 62.50% | 193.35 | 9.67 | 70.00% | 47.29 | -78.11 | 0.61 | -102.54 | 6 | 14 |
| F4 | March | 33 | 46.48% | -128.78 | -3.90 | 54.55% | 34.63 | -50.14 | 0.69 | -85.29 | 15 | 18 |
| F4 | Q1 | 53 | 51.46% | 64.58 | 1.22 | 60.38% | 40.16 | -58.13 | 0.69 | -102.54 | 21 | 32 |
| F5 | Jan+Feb | 20 | 62.50% | 193.35 | 9.67 | 70.00% | 47.29 | -78.11 | 0.61 | -102.54 | 6 | 14 |
| F5 | March | 33 | 46.48% | -128.78 | -3.90 | 54.55% | 34.63 | -50.14 | 0.69 | -85.29 | 15 | 18 |
| F5 | Q1 | 53 | 51.46% | 64.58 | 1.22 | 60.38% | 40.16 | -58.13 | 0.69 | -102.54 | 21 | 32 |
| F6 | Jan+Feb | 29 | 90.62% | 314.73 | 10.85 | 72.41% | 46.51 | -82.74 | 0.56 | -103.44 | 8 | 21 |
| F6 | March | 51 | 71.83% | -87.84 | -1.72 | 58.82% | 36.65 | -56.54 | 0.65 | -135.92 | 21 | 30 |
| F6 | Q1 | 80 | 77.67% | 226.89 | 2.84 | 63.75% | 40.71 | -63.77 | 0.64 | -135.92 | 29 | 51 |

---

## 4. Best Filter Candidates

| filter | title | March improvement vs F0 | Jan+Feb winner pnl retained | Jan+Feb winner trade retained | Q1 total_pnl |
| --- | --- | --- | --- | --- | --- |
| F6 | anti-exhaustion-green-bounce | 66.88 | 79.23% | 95.45% | 226.89 |
| F1 | only-after-red-bar | 25.94 | 53.71% | 63.64% | 64.58 |
| F2 | reject-green-entry-bar | 25.94 | 53.71% | 63.64% | 64.58 |
| F3 | require-negative-delta-vs-prev-close | 25.94 | 53.71% | 63.64% | 64.58 |
| F4 | reject-positive-delta-vs-prev-close | 25.94 | 53.71% | 63.64% | 64.58 |
| F5 | combined-conservative-dip-filter | 25.94 | 53.71% | 63.64% | 64.58 |
| F0 | baseline | 0.00 | 100.00% | 100.00% | 217.26 |

---

## 5. Candidate Reading

- Best March cutter: F6 (Reject green micro-bounce LONGs where 5m delta vs previous close exceeds +0.15%).
- Least harmful to Jan+Feb winners: F0 (All ETHUSDT x TREND_DOWN LONG trades).
- Best balanced candidate: F6 (Reject green micro-bounce LONGs where 5m delta vs previous close exceeds +0.15%).

---

## 6. Is A Simple Entry-Phase Filter Enough?

A simple entry-phase filter looks promising enough for patched7 research if the balanced candidate preserves most Jan+Feb winner pnl while materially improving March.

Summary JSON written alongside this report: reports/eth_trend_down_counterfactual_summary.json

