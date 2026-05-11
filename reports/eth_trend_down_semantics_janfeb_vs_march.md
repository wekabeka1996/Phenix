# ETHUSDT TREND_DOWN Semantics Research
*Comparison: Jan+Feb 2024 winners vs March 2024 losers*
*Run source: 20260312_010242*
*Method: close-month cohorting, 5m entry-bar context from processed ETH dataset*

---

## 1. Research Question

Before patched7, clarify what ETHUSDT x TREND_DOWN is doing in practice:

- continuation-following;
- or dip-buying inside a downtrend.

The narrow comparison requested was:

- Jan+Feb winners;
- versus March losers;

across:

- side mix;
- entry timing;
- 5m bar range;
- delta to previous bar;
- 14-16 March cluster;
- holding time;
- SL size buckets.

---

## 2. Cohort Definition

For consistency with the earlier post-mortem, cohorts are grouped by **trade close month**.

Compared cohorts:

| Cohort | Definition | Count |
|---|---|---:|
| Jan+Feb winners | ETHUSDT x TREND_DOWN, close month in Jan/Feb, pnl_net > 0 | 25 |
| March losers | ETHUSDT x TREND_DOWN, close month in Mar, pnl_net <= 0 | 31 |
| March 14-16 losers | subset of March losers closing on 14/15/16 Mar | 9 |

Entry-bar context is taken from:

- data/processed/ETHUSDT/5m/2024-01_enriched.parquet
- data/processed/ETHUSDT/5m/2024-02_enriched.parquet
- data/processed/ETHUSDT/5m/2024-03_enriched.parquet

---

## 3. High-Level Comparison

| Metric | Jan+Feb winners | March losers | March 14-16 losers |
|---|---:|---:|---:|
| LONG count | 22/25 = 88.0% | 29/31 = 93.5% | 8/9 = 88.9% |
| SHORT count | 3/25 = 12.0% | 2/31 = 6.5% | 1/9 = 11.1% |
| avg hold | 187.0 min | 62.7 min | 82.8 min |
| median hold | 115.0 min | 45.0 min | 60.0 min |
| <=30m share | 20.0% | 48.4% | 33.3% |
| avg 5m bar range | 0.576% | 0.493% | 0.420% |
| avg delta vs previous close | +0.070% | -0.027% | +0.156% |
| avg bar body | +0.071% | -0.027% | +0.156% |

Immediate reading:

- both good and bad cohorts are dominated by LONGs;
- March losers are much faster failures than Jan+Feb winners;
- 14-16 March losses are not coming from unusually wide bars;
- the distinguishing feature is not bar volatility alone.

---

## 4. Semantics Test: Continuation Or Dip-Buying

The strongest semantic clue is where entries are placed relative to the current bar open and previous bar close.

| Metric | Jan+Feb winners | March losers | March 14-16 losers |
|---|---:|---:|---:|
| avg entry vs current 5m open | -1.082% | -1.589% | -1.071% |
| median entry vs current 5m open | -1.279% | -1.466% | -1.158% |
| share entered above current open | 20.0% | 6.5% | 0.0% |
| avg entry vs previous close | -1.083% | -1.589% | -1.071% |
| median entry vs previous close | -1.279% | -1.466% | -1.159% |
| share entered above previous close | 20.0% | 6.5% | 0.0% |

This is the decisive result.

The regime is **not behaving like continuation-following entries**.

Mechanically, ETH TREND_DOWN entries are overwhelmingly being filled **below the current bar open and below the previous close**. That is a pullback-catching / dip-buying entry style.

Therefore the best current semantic interpretation is:

> ETHUSDT x TREND_DOWN is implemented in practice as dip-buying inside a downtrend, not as continuation-following downside participation.

This does not prove the original design intent. It does prove the runtime trading behavior.

---

## 5. Side Mix

| Cohort | Side mix |
|---|---|
| Jan+Feb winners | 22 LONG, 3 SHORT |
| March losers | 29 LONG, 2 SHORT |
| March 14-16 losers | 8 LONG, 1 SHORT |

Interpretation:

- the regime is not switching from long-biased to short-biased across the failure;
- the failure is mostly a **LONG failure**;
- the difference is not that March suddenly became short-only and the model missed it.

---

## 6. Entry Timing

Top entry hours by cohort:

| Cohort | Most frequent hours UTC |
|---|---|
| Jan+Feb winners | 12, 14, 16, 20 |
| March losers | 4, 6, 11, 15, 16 |
| March 14-16 losers | 6, 11, 15 |

Interpretation:

- the March loss cluster is not random in time;
- 14-16 March losses concentrate in a narrower hour band than Jan+Feb winners;
- timing changed, but not enough by itself to explain the entire failure.

---

## 7. Entry-Bar Shape

### 7.1 Jan+Feb winners

| Metric | Value |
|---|---:|
| avg range | 0.576% |
| median range | 0.263% |
| avg delta vs previous close | +0.070% |
| median delta vs previous close | -0.054% |
| negative delta share | 64.0% |
| down-bar share | 64.0% |
| LONG entered after negative bar | 63.6% |

This is consistent with profitable dip-buying: many winning LONGs were entered after negative 5m bars.

### 7.2 March losers

| Metric | Value |
|---|---:|
| avg range | 0.493% |
| median range | 0.454% |
| avg delta vs previous close | -0.027% |
| median delta vs previous close | +0.023% |
| negative delta share | 48.4% |
| positive delta share | 51.6% |
| LONG entered after negative bar | 51.7% |

The March losing cohort is much less clearly a pure dip-buying success pattern. It is closer to mixed entry conditions and is not being rewarded.

### 7.3 March 14-16 cluster

| Metric | Value |
|---|---:|
| avg range | 0.420% |
| median range | 0.425% |
| avg delta vs previous close | +0.156% |
| median delta vs previous close | +0.208% |
| positive delta share | 77.8% |
| LONG entered after negative bar | 25.0% |

This is the sharpest cluster signal.

During 14-16 March, most losing entries happened in a context where the entry bar itself was **green / positive** versus the previous close, yet the actual fill still happened below the bar open / previous close because the execution style was pullback-based.

Interpretation:

- the system was still buying pullbacks;
- but now it was doing so inside short-term upward bars that were not converting into durable favorable continuation;
- that looks like **phase mismatch after 13 March**, not merely low confidence.

---

## 8. Holding Time

| Cohort | Avg hold | Median hold | <=30m share |
|---|---:|---:|---:|
| Jan+Feb winners | 187.0 min | 115.0 min | 20.0% |
| March losers | 62.7 min | 45.0 min | 48.4% |
| March 14-16 losers | 82.8 min | 60.0 min | 33.3% |

Interpretation:

- winning Jan+Feb dip-buys needed time to work;
- March losses failed much faster;
- this supports the idea that the regime stopped receiving the same post-entry rebound structure in March.

---

## 9. SL Size Buckets For March Losers

| Bucket | Count |
|---|---:|
| 0-25 USDT | 6 |
| 25-50 USDT | 2 |
| 50-75 USDT | 13 |
| 75-100 USDT | 9 |
| 100+ USDT | 1 |

For the 14-16 March cluster specifically:

| Bucket | Count |
|---|---:|
| 50-75 USDT | 2 |
| 75-100 USDT | 7 |

Interpretation:

- the 14-16 March cluster is not death by many tiny scratches;
- it is a dense block of medium-large stopouts;
- that matches the earlier payoff-geometry concern.

---

## 10. 14-16 March Cluster Detail

Worst losses in the cluster:

| Exit time UTC | Side | pnl_net | Hold | Bar range | Delta vs previous close | Bar body |
|---|---|---:|---:|---:|---:|---:|
| 2024-03-14 12:25 | LONG | -96.14 | 60 min | 0.241% | +0.072% | +0.072% |
| 2024-03-15 06:10 | LONG | -92.05 | 5 min | 0.425% | +0.266% | +0.267% |
| 2024-03-14 15:45 | LONG | -91.16 | 45 min | 0.521% | +0.341% | +0.341% |
| 2024-03-14 16:30 | LONG | -86.14 | 30 min | 0.630% | +0.581% | +0.580% |
| 2024-03-15 06:35 | SHORT | -78.34 | 20 min | 0.364% | +0.162% | +0.162% |
| 2024-03-16 15:10 | LONG | -77.32 | 230 min | 0.432% | -0.220% | -0.220% |

Interpretation:

- most major 14-16 March losses are LONGs;
- many occur after modest positive bar deltas, not after panic downside dumps;
- the cluster looks like repeated failed pullback entries in the wrong local phase.

---

## 11. Final Reading For patched7

This research step resolves the semantic question enough to make patched7 design choices cleaner.

### What is now evidenced

1. ETHUSDT x TREND_DOWN behaves in practice like **dip-buying**, not continuation-following.
2. Jan+Feb winners were compatible with that behavior because rebounds had time to develop.
3. March losers, especially 14-16 March, show the same broad entry style no longer being rewarded.
4. The failure is therefore more consistent with:
   - payoff / stop geometry fragility;
   - threshold/phase mismatch after 13 March;
   - possibly excessive permission for ETH TREND_DOWN LONGs.

### What this means for patched7 choice space

The evidence now makes these options logically cleaner:

1. limit or remove **ETH TREND_DOWN LONG** behavior;
2. keep the regime but redesign TP/SL or thresholding specifically for dip-buying in downtrend;
3. block ETH TREND_DOWN entirely if that dip-buying semantics is no longer desired.

### What this research does not prove

- It does not prove the classifier labels are wrong.
- It does not prove a code bug in bracket handling.
- It does not prove continuation-following was ever the implemented behavior.

It does prove the current runtime semantics well enough to stop guessing.
